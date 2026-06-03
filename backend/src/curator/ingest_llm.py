"""LLM compilation pipeline — multi-phase DAG build.

This module provides the core logic for high-level knowledge synthesis:
- Phase A (L2 Atoms) & Phase B (L3 Concepts): Driven by `wiki add`.
- Phase C (L4 Exhibitions): Driven by `wiki curate`.

The pipeline is sequential to ensure cross-source concepts and exhibitions 
emerge correctly. All IDs are UUID-based (ATM-/CON-/EXH-).
"""

from __future__ import annotations
from . import constants as consts

import json
import re
import shutil
import sys
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
from .llm import LLMError


MAX_SOURCE_CHARS = 100_000
EXCERPT_CHARS = 4000


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class AtomCandidate(BaseModel):
    name: str
    type: str = consts.CLAIM_TYPE_FACT
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
    domain: str = ""
    rationale: str = ""


class SynthesisPlanResult(BaseModel):
    synthesis_plans: list[SynthesisPlan] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class PageChange:
    id: str          # CTX-/ATM-/CON-/EXH- UUID
    path: str        # relative to .curator/Collections/
    layer: str       # '01_Contexts' | '02_Atoms' | '03_Concepts' | '04_Exhibitions'
    operation: str   # 'created' | 'updated'


@dataclass
class IngestResult:
    source_id: int
    source_title: str
    fragments_created: int = 0
    fragments_updated: int = 0
    themes_created: int = 0
    curations_created: int = 0
    changes: list[PageChange] = field(default_factory=list)
    error: str | None = None
    skipped: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None and not self.skipped

    @property
    def pages_created(self) -> int:
        return self.fragments_created + self.themes_created + self.curations_created

    @property
    def pages_updated(self) -> int:
        return self.fragments_updated


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


class IngestCallbacks:
    def on_start(self, source_id: int, source_title: str, context_id: str) -> None: ...
    def on_pass1_start(self, fragment_count: int) -> None: ...
    def on_fragment_drafting(self, fragment_id: str, name: str, operation: str) -> None: ...
    def on_stream_chunk(self, chunk: str) -> None: ...
    def on_fragment_written(self, change: PageChange) -> None: ...
    def on_pass2_start(self, fragment_count: int) -> None: ...
    def on_theme_drafting(self, theme_id: str, name: str) -> None: ...
    def on_theme_written(self, change: PageChange) -> None: ...
    def on_pass3_start(self, theme_count: int) -> None: ...
    def on_curation_drafting(self, cur_id: str, topic: str) -> None: ...
    def on_curation_written(self, change: PageChange) -> None: ...
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
    import re

    def _sanitize_string_content(match):
        s = match.group(0)
        content = s[1:-1]
        new_content = []
        i = 0
        while i < len(content):
            if content[i] == '\\':
                if i + 1 < len(content):
                    nxt = content[i + 1]
                    if nxt in '"\\/bfnrt':
                        new_content.append('\\' + nxt)
                        i += 2
                        continue
                    elif nxt == 'u' and i + 5 < len(content) and all(c in '0123456789abcdefABCDEF' for c in content[i+2:i+6]):
                        new_content.append('\\' + content[i+1:i+6])
                        i += 6
                        continue
                new_content.append('\\\\')
                i += 1
            else:
                new_content.append(content[i])
                i += 1
        return '"' + "".join(new_content) + '"'

    json_str = re.sub(r'"([^"\\]|\\.)*"', _sanitize_string_content, json_str)
    try:
        data = json.loads(json_str, strict=False)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e
    try:
        return model_class(**data)
    except ValidationError as e:
        raise ValueError(f"Schema mismatch: {e}") from e




def _mark_source_status(paths, source_id, status, last_ingested=None, error_reason=None):
    with db.connect(paths.state_db) as conn:
        if last_ingested and error_reason:
            conn.execute(
                "UPDATE sources SET status = ?, last_ingested = ?, error_reason = ? WHERE id = ?",
                (status, last_ingested, error_reason, source_id),
            )
        elif last_ingested:
            conn.execute(
                "UPDATE sources SET status = ?, last_ingested = ? WHERE id = ?",
                (status, last_ingested, source_id),
            )
        elif error_reason:
            conn.execute(
                "UPDATE sources SET status = ?, error_reason = ? WHERE id = ?",
                (status, error_reason, source_id),
            )
        else:
            conn.execute("UPDATE sources SET status = ? WHERE id = ?", (status, source_id))




