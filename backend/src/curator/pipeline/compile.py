"""End-to-end L2/L3 compile orchestration (the v0.3.1 `wiki build` core).

Drives the curation-native compile for sources whose L1 (source_spans) exists:

    per source : spans -> knowledge_units -> graph entities/relations
                 -> emit ATM projection pages, set l2_status
    global     : detect communities -> community reports
                 -> emit CON projection pages, set l3_status

The DB is the source of truth; ATM/CON markdown pages are derived projections
emitted for qmd indexing (SYSTEM_BEHAVIOR.md §22). Source spans are
re-derived from the source here (the DB stores only previews) so units cite the
exact stored span ids.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import config as cfg
from .. import constants as consts
from .. import db, parsers
from ..retrieval import materializer
from . import (
    community_reports,
    graph_index,
    knowledge_units,
    projection,
    source_spans,
    synthesis,
)
from .claim_support import (
    AuditReport,
    reconcile_source,
    run_compiler_audit,
    validate_claim_support,
)
from .formula_recovery import (
    classify_formula_loss,
    invalidate_formula_recoveries,
    recover_formula,
)

__all__ = [
    "CompileResult", "compile_source_l2", "compile_global_l3", "reemit_projections",
    # Plan B (v0.8.0) claim-support validation surface (SYSTEM_BEHAVIOR §26).
    "AuditReport", "validate_claim_support", "run_compiler_audit", "reconcile_source",
    "classify_formula_loss", "invalidate_formula_recoveries", "recover_formula",
    # Plan B (v0.8.0) full-span evidence hydration (SEARCH_ENGINE_SCHEMA §10.2 / F10).
    "SpanTextUnavailable", "hydrate_span_text", "hydrate_spans",
    # Plan B (v0.8.0) staged compiler generations + atomic publish (§26.3).
    "PROMPT_CONTRACT_VERSION", "recompile_source",
]

# The L2 knowledge-unit extraction prompt contract version (Plan B P4). Two
# compiles of the same source under the same contract version are an unchanged
# rebuild and must reuse the authoritative generation (§26.3).
PROMPT_CONTRACT_VERSION = "curator.knowledge_unit_extract@v2"


@dataclass
class CompileResult:
    source_id: int
    atom_ids: list[str] = field(default_factory=list)
    concept_ids: list[str] = field(default_factory=list)
    knowledge_unit_ids: list[str] = field(default_factory=list)
    entity_ids: list[str] = field(default_factory=list)
    prompt_trace_ids: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _section_dicts(paths: cfg.WikiPaths, relpath: str):
    """Re-parse a source into structural sections (full text)."""
    from ..ingest_raw import _extract_structural_sections, _resolve_reference_source

    file_path = paths.root / relpath
    parsed = parsers.parse(_resolve_reference_source(paths, file_path))
    return parsed.title, _extract_structural_sections(parsed)


# ---------------------------------------------------------------------------
# Full-span evidence hydration (F10 / SEARCH_ENGINE_SCHEMA §10.2).
#
# The DB stores only a 200-char `text_preview`; the full span text is hydrated
# on demand from the registered source file. Hydration re-parses the source with
# the SAME deterministic parser + `spans_from_sections` that produced the stored
# spans, so every re-derived `content_hash` matches a stored span's hash — which
# IS the verification key. The preview is never silently substituted: an
# unreadable source or a content-hash drift raises `SpanTextUnavailable`, and
# evidence surfaces flag such items rather than passing the preview off as full
# evidence.
# ---------------------------------------------------------------------------


# Keep `IN (?, …)` parameter counts under SQLite's SQLITE_MAX_VARIABLE_NUMBER
# (999 on older builds) so a source with thousands of spans cannot crash bulk
# span queries.
_SQL_VAR_CHUNK = 900


class SpanTextUnavailable(Exception):
    """A source span's full text could not be hydrated and verified (F10)."""


def _paths_from_state_db(db_path: Path) -> cfg.WikiPaths:
    """Resolve the vault root from the state DB path (``root/.curator/state.sqlite``)."""
    return cfg.WikiPaths(Path(db_path).resolve().parent.parent)


def _reparse_hash_index(paths: cfg.WikiPaths, relpath: str) -> dict[str, str]:
    """Map ``content_hash -> exact full span text`` by re-parsing one source."""
    _title, sections = _section_dicts(paths, relpath)
    return {
        record.content_hash: record.text
        for record in source_spans.spans_from_sections(sections)
    }


