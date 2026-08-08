"""End-to-end L2/L3 compile orchestration (the v0.3.1 `wiki build` core).

Drives the curation-native compile for sources whose L1 (source_spans) exists:

    per source : spans -> knowledge_units -> graph entities/relations
                 -> emit ATM projection pages, set l2_status
    global     : detect communities -> community reports
                 -> emit CON projection pages, set l3_status

The DB is the source of truth; ATM/CON markdown pages are derived projections
emitted for DB-native indexing (SYSTEM_BEHAVIOR.md §22). Source spans are
re-derived from the source here (the DB stores only previews) so units cite the
exact stored span ids.
"""

from __future__ import annotations

import json
import logging
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import config as cfg
from .. import constants as consts
from .. import db, parsers
from ..retrieval import materializer
from . import (
    authored_topology,
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

logger = logging.getLogger(__name__)

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
PROMPT_CONTRACT_VERSION = "curator.knowledge_unit_extract@v3"
_POST_PUBLISH_PROJECTION_ERROR = f"{consts.POST_PUBLISH_PROJECTION_PREFIX} failed:"
_POST_PUBLISH_PROJECTION_PENDING = f"{consts.POST_PUBLISH_PROJECTION_PREFIX} pending"


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


def _audit_content_hash(generation: dict[str, Any]) -> str:
    """Read the recovery fingerprint from a generation audit, failing closed."""
    try:
        audit = json.loads(str(generation.get("audit_json") or "{}"))
    except (TypeError, ValueError):
        return ""
    return str(audit.get("content_hash") or "") if isinstance(audit, dict) else ""


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


def _source_ids_for_span_ids(conn: Any, span_ids: set[str]) -> set[int]:
    """Resolve span provenance without exceeding SQLite's variable limit."""
    ordered_ids = sorted(span_ids)
    source_ids: set[int] = set()
    for start in range(0, len(ordered_ids), _SQL_VAR_CHUNK):
        chunk = ordered_ids[start:start + _SQL_VAR_CHUNK]
        placeholders = ",".join("?" for _ in chunk)
        source_ids.update(
            int(row["source_id"])
            for row in conn.execute(
                f"SELECT DISTINCT source_id FROM source_spans "
                f"WHERE id IN ({placeholders})",
                tuple(chunk),
            ).fetchall()
        )
    return source_ids


def _atom_ids_for_report(paths: cfg.WikiPaths, report: dict) -> list[str]:
    """Resolve the ATM pages that support a community report's active relations."""
    relation_ids = [str(rid) for rid in (report.get("relation_ids") or []) if rid]
    if not relation_ids:
        return []
    atom_ids: set[str] = set()
    with db.connect(paths.state_db) as conn:
        for start in range(0, len(relation_ids), _SQL_VAR_CHUNK):
            chunk = relation_ids[start:start + _SQL_VAR_CHUNK]
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"""
                SELECT DISTINCT ku.atom_node_id
                FROM graph_relation_supports grs
                JOIN knowledge_units ku ON ku.id = grs.knowledge_unit_id
                JOIN compiler_generations g ON g.id = ku.generation_id
                WHERE grs.relation_id IN ({placeholders})
                  AND grs.support_status = 'verified'
                  AND ku.support_status = 'verified'
                  AND ku.retired_at IS NULL
                  AND g.status = 'authoritative'
                  AND ku.atom_node_id IS NOT NULL
                  AND ku.atom_node_id != ''
                """,
                tuple(chunk),
            ).fetchall()
            atom_ids.update(str(row["atom_node_id"]) for row in rows)
    return sorted(atom_ids)


def _concept_id_for_report(report: dict) -> str:
    report_key = str(report.get("id") or report.get("community_key") or "")
    digest = hashlib.sha256(f"concept:{report_key}".encode("utf-8")).hexdigest()[:8]
    return f"{consts.PREFIX_L3}-{digest}"


class SpanTextUnavailable(Exception):
    """A source span's full text could not be hydrated and verified (F10)."""