def invalidate_exh_cache_for_concept(concept_id: str, db_path: str) -> list[str]:
    """Mark unverified Exhibitions that depend on concept_id as cache-invalid."""
    state_db = Path(db_path)
    paths = cfg.WikiPaths(state_db.parent.parent)
    if not paths.exhibitions.exists():
        return []
    invalidated: list[str] = []
    for exh_path in sorted(paths.exhibitions.glob(f"{consts.PREFIX_L4}-*.md")):
        page = page_writer.read_page(exh_path)
        if not page:
            continue
        fm = page.frontmatter
        if bool(fm.get("is_verified_by_human", False)):
            continue
        core = fm.get("core_concepts", [])
        if isinstance(core, str):
            core_values = [core]
        elif isinstance(core, list):
            core_values = [str(v) for v in core]
        else:
            core_values = []
        if not any(str(v).rstrip("/").rsplit("/", 1)[-1] == concept_id for v in core_values):
            continue
        fm["is_cache_invalidated"] = True
        page.frontmatter = fm
        exh_path.write_text(page.to_markdown(), encoding="utf-8")
        invalidated.append(exh_path.stem)
    return invalidated


def _stream_page(client, messages, callbacks: IngestCallbacks) -> str:
    """Stream a page from LLM, collecting chunks via callbacks. Returns full text."""
    full = ""
    gen = client.chat_stream(messages, temperature=0.3)
    try:
        while True:
            chunk = next(gen)
            callbacks.on_stream_chunk(chunk)
            full += chunk
    except StopIteration as stop:
        if stop.value:
            full = stop.value
    text = page_writer.strip_llm_noise(full)
    return page_writer.sanitize_wikilinks(text)


# ---------------------------------------------------------------------------
# Pass 1 — L2 Fragments
# ---------------------------------------------------------------------------






def _strip_embedded_frontmatter(body: str) -> str:
    body = re.sub(
        r"(?is)\s*```(?:ya?ml|markdown|md)?\s*\n---\s*\n.*?\n---\s*\n```\s*",
        "\n\n",
        body,
    )
    return re.sub(r"(?is)^\s*---\s*\n.*?\n---\s*", "", body, count=1).strip()








def _strip_out_of_scope_curator_links(body: str, allowed_targets: set[str]) -> str:
    """Unlink curator DAG targets that are not part of the trusted write plan."""
    curator_prefixes = (f"{consts.LAYER_L1}/", f"{consts.LAYER_L2}/", f"{consts.LAYER_L3}/", f"{consts.LAYER_L4}/")

    def repl(match: re.Match[str]) -> str:
        inner = match.group(1)
        target, _, alias = inner.partition("|")
        target = target.strip().removesuffix(".md")
        if not target.startswith(curator_prefixes):
            return match.group(0)
        if target in allowed_targets:
            return f"[[{inner}]]"
        return alias.strip() or target.rsplit("/", 1)[-1]

    return re.sub(r"\[\[([^\]]+)\]\]", repl, body)


def _is_llm_refusal(content: str) -> bool:
    lowered = content.lower()
    refusal_markers = (
        "i am unable to write",
        "i can't write",
        "i cannot write",
        "i do not have the",
        "write_file",
        "run_shell_command",
    )
    return any(marker in lowered for marker in refusal_markers)










































def _concept_atom_ids(page: page_writer.ParsedPage | None) -> list[str]:
    """Concept dependencies are stored as `## Relations` Atom wikilinks."""
    if not page:
        return []
    ids: list[str] = []
    for target in page_writer.extract_relation_targets(page.body, prefix=f"{consts.LAYER_L2}/"):
        atom_id = target.rsplit("/", 1)[-1]
        if atom_id.startswith(f"{consts.PREFIX_L2}-") and atom_id not in ids:
            ids.append(atom_id)
    return ids


def _enforce_exhibition_contract(
    content: str,
    *,
    exh_id: str,
    plan: SynthesisPlan,
    today: str,
    workspace: str | None = None,
) -> str:
    content = page_writer.strip_llm_noise(content)
    if _is_llm_refusal(content):
        raise LLMError(f"Refusal/tool-use response while drafting exhibition {exh_id}")
    parsed = page_writer.parse_page(page_writer.sanitize_wikilinks(content))
    fm = parsed.frontmatter or {}
    try:
        confidence = float(fm.get("confidence_score", plan.confidence))
    except (TypeError, ValueError):
        confidence = plan.confidence
    confidence = min(1.0, max(0.0, confidence))
    concept_ids = [cid for cid in plan.concept_ids if isinstance(cid, str) and cid.startswith(f"{consts.PREFIX_L3}-")]
    fm: dict = {
        "id": exh_id,
        "type": consts.TYPE_L4,
        "core_concepts": [f"{consts.LAYER_L3}/{cid}" for cid in concept_ids],
        "confidence_score": confidence,
        "last_updated": today,
    }
    if plan.domain:
        fm["domain"] = plan.domain
    if workspace:
        fm["workspace"] = workspace
    parsed.frontmatter = fm
    body = _strip_embedded_frontmatter(parsed.body or "")
    allowed_targets = {f"{consts.LAYER_L3}/{cid}" for cid in concept_ids}
    body = _strip_out_of_scope_curator_links(body, allowed_targets)
    body = re.sub(r"(?im)^##\s+", r"### ", body)
    required = [
        "- **1. Executive Brief**:",
        "- **2. Background & Evidence**:",
        "- **3. Actionable Directives for Agent**:",
        "- **4. Key Facts**:",
        "- **5. Open Questions**:",
    ]
    for label in required:
        if label not in body:
            body = f"{body.rstrip()}\n\n{label} "
    parsed.body = body.strip()
    return parsed.to_markdown()
