def hydrate_span_text(db_path: Path, span_id: str) -> str:
    """Return a source span's exact full text (SEARCH_ENGINE_SCHEMA §10.2 / F10).

    Re-parses the registered source and returns the span whose ``content_hash``
    matches the stored hash, verifying the hydrated text against it. The 200-char
    preview is never substituted. Raises :class:`SpanTextUnavailable` when the
    source is missing/unreadable or no current span matches the stored hash
    (content drift).
    """
    with db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT relpath, content_hash FROM source_spans WHERE id = ?",
            (span_id,),
        ).fetchone()
    if row is None:
        raise SpanTextUnavailable(f"unknown source span: {span_id}")
    paths = _paths_from_state_db(db_path)
    try:
        index = _reparse_hash_index(paths, row["relpath"])
    except Exception as e:  # missing / unreadable / unparseable source file
        raise SpanTextUnavailable(f"source unreadable for span {span_id}: {e}") from e
    text = index.get(row["content_hash"])
    if text is None:
        raise SpanTextUnavailable(
            f"span {span_id} not found in current source (content-hash drift)"
        )
    return text


def hydrate_spans(db_path: Path, span_ids: list[str]) -> dict[str, str]:
    """Best-effort batch hydration, re-parsing each cited source only once.

    Returns ``span_id -> full text`` for every span that hydrates and verifies;
    spans whose source is unavailable or whose hash drifted are omitted, leaving
    the caller to flag them stale/unavailable (the preview is never silently
    presented as full evidence).
    """
    if not span_ids:
        return {}
    # Chunk the IN (...) parameter list under SQLite's variable cap so a source
    # with thousands of spans does not crash bulk hydration.
    rows: list[Any] = []
    with db.connect(db_path) as conn:
        for start in range(0, len(span_ids), _SQL_VAR_CHUNK):
            chunk = span_ids[start:start + _SQL_VAR_CHUNK]
            placeholders = ",".join("?" for _ in chunk)
            rows.extend(
                conn.execute(
                    f"SELECT id, relpath, content_hash FROM source_spans "
                    f"WHERE id IN ({placeholders})",
                    tuple(chunk),
                ).fetchall()
            )
    paths = _paths_from_state_db(db_path)
    by_relpath: dict[str, list[Any]] = {}
    for row in rows:
        by_relpath.setdefault(row["relpath"], []).append(row)
    out: dict[str, str] = {}
    for relpath, group in by_relpath.items():
        try:
            index = _reparse_hash_index(paths, relpath)
        except Exception:
            continue  # source unavailable → omit; caller flags these spans
        for row in group:
            text = index.get(row["content_hash"])
            if text is not None:
                out[row["id"]] = text
    return out


