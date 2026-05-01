"""LLM ingest pipeline — L2 Atoms → L3 Concepts → L4 Synthesis.

Runs after `wiki sync` (which generates L1 Summaries).

Three-pass flow per source:
    Pass 1 (ATOMS)    — extract irreducible facts into 02_Atoms/ATM-*.md
    Pass 2 (CONCEPTS) — cluster atoms into 03_Concepts/CON-*.md
    Pass 3 (SYNTHESIS)— build terminal outputs in 04_Synthesis/SYN-*.md

All IDs are UUID-based (ATM-/CON-/SYN-). Pages are transactionally staged
before commit. DB source status flips to 'ingested' only after full success.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from pydantic import BaseModel, Field, ValidationError

from . import config as cfg
from . import db
from . import page_writer
from . import parsers
from . import prompts
from .llm import LLMError, OllamaClient


MAX_SOURCE_CHARS = 100_000
EXCERPT_CHARS = 4000


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class AtomCandidate(BaseModel):
    name: str
    type: str = "fact"
    one_liner: str


class SummaryData(BaseModel):
    title: str
    domain: str = ""
    summary: str
    key_claims: list[str] = Field(default_factory=list)
    atom_candidates: list[AtomCandidate] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ConceptPlan(BaseModel):
    name: str
    domain: str = ""
    atom_ids: list[str]
    description: str


class ConceptClusterResult(BaseModel):
    concepts: list[ConceptPlan] = Field(default_factory=list)


class SynthesisPlan(BaseModel):
    topic: str
    concept_ids: list[str]
    confidence: float = 0.7
    requires_math_rigor: bool = False
    rationale: str = ""


class SynthesisPlanResult(BaseModel):
    synthesis_plans: list[SynthesisPlan] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class PageChange:
    id: str          # SUM-/ATM-/CON-/SYN- UUID
    path: str        # relative to .curator/Collections/
    layer: str       # '01_Summaries' | '02_Atoms' | '03_Concepts' | '04_Synthesis'
    operation: str   # 'created' | 'updated'


@dataclass
class IngestResult:
    source_id: int
    source_title: str
    atoms_created: int = 0
    atoms_updated: int = 0
    concepts_created: int = 0
    synthesis_created: int = 0
    changes: list[PageChange] = field(default_factory=list)
    error: str | None = None
    skipped: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None and not self.skipped

    @property
    def pages_created(self) -> int:
        return self.atoms_created + self.concepts_created + self.synthesis_created

    @property
    def pages_updated(self) -> int:
        return self.atoms_updated


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


class IngestCallbacks:
    def on_start(self, source_id: int, source_title: str, summary_id: str) -> None: ...
    def on_pass1_start(self, atom_count: int) -> None: ...
    def on_atom_drafting(self, atom_id: str, name: str, operation: str) -> None: ...
    def on_stream_chunk(self, chunk: str) -> None: ...
    def on_atom_written(self, change: PageChange) -> None: ...
    def on_pass2_start(self, atom_count: int) -> None: ...
    def on_concept_drafting(self, concept_id: str, name: str) -> None: ...
    def on_concept_written(self, change: PageChange) -> None: ...
    def on_pass3_start(self, concept_count: int) -> None: ...
    def on_synthesis_drafting(self, syn_id: str, topic: str) -> None: ...
    def on_synthesis_written(self, change: PageChange) -> None: ...
    def on_finalizing(self) -> None: ...
    def on_complete(self, result: IngestResult) -> None: ...
    def on_error(self, error: str) -> None: ...
    def ask_confirm(self, summary: SummaryData) -> bool:
        return True


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("\n", 1)
        text = parts[1] if len(parts) == 2 else text
        if text.rstrip().endswith("```"):
            text = text.rsplit("```", 1)[0]
    start = text.find("{")
    if start == -1:
        return text
    depth, in_str, escape = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False; continue
        if c == "\\":
            escape = True; continue
        if c == '"':
            in_str = not in_str; continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return text[start:]


def _parse_json_model(raw: str, model_class):
    json_str = _extract_json(raw)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e
    try:
        return model_class(**data)
    except ValidationError as e:
        raise ValueError(f"Schema mismatch: {e}") from e


def _build_excerpt(text: str, max_chars: int = EXCERPT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[... truncated ...]"


def _mark_source_status(paths, source_id, status, last_ingested=None):
    with db.connect(paths.state_db) as conn:
        if last_ingested:
            conn.execute(
                "UPDATE sources SET status = ?, last_ingested = ? WHERE id = ?",
                (status, last_ingested, source_id),
            )
        else:
            conn.execute("UPDATE sources SET status = ? WHERE id = ?", (status, source_id))


def _record_ingest_run(paths, source_id, started, mode, created, updated, error):
    with db.connect(paths.state_db) as conn:
        conn.execute(
            """INSERT INTO ingest_runs
               (started_at, finished_at, source_id, mode, pages_created, pages_updated, error)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (_now_iso(), _now_iso(), source_id, mode, created, updated, error),
        )