# ---------------------------------------------------------------------------
# Pass 2 — L3 Themes
# ---------------------------------------------------------------------------












def _source_ids_with_l2_done(paths: cfg.WikiPaths) -> list[int]:
    with db.connect(paths.state_db) as conn:
        rows = conn.execute(
            "SELECT id FROM sources WHERE l2_status = 'done' ORDER BY id ASC"
        ).fetchall()
    return [int(row["id"]) for row in rows]




def _source_ids_with_l2_done_and_l3_unset(paths: cfg.WikiPaths) -> list[int]:
    with db.connect(paths.state_db) as conn:
        rows = conn.execute(
            "SELECT id FROM sources "
            "WHERE l2_status = 'done' AND l3_status IN ('pending', 'skipped') "
            "ORDER BY id ASC"
        ).fetchall()
    return [int(row["id"]) for row in rows]


def _mark_existing_l3_done_if_present(paths: cfg.WikiPaths) -> None:
    if paths.concepts.exists() and any(paths.concepts.glob(f"{consts.PREFIX_L3}-*.md")):
        source_ids = _source_ids_with_l2_done_and_l3_unset(paths)
        if source_ids:
            db.set_sources_layer_status(paths.state_db, source_ids, "l3", "done")


# ---------------------------------------------------------------------------
# Pass 3 — L4 Curations
# ---------------------------------------------------------------------------


def _write_one_exhibition_plan(
    plan: SynthesisPlan,
    client,
    paths: cfg.WikiPaths,
    staging: Path,
    today: str,
    agent_context: str,
    exhibition_intent: str,
    workspace_project: str | None,
) -> tuple[Path, Path, PageChange] | None:
    """Write one L4 Exhibition page using non-streaming chat. Thread-safe."""
    if not plan.concept_ids:
        return None

    exh_id = _gen_id(consts.PREFIX_L4)
    concepts_content = ""
    flagged_ids: list[str] = []
    for cid in plan.concept_ids:
        cp = page_writer.read_page(paths.concepts / f"{cid}.md")
        if cp:
            concepts_content += f"\n### Concept {cid}\n{cp.body[:4000]}\n"
            for atm_id in _concept_atom_ids(cp):
                atm_path = paths.atoms / f"{atm_id}.md"
                atm_page = page_writer.read_page(atm_path)
                if atm_page and atm_page.frontmatter.get("is_flagged_for_agent") is True:
                    if atm_id not in flagged_ids:
                        flagged_ids.append(atm_id)

    messages = prompts.build_curation_page_messages(
        curation_id=exh_id,
        topic=plan.topic,
        theme_ids=plan.concept_ids,
        themes_content=concepts_content,
        confidence=plan.confidence,
        today=today,
        domain=plan.domain,
        flagged_fragment_ids=flagged_ids,
        agent_context=agent_context,
        exhibition_intent=exhibition_intent,
    )
    try:
        content = client.chat(messages, temperature=0.3)
    except LLMError:
        return None

    content = page_writer.strip_llm_noise(content)
    content = page_writer.sanitize_wikilinks(content)
    if not content:
        return None

    try:
        content = _enforce_exhibition_contract(
            content, exh_id=exh_id, plan=plan, today=today, workspace=workspace_project
        )
    except LLMError:
        return None

    final_path = paths.exhibitions / f"{exh_id}.md"
    staged_path = staging / f"{consts.LAYER_L4}__{exh_id}.md"
    staged_path.write_text(content, encoding="utf-8")
    change = PageChange(
        id=exh_id,
        path=f"{consts.LAYER_L4}/{exh_id}.md",
        layer=consts.LAYER_L4,
        operation="created",
    )
    return staged_path, final_path, change


