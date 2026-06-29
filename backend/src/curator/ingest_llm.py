"""LLM compilation pipeline — multi-phase DAG build.

This module provides the core logic for high-level knowledge synthesis:
- Phase A (L2 Atoms) & Phase B (L3 Concepts): Driven by `wiki add`.
- Phase C (L4 Synthesis): Driven by `wiki build`.

The pipeline is sequential to ensure cross-source concepts and exhibitions 
emerge correctly. All IDs are UUID-based (ATM-/CON-/SYN-).
"""

from __future__ import annotations
from . import constants as consts

import json
import re
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


@dataclass
class PageChange:
    id: str          # CTX-/ATM-/CON-/SYN- UUID
    path: str        # relative to .curator/Collections/
    layer: str       # '01_Contexts' | '02_Atoms' | '03_Concepts' | '04_Synthesis'
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
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_str = not in_str
            continue
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
    total_exhibs    = sum(1 for _ in paths.synthesis.glob("*.md"))   if paths.synthesis.exists()  else 0

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
        f"| L4 Synthesis   | {total_exhibs} |",
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
    exhibitions = _read_layer(paths.synthesis   if paths.synthesis.exists()   else None)

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
        f"| L4 Synthesis   | {len(exhibitions)} |",
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

    _layer_section("L1 — Contexts",  consts.LAYER_L1,  contexts)
    _layer_section("L2 — Atoms",     consts.LAYER_L2,  atoms)
    _layer_section("L3 — Concepts",  consts.LAYER_L3,  concepts)
    _layer_section("L4 — Synthesis", consts.LAYER_L4, exhibitions)

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
# Entry points — pipeline split (wiki add = L1, wiki build = L2/L3/L4)
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
    L4 Synthesis status/projections are updated by ``compile_global_l3``.
    """
    today = _now_iso()
    from .pipeline import compile as _compile

    # L3 clustering is global; replace the current Concept set. Invalidate stale
    # L4 synthesis: delete SYN markdown and reset l4_status so compile_global_l3
    # can set the correct terminal status after its own synthesis attempt.
    if paths.concepts.exists():
        for md_path in paths.concepts.glob(f"{consts.PREFIX_L3}-*.md"):
            md_path.unlink()
    if paths.synthesis.exists():
        for md_path in paths.synthesis.glob(f"{consts.PREFIX_L4}-*.md"):
            md_path.unlink()
    source_ids = _source_ids_with_l2_done(paths)
    if source_ids:
        db.set_sources_layer_status(paths.state_db, source_ids, "l4", "pending")

    concept_ids = _compile.compile_global_l3(paths, client)

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


def read_recent_domains(paths: cfg.WikiPaths, limit: int = 8) -> list[str]:
    """Return recent top-level source folders as lightweight persona hints."""
    if not paths.state_db.exists():
        return []
    domains: list[str] = []
    with db.connect(paths.state_db) as conn:
        rows = conn.execute(
            "SELECT relpath FROM sources ORDER BY added_at DESC LIMIT ?",
            (max(1, limit * 3),),
        ).fetchall()
    for row in rows:
        relpath = str(row["relpath"] or "")
        if not relpath:
            continue
        parts = Path(relpath).parts
        domain = parts[1] if len(parts) > 1 and parts[0].startswith("0") else parts[0]
        domain = domain.strip()
        if domain and domain not in domains:
            domains.append(domain)
        if len(domains) >= limit:
            break
    return domains


def find_workspace_exhibition(paths: cfg.WikiPaths, project: str) -> Optional[Path]:
    """Return any existing Exhibition tagged for this workspace project.

    Intentionally ignores curate_spec_hash so stale Exhibitions are still found
    after curate.yml edits (the caller can re-curate to refresh them).
    """
    if not paths.synthesis.exists() or not project:
        return None
    for md_path in sorted(paths.synthesis.glob(f"{consts.PREFIX_L4}-*.md")):
        try:
            parsed = page_writer.read_page(md_path)
            if parsed and parsed.frontmatter.get("workspace") == project:
                if not parsed.frontmatter.get("superseded_by"):
                    return md_path
        except Exception:
            continue
    return None