def _stream_page(client, messages, callbacks: IngestCallbacks) -> str:
    """Stream a page from LLM, collecting chunks via callbacks. Returns full text."""
    full = ""
    gen = client.chat_stream(messages, thinking=False, temperature=0.3)
    try:
        while True:
            chunk = next(gen)
            callbacks.on_stream_chunk(chunk)
            full += chunk
    except StopIteration as stop:
        if stop.value:
            full = stop.value
    return page_writer.strip_llm_noise(full)


# ---------------------------------------------------------------------------
# Pass 1 — L2 Atoms
# ---------------------------------------------------------------------------


def _find_existing_atom(paths: cfg.WikiPaths, name: str) -> tuple[str, bool]:
    """Check if an Atom page for this concept name already exists.
    Returns (atom_id, exists).
    """
    if not paths.atoms.exists():
        return _gen_id("ATM"), False
    for md in paths.atoms.glob("*.md"):
        parsed = page_writer.read_page(md)
        if parsed and parsed.frontmatter.get("type") == "atom":
            # Match by name in H1
            for line in parsed.body.splitlines():
                if line.startswith("# ") and name.lower() in line.lower():
                    return md.stem, True
    return _gen_id("ATM"), False


def _run_pass1_atoms(
    paths: cfg.WikiPaths,
    client,
    callbacks: IngestCallbacks,
    summary_data: SummaryData,
    summary_id: str,
    relpath: str,
    excerpt: str,
    today: str,
    staging: Path,
) -> list[tuple[Path, Path, PageChange]]:
    """Draft L2 Atom pages for all atom_candidates in summary_data."""
    staged: list[tuple[Path, Path, PageChange]] = []

    callbacks.on_pass1_start(len(summary_data.atom_candidates))

    for candidate in summary_data.atom_candidates:
        atom_id, exists = _find_existing_atom(paths, candidate.name)
        operation = "updated" if exists else "created"
        callbacks.on_atom_drafting(atom_id, candidate.name, operation)

        final_path = paths.atoms / f"{atom_id}.md"
        staged_path = staging / f"02_Atoms__{atom_id}.md"

        if exists:
            existing_content = page_writer.read_page(final_path)
            existing_md = existing_content.to_markdown() if existing_content else ""
            messages = prompts.build_merge_atom_messages(
                existing_content=existing_md,
                name=candidate.name,
                new_summary_id=summary_id,
                new_source_path=relpath,
                new_description=candidate.one_liner,
                excerpt=excerpt,
                today=today,
            )
        else:
            messages = prompts.build_atom_page_messages(
                atom_id=atom_id,
                name=candidate.name,
                atom_type=candidate.type,
                one_liner=candidate.one_liner,
                summary_id=summary_id,
                source_path=relpath,
                excerpt=excerpt,
                today=today,
            )

        content = _stream_page(client, messages, callbacks)
        if not content:
            raise LLMError(f"Empty response for atom '{candidate.name}'")

        staged_path.write_text(content, encoding="utf-8")
        change = PageChange(
            id=atom_id,
            path=f"02_Atoms/{atom_id}.md",
            layer="02_Atoms",
            operation=operation,
        )
        staged.append((staged_path, final_path, change))
        callbacks.on_atom_written(change)

    return staged


# ---------------------------------------------------------------------------
# Pass 2 — L3 Concepts
# ---------------------------------------------------------------------------