def _run_pass3_synthesis(
    paths: cfg.WikiPaths,
    client,
    callbacks: IngestCallbacks,
    concept_ids: list[str],
    today: str,
    staging: Path,
    workspace_project: str | None = None,
    artist_persona=None,
) -> list[tuple[Path, Path, PageChange]]:
    """Build L4 Exhibition pages from concept clusters."""
    staged: list[tuple[Path, Path, PageChange]] = []

    if not concept_ids:
        return staged

    concept_summaries = []
    for cid in concept_ids:
        cp = page_writer.read_page(paths.concepts / f"{cid}.md")
        if cp:
            # Prefer frontmatter name, then H1 heading, then ID
            name = cp.frontmatter.get("name", "")
            if not name:
                for line in cp.body.splitlines():
                    if line.startswith("# "):
                        name = line[2:].strip()
                        break
            if not name:
                name = cid
            concept_summaries.append({
                "id": cid,
                "name": name,
                "domain": cp.frontmatter.get("domain", ""),
                "atom_count": len(_concept_atom_ids(cp)),
            })

    callbacks.on_pass3_start(len(concept_summaries))

    # Pull thresholds from Artist persona if present
    high_threshold = 0.90
    low_threshold = 0.60
    if artist_persona and isinstance(artist_persona.confidence, dict):
        high_threshold = float(artist_persona.confidence.get("high_threshold", 0.90))
        low_threshold = float(artist_persona.confidence.get("low_threshold", 0.60))

    plan_messages = prompts.build_curation_planning_messages(
        concept_summaries,
        high_threshold=high_threshold,
        low_threshold=low_threshold,
    )
    try:
        raw = client.chat(plan_messages, json_mode=True, temperature=0.2)
        plan_result: SynthesisPlanResult = _parse_json_model(raw, SynthesisPlanResult)
    except (ValueError, LLMError) as e:
        print(f"Warning: Synthesis planning failed: {e}", file=sys.stderr)
        return staged

    plans: list[SynthesisPlan] = list(plan_result.synthesis_plans)

    # Workspace-scoped curation: merge all plans into one Exhibition.
    # One Exhibition per workspace is the spec invariant.
    if workspace_project and len(plans) > 1:
        all_concept_ids = list(dict.fromkeys(
            cid for p in plans for cid in p.concept_ids
        ))
        plans = [SynthesisPlan(
            topic=workspace_project,
            concept_ids=all_concept_ids,
            confidence=max(p.confidence for p in plans),
        )]

    # Build agent_context string for exhibition page prompts
    agent_context = ""
    if artist_persona and artist_persona.goal:
        agent_context = f"exhibition_intent:{artist_persona.exhibition_intent} — {artist_persona.goal}"

    exhibition_intent = artist_persona.exhibition_intent if artist_persona else ""
    eligible_plans = [p for p in plans if p.concept_ids]
    _clone = getattr(client, "clone", None)
    max_workers = min(2, len(eligible_plans)) if eligible_plans else 1

    from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed as _ac
    with _TPE(max_workers=max_workers) as executor:
        future_to_plan = {
            executor.submit(
                _write_one_exhibition_plan,
                plan,
                _clone() if callable(_clone) else client,
                paths, staging, today,
                agent_context, exhibition_intent, workspace_project,
            ): plan
            for plan in eligible_plans
        }
        for future in _ac(future_to_plan):
            result = future.result()
            if result is None:
                continue
            staged_path, final_path, change = result
            staged.append((staged_path, final_path, change))
            callbacks.on_curation_written(change)

    return staged


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------




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
            ph = ','.join('?' * len(orphans))
            conn.execute(f"DELETE FROM job_events WHERE job_id IN (SELECT id FROM ingest_jobs WHERE source_id IN ({ph}))", orphans)
            conn.execute(f"DELETE FROM ingest_jobs WHERE source_id IN ({ph})", orphans)
            conn.execute(f"DELETE FROM ingest_runs WHERE source_id IN ({ph})", orphans)
            conn.execute(f"DELETE FROM source_pages WHERE source_id IN ({ph})", orphans)
            conn.execute(f"DELETE FROM dag_edges WHERE source_id IN ({ph})", orphans)
            conn.execute(f"DELETE FROM source_pdf_pages WHERE source_id IN ({ph})", orphans)
            conn.execute(f"DELETE FROM sources WHERE id IN ({ph})", orphans)
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



# ---------------------------------------------------------------------------
# Phase B — Global L3 Themes (all Fragments → Themes)
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Phase C — Global L4 Curations (all Themes → Curations)
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Phase D helpers — ledger + overview
# ---------------------------------------------------------------------------