def _paths_from_state_db(db_path: Path) -> cfg.WikiPaths:
    """Resolve the vault root from the machine-cache marker beside the DB."""
    marker = Path(db_path).resolve().parent / "vault_root"
    if not marker.exists():
        raise RuntimeError(f"Missing vault_root marker beside state DB: {marker}")
    root = Path(marker.read_text(encoding="utf-8").strip()).expanduser().resolve()
    return cfg.paths_from_config(root)


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
        except Exception as e:
            # KEEP broad: best-effort batch hydration — a source that is missing
            # or unparseable just omits its spans (caller flags them); now logged
            # instead of swallowed silently.
            logger.debug("Span hydration skipped for '%s' (source unavailable): %s", relpath, e)
            continue
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
    prior_generation = db.get_authoritative_generation(paths.state_db, source_id)
    projection_state = str(source.get("layer_error") or "")
    if (
        prior_generation is not None
        and (
            projection_state == _POST_PUBLISH_PROJECTION_PENDING
            or (
                str(source.get("l2_status") or "") == "error"
                and projection_state.startswith(_POST_PUBLISH_PROJECTION_ERROR)
            )
        )
        and prior_generation["prompt_contract_version"] == PROMPT_CONTRACT_VERSION
        and _audit_content_hash(prior_generation) == source.get("content_hash")
    ):
        return _recover_published_source(
            paths,
            source_id=source_id,
            context_id=str(context_id),
        )
    db.set_source_layer_status(paths.state_db, source_id, "l2", "running")
    try:
        title, sections = _section_dicts(paths, relpath)
    except Exception as e:
        # KEEP broad: L2 parse boundary — any parse failure is surfaced (l2 status
        # set to error + returned as a CompileResult error), never swallowed.
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
        error_msg = "; ".join(ku_result.errors) or "knowledge unit extraction failed"
        materializer.materialize_search_documents(paths.state_db)
        db.set_source_layer_status(
            paths.state_db, source_id, "l2", "error",
            error=error_msg,
        )
        return CompileResult(
            source_id=source_id,
            prompt_trace_ids=[ku_result.trace_id] if ku_result.trace_id else [],
            error=error_msg,
        )

    # --- Copy-on-stage staging + atomic publish (SYSTEM_BEHAVIOR §26.3) ------
    # A fresh staged generation OWNS this compile's extracted units. They are
    # validated and gated BEFORE any served write: a blocked gate (or any error)
    # discards the staged units and leaves the prior authoritative generation —
    # its rows, ATM pages, graph, and search — completely untouched. No ATM page,
    # graph entity, or search doc is written for a staged generation.
    gen_id = db.create_compiler_generation(
        paths.state_db, prompt_contract_version=PROMPT_CONTRACT_VERSION, source_id=source_id
    )
    try:
        authored_data = authored_topology.empty_authored_topology(str(relpath))
        if authored_topology.is_markdown_path(str(relpath)):
            source_text = (paths.root / str(relpath)).read_text(
                encoding="utf-8", errors="replace"
            )
            authored_data = authored_topology.extract_authored_topology(
                paths.root,
                str(relpath),
                source_text,
            )
        with db.connect(paths.state_db) as conn:
            for uid in ku_result.unit_ids:
                conn.execute(
                    "UPDATE knowledge_units SET generation_id = ? WHERE id = ?",
                    (gen_id, uid),
                )
        span_texts = {str(item["id"]): str(item["text"]) for item in span_inputs}
        for unit_id in ku_result.unit_ids:
            validate_claim_support(paths.state_db, unit_id, span_texts=span_texts)
        # Graph LLM extraction runs DURING staging (returning data IN MEMORY) so a
        # graph failure occurs BEHIND the publish gate: it discards the staged
        # units and never leaves a published generation without its graph (§26.3).
        # The persist (no LLM) happens only after the gate + flip.
        staged_units = db.list_generation_units(paths.state_db, gen_id)
        graph_data = graph_index.extract_graph_data(
            paths.state_db, client, units=staged_units,
            valid_span_ids=span_ids, curate_spec_hash=curate_spec_hash,
        )
        if not graph_data.ok:
            raise RuntimeError(
                "graph extraction failed: " + ("; ".join(graph_data.errors) or "unknown")
            )
        _run_publish_gate(paths.state_db, source_id)
        # Reconcile (carrying unchanged claims' stable ids into this generation),
        # persist the in-memory graph, and publish — ALL in ONE transaction, so
        # ANY exception (reconcile, graph persist, or the flip) rolls the prior
        # authoritative state AND the graph back unchanged (§26.3 atomic publish).
        # The outer except then discards only the still-staged candidates.
        fingerprint = _source_content_hash(paths.state_db, source_id)
        authored_graph = authored_topology.AuthoredPersistence()
        with db.connect(paths.state_db) as conn:
            reconcile_source(
                paths.state_db, source_id,
                current_span_ids=span_ids, candidate_unit_ids=ku_result.unit_ids,
                generation_id=gen_id, conn=conn,
            )
            graph = graph_index.persist_graph_data(
                paths.state_db, graph_data, conn=conn,
                units=staged_units, source_lineage_hash=source["content_hash"],
            )
            authored_graph = authored_topology.persist_authored_topology(
                paths.state_db,
                authored_data,
                source_id=source_id,
                generation_id=gen_id,
                conn=conn,
            )
            _publish_generation(
                paths.state_db,
                source_id,
                gen_id,
                fingerprint,
                authored_relation_ids=authored_graph.relation_ids,
                conn=conn,
            )
            newly_active: list[str] = []
            for relation_id in authored_graph.relation_ids:
                status = db.compile_relation_lifecycle(
                    paths.state_db,
                    relation_id=relation_id,
                    conn=conn,
                )
                if (
                    status == "active"
                    and relation_id in authored_graph.activated_relation_ids
                ):
                    newly_active.append(relation_id)
            db.retire_community_reports_for_relation_endpoints_on_connection(
                conn,
                newly_active,
            )
            # This marker commits atomically with the authoritative generation.
            # If the process exits before the post-commit projection phase can
            # report success or failure, the next attempt recovers from the DB
            # instead of invoking the LLM again.
            conn.execute(
                "UPDATE sources SET layer_error = ? WHERE id = ?",
                (_POST_PUBLISH_PROJECTION_PENDING, source_id),
            )
    except Exception as e:
        # KEEP broad: transactional rollback boundary — ANY staged-compile failure
        # must discard the staged generation and surface (l2 error), so a partial
        # generation is never published.
        _discard_staged_units(paths.state_db, gen_id)
        db.discard_compiler_generation(paths.state_db, gen_id)
        db.set_source_layer_status(
            paths.state_db, source_id, "l2", "error", error=f"staged compile failed: {e}"
        )
        return CompileResult(
            source_id=source_id,
            prompt_trace_ids=[ku_result.trace_id] if ku_result.trace_id else [],
            error=f"staged compile failed: {e}",
        )

    # Canonical publish has committed. Stable projection identities and
    # dependencies are persisted before disposable markdown/search output.
    try:
        units = _finalize_published_source(
            paths,
            source_id=source_id,
            context_id=str(context_id),
            source_path=str(relpath),
        )
    except Exception as e:
        error_msg = f"{_POST_PUBLISH_PROJECTION_ERROR} {e}"
        db.set_source_layer_status(
            paths.state_db,
            source_id,
            "l2",
            "error",
            error=error_msg,
        )
        return CompileResult(
            source_id=source_id,
            prompt_trace_ids=[ku_result.trace_id] if ku_result.trace_id else [],
            error=error_msg,
        )

    atom_ids = [str(unit["atom_node_id"]) for unit in units]
    trace_ids = [t for t in (ku_result.trace_id, graph.trace_id) if t]
    l2_status = (
        "done" if db.list_serving_units(paths.state_db, source_id) else "skipped"
    )
    db.set_source_layer_status(paths.state_db, source_id, "l2", l2_status)
    return CompileResult(
        source_id=source_id,
        atom_ids=atom_ids,
        knowledge_unit_ids=[str(unit["id"]) for unit in units],
        entity_ids=sorted(
            set(graph.entity_ids.values()) | set(authored_graph.entity_ids)
        ),
        prompt_trace_ids=trace_ids,
    )