def compile_source_l2(
    paths: cfg.WikiPaths,
    client: Any,
    source_id: int,
    *,
    curate_spec_hash: str = "",
) -> CompileResult:
    """Compile one source's L2: knowledge_units + graph, emit ATM pages.

    Re-derives source spans from the source (stable ids via content-hash dedup),
    extracts knowledge units, builds graph entities/relations, and emits one ATM
    projection page per unit. Sets the source's l2_status.
    """
    with db.connect(paths.state_db) as conn:
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        if row is None:
            return CompileResult(source_id=source_id, error=f"no source id {source_id}")
        source = dict(row)
    relpath = source["relpath"]
    context_id = source.get("context_id") or ""

    db.set_source_layer_status(paths.state_db, source_id, "l2", "running")
    try:
        title, sections = _section_dicts(paths, relpath)
    except Exception as e:
        db.set_source_layer_status(paths.state_db, source_id, "l2", "error", error=str(e))
        return CompileResult(source_id=source_id, error=f"parse failed: {e}")

    spans = source_spans.spans_from_sections(sections)
    span_ids = source_spans.store_source_spans(paths.state_db, source_id, relpath, spans)
    span_inputs = [
        {"id": span_ids[i], "text": spans[i].text, "section_title": spans[i].section_title}
        for i in range(len(span_ids))
    ]

    ku_result = knowledge_units.extract_knowledge_units(
        paths.state_db,
        client,
        source_id=source_id,
        source_title=title,
        spans=span_inputs,
        curate_spec_hash=curate_spec_hash,
    )
    if not ku_result.ok:
        materializer.materialize_search_documents(paths.state_db)
        db.set_source_layer_status(
            paths.state_db, source_id, "l2", "error",
            error="; ".join(ku_result.errors) or "knowledge unit extraction failed",
        )
        return CompileResult(
            source_id=source_id,
            prompt_trace_ids=[ku_result.trace_id] if ku_result.trace_id else [],
            error="knowledge unit extraction failed",
        )

    span_texts = {str(item["id"]): str(item["text"]) for item in span_inputs}
    for unit_id in ku_result.unit_ids:
        validate_claim_support(paths.state_db, unit_id, span_texts=span_texts)
    reconcile_source(
        paths.state_db,
        source_id,
        current_span_ids=span_ids,
        candidate_unit_ids=ku_result.unit_ids,
    )

    # Emit ATM projection pages from the stored units; link them to the CTX.
    atom_ids: list[str] = []
    units = db.list_eligible_knowledge_units(paths.state_db, source_id)
    paths.atoms.mkdir(parents=True, exist_ok=True)
    for unit in units:
        atom_id = projection.new_atom_id()
        page = projection.emit_atom_markdown(unit, atom_id, source_path=relpath)
        (paths.atoms / f"{atom_id}.md").write_text(page, encoding="utf-8")
        db.upsert_knowledge_unit(
            paths.state_db,
            unit_id=unit["id"],
            unit_type=unit["unit_type"],
            canonical_name=unit["canonical_name"],
            statement=unit["statement"],
            source_span_ids=unit["source_span_ids"],
            source_id=source_id,
            confidence=unit["confidence"],
            truth_status=unit["truth_status"],
            atom_node_id=atom_id,
            prompt_run_id=unit.get("prompt_run_id"),
        )
        atom_ids.append(atom_id)
        if context_id:
            db.insert_dag_edge(paths.state_db, context_id, atom_id, "extracted_from", source_id)
        for span_id in unit.get("source_span_ids") or []:
            db.record_artifact_dependency(
                paths.state_db,
                artifact_id=unit["id"],
                artifact_type="knowledge_unit",
                depends_on_id=span_id,
                depends_on_type="source_span",
                dependency_hash=unit.get("prompt_run_id") or "",
            )

    # Build the graph (entities/relations) from this source's units.
    graph = graph_index.extract_entities_and_relations(
        paths.state_db,
        client,
        units=units,
        valid_span_ids=span_ids,
        curate_spec_hash=curate_spec_hash,
    )
    if not graph.ok:
        materializer.materialize_search_documents(paths.state_db)
        db.set_source_layer_status(
            paths.state_db, source_id, "l2", "error",
            error="; ".join(graph.errors) or "graph extraction failed",
        )
        return CompileResult(
            source_id=source_id,
            prompt_trace_ids=[ku_result.trace_id, graph.trace_id] if graph.trace_id else [ku_result.trace_id],
            error="graph extraction failed",
        )

    materializer.materialize_search_documents(paths.state_db)
    trace_ids = [t for t in (ku_result.trace_id, graph.trace_id) if t]

    # Publish this source's compiled claims as one authoritative generation
    # (§26.3). A publish-gate violation discards the staged generation and leaves
    # the prior authoritative one untouched; the extracted rows still persist for
    # the next attempt and the compiler audit. The clean path never raises here.
    try:
        recompile_source(paths.state_db, source_id)
    except Exception as e:
        db.set_source_layer_status(
            paths.state_db, source_id, "l2", "error",
            error=f"generation publish gate failed: {e}",
        )
        return CompileResult(
            source_id=source_id,
            atom_ids=atom_ids,
            knowledge_unit_ids=[str(unit["id"]) for unit in units],
            entity_ids=list(graph.entity_ids.values()),
            prompt_trace_ids=trace_ids,
            error=f"generation publish gate failed: {e}",
        )

    db.set_source_layer_status(paths.state_db, source_id, "l2", "done")
    return CompileResult(
        source_id=source_id,
        atom_ids=atom_ids,
        knowledge_unit_ids=[str(unit["id"]) for unit in units],
        entity_ids=list(graph.entity_ids.values()),
        prompt_trace_ids=trace_ids,
    )


# ---------------------------------------------------------------------------
# Staged compiler generations + atomic publish (SYSTEM_BEHAVIOR §26.3, SCHEMA
# §20.3). A Plan-B-owned compile stages its claims in a `GEN-` generation that
# becomes authoritative only after the publish-gate audit passes; a failed
# compile discards the staged generation and leaves the prior authoritative one
# (and its served state) untouched — no partial authoritative publish.
# ---------------------------------------------------------------------------