def _update_ledger(paths: cfg.WikiPaths) -> None:
    """Rebuild ledger.md with current collection stats."""
    total_contexts  = sum(1 for _ in paths.contexts.glob("*.md"))   if paths.contexts.exists()   else 0
    total_atoms     = sum(1 for _ in paths.atoms.glob("*.md"))       if paths.atoms.exists()      else 0
    total_concepts  = sum(1 for _ in paths.concepts.glob("*.md"))    if paths.concepts.exists()   else 0
    total_exhibs    = sum(1 for _ in paths.exhibitions.glob("*.md")) if paths.exhibitions.exists() else 0

    with db.connect(paths.state_db) as conn:
        row = conn.execute(
            "SELECT COUNT(*) as n, MAX(last_ingested) as last FROM sources WHERE status='curated'"
        ).fetchone()
        curated_sources = row["n"] if row else 0
        last_ingested = row["last"] if row else ""

    lines = [
        "---",
        "title: Ledger",
        "type: ledger",
        f"updated: {_now_iso()}",
        "---",
        "",
        "# .curator/ledger.md \u2014 Knowledge Ledger",
        "",
        "> Auto-maintained by the Curator engine. Updated after every curate. DO NOT edit manually.",
        "",
        "## Collection Stats",
        "",
        "| Layer | Count |",
        "| --- | --- |",
        f"| Sources curated | {curated_sources} |",
        f"| L1 Contexts    | {total_contexts} |",
        f"| L2 Atoms       | {total_atoms} |",
        f"| L3 Concepts    | {total_concepts} |",
        f"| L4 Exhibitions | {total_exhibs} |",
        "",
        f"*Last curated: {last_ingested or 'never'}*",
        "",
    ]
    paths.ledger.parent.mkdir(parents=True, exist_ok=True)
    paths.ledger.write_text("\n".join(lines), encoding="utf-8")


def _update_overview(paths: cfg.WikiPaths) -> None:
    """Refresh overview.md — summarise every layer in Collections/."""

    def _read_layer(directory: "Path | None") -> list[tuple[str, str, str]]:
        """Return (slug, title, summary) for each .md in directory."""
        if directory is None or not directory.exists():
            return []
        results = []
        for md in sorted(directory.glob("*.md")):
            if md.name.startswith("."):
                continue
            parsed = page_writer.read_page(md)
            title = md.stem
            summary = ""
            if parsed:
                fm = parsed.frontmatter
                title = fm.get("title", title)
                summary = fm.get("summary", "")
                if not summary:
                    # fall back to first non-empty body line
                    for line in (parsed.body or "").splitlines():
                        line = line.strip().lstrip("#").strip()
                        if line and not line.startswith(">"):
                            summary = line[:120]
                            break
            results.append((md.stem, str(title), str(summary)))
        return results

    contexts    = _read_layer(paths.contexts    if paths.contexts.exists()    else None)
    atoms       = _read_layer(paths.atoms       if paths.atoms.exists()       else None)
    concepts    = _read_layer(paths.concepts    if paths.concepts.exists()    else None)
    exhibitions = _read_layer(paths.exhibitions if paths.exhibitions.exists() else None)

    # Domain distribution from L1
    domains: dict[str, int] = {}
    for md in sorted((paths.contexts.glob("*.md") if paths.contexts.exists() else [])):
        if md.name.startswith("."):
            continue
        parsed = page_writer.read_page(md)
        if parsed:
            d = parsed.frontmatter.get("domain", "").strip()
            if d:
                domains[d] = domains.get(d, 0) + 1

    lines = [
        "---",
        "title: Domain Manifest",
        "type: overview",
        f"updated: {_now_iso()}",
        "---",
        "",
        "# .curator/overview.md \u2014 Collections Summary",
        "",
        "> Auto-maintained by the Curator engine. Updated after every curate. DO NOT edit manually.",
        "",
        "## Stats",
        "",
        "| Layer | Count |",
        "| --- | --- |",
        f"| L1 Contexts    | {len(contexts)} |",
        f"| L2 Atoms       | {len(atoms)} |",
        f"| L3 Concepts    | {len(concepts)} |",
        f"| L4 Exhibitions | {len(exhibitions)} |",
        "",
    ]

    if domains:
        lines += ["## Knowledge Domains", ""]
        for domain, count in sorted(domains.items(), key=lambda x: -x[1]):
            lines.append(f"- **{domain}** \u2014 {count} source(s)")
        lines.append("")

    def _layer_section(heading: str, layer_dir: str, entries: list[tuple[str, str, str]]) -> None:
        lines.append(f"## {heading}")
        lines.append("")
        if not entries:
            lines.append("*No pages yet.*")
            lines.append("")
            return
        for slug, title, summary in entries:
            link = f"[[{layer_dir}/{slug}|{title}]]"
            if summary:
                lines.append(f"- {link} — {summary}")
            else:
                lines.append(f"- {link}")
        lines.append("")

    _layer_section("L1 — Contexts",    consts.LAYER_L1,    contexts)
    _layer_section("L2 — Atoms",       consts.LAYER_L2,       atoms)
    _layer_section("L3 — Concepts",    consts.LAYER_L3,    concepts)
    _layer_section("L4 — Exhibitions", consts.LAYER_L4, exhibitions)

    paths.overview.parent.mkdir(parents=True, exist_ok=True)
    paths.overview.write_text("\n".join(lines), encoding="utf-8")