def _finalize_published_source(
    paths: cfg.WikiPaths,
    *,
    source_id: int,
    context_id: str,
    source_path: str = "",
    recover: bool = False,
) -> list[dict]:
    """Persist stable projection identity, then emit disposable output.

    A normal compile rewrites only this source's ATM pages and the DB-native
    search corpus. Recovery uses the workspace-wide DB re-emitter so any
    partially written ATM/CON/SYN projection is repaired without another LLM
    call or compiler generation.
    """
    units, all_source_atom_ids = _persist_source_projection_state(
        paths,
        source_id=source_id,
        context_id=context_id,
    )
    if recover:
        reemit_projections(paths)
        return units

    live_atom_ids = {str(unit["atom_node_id"]) for unit in units}
    paths.atoms.mkdir(parents=True, exist_ok=True)
    for stale_atom_id in sorted(all_source_atom_ids - live_atom_ids):
        (paths.atoms / f"{stale_atom_id}.md").unlink(missing_ok=True)
    for unit in units:
        atom_id = str(unit["atom_node_id"])
        page = projection.emit_atom_markdown(
            unit,
            atom_id,
            source_path=source_path,
        )
        (paths.atoms / f"{atom_id}.md").write_text(page, encoding="utf-8")
    materializer.materialize_search_documents(paths.state_db)
    return units


