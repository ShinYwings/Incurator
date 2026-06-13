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

from dataclasses import dataclass, field
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

__all__ = [
    "CompileResult", "compile_source_l2", "compile_global_l3", "reemit_projections",
    # Plan B (v0.8.0) claim-support validation surface (SYSTEM_BEHAVIOR §26).
    "AuditReport", "validate_claim_support", "run_compiler_audit", "reconcile_source",
]


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

    # Emit ATM projection pages from the stored units; link them to the CTX.
    atom_ids: list[str] = []
    units = db.list_knowledge_units_for_source(paths.state_db, source_id)
    paths.atoms.mkdir(parents=True, exist_ok=True)
    for unit in units:
        if unit["id"] not in ku_result.unit_ids:
            continue
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
    db.set_source_layer_status(paths.state_db, source_id, "l2", "done")
    trace_ids = [t for t in (ku_result.trace_id, graph.trace_id) if t]
    return CompileResult(
        source_id=source_id,
        atom_ids=atom_ids,
        knowledge_unit_ids=ku_result.unit_ids,
        entity_ids=list(graph.entity_ids.values()),
        prompt_trace_ids=trace_ids,
    )


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
        for unit in db.list_knowledge_units_for_source(paths.state_db, sid):
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