# ---------------------------------------------------------------------------
# Persona evolution helpers (D4)
# ---------------------------------------------------------------------------

def _collect_domains_from_contexts(paths: cfg.WikiPaths, ctx_ids: list[str]) -> list[str]:
    """Return unique non-empty domain strings from the given CTX frontmatters."""
    domains = []
    for ctx_id in ctx_ids:
        ctx_path = paths.contexts / f"{ctx_id}.md"
        if not ctx_path.exists():
            continue
        page = page_writer.read_page(ctx_path)
        if page:
            domain = page.frontmatter.get("domain", "")
            if domain and domain not in domains:
                domains.append(domain)
    return domains






# ---------------------------------------------------------------------------
# Entry points — pipeline split (wiki add = L1-L3, wiki curate = L4)
# ---------------------------------------------------------------------------


def run_l1_to_l3(
    paths: cfg.WikiPaths,
    client,
    callbacks_factory: Callable[[], IngestCallbacks],
    *,
    mode: str = "interactive",
    auto_discover: bool = True,
    force: bool = False,
) -> list[IngestResult]:
    """Run L1→L3 pipeline (Atoms + Concepts) for all pending sources.

    Does NOT generate L4 Exhibitions. Call run_l4_scoped() separately.

    Phase A: each pending source → L2 Atoms (sequential, per-source)
    Phase B: ALL Atom files     → L3 Concepts (global clustering)
    Phase D: rebuild index, ledger, overview
    """
    if auto_discover:
        _auto_discover_pending(paths)

    if force:
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "UPDATE sources SET status = 'force_pending', error_reason = NULL, "
                "l2_status = 'pending', l3_status = 'pending', l4_status = 'pending', layer_error = NULL "
                "WHERE status IN ('curated', 'error')"
            )

    with db.connect(paths.state_db) as conn:
        rows = conn.execute(
            "SELECT id FROM sources WHERE status IN ('pending', 'force_pending', 'error') ORDER BY id ASC"
        ).fetchall()
        pending_ids = [row["id"] for row in rows]

    from .pipeline import compile as _compile

    results: list[IngestResult] = []
    for sid in pending_ids:
        cr = _compile.compile_source_l2(paths, client, sid)
        changes = [
            PageChange(
                id=atom_id,
                path=f"{consts.LAYER_L2}/{atom_id}.md",
                layer=consts.LAYER_L2,
                operation="created",
            )
            for atom_id in cr.atom_ids
        ]
        results.append(
            IngestResult(
                source_id=sid,
                source_title=str(sid),
                fragments_created=len(cr.atom_ids),
                changes=changes,
                error=cr.error,
            )
        )
        if cr.ok:
            _mark_source_status(paths, sid, "curated", last_ingested=_now_iso())
        if cr.error and "Ollama" in (cr.error or ""):
            break

    # Global L3: detect communities → reports → CON projection pages.
    today = _now_iso()
    concept_ids = _compile.compile_global_l3(paths, client)
    page_writer.rebuild_index(paths, today)
    if concept_ids:
        log_bullets = [
            f"created: [[{consts.LAYER_L3}/{cid}]]" for cid in concept_ids
        ]
        page_writer.append_log_entry(paths, today, "add", "L1-L3 pipeline", log_bullets)
    _update_ledger(paths)
    _update_overview(paths)
    return results


def run_l3_from_existing_atoms(
    paths: cfg.WikiPaths,
    client,
    callbacks_factory: Callable[[], IngestCallbacks],
) -> list[PageChange]:
    """Regenerate L3 Concepts from existing L2 Atoms without touching L1/L2.

    L3 clustering is global, so this replaces the current Concept set. Existing
    L4 Exhibitions are invalidated because their Concept inputs may disappear.
    """
    today = _now_iso()
    from .pipeline import compile as _compile

    # L3 clustering is global; replace the current Concept set. Existing L4
    # Exhibitions are invalidated because their Concept inputs may disappear.
    if paths.concepts.exists():
        for md_path in paths.concepts.glob(f"{consts.PREFIX_L3}-*.md"):
            md_path.unlink()
    if paths.exhibitions.exists():
        for md_path in paths.exhibitions.glob(f"{consts.PREFIX_L4}-*.md"):
            md_path.unlink()

    concept_ids = _compile.compile_global_l3(paths, client)
    source_ids = _source_ids_with_l2_done(paths)
    if source_ids:
        db.set_sources_layer_status(paths.state_db, source_ids, "l4", "pending")

    changes = [
        PageChange(
            id=cid,
            path=f"{consts.LAYER_L3}/{cid}.md",
            layer=consts.LAYER_L3,
            operation="created",
        )
        for cid in concept_ids
    ]
    page_writer.rebuild_index(paths, today)
    if changes:
        log_bullets = [f"created: [[{consts.LAYER_L3}/{cid}]]" for cid in concept_ids]
        page_writer.append_log_entry(paths, today, "add", "L3-only regeneration", log_bullets)
    _update_ledger(paths)
    _update_overview(paths)
    return changes