def _persist_source_projection_state(
    paths: cfg.WikiPaths,
    *,
    source_id: int,
    context_id: str,
) -> tuple[list[dict], set[str]]:
    """Persist stable ATM ids and canonical dependencies before file output."""
    from ..db_sync import (
        clear_row_tombstone_on_connection,
        delete_rows_with_tombstones_on_connection,
        record_row_tombstone_on_connection,
    )

    with db.connect(paths.state_db) as conn:
        rows = conn.execute(
            "SELECT ku.* FROM knowledge_units ku "
            "JOIN compiler_generations g ON g.id = ku.generation_id "
            "JOIN sources s ON s.id = ku.source_id AND s.id = g.source_id "
            "WHERE ku.source_id = ? AND ku.retired_at IS NULL "
            "AND ku.support_status = 'verified' AND g.status = 'authoritative' "
            "ORDER BY ku.created_at",
            (source_id,),
        ).fetchall()
        live_unit_ids: set[str] = set()
        live_atom_ids: set[str] = set()
        desired_edge_ids: set[str] = set()
        all_source_atom_ids = {
            str(row["atom_node_id"])
            for row in conn.execute(
                "SELECT atom_node_id FROM knowledge_units "
                "WHERE source_id = ? AND atom_node_id IS NOT NULL "
                "AND atom_node_id != ''",
                (source_id,),
            ).fetchall()
        }
        for row in rows:
            unit_id = str(row["id"])
            atom_id = str(row["atom_node_id"] or projection.new_atom_id())
            live_unit_ids.add(unit_id)
            live_atom_ids.add(atom_id)
            if not row["atom_node_id"]:
                revision = db.strict_successor_timestamp(row["updated_at"])
                conn.execute(
                    "UPDATE knowledge_units SET atom_node_id = ?, updated_at = ? "
                    "WHERE id = ?",
                    (atom_id, revision, unit_id),
                )
            if context_id:
                edge_id = f"{context_id}:{atom_id}"
                desired_edge_ids.add(edge_id)
                conn.execute(
                    "INSERT OR IGNORE INTO dag_edges "
                    "(id, from_id, to_id, edge_type, source_id, created_at) "
                    "VALUES (?, ?, ?, 'extracted_from', ?, ?)",
                    (
                        edge_id,
                        context_id,
                        atom_id,
                        source_id,
                        db._now_iso(),
                    ),
                )
                clear_row_tombstone_on_connection(
                    conn,
                    "dag_edges",
                    {"id": edge_id},
                )
            try:
                span_ids = json.loads(str(row["source_span_ids"] or "[]"))
            except (TypeError, ValueError):
                span_ids = []
            if not isinstance(span_ids, list):
                span_ids = []
            for span_id in span_ids:
                dependency_hash = str(row["prompt_run_id"] or "")
                existing = conn.execute(
                    "SELECT dependency_hash FROM artifact_dependencies "
                    "WHERE artifact_id = ? AND depends_on_id = ? "
                    "AND depends_on_type = 'source_span'",
                    (unit_id, str(span_id)),
                ).fetchone()
                if (
                    existing is not None
                    and str(existing["dependency_hash"]) == dependency_hash
                ):
                    continue
                db.record_artifact_dependency(
                    paths.state_db,
                    artifact_id=unit_id,
                    artifact_type="knowledge_unit",
                    depends_on_id=str(span_id),
                    depends_on_type="source_span",
                    dependency_hash=dependency_hash,
                    conn=conn,
                )

        stale_unit_ids = [
            str(row["id"])
            for row in conn.execute(
                "SELECT id FROM knowledge_units WHERE source_id = ?",
                (source_id,),
            ).fetchall()
            if str(row["id"]) not in live_unit_ids
        ]
        for start in range(0, len(stale_unit_ids), _SQL_VAR_CHUNK):
            chunk = stale_unit_ids[start:start + _SQL_VAR_CHUNK]
            placeholders = ",".join("?" for _ in chunk)
            dependency_rows = conn.execute(
                "SELECT created_at FROM artifact_dependencies "
                "WHERE artifact_type = 'knowledge_unit' "
                f"AND artifact_id IN ({placeholders})",
                tuple(chunk),
            ).fetchall()
            dependency_revision = db.strict_successor_timestamp(
                *(row["created_at"] for row in dependency_rows)
            )
            delete_rows_with_tombstones_on_connection(
                conn,
                "artifact_dependencies",
                "artifact_type = 'knowledge_unit' "
                f"AND artifact_id IN ({placeholders})",
                tuple(chunk),
                deleted_at=dependency_revision,
            )

        stale_edges = [
            row
            for row in conn.execute(
                "SELECT * FROM dag_edges WHERE source_id = ?",
                (source_id,),
            ).fetchall()
            if str(row["id"]) not in desired_edge_ids
        ]
        for row in stale_edges:
            record_row_tombstone_on_connection(
                conn,
                "dag_edges",
                row,
                deleted_at=db.strict_successor_timestamp(row["created_at"]),
            )
        if stale_edges:
            conn.executemany(
                "DELETE FROM dag_edges WHERE id = ?",
                [(row["id"],) for row in stale_edges],
            )

        stale_atom_ids = sorted(all_source_atom_ids - live_atom_ids)
        for start in range(0, len(stale_atom_ids), _SQL_VAR_CHUNK):
            chunk = stale_atom_ids[start:start + _SQL_VAR_CHUNK]
            placeholders = ",".join("?" for _ in chunk)
            for row in conn.execute(
                f"SELECT * FROM atoms WHERE id IN ({placeholders})",
                tuple(chunk),
            ).fetchall():
                record_row_tombstone_on_connection(
                    conn,
                    "atoms",
                    row,
                    deleted_at=db.strict_successor_timestamp(row["last_updated"]),
                )
            conn.execute(
                f"DELETE FROM atoms WHERE id IN ({placeholders})",
                tuple(chunk),
            )

    units = db.list_serving_units(paths.state_db, source_id)
    return units, all_source_atom_ids