def _source_content_hash(db_path: Path, source_id: int) -> str:
    with db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT content_hash FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
    return row["content_hash"] if row else ""


def _generation_summary(source_id: int, gen: dict) -> dict:
    """Deterministic, timestamp-free summary of an authoritative generation, so
    an unchanged rebuild returns a value equal to the prior publish (§26.3)."""
    audit = json.loads(gen.get("audit_json") or "{}")
    return {
        "source_id": source_id,
        "status": gen["status"],
        "prompt_contract_version": gen["prompt_contract_version"],
        "content_hash": audit.get("content_hash", ""),
        "unit_ids": audit.get("unit_ids", []),
        "unit_count": audit.get("unit_count", 0),
    }


def recompile_source(
    db_path: Path, source_id: int, *, _inject_failure: str | None = None
) -> dict:
    """Stage, validate, and atomically publish one source's compiled claims as a
    `GEN-` generation (SYSTEM_BEHAVIOR §26.3).

    Operates on the already-extracted DB state (no LLM): it re-validates the
    source's active units, attributes them to a staged generation, and publishes
    only when the compiler audit finds no release-blocking violation for the
    scope. Behavior:

    - Unchanged rebuild — same source `content_hash` + same prompt contract
      version — reuses the existing authoritative generation and returns the
      identical summary (no duplicate accumulation, no count amplification).
    - A failed compile (`_inject_failure`, an audit violation, or any raised
      error) discards the staged generation and re-raises; the prior
      authoritative generation, projections, and search state are untouched.

    `_inject_failure` is a test seam that simulates a failure at the staged
    compile boundary.
    """
    fingerprint = _source_content_hash(db_path, source_id)
    prior = db.get_authoritative_generation(db_path, source_id)
    if (
        prior is not None
        and _inject_failure is None
        and prior["prompt_contract_version"] == PROMPT_CONTRACT_VERSION
        and json.loads(prior.get("audit_json") or "{}").get("content_hash") == fingerprint
    ):
        return _generation_summary(source_id, prior)

    gen_id = db.create_compiler_generation(
        db_path, prompt_contract_version=PROMPT_CONTRACT_VERSION, source_id=source_id
    )
    try:
        if _inject_failure:
            raise RuntimeError(f"compile failure injected: {_inject_failure}")
        with db.connect(db_path) as conn:
            unit_ids = [
                str(r[0]) for r in conn.execute(
                    "SELECT id FROM knowledge_units "
                    "WHERE source_id = ? AND retired_at IS NULL ORDER BY created_at",
                    (source_id,),
                ).fetchall()
            ]
        for uid in unit_ids:
            validate_claim_support(db_path, uid)
        # Publish gate runs BEFORE any authoritative mutation. A failed audit
        # must leave the prior authoritative generation — including each unit's
        # generation_id attribution — completely untouched (§26.3). Only after
        # the gate clears do we attribute the units to this generation and
        # publish; on failure the prior served state is never overwritten.
        report = run_compiler_audit(db_path)
        if report.publish_blocking:
            raise RuntimeError(
                f"compiler audit blocked publish for source {source_id}: "
                f"{report.publish_blocking}"
            )
        verified_ids = sorted(
            str(u["id"]) for u in db.list_eligible_knowledge_units(db_path, source_id)
        )
        with db.connect(db_path) as conn:
            conn.execute(
                "UPDATE knowledge_units SET generation_id = ? "
                "WHERE source_id = ? AND retired_at IS NULL",
                (gen_id, source_id),
            )
        audit_json = json.dumps(
            {"content_hash": fingerprint, "unit_ids": verified_ids,
             "unit_count": len(verified_ids)},
            sort_keys=True,
        )
        db.publish_compiler_generation(db_path, gen_id, audit_json=audit_json)
    except Exception:
        db.discard_compiler_generation(db_path, gen_id)
        raise

    published = db.get_authoritative_generation(db_path, source_id)
    assert published is not None  # just published above
    return _generation_summary(source_id, published)