def _run_pass2_concepts(
    paths: cfg.WikiPaths,
    client,
    callbacks: IngestCallbacks,
    atom_ids: list[str],
    today: str,
    staging: Path,
) -> list[tuple[Path, Path, PageChange]]:
    """Cluster atoms into L3 Concept pages."""
    staged: list[tuple[Path, Path, PageChange]] = []

    if len(atom_ids) < 2:
        return staged  # Need at least 2 atoms to cluster

    # Build atom summaries for clustering prompt
    atom_summaries = []
    for aid in atom_ids:
        atom_path = paths.atoms / f"{aid}.md"
        parsed = page_writer.read_page(atom_path)
        if parsed:
            one_liner = ""
            for line in parsed.body.splitlines():
                if line.startswith("**Definition"):
                    one_liner = line.replace("**Definition / Claim**:", "").strip()
                    break
            atom_summaries.append({
                "id": aid,
                "name": parsed.frontmatter.get("name", aid),
                "claim_type": parsed.frontmatter.get("claim_type", "fact"),
                "one_liner": one_liner[:100],
            })

    callbacks.on_pass2_start(len(atom_summaries))

    # Get clustering plan
    cluster_messages = prompts.build_concept_clustering_messages(atom_summaries)
    try:
        raw = client.chat(cluster_messages, thinking=False, json_mode=True, temperature=0.2)
        cluster_result: ConceptClusterResult = _parse_json_model(raw, ConceptClusterResult)
    except (ValueError, LLMError):
        return staged  # Non-fatal — skip concept layer for this run

    for plan in cluster_result.concepts:
        if len(plan.atom_ids) < 2:
            continue
        concept_id = _gen_id("CON")
        callbacks.on_concept_drafting(concept_id, plan.name)

        # Build atoms content for the concept page prompt
        atoms_content = ""
        for aid in plan.atom_ids:
            ap = page_writer.read_page(paths.atoms / f"{aid}.md")
            if ap:
                atoms_content += f"\n### [[02_Atoms/{aid}]]\n{ap.body[:600]}\n"

        messages = prompts.build_concept_page_messages(
            concept_id=concept_id,
            name=plan.name,
            domain=plan.domain,
            atom_ids=plan.atom_ids,
            atoms_content=atoms_content,
            today=today,
        )
        content = _stream_page(client, messages, callbacks)
        if not content:
            continue

        final_path = paths.concepts / f"{concept_id}.md"
        staged_path = staging / f"03_Concepts__{concept_id}.md"
        staged_path.write_text(content, encoding="utf-8")
        change = PageChange(
            id=concept_id,
            path=f"03_Concepts/{concept_id}.md",
            layer="03_Concepts",
            operation="created",
        )
        staged.append((staged_path, final_path, change))
        callbacks.on_concept_written(change)

    return staged


# ---------------------------------------------------------------------------
# Pass 3 — L4 Synthesis
# ---------------------------------------------------------------------------


def _run_pass3_synthesis(
    paths: cfg.WikiPaths,
    client,
    callbacks: IngestCallbacks,
    concept_ids: list[str],
    today: str,
    staging: Path,
) -> list[tuple[Path, Path, PageChange]]:
    """Build L4 Synthesis pages from concept clusters."""
    staged: list[tuple[Path, Path, PageChange]] = []

    if not concept_ids:
        return staged

    concept_summaries = []
    for cid in concept_ids:
        cp = page_writer.read_page(paths.concepts / f"{cid}.md")
        if cp:
            concept_summaries.append({
                "id": cid,
                "name": cp.frontmatter.get("name", cid),
                "domain": cp.frontmatter.get("domain", ""),
                "atom_count": len(cp.frontmatter.get("dependencies", [])),
            })

    callbacks.on_pass3_start(len(concept_summaries))

    plan_messages = prompts.build_synthesis_planning_messages(concept_summaries)
    try:
        raw = client.chat(plan_messages, thinking=False, json_mode=True, temperature=0.2)
        plan_result: SynthesisPlanResult = _parse_json_model(raw, SynthesisPlanResult)
    except (ValueError, LLMError):
        return staged

    for plan in plan_result.synthesis_plans:
        if not plan.concept_ids:
            continue
        syn_id = _gen_id("SYN")
        callbacks.on_synthesis_drafting(syn_id, plan.topic)

        concepts_content = ""
        for cid in plan.concept_ids:
            cp = page_writer.read_page(paths.concepts / f"{cid}.md")
            if cp:
                concepts_content += f"\n### [[03_Concepts/{cid}]]\n{cp.body[:800]}\n"

        messages = prompts.build_synthesis_page_messages(
            synthesis_id=syn_id,
            topic=plan.topic,
            concept_ids=plan.concept_ids,
            concepts_content=concepts_content,
            confidence=plan.confidence,
            requires_math=plan.requires_math_rigor,
            today=today,
        )
        content = _stream_page(client, messages, callbacks)
        if not content:
            continue

        final_path = paths.synthesis / f"{syn_id}.md"
        staged_path = staging / f"04_Synthesis__{syn_id}.md"
        staged_path.write_text(content, encoding="utf-8")
        change = PageChange(
            id=syn_id,
            path=f"04_Synthesis/{syn_id}.md",
            layer="04_Synthesis",
            operation="created",
        )
        staged.append((staged_path, final_path, change))
        callbacks.on_synthesis_written(change)

    return staged


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------