def _recover_published_source(
    paths: cfg.WikiPaths,
    *,
    source_id: int,
    context_id: str,
) -> CompileResult:
    try:
        units = _finalize_published_source(
            paths,
            source_id=source_id,
            context_id=context_id,
            recover=True,
        )
    except Exception as e:
        error_msg = f"{_POST_PUBLISH_PROJECTION_ERROR} {e}"
        db.set_source_layer_status(
            paths.state_db,
            source_id,
            "l2",
            "error",
            error=error_msg,
        )
        return CompileResult(source_id=source_id, error=error_msg)
    db.set_source_layer_status(
        paths.state_db,
        source_id,
        "l2",
        "done" if units else "skipped",
    )
    return CompileResult(
        source_id=source_id,
        atom_ids=[str(unit["atom_node_id"]) for unit in units],
        knowledge_unit_ids=[str(unit["id"]) for unit in units],
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


def _run_publish_gate(
    db_path: Path, source_id: int, *, conn: Any = None
) -> None:
    """The publish gate (§26.3): raise if the compiler audit finds any
    structural violation that blocks publishing the served set. Pass ``conn`` to
    audit the caller's uncommitted transaction, so the gate checks the exact
    re-validated state about to be published."""
    report = run_compiler_audit(db_path, conn=conn)
    if report.publish_blocking:
        raise RuntimeError(
            f"compiler audit blocked publish for source {source_id}: "
            f"{report.publish_blocking}"
        )


def _discard_staged_units(db_path: Path, generation_id: str) -> None:
    """Delete a staged generation's knowledge_units + their claim_supports
    (copy-on-stage discard, §26.3). The staged rows are distinct from the prior
    authoritative generation's rows, so this never touches served state."""
    from ..db_sync import delete_rows_with_tombstones_on_connection

    with db.connect(db_path) as conn:
        unit_ids = [
            str(r[0]) for r in conn.execute(
                "SELECT id FROM knowledge_units WHERE generation_id = ?",
                (generation_id,),
            ).fetchall()
        ]
        for uid in unit_ids:
            delete_rows_with_tombstones_on_connection(
                conn,
                "claim_supports",
                "knowledge_unit_id = ?",
                (uid,),
            )
        conn.execute("DELETE FROM knowledge_units WHERE generation_id = ?", (generation_id,))


def _retire_prior_generation_units(
    db_path: Path, source_id: int, generation_id: str, *, conn: Any = None
) -> None:
    """Retire the source's active units that are NOT part of the generation being
    published (their generation becomes 'discarded' on publish, so they leave
    serving; retiring also drops their claim_supports — §26.3, §20.5 #3).
    Pass ``conn`` to run inside a caller's transaction (atomic publish)."""
    with db._maybe_conn(db_path, conn) as c:
        prior = [
            str(r[0]) for r in c.execute(
                "SELECT id FROM knowledge_units WHERE source_id = ? AND retired_at IS NULL "
                "AND (generation_id IS NULL OR generation_id != ?)",
                (source_id, generation_id),
            ).fetchall()
        ]
    for uid in prior:
        db.retire_knowledge_unit(db_path, uid, conn=conn)


def _publish_generation(
    db_path: Path,
    source_id: int,
    generation_id: str,
    fingerprint: str,
    *,
    authored_relation_ids: tuple[str, ...] = (),
    conn: Any = None,
) -> None:
    """Atomically publish a staged generation: retire the source's prior-generation
    units, then flip this generation authoritative (prior → discarded). Assumes the
    generation's units are already attributed and the publish gate has passed.
    Pass ``conn`` so the retire + flip run in the caller's single transaction."""
    _retire_prior_generation_units(db_path, source_id, generation_id, conn=conn)
    verified_ids = sorted(
        str(u["id"]) for u in db.list_generation_units(db_path, generation_id, conn=conn)
    )
    audit_json = json.dumps(
        {
            "authored_relation_ids": sorted(set(authored_relation_ids)),
            "content_hash": fingerprint,
            "unit_ids": verified_ids,
            "unit_count": len(verified_ids),
        },
        sort_keys=True,
    )
    db.publish_compiler_generation(db_path, generation_id, audit_json=audit_json, conn=conn)


def _generation_authored_relation_ids(generation: dict | None) -> tuple[str, ...] | None:
    if generation is None:
        return None
    return db.generation_authored_relation_ids(generation.get("audit_json"))


def _reconcile_db_only_authored_membership(
    *,
    source_id: int,
    prior: dict | None,
    generation_id: str,
    fingerprint: str,
    conn: Any,
) -> tuple[str, ...]:
    source_owned_ids = {
        str(row[0])
        for row in conn.execute(
            "SELECT r.id FROM graph_relations r "
            "JOIN compiler_generations g ON g.id = r.generation_id "
            "WHERE r.edge_class = 'authored' AND g.source_id = ?",
            (source_id,),
        ).fetchall()
    }
    carried: tuple[str, ...] = ()
    if prior is not None:
        try:
            prior_audit = json.loads(prior.get("audit_json") or "{}")
        except (TypeError, ValueError):
            prior_audit = {}
        requested = _generation_authored_relation_ids(prior)
        prior_ids = {
            str(row[0])
            for row in conn.execute(
                "SELECT id FROM graph_relations "
                "WHERE edge_class = 'authored' AND generation_id = ?",
                (prior["id"],),
            ).fetchall()
        }
        if (
            isinstance(prior_audit, dict)
            and prior_audit.get("content_hash") == fingerprint
            and requested is not None
            and set(requested) == prior_ids
        ):
            carried = requested

    for relation_id in carried:
        conn.execute(
            "UPDATE graph_relations SET generation_id = ?, "
            "lifecycle_status = 'provisional', quarantine_reason = '', "
            "reeval_trigger = '', updated_at = ? WHERE id = ?",
            (generation_id, db._now_iso(), relation_id),
        )
    db.retire_graph_relations_on_connection(
        conn,
        source_owned_ids - set(carried),
    )
    return carried


def recompile_source(
    db_path: Path, source_id: int, *, _inject_failure: str | None = None
) -> dict:
    """Stage, validate, and atomically publish one source's compiled claims as a
    `GEN-` generation (SYSTEM_BEHAVIOR §26.3) — the DB-level re-publish path (no
    LLM). It re-validates the source's active units, and on a passing gate
    attributes them to a staged generation and publishes.

    - Unchanged rebuild — same source `content_hash` + same prompt contract
      version — reuses the existing authoritative generation and returns the
      identical summary (no duplicate accumulation, no count amplification).
    - A failed compile (`_inject_failure`, an audit violation, or any raised
      error) discards the staged generation and re-raises; the prior
      authoritative generation, projections, and search state are untouched
      (attribution happens only AFTER the gate clears — Flaw-2-safe).

    `_inject_failure` is a test seam that simulates a failure at the staged
    compile boundary.
    """
    fingerprint = _source_content_hash(db_path, source_id)
    prior = db.get_authoritative_generation(db_path, source_id)
    if (
        prior is not None
        and _inject_failure is None
        and prior["prompt_contract_version"] == PROMPT_CONTRACT_VERSION
        and _audit_content_hash(prior) == fingerprint
    ):
        materializer.materialize_search_documents(db_path)
        return _generation_summary(source_id, prior)

    gen_id = db.create_compiler_generation(
        db_path, prompt_contract_version=PROMPT_CONTRACT_VERSION, source_id=source_id
    )
    try:
        if _inject_failure:
            raise RuntimeError(f"compile failure injected: {_inject_failure}")
        # Validate, audit, attribute, and flip atomically in ONE transaction
        # (DB-level re-publish: all of the source's active units belong to this
        # generation). The publish gate runs INSIDE the transaction, AFTER
        # re-validation, so it audits the exact uncommitted state about to be
        # published — never a pre-validation snapshot. This lets a re-validation
        # heal a transiently-dangling support (re-write it against the live span)
        # instead of the gate refusing to republish, while a genuine structural
        # break still raises and rolls the whole transaction back: no partial
        # publish, no mutated served state (§26.3).
        with db.connect(db_path) as conn:
            unit_ids = [
                str(r[0]) for r in conn.execute(
                    "SELECT id FROM knowledge_units "
                    "WHERE source_id = ? AND retired_at IS NULL ORDER BY created_at",
                    (source_id,),
                ).fetchall()
            ]
            for uid in unit_ids:
                validate_claim_support(db_path, uid, conn=conn)
            _run_publish_gate(db_path, source_id, conn=conn)
            conn.execute(
                "UPDATE knowledge_units SET generation_id = ? "
                "WHERE source_id = ? AND retired_at IS NULL",
                (gen_id, source_id),
            )
            authored_relation_ids = _reconcile_db_only_authored_membership(
                source_id=source_id,
                prior=prior,
                generation_id=gen_id,
                fingerprint=fingerprint,
                conn=conn,
            )
            _publish_generation(
                db_path,
                source_id,
                gen_id,
                fingerprint,
                authored_relation_ids=authored_relation_ids,
                conn=conn,
            )
            for relation_id in authored_relation_ids:
                db.compile_relation_lifecycle(
                    db_path,
                    relation_id=relation_id,
                    conn=conn,
                )
    except Exception:
        # KEEP broad: transactional rollback — discard the staged generation on
        # any failure and re-raise so the caller sees the real error.
        db.discard_compiler_generation(db_path, gen_id)
        raise

    published = db.get_authoritative_generation(db_path, source_id)
    assert published is not None  # just published above
    materializer.materialize_search_documents(db_path)
    return _generation_summary(source_id, published)


def compile_global_l3(
    paths: cfg.WikiPaths,
    client: Any,
    *,
    curate_spec_hash: str = "",
) -> list[str]:
    """Global L3 (claim-grounded, SYSTEM_BEHAVIOR §27.5/§27.8): deterministically
    rebuild the authoritative community/report generation from ``active`` relations
    over canonical entities, fill each served report with LLM prose, and emit CON
    pages.

    A relation grounds a report once **≥1 independent source** asserts it (§27.2);
    only a relation with no verified support is excluded. There is still no broad
    community-span fallback (SYSTEM_BEHAVIOR §27.5). The deterministic
    ``db.rebuild_graph_generation`` builds the report identity + grounding and
    retires stale communities BEFORE this prose pass / synthesis consume them.

    Returns the list of concept (CON) page ids written. Sets l3_status='done'
    for sources whose L2 is done.
    """
    # (1) Deterministic claim-grounded compile: relation lifecycle -> active
    # topology -> community/report skeletons (identity, exact active relations,
    # eligible support spans, dependency hashes), retiring stale communities (§27.5).
    db.rebuild_graph_generation(paths.state_db)

    concept_ids: list[str] = []
    report_concept_ids: dict[str, str] = {}
    paths.concepts.mkdir(parents=True, exist_ok=True)
    l3_errors: list[str] = []
    l4_errors: list[str] = []
    # (2) Prose pass over each SERVED (non-retired) report, merge-upserted by key.
    # rebuild_graph_generation already recorded the report's precise artifact
    # dependencies (report->relation, report->span), so the prose pass adds no
    # broad dependency rows.
    for report in db.list_community_reports(paths.state_db):
        try:
            rep_id = community_reports.generate_report_prose(
                paths.state_db, client, report, curate_spec_hash=curate_spec_hash
            )
            if not rep_id:
                continue
            full = db.get_community_report(paths.state_db, rep_id)
            if not full:
                continue
            concept_id = _concept_id_for_report(full)
            full["atom_ids"] = _atom_ids_for_report(paths, full)
            page = projection.emit_concept_markdown(full, concept_id)
            (paths.concepts / f"{concept_id}.md").write_text(page, encoding="utf-8")
            concept_ids.append(concept_id)
            report_concept_ids[rep_id] = concept_id
        except Exception as e:
            # KEEP broad: per-report prose is best-effort — collect the error and
            # continue so one bad report does not abort the whole L3 pass; the
            # aggregated errors gate the synthesis step below.
            logger.warning("Community report prose failed: %s", e)
            l3_errors.append(str(e))

    # L4 Synthesis: distill all community reports into shared corpus-wide insights.
    # Skipped automatically when the report corpus is unchanged.
    synthesis_ids: list[str] = []
    if not l3_errors:
        try:
            synthesis_ids = synthesis.generate_synthesis(
                paths, client, curate_spec_hash=curate_spec_hash,
                concept_ids_by_report=report_concept_ids,
            )
        except Exception as e:
            # KEEP broad: synthesis is the final best-effort L4 step; record the
            # error (surfaced via the errors list) rather than crashing L3.
            logger.warning("L4 synthesis failed: %s", e)
            l4_errors.append(str(e))

    # Mark L3 done for sources whose L2 is complete.
    with db.connect(paths.state_db) as conn:
        rows = conn.execute(
            f"SELECT id FROM sources WHERE l2_status = '{consts.STATUS_DONE}'"
        ).fetchall()
        l2_done_ids = [r["id"] for r in rows]
    
    # `layer_error` is ONE column shared by all four layers, so the two writes
    # below cannot each carry their own message — the second would clobber the
    # first. Compose a single layer-tagged message and write it once.
    #
    # The two error lists are kept apart because conflating them made both
    # statuses lie: a synthesis failure marked L3 `error` even though clustering
    # had succeeded, and the L4 message claimed "synthesis not attempted" in the
    # one case where it demonstrably had been attempted and had thrown.
    l3_error_msg = "; ".join(l3_errors) if l3_errors else None
    if l3_errors:
        l4_error_msg = "L3 prerequisite failed; synthesis not attempted"
    elif l4_errors:
        l4_error_msg = "; ".join(l4_errors)
    else:
        l4_error_msg = None
    error_msg = "; ".join(
        part
        for part in (
            f"l3: {l3_error_msg}" if l3_error_msg else "",
            f"l4: {l4_error_msg}" if l4_error_msg else "",
        )
        if part
    ) or None

    report_span_ids = {
        span_id
        for report in db.list_community_reports(paths.state_db)
        for span_id in (report.get("source_span_ids") or [])
    }
    report_source_ids: set[int] = set()
    if report_span_ids:
        with db.connect(paths.state_db) as conn:
            report_source_ids = _source_ids_for_span_ids(conn, report_span_ids)

    synthesis_source_ids = report_source_ids if synthesis_ids else set()

    for sid in l2_done_ids:
        l3_status = "error" if l3_errors else (
            "done" if sid in report_source_ids else "skipped"
        )
        # SYSTEM_BEHAVIOR §4.1: a layer that was attempted and failed is
        # `error`, never `skipped`. `skipped` means "this source contributed
        # nothing to the layer" — a different, non-failing outcome. Reporting a
        # failure as `skipped` is what let a broken L4 read as an ordinary no-op.
        source_l4_status = "error" if (l3_errors or l4_errors) else (
            "done" if sid in synthesis_source_ids else "skipped"
        )
        db.set_source_layer_status(
            paths.state_db, sid, "l3", l3_status, error=error_msg
        )
        # UNSET: the composed message written by the l3 call above already
        # covers both layers. Passing an error here would clobber it.
        db.set_source_layer_status(
            paths.state_db, sid, "l4", source_l4_status, error=db.UNSET
        )

    if l3_errors or l4_errors:
        raise RuntimeError(f"L3 global clustering encountered errors: {error_msg}")

    materializer.materialize_search_documents(paths.state_db)
    return concept_ids


def reemit_projections(paths: cfg.WikiPaths) -> dict[str, int]:
    """Re-emit the derived L2/L3 markdown corpus from the authoritative DB records.

    Realizes the compile-model invariant: the DB is the source of truth and the
    ``.curator/Collections`` markdown is a disposable projection. Existing ATM/CON
    projection files are deleted first, then re-emitted from current
    ``knowledge_units`` / ``community_reports`` rows — so the search projection always
    reflects the DB after any correction. Source truth (CTX/spans, 03_Notes,
    04_Resources) is never touched.

    Returns counts of emitted atom/concept pages.
    """
    with db.connect(paths.state_db) as conn:
        source_rows = conn.execute(
            "SELECT id, relpath, context_id FROM sources"
        ).fetchall()
    source_ids = [int(row["id"]) for row in source_rows]
    source_relpaths = {
        int(row["id"]): str(row["relpath"])
        for row in source_rows
    }
    for row in source_rows:
        _persist_source_projection_state(
            paths,
            source_id=int(row["id"]),
            context_id=str(row["context_id"] or ""),
        )

    live_reports = db.list_community_reports(paths.state_db)
    report_span_ids = {
        span_id
        for report in live_reports
        for span_id in (report.get("source_span_ids") or [])
    }
    synthesis_span_ids = {
        span_id
        for node in db.list_synthesis_nodes(paths.state_db)
        for report_id in (node.get("community_report_ids") or [])
        for report in live_reports
        if report.get("id") == report_id
        for span_id in (report.get("source_span_ids") or [])
    }
    report_source_ids: set[int] = set()
    synthesis_source_ids: set[int] = set()
    with db.connect(paths.state_db) as conn:
        serving_source_ids = {
            int(row["source_id"])
            for row in conn.execute(
                """
                SELECT DISTINCT ku.source_id
                FROM knowledge_units ku
                JOIN compiler_generations g ON g.id = ku.generation_id
                JOIN sources s ON s.id = ku.source_id AND s.id = g.source_id
                WHERE ku.retired_at IS NULL
                  AND ku.support_status = 'verified'
                  AND g.status = 'authoritative'
                """
            ).fetchall()
        }
        if report_span_ids:
            report_source_ids = _source_ids_for_span_ids(conn, report_span_ids)
        if synthesis_span_ids:
            synthesis_source_ids = _source_ids_for_span_ids(conn, synthesis_span_ids)
        has_synthesis = (
            conn.execute("SELECT 1 FROM synthesis_nodes LIMIT 1").fetchone()
            is not None
        )
        completed_rows = conn.execute(
            "SELECT id, l2_status, l3_status, l4_status, layer_error FROM sources "
            "WHERE l2_status IN ('done', 'skipped')"
        ).fetchall()
    for row in completed_rows:
        source_id = int(row["id"])
        has_layer_error = bool(row["layer_error"])
        desired_l2 = "done" if source_id in serving_source_ids else "skipped"
        if row["l2_status"] != desired_l2:
            db.set_source_layer_status(
                paths.state_db, source_id, "l2", desired_l2
            )
        if has_layer_error and row["l3_status"] == "error":
            desired_l3 = "error"
        elif desired_l2 == "skipped":
            desired_l3 = "skipped"
        else:
            desired_l3 = (
                "done"
                if desired_l2 == "done" and source_id in report_source_ids
                else "skipped"
            )
        if row["l3_status"] != desired_l3:
            db.set_source_layer_status(
                paths.state_db, source_id, "l3", desired_l3
            )
        if has_layer_error and row["l4_status"] == "error":
            desired_l4 = "error"
        elif desired_l2 == "skipped":
            desired_l4 = "skipped"
        else:
            desired_l4 = (
                "done"
                if desired_l2 == "done" and has_synthesis and source_id in synthesis_source_ids
                else "skipped"
            )
        if row["l4_status"] != desired_l4:
            db.set_source_layer_status(
                paths.state_db, source_id, "l4", desired_l4
            )

    paths.contexts.mkdir(parents=True, exist_ok=True)
    with db.connect(paths.state_db) as conn:
        current_context_ids = {
            str(row["context_id"])
            for row in conn.execute(
                "SELECT context_id FROM sources "
                "WHERE context_id IS NOT NULL AND context_id != ''"
            ).fetchall()
        }
    for stale in paths.contexts.glob(f"{consts.PREFIX_L1}-*.md"):
        if stale.stem not in current_context_ids:
            stale.unlink()
            db.delete_page_hash(
                paths.state_db,
                f"{paths.contexts.name}/{stale.name}",
            )

    paths.atoms.mkdir(parents=True, exist_ok=True)
    paths.concepts.mkdir(parents=True, exist_ok=True)
    for stale in paths.atoms.glob(f"{consts.PREFIX_L2}-*.md"):
        stale.unlink()
    for stale in paths.concepts.glob(f"{consts.PREFIX_L3}-*.md"):
        stale.unlink()

    n_atoms = 0
    for sid in source_ids:
        # Serving projection rebuild: only authoritative-generation units (§26.3).
        for unit in db.list_serving_units(paths.state_db, sid):
            atom_id = unit.get("atom_node_id") or projection.new_atom_id()
            page = projection.emit_atom_markdown(
                unit, atom_id, source_path=source_relpaths.get(sid, "")
            )
            (paths.atoms / f"{atom_id}.md").write_text(page, encoding="utf-8")
            n_atoms += 1

    n_concepts = 0
    report_concept_ids: dict[str, str] = {}
    for report in db.list_community_reports(paths.state_db):
        concept_id = _concept_id_for_report(report)
        report["atom_ids"] = _atom_ids_for_report(paths, report)
        page = projection.emit_concept_markdown(report, concept_id)
        (paths.concepts / f"{concept_id}.md").write_text(page, encoding="utf-8")
        report_concept_ids[report["id"]] = concept_id
        n_concepts += 1

    synthesis_nodes = db.list_synthesis_nodes(paths.state_db)
    with db.connect(paths.state_db) as conn:
        for node in synthesis_nodes:
            concept_ids = sorted(
                {
                    report_concept_ids[report_id]
                    for report_id in (node.get("community_report_ids") or [])
                    if report_id in report_concept_ids
                }
            )
            if list(node.get("concept_ids") or []) != concept_ids:
                conn.execute(
                    "UPDATE synthesis_nodes SET concept_ids = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(concept_ids), db._now_iso(), node["id"]),
                )

    n_synthesis = synthesis.reemit_synthesis(paths)
    materializer.materialize_search_documents(paths.state_db)
    from .. import sync as sync_state

    sync_state.update_all_page_hashes(
        paths,
        layer_dirs=(paths.atoms, paths.concepts, paths.synthesis),
    )

    return {
        "contexts": len(list(paths.contexts.glob(f"{consts.PREFIX_L1}-*.md"))),
        "atoms": n_atoms,
        "concepts": n_concepts,
        "synthesis": n_synthesis,
    }