def _get_scoped_concept_ids(
    paths: cfg.WikiPaths,
    curate_spec,
) -> list[str]:
    """Return Concept IDs whose Atoms trace back to sources matching curate_spec.

    Traces: CON → ATM.parent_source → fnmatch against curate_spec.sources.include/exclude.
    If curate_spec has no include patterns, all concepts are returned.
    """
    if not paths.concepts.exists():
        return []

    all_concept_ids = [
        md.stem for md in sorted(paths.concepts.glob("*.md"))
        if not md.name.startswith(".")
    ]

    if not curate_spec.sources.include:
        return all_concept_ids

    def _context_source_path(context_link: str) -> str:
        target = str(context_link or "").strip()
        if target.startswith("[[") and target.endswith("]]"):
            target = target[2:-2].strip()
        if "|" in target:
            target = target.split("|", 1)[0].strip()
        context_id = target.rsplit("/", 1)[-1].removesuffix(".md")
        if not context_id.startswith(f"{consts.PREFIX_L1}-"):
            return ""
        ctx_page = page_writer.read_page(paths.contexts / f"{context_id}.md")
        if not ctx_page:
            return ""
        source_path = str(ctx_page.frontmatter.get("source_path", "") or "")
        if source_path.startswith("[[") and source_path.endswith("]]"):
            source_path = source_path[2:-2].strip()
        if "|" in source_path:
            source_path = source_path.split("|", 1)[0].strip()
        return source_path

    scoped = []
    for cid in all_concept_ids:
        cp = page_writer.read_page(paths.concepts / f"{cid}.md")
        if not cp:
            continue
        for atm_id in _concept_atom_ids(cp):
            atm_page = page_writer.read_page(paths.atoms / f"{atm_id}.md")
            if not atm_page:
                continue
            parent_source = atm_page.frontmatter.get("parent_source", "")
            source_path = _context_source_path(str(parent_source or ""))
            if source_path and curate_spec.matches_sources(source_path):
                scoped.append(cid)
                break
    return scoped


def _count_followup_sections(body: str) -> int:
    """Count ## Follow-up: sections in an Exhibition body."""
    import re
    return len(re.findall(r"^## Follow-up:", body, re.MULTILINE))


def _extract_followup_questions(body: str) -> list[str]:
    """Extract the question text from ## Follow-up: sections."""
    import re
    return re.findall(r"^## Follow-up:\s*(.+)$", body, re.MULTILINE)


def _run_exhibition_refinement(
    paths: cfg.WikiPaths,
    client,
    callbacks: IngestCallbacks,
    exh_path: Path,
    curate_spec,
    today: str,
    staging: Path,
) -> list[tuple[Path, Path, PageChange]]:
    """Refine an existing Exhibition in-place by integrating accumulated Follow-up queries.

    Called when the workspace Exhibition already has 3+ Follow-up sections.
    """
    existing = page_writer.read_page(exh_path)
    if existing is None:
        return []

    followup_questions = _extract_followup_questions(existing.body or "")
    existing_content = existing.to_markdown()

    # Gather supporting concept content from core_concepts in frontmatter
    concepts_content = ""
    for ref in existing.frontmatter.get("core_concepts") or []:
        cid = str(ref).rsplit("/", 1)[-1]
        if not cid.startswith(f"{consts.PREFIX_L3}-"):
            continue
        cp = page_writer.read_page(paths.concepts / f"{cid}.md")
        if cp:
            concepts_content += f"\n### Concept {cid}\n{cp.body[:3000]}\n"

    messages = prompts.build_exhibition_refinement_messages(
        exh_id=exh_path.stem,
        today=today,
        existing_content=existing_content,
        followup_questions=followup_questions,
        concepts_content=concepts_content,
    )
    content = _stream_page(client, messages, callbacks)
    if not content:
        return []

    # Enforce the exhibition contract (keeps existing ID + frontmatter intact)
    plan = SynthesisPlan(
        topic=existing.frontmatter.get("workspace", exh_path.stem),
        concept_ids=[
            str(ref).rsplit("/", 1)[-1]
            for ref in (existing.frontmatter.get("core_concepts") or [])
        ],
        confidence=float(existing.frontmatter.get("confidence_score", 0.7)),
        domain=existing.frontmatter.get("domain", ""),
    )
    content = _enforce_exhibition_contract(
        content,
        exh_id=exh_path.stem,
        plan=plan,
        today=today,
    )

    staged_path = staging / f"{consts.LAYER_L4}__{exh_path.stem}.md"
    staged_path.write_text(content, encoding="utf-8")
    change = PageChange(
        id=exh_path.stem,
        path=f"{consts.LAYER_L4}/{exh_path.name}",
        layer=consts.LAYER_L4,
        operation="updated",
    )
    callbacks.on_curation_written(change)
    return [(staged_path, exh_path, change)]