def ingest_source(
    paths: cfg.WikiPaths,
    source_id: int,
    client,
    callbacks: IngestCallbacks,
    *,
    mode: str = "interactive",
    thinking_for_extraction: bool = True,
) -> IngestResult:
    """Run the full 3-pass ingest pipeline (L2→L3→L4) on a single source."""
    started = _now_iso()

    # Load source row
    with db.connect(paths.state_db) as conn:
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        if row is None:
            result = IngestResult(source_id=source_id, source_title="?",
                                  error=f"No source with id {source_id}")
            callbacks.on_error(result.error)
            return result
        source_row = dict(row)

    summary_id = source_row.get("summary_id") or ""
    file_path = paths.root / source_row["relpath"]

    # Parse source
    try:
        parsed = parsers.parse(file_path)
    except parsers.ParserError as e:
        result = IngestResult(source_id=source_id, source_title=source_row["relpath"],
                              error=f"Parse failed: {e}")
        _mark_source_status(paths, source_id, "error")
        _record_ingest_run(paths, source_id, started, mode, 0, 0, result.error)
        callbacks.on_error(result.error)
        return result

    callbacks.on_start(source_id, parsed.title, summary_id)

    # Load or regenerate L1 summary data
    summary_data: SummaryData | None = None
    if summary_id:
        sum_path = paths.summaries / f"{summary_id}.md"
        sum_page = page_writer.read_page(sum_path)
        if sum_page:
            # Extract atom_candidates from the summary page body
            candidates = []
            in_candidates = False
            for line in sum_page.body.splitlines():
                if "## Atom Candidates" in line:
                    in_candidates = True
                    continue
                if in_candidates and line.startswith("## "):
                    break
                if in_candidates and line.startswith("- ["):
                    # Format: - [type] Name: one_liner
                    try:
                        type_end = line.index("]")
                        atype = line[3:type_end]
                        rest = line[type_end + 2:]
                        name, one_liner = rest.split(":", 1) if ":" in rest else (rest, "")
                        candidates.append(AtomCandidate(
                            name=name.strip(),
                            type=atype.strip(),
                            one_liner=one_liner.strip(),
                        ))
                    except (ValueError, IndexError):
                        pass
            summary_data = SummaryData(
                title=parsed.title,
                domain=sum_page.frontmatter.get("domain", ""),
                summary="",
                atom_candidates=candidates,
                tags=sum_page.frontmatter.get("tags", []),
            )

    if summary_data is None or not summary_data.atom_candidates:
        # Re-run Pass 0 inline (summary was missing or malformed)
        source_text = parsed.text[:MAX_SOURCE_CHARS]
        messages = prompts.build_summary_messages(parsed.title, source_text)
        try:
            raw = client.chat(messages, thinking=thinking_for_extraction, json_mode=True, temperature=0.2)
            summary_data = _parse_json_model(_extract_json(raw), SummaryData)
        except (ValueError, LLMError) as e:
            result = IngestResult(source_id=source_id, source_title=parsed.title,
                                  error=f"Summary extraction failed: {e}")
            _mark_source_status(paths, source_id, "error")
            _record_ingest_run(paths, source_id, started, mode, 0, 0, result.error)
            callbacks.on_error(result.error)
            return result

    # Interactive confirmation
    if mode == "interactive" and not callbacks.ask_confirm(summary_data):
        result = IngestResult(source_id=source_id, source_title=parsed.title, skipped=True)
        callbacks.on_complete(result)
        return result

    today = _now_iso()
    max_excerpt = getattr(client, "optimal_chunk_chars", 30000)
    excerpt = _build_excerpt(parsed.text, max_chars=max_excerpt)
    staging = Path(tempfile.mkdtemp(prefix="curator-ingest-"))

    try:
        all_staged: list[tuple[Path, Path, PageChange]] = []

        # Pass 1 — L2 Atoms
        try:
            atom_staged = _run_pass1_atoms(
                paths, client, callbacks, summary_data, summary_id,
                source_row["relpath"], excerpt, today, staging,
            )
            all_staged.extend(atom_staged)
        except LLMError as e:
            result = IngestResult(source_id=source_id, source_title=parsed.title,
                                  error=f"Atom pass failed: {e}")
            _mark_source_status(paths, source_id, "error")
            _record_ingest_run(paths, source_id, started, mode, 0, 0, result.error)
            callbacks.on_error(result.error)
            return result

        new_atom_ids = [c.id for _, _, c in atom_staged if c.layer == "02_Atoms"]

        # Pass 2 — L3 Concepts
        concept_staged = _run_pass2_concepts(
            paths, client, callbacks, new_atom_ids, today, staging
        )
        all_staged.extend(concept_staged)
        new_concept_ids = [c.id for _, _, c in concept_staged]

        # Pass 3 — L4 Synthesis
        synthesis_staged = _run_pass3_synthesis(
            paths, client, callbacks, new_concept_ids, today, staging
        )
        all_staged.extend(synthesis_staged)

        # Commit all staged files
        callbacks.on_finalizing()
        changes: list[PageChange] = []
        atoms_created = atoms_updated = concepts_created = synthesis_created = 0

        for staged_path, final_path, change in all_staged:
            final_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged_path, final_path)
            changes.append(change)
            if change.layer == "02_Atoms":
                if change.operation == "created":
                    atoms_created += 1
                else:
                    atoms_updated += 1
            elif change.layer == "03_Concepts":
                concepts_created += 1
            elif change.layer == "04_Synthesis":
                synthesis_created += 1

        # Update index and log
        page_writer.rebuild_index(paths, today)
        log_bullets = [f"{c.operation}: [[{c.path.replace('.md', '')}]]" for c in changes]
        page_writer.append_log_entry(paths, today, "ingest", parsed.title, log_bullets)

        # Update DB
        _mark_source_status(paths, source_id, "ingested", last_ingested=_now_iso())
        _record_ingest_run(paths, source_id, started, mode,
                           atoms_created + concepts_created + synthesis_created,
                           atoms_updated, error=None)

        result = IngestResult(
            source_id=source_id,
            source_title=parsed.title,
            atoms_created=atoms_created,
            atoms_updated=atoms_updated,
            concepts_created=concepts_created,
            synthesis_created=synthesis_created,
            changes=changes,
        )
        callbacks.on_complete(result)
        return result

    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _auto_discover_pending(paths: cfg.WikiPaths) -> tuple[int, int]:
    """Scan raw_dirs for files not yet tracked. 
    Returns (discovered_count, removed_count).
    """
    from . import ingest_raw
    with db.connect(paths.state_db) as conn:
        rows = conn.execute("SELECT id, relpath FROM sources").fetchall()
        tracked = {row["relpath"]: row["id"] for row in rows}

    valid_prefixes = tuple(str(d.relative_to(paths.root)) for d in paths.raw_dirs)

    orphans = []
    for relpath, sid in tracked.items():
        if not (paths.root / relpath).exists() or not relpath.startswith(valid_prefixes):
            orphans.append(sid)

    removed = 0
    if orphans:
        with db.connect(paths.state_db) as conn:
            conn.execute(
                f"DELETE FROM sources WHERE id IN ({','.join('?' * len(orphans))})",
                orphans,
            )
        removed = len(orphans)
        for relpath in [k for k, v in tracked.items() if v in orphans]:
            del tracked[relpath]

    discovered = 0
    for raw_dir in paths.raw_dirs:
        if not raw_dir.exists():
            continue
        for file_path in raw_dir.rglob("*"):
            if not file_path.is_file() or file_path.name.startswith("."):
                continue
            if not parsers.is_supported(file_path):
                continue
            try:
                relpath = str(file_path.relative_to(paths.root))
            except ValueError:
                continue
            if relpath in tracked:
                continue
            outcome = ingest_raw.add_file(paths, file_path)
            if outcome.result == ingest_raw.AddResult.ADDED:
                discovered += 1
    return discovered, removed


def ingest_pending(
    paths: cfg.WikiPaths,
    client,
    callbacks_factory: Callable[[], IngestCallbacks],
    *,
    mode: str = "interactive",
    auto_discover: bool = True,
    thinking_for_extraction: bool = True,
) -> list[IngestResult]:
    """Ingest all pending sources."""
    if auto_discover:
        _auto_discover_pending(paths)

    with db.connect(paths.state_db) as conn:
        rows = conn.execute(
            "SELECT id FROM sources WHERE status = 'pending' ORDER BY id ASC"
        ).fetchall()
        pending_ids = [row["id"] for row in rows]

    results: list[IngestResult] = []
    for sid in pending_ids:
        cb = callbacks_factory()
        result = ingest_source(paths, sid, client, cb, mode=mode,
                               thinking_for_extraction=thinking_for_extraction)
        results.append(result)
        if result.error and "Ollama" in (result.error or ""):
            break

    return results