def compile_global_l3(
    paths: cfg.WikiPaths,
    client: Any,
    *,
    curate_spec_hash: str = "",
) -> list[str]:
    """Global L3: detect communities, generate reports, emit CON pages.

    Returns the list of concept (CON) page ids written. Sets l3_status='done'
    for sources whose L2 is done.
    """
    plans = community_reports.detect_communities(paths.state_db)
    concept_ids: list[str] = []
    paths.concepts.mkdir(parents=True, exist_ok=True)
    errors = []
    for plan in plans:
        try:
            rep_id = community_reports.generate_community_report(
                paths.state_db, client, plan, curate_spec_hash=curate_spec_hash
            )
            if not rep_id:
                continue

            report = db.get_community_report(paths.state_db, rep_id)
            if not report:
                continue
            concept_id = projection.new_concept_id()
            page = projection.emit_concept_markdown(report, concept_id)
            (paths.concepts / f"{concept_id}.md").write_text(page, encoding="utf-8")
            concept_ids.append(concept_id)
            # dag_edges: ATM(units of entities) -> CON. Link via knowledge units whose
            # spans back the community's entities (best-effort traversal aid).
            for span_id in report.get("source_span_ids") or []:
                db.record_artifact_dependency(
                    paths.state_db,
                    artifact_id=rep_id,
                    artifact_type="community_report",
                    depends_on_id=span_id,
                    depends_on_type="source_span",
                    dependency_hash=report.get("dependency_hash", ""),
                )
        except Exception as e:
            errors.append(str(e))

    # L4 Synthesis: distill all community reports into shared corpus-wide insights.
    # Skipped automatically when the report corpus is unchanged.
    if not errors:
        try:
            synthesis.generate_synthesis(paths, client, curate_spec_hash=curate_spec_hash)
        except Exception as e:
            errors.append(str(e))

    # Mark L3 done for sources whose L2 is complete.
    with db.connect(paths.state_db) as conn:
        rows = conn.execute(
            f"SELECT id FROM sources WHERE l2_status = '{consts.STATUS_DONE}'"
        ).fetchall()
        l2_done_ids = [r["id"] for r in rows]
    
    status = "error" if errors else "done"
    error_msg = "; ".join(errors) if errors else None
    
    for sid in l2_done_ids:
        db.set_source_layer_status(paths.state_db, sid, "l3", status, error=error_msg)
        
    if errors:
        raise RuntimeError(f"L3 global clustering encountered errors: {error_msg}")

    materializer.materialize_search_documents(paths.state_db)
    return concept_ids


def reemit_projections(paths: cfg.WikiPaths) -> dict[str, int]:
    """Re-emit the derived L2/L3 markdown corpus from the authoritative DB records.

    Realizes the compile-model invariant: the DB is the source of truth and the
    ``.curator/Collections`` markdown is a disposable projection. Existing ATM/CON
    projection files are deleted first, then re-emitted from current
    ``knowledge_units`` / ``community_reports`` rows — so the qmd corpus always
    reflects the DB after any correction. Source truth (CTX/spans, 03_Notes,
    04_Resources) is never touched.

    Returns counts of emitted atom/concept pages.
    """
    paths.atoms.mkdir(parents=True, exist_ok=True)
    paths.concepts.mkdir(parents=True, exist_ok=True)
    for stale in paths.atoms.glob(f"{consts.PREFIX_L2}-*.md"):
        stale.unlink()
    for stale in paths.concepts.glob(f"{consts.PREFIX_L3}-*.md"):
        stale.unlink()

    n_atoms = 0
    with db.connect(paths.state_db) as conn:
        source_ids = [int(r["id"]) for r in conn.execute("SELECT id FROM sources").fetchall()]
    for sid in source_ids:
        for unit in db.list_eligible_knowledge_units(paths.state_db, sid):
            atom_id = unit.get("atom_node_id") or projection.new_atom_id()
            page = projection.emit_atom_markdown(unit, atom_id)
            (paths.atoms / f"{atom_id}.md").write_text(page, encoding="utf-8")
            n_atoms += 1

    n_concepts = 0
    for report in db.list_community_reports(paths.state_db):
        concept_id = projection.new_concept_id()
        page = projection.emit_concept_markdown(report, concept_id)
        (paths.concepts / f"{concept_id}.md").write_text(page, encoding="utf-8")
        n_concepts += 1

    n_synthesis = synthesis.reemit_synthesis(paths)
    materializer.materialize_search_documents(paths.state_db)

    return {"atoms": n_atoms, "concepts": n_concepts, "synthesis": n_synthesis}