def run_l4_scoped(
    paths: cfg.WikiPaths,
    client,
    callbacks: IngestCallbacks,
    curate_spec,
    today: str,
    staging: Path,
) -> list[tuple[Path, Path, PageChange]]:
    """Run L4 Exhibition synthesis, optionally scoped by curate_spec source filters.

    curate_spec may be None for unscoped global synthesis.
    When a workspace Exhibition already exists with 3+ accumulated Follow-up queries,
    runs refinement mode (integrate queries, rewrite directives) instead of regenerating.
    """
    workspace_project = curate_spec.project if curate_spec is not None else None
    artist_persona = curate_spec.persona if curate_spec is not None else None

    # Refinement mode: re-run over an Exhibition that has accumulated queries
    if workspace_project:
        existing_exh = find_workspace_exhibition(paths, workspace_project)
        if existing_exh is not None:
            existing = page_writer.read_page(existing_exh)
            if existing is not None and _count_followup_sections(existing.body or "") >= 3:
                return _run_exhibition_refinement(
                    paths, client, callbacks, existing_exh, curate_spec, today, staging,
                )

    if curate_spec is not None and curate_spec.sources.include:
        concept_ids = _get_scoped_concept_ids(paths, curate_spec)
    else:
        if not paths.concepts.exists():
            return []
        concept_ids = [
            md.stem for md in sorted(paths.concepts.glob("*.md"))
            if not md.name.startswith(".")
        ]
    if not concept_ids:
        return []
    return _run_pass3_synthesis(
        paths, client, callbacks, concept_ids, today, staging,
        workspace_project=workspace_project,
        artist_persona=artist_persona,
    )


def add_atom_from_insight(
    paths: cfg.WikiPaths,
    client,
    insight_text: str,
    today: str,
    source_hint: str = "conversational",
) -> Optional[str]:
    """Create a new L2 Atom from a conversational insight or query answer.

    Returns the new atom_id, or None on failure.
    """
    messages = prompts.build_summary_messages("Conversational Insight", insight_text[:4000])
    try:
        raw = client.chat(messages, json_mode=True, temperature=0.2)
        summary_data = _parse_json_model(_extract_json(raw), SummaryData)
    except (ValueError, LLMError):
        return None

    if not summary_data.atom_candidates:
        return None

    candidate = summary_data.atom_candidates[0]
    atom_id = _gen_id(consts.PREFIX_L2)

    messages = prompts.build_fragment_page_messages(
        fragment_id=atom_id,
        name=candidate.name,
        fragment_type=candidate.type,
        one_liner=candidate.one_liner,
        context_id="",
        source_path=source_hint,
        excerpt=insight_text[:2000],
        today=today,
    )

    tmp_staging = Path(tempfile.mkdtemp(prefix="curator-insight-"))
    try:
        full = ""
        gen = client.chat_stream(messages, temperature=0.3)
        try:
            while True:
                chunk = next(gen)
                full += chunk
        except StopIteration as stop:
            if stop.value:
                full = stop.value

        content = page_writer.strip_llm_noise(full)
        content = page_writer.sanitize_wikilinks(content)
        if not content:
            return None

        final_path = paths.atoms / f"{atom_id}.md"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_text(content, encoding="utf-8")
        return atom_id
    except Exception:
        return None
    finally:
        shutil.rmtree(tmp_staging, ignore_errors=True)


def find_workspace_exhibition(paths: cfg.WikiPaths, project: str) -> Optional[Path]:
    """Return any existing Exhibition tagged for this workspace project.

    Intentionally ignores curate_spec_hash so stale Exhibitions are still found
    after curate.yml edits (the caller can re-curate to refresh them).
    """
    if not paths.exhibitions.exists() or not project:
        return None
    for md_path in sorted(paths.exhibitions.glob(f"{consts.PREFIX_L4}-*.md")):
        try:
            parsed = page_writer.read_page(md_path)
            if parsed and parsed.frontmatter.get("workspace") == project:
                if not parsed.frontmatter.get("superseded_by"):
                    return md_path
        except Exception:
            continue
    return None
