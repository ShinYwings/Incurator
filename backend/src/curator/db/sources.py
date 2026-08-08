"""Curator state DB — sources, layer status, DAG edges, source pages (DB-2 slice 2).

Carved verbatim from db/_entities.py; re-exported by db/__init__.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import constants as consts
from .schema import (
    _now_iso,
    connect,
)
from ._entities import (
    delete_source_spans,
    reconcile_source_change,
    retire_graph_relations_on_connection,
    strict_successor_timestamp,
)


def _json_id_set(raw: object) -> set[str]:
    try:
        value = json.loads(str(raw or "[]"))
    except (TypeError, ValueError):
        return set()
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value if isinstance(item, str) and item}


def _chunks(values: list[str], size: int = 500) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _database_path(conn: Any) -> Path:
    row = conn.execute("PRAGMA database_list").fetchone()
    value = str(row["file"] if hasattr(row, "keys") else row[2]) if row else ""
    return Path(value) if value else Path(".")


def _delete_scalar_rows_with_tombstones(
    conn: Any,
    table_name: str,
    id_column: str,
    record_ids: list[str],
    *,
    deleted_at: str,
) -> None:
    from ..db_sync import record_tombstone_on_connection

    for chunk in _chunks(sorted(set(record_ids))):
        placeholders = ",".join("?" for _ in chunk)
        existing = [
            str(row[0])
            for row in conn.execute(
                f"SELECT {id_column} FROM {table_name} "
                f"WHERE {id_column} IN ({placeholders})",
                tuple(chunk),
            ).fetchall()
        ]
        conn.execute(
            f"DELETE FROM {table_name} WHERE {id_column} IN ({placeholders})",
            tuple(chunk),
        )
        for record_id in existing:
            record_tombstone_on_connection(
                conn,
                table_name,
                record_id,
                deleted_at=deleted_at,
            )


def _delete_source_on_connection(
    conn: Any,
    source_id: int,
    *,
    observed_revision: str | None = None,
) -> str:
    """Delete one source and every non-cascading dependent in one transaction.

    Canonical audit rows are retired/discarded, shared graph state is
    recompiled from its remaining live support, source-owned canonical rows
    receive tombstones, and device-local derivatives are hard-deleted.
    Returns the closure revision so the caller can timestamp the source
    tombstone with the same strict-successor clock.
    """
    source = conn.execute(
        "SELECT sync_key, updated_at FROM sources WHERE id = ?",
        (source_id,),
    ).fetchone()
    if source is None:
        return strict_successor_timestamp(observed_revision)

    span_rows = conn.execute(
        "SELECT id, created_at FROM source_spans WHERE source_id = ?",
        (source_id,),
    ).fetchall()
    span_ids = [str(row["id"]) for row in span_rows]
    unit_rows = conn.execute(
        "SELECT id, atom_node_id, updated_at FROM knowledge_units "
        "WHERE source_id = ?",
        (source_id,),
    ).fetchall()
    unit_ids = [str(row["id"]) for row in unit_rows]
    atom_ids = [
        str(row["atom_node_id"])
        for row in unit_rows
        if row["atom_node_id"]
    ]
    generation_rows = conn.execute(
        "SELECT id, updated_at FROM compiler_generations WHERE source_id = ?",
        (source_id,),
    ).fetchall()
    authored_relation_rows = conn.execute(
        "SELECT r.id, r.updated_at FROM graph_relations r "
        "JOIN compiler_generations g ON g.id = r.generation_id "
        "WHERE r.edge_class = 'authored' AND g.source_id = ? "
        "AND r.lifecycle_status != 'retired'",
        (source_id,),
    ).fetchall()

    touched_entity_rows = []
    for row in conn.execute(
        "SELECT id, source_span_ids, knowledge_unit_ids, updated_at "
        "FROM graph_entities"
    ).fetchall():
        if (
            _json_id_set(row["source_span_ids"]).intersection(span_ids)
            or _json_id_set(row["knowledge_unit_ids"]).intersection(unit_ids)
        ):
            touched_entity_rows.append(row)
    touched_alias_rows = []
    for row in conn.execute(
        "SELECT id, source_span_ids, knowledge_unit_ids, updated_at "
        "FROM entity_aliases"
    ).fetchall():
        if (
            _json_id_set(row["source_span_ids"]).intersection(span_ids)
            or _json_id_set(row["knowledge_unit_ids"]).intersection(unit_ids)
        ):
            touched_alias_rows.append(row)
    touched_relation_rows = [
        row
        for row in conn.execute(
            "SELECT id, source_span_ids, updated_at FROM graph_relations"
        ).fetchall()
        if _json_id_set(row["source_span_ids"]).intersection(span_ids)
    ]

    support_rows = []
    for chunk in _chunks(unit_ids):
        placeholders = ",".join("?" for _ in chunk)
        support_rows.extend(
            conn.execute(
                "SELECT relation_id, updated_at FROM graph_relation_supports "
                f"WHERE knowledge_unit_id IN ({placeholders})",
                tuple(chunk),
            ).fetchall()
        )
    claim_support_rows = []
    for chunk in _chunks(unit_ids):
        placeholders = ",".join("?" for _ in chunk)
        claim_support_rows.extend(
            conn.execute(
                "SELECT updated_at FROM claim_supports "
                f"WHERE knowledge_unit_id IN ({placeholders})",
                tuple(chunk),
            ).fetchall()
        )
    synthesis_rows = conn.execute(
        "SELECT id, community_report_ids, source_span_ids, updated_at "
        "FROM synthesis_nodes"
    ).fetchall()
    affected_relation_ids = {
        *(str(row["id"]) for row in authored_relation_rows),
        *(str(row["id"]) for row in touched_relation_rows),
        *(str(row["relation_id"]) for row in support_rows),
    }
    affected_report_rows = [
        row
        for row in conn.execute(
            "SELECT id, relation_ids, source_span_ids FROM community_reports"
        ).fetchall()
        if (
            _json_id_set(row["relation_ids"]).intersection(affected_relation_ids)
            or _json_id_set(row["source_span_ids"]).intersection(span_ids)
        )
    ]
    memory_path_rows = [
        row
        for row in conn.execute(
            "SELECT id, source_span_ids, created_at FROM memory_paths"
        ).fetchall()
        if _json_id_set(row["source_span_ids"]).intersection(span_ids)
    ]
    dag_edge_rows_by_id = {
        str(row["id"]): row
        for row in conn.execute(
            "SELECT id, created_at FROM dag_edges WHERE source_id = ?",
            (source_id,),
        ).fetchall()
    }
    atom_rows = []
    for chunk in _chunks(atom_ids, size=400):
        placeholders = ",".join("?" for _ in chunk)
        for row in conn.execute(
            "SELECT id, created_at FROM dag_edges "
            f"WHERE from_id IN ({placeholders}) "
            f"OR to_id IN ({placeholders})",
            (*chunk, *chunk),
        ).fetchall():
            dag_edge_rows_by_id[str(row["id"])] = row
        atom_rows.extend(
            conn.execute(
                "SELECT id, last_updated FROM atoms "
                f"WHERE id IN ({placeholders})",
                tuple(chunk),
            ).fetchall()
        )
    dag_edge_rows = list(dag_edge_rows_by_id.values())
    source_page_rows = conn.execute(
        "SELECT at FROM source_pages WHERE source_id = ?",
        (source_id,),
    ).fetchall()
    pdf_page_rows = conn.execute(
        "SELECT extracted_at FROM source_pdf_pages WHERE source_id = ?",
        (source_id,),
    ).fetchall()
    span_dependency_rows = []
    for chunk in _chunks(span_ids):
        placeholders = ",".join("?" for _ in chunk)
        span_dependency_rows.extend(
            conn.execute(
                "SELECT created_at FROM artifact_dependencies "
                "WHERE depends_on_type = 'source_span' "
                f"AND depends_on_id IN ({placeholders})",
                tuple(chunk),
            ).fetchall()
        )

    revision = strict_successor_timestamp(
        observed_revision,
        source["updated_at"],
        *(row["created_at"] for row in span_rows),
        *(row["updated_at"] for row in unit_rows),
        *(row["updated_at"] for row in generation_rows),
        *(row["updated_at"] for row in touched_entity_rows),
        *(row["updated_at"] for row in touched_alias_rows),
        *(row["updated_at"] for row in touched_relation_rows),
        *(row["updated_at"] for row in authored_relation_rows),
        *(row["updated_at"] for row in support_rows),
        *(row["updated_at"] for row in claim_support_rows),
        *(row["created_at"] for row in memory_path_rows),
        *(row["created_at"] for row in dag_edge_rows),
        *(row["last_updated"] for row in atom_rows),
        *(row["at"] for row in source_page_rows),
        *(row["extracted_at"] for row in pdf_page_rows),
        *(row["created_at"] for row in span_dependency_rows),
    )

    for row in touched_entity_rows:
        kept_spans = sorted(_json_id_set(row["source_span_ids"]) - set(span_ids))
        kept_units = sorted(_json_id_set(row["knowledge_unit_ids"]) - set(unit_ids))
        conn.execute(
            "UPDATE graph_entities SET source_span_ids = ?, "
            "knowledge_unit_ids = ?, updated_at = ? WHERE id = ?",
            (json.dumps(kept_spans), json.dumps(kept_units), revision, row["id"]),
        )
    for row in touched_alias_rows:
        kept_spans = sorted(_json_id_set(row["source_span_ids"]) - set(span_ids))
        kept_units = sorted(_json_id_set(row["knowledge_unit_ids"]) - set(unit_ids))
        conn.execute(
            "UPDATE entity_aliases SET source_span_ids = ?, "
            "knowledge_unit_ids = ?, updated_at = ? WHERE id = ?",
            (json.dumps(kept_spans), json.dumps(kept_units), revision, row["id"]),
        )

    if generation_rows:
        conn.execute(
            "UPDATE compiler_generations SET status = 'discarded', "
            "discarded_at = ?, updated_at = ? WHERE source_id = ?",
            (revision, revision, source_id),
        )
    from ..db_sync import delete_rows_with_tombstones_on_connection

    for unit_id in unit_ids:
        conn.execute(
            "UPDATE knowledge_units SET retired_at = ?, updated_at = ? "
            "WHERE id = ? AND retired_at IS NULL",
            (revision, revision, unit_id),
        )
        delete_rows_with_tombstones_on_connection(
            conn,
            "claim_supports",
            "knowledge_unit_id = ?",
            (unit_id,),
            deleted_at=revision,
        )

    authored_relation_ids = [str(row["id"]) for row in authored_relation_rows]
    retire_graph_relations_on_connection(
        conn,
        authored_relation_ids,
        now=revision,
    )
    reconcile_source_change(
        _database_path(conn),
        source_id=source_id,
        removed_span_ids=span_ids,
        removed_unit_ids=unit_ids,
        conn=conn,
        now=revision,
    )

    removable_entity_ids: list[str] = []
    for row in touched_entity_rows:
        entity_id = str(row["id"])
        current = conn.execute(
            "SELECT source_span_ids, knowledge_unit_ids FROM graph_entities "
            "WHERE id = ?",
            (entity_id,),
        ).fetchone()
        if current is None:
            continue
        has_provenance = bool(
            _json_id_set(current["source_span_ids"])
            or _json_id_set(current["knowledge_unit_ids"])
        )
        has_graph_reference = conn.execute(
            "SELECT 1 FROM graph_relations "
            "WHERE source_entity_id = ? OR target_entity_id = ? LIMIT 1",
            (entity_id, entity_id),
        ).fetchone()
        has_resolution_reference = conn.execute(
            "SELECT 1 FROM entity_aliases WHERE entity_id = ? LIMIT 1",
            (entity_id,),
        ).fetchone() or conn.execute(
            "SELECT 1 FROM entity_merge_proposals "
            "WHERE source_entity_id = ? OR target_entity_id = ? LIMIT 1",
            (entity_id, entity_id),
        ).fetchone() or conn.execute(
            "SELECT 1 FROM entity_resolution_lineage "
            "WHERE origin_entity_id = ? OR canonical_entity_id = ? LIMIT 1",
            (entity_id, entity_id),
        ).fetchone()
        if not has_provenance and not has_graph_reference and not has_resolution_reference:
            removable_entity_ids.append(entity_id)
    _delete_scalar_rows_with_tombstones(
        conn,
        "graph_entities",
        "id",
        removable_entity_ids,
        deleted_at=revision,
    )

    live_report_ids = {
        str(row[0])
        for row in conn.execute(
            "SELECT id FROM community_reports WHERE retired_at IS NULL"
        ).fetchall()
    }
    invalid_synthesis_rows = [
        row
        for row in synthesis_rows
        if (
            _json_id_set(row["source_span_ids"]).intersection(span_ids)
            or not _json_id_set(row["community_report_ids"]).issubset(
                live_report_ids
            )
        )
    ]
    invalid_synthesis_ids = [
        str(row["id"]) for row in invalid_synthesis_rows
    ]
    synthesis_dependency_rows = []
    for chunk in _chunks(invalid_synthesis_ids):
        placeholders = ",".join("?" for _ in chunk)
        synthesis_dependency_rows.extend(
            conn.execute(
                "SELECT created_at FROM artifact_dependencies "
                "WHERE artifact_type = 'synthesis_node' "
                f"AND artifact_id IN ({placeholders})",
                tuple(chunk),
            ).fetchall()
        )
    if invalid_synthesis_rows:
        revision = strict_successor_timestamp(
            revision,
            *(row["updated_at"] for row in invalid_synthesis_rows),
            *(row["created_at"] for row in synthesis_dependency_rows),
        )

    affected_search_record_ids = {
        *span_ids,
        *unit_ids,
        *(str(row["id"]) for row in touched_entity_rows),
        *affected_relation_ids,
        *(str(row["id"]) for row in affected_report_rows),
        *invalid_synthesis_ids,
    }
    affected_search_doc_ids = {
        str(row["doc_id"])
        for row in conn.execute(
            "SELECT doc_id FROM search_documents WHERE source_id = ?",
            (source_id,),
        ).fetchall()
    }
    for chunk in _chunks(sorted(affected_search_record_ids)):
        placeholders = ",".join("?" for _ in chunk)
        affected_search_doc_ids.update(
            str(row["doc_id"])
            for row in conn.execute(
                "SELECT doc_id FROM search_documents "
                f"WHERE record_id IN ({placeholders})",
                tuple(chunk),
            ).fetchall()
        )
    for chunk in _chunks(sorted(affected_search_doc_ids)):
        placeholders = ",".join("?" for _ in chunk)
        for table in ("search_documents_fts", "search_documents_fts_tri"):
            conn.execute(
                f"DELETE FROM {table} WHERE doc_id IN ({placeholders})",
                tuple(chunk),
            )
        conn.execute(
            f"DELETE FROM search_documents WHERE doc_id IN ({placeholders})",
            tuple(chunk),
        )
    for synthesis_id in invalid_synthesis_ids:
        delete_rows_with_tombstones_on_connection(
            conn,
            "artifact_dependencies",
            "artifact_id = ? AND artifact_type = 'synthesis_node'",
            (synthesis_id,),
            deleted_at=revision,
        )
    _delete_scalar_rows_with_tombstones(
        conn,
        "synthesis_nodes",
        "id",
        invalid_synthesis_ids,
        deleted_at=revision,
    )

    affected_memory_paths = [str(row["id"]) for row in memory_path_rows]
    _delete_scalar_rows_with_tombstones(
        conn,
        "memory_paths",
        "id",
        affected_memory_paths,
        deleted_at=revision,
    )

    affected_dag_edges = [str(row["id"]) for row in dag_edge_rows]
    _delete_scalar_rows_with_tombstones(
        conn,
        "dag_edges",
        "id",
        affected_dag_edges,
        deleted_at=revision,
    )
    _delete_scalar_rows_with_tombstones(
        conn,
        "atoms",
        "id",
        atom_ids,
        deleted_at=revision,
    )

    delete_source_spans(
        _database_path(conn),
        span_ids,
        conn=conn,
        now=revision,
    )
    conn.execute(
        "DELETE FROM job_events WHERE job_id IN "
        "(SELECT id FROM ingest_jobs WHERE source_id = ?)",
        (source_id,),
    )
    conn.execute("DELETE FROM ingest_jobs WHERE source_id = ?", (source_id,))
    conn.execute("DELETE FROM ingest_runs WHERE source_id = ?", (source_id,))
    delete_rows_with_tombstones_on_connection(
        conn,
        "source_pages",
        "source_id = ?",
        (source_id,),
        deleted_at=revision,
    )
    delete_rows_with_tombstones_on_connection(
        conn,
        "source_pdf_pages",
        "source_id = ?",
        (source_id,),
        deleted_at=revision,
    )
    conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    return revision


class _UnsetType:
    """Sentinel for "do not touch ``layer_error``"."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "UNSET"


UNSET = _UnsetType()
"""Passed as ``error=`` to leave ``sources.layer_error`` exactly as it is.

``sources.layer_error`` is overloaded three ways: human error text, the
post-publish projection control-flow marker that ``pipeline/compile.py:296-307``
*reads* to decide whether to recover instead of recompile, and sync annotations
(``sync_logical_gap:…``). A status write that also clears the column therefore
destroys pipeline state, not just a message.

``error=None`` still means "clear it", because for success transitions that is
the correct and intended behaviour. Preservation is opt-in and every site that
opts in says what it is protecting.
"""


def set_source_layer_status(
    db_path: Path,
    source_id: int,
    layer: str,
    status: str,
    *,
    error: str | None | _UnsetType = None,
) -> None:
    """Update a source's per-layer pipeline status.

    layer must be one of: l1, l2, l3, l4.
    status should be: pending, running, done, error, or skipped.

    ``error`` is written to ``layer_error``: a string sets it, ``None`` clears
    it, and :data:`UNSET` leaves it untouched.
    """
    if layer not in {"l1", "l2", "l3", "l4"}:
        raise ValueError(f"Invalid layer status key: {layer}")
    column = f"{layer}_status"
    with connect(db_path) as conn:
        if isinstance(error, _UnsetType):
            conn.execute(
                f"UPDATE sources SET {column} = ? WHERE id = ?",
                (status, source_id),
            )
            return
        conn.execute(
            f"UPDATE sources SET {column} = ?, layer_error = ? WHERE id = ?",
            (status, error, source_id),
        )


def relocate_source(db_path: Path, source_id: int, new_relpath: str) -> dict[str, int]:
    """Record that a registered source moved to a new vault-relative path.

    The file's CONTENT did not change, only its location, so this preserves the
    content hash, every layer status, the context id, the logical source id, and
    the entire derived closure. Nothing is recompiled and no knowledge is lost.

    The path is denormalized into three places and all three move together:
    ``sources.relpath``, the copy on every ``source_spans`` row for the source,
    and ``search_documents.projection_path`` for that source's rows.

    ``sync_key`` is deliberately NOT rewritten. It is the cross-device sync
    identity, minted once by the ``sources_set_sync_key`` trigger (which fires
    only on INSERT and only when the column is empty) and thereafter matched by
    equality alone — nothing anywhere reverses it back into a path. Changing it
    on a move would make a peer replica see a delete plus an insert instead of
    one moved row, manufacturing exactly the divergence the sync-convergence
    work exists to prevent. Location is not identity.

    Returns the per-table row counts actually updated, so callers can report a
    truthful outcome instead of assuming.
    """
    new_relpath = new_relpath.replace("\\", "/").lstrip("/")
    if not new_relpath:
        raise ValueError("new_relpath is required")
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT relpath FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"source {source_id} not found")
        old_relpath = str(row["relpath"])
        if old_relpath == new_relpath:
            return {"sources": 0, "source_spans": 0, "search_documents": 0}
        counts = {
            "sources": conn.execute(
                "UPDATE sources SET relpath = ? WHERE id = ?",
                (new_relpath, source_id),
            ).rowcount,
            "source_spans": conn.execute(
                "UPDATE source_spans SET relpath = ? WHERE source_id = ?",
                (new_relpath, source_id),
            ).rowcount,
            "search_documents": conn.execute(
                "UPDATE search_documents SET projection_path = ? "
                "WHERE source_id = ? AND projection_path = ?",
                (new_relpath, source_id, old_relpath),
            ).rowcount,
        }
    return {k: int(v or 0) for k, v in counts.items()}


FILE_MISSING_REASON = "file_missing"


def set_source_file_missing(db_path: Path, source_id: int, missing: bool) -> None:
    """Flag or unflag a registered source whose file is gone from the vault.

    Deleting a note MARKS the source and preserves its knowledge: L1-L4 records,
    the graph, and every layer status are left exactly as they are. An accidental
    delete in Obsidian, or a file moved out of the vault and back, must not
    silently destroy extracted knowledge. `wiki lint` surfaces the mark and
    `wiki source rm` remains the explicit, user-driven way to retire the
    dependency closure.

    Uses ``sources.error_reason``, the existing free-text source-level reason
    column (``empty_file`` is the established precedent), so there is no schema
    change and no migration.
    """
    with connect(db_path) as conn:
        if missing:
            conn.execute(
                "UPDATE sources SET error_reason = ? WHERE id = ?",
                (FILE_MISSING_REASON, source_id),
            )
        else:
            conn.execute(
                "UPDATE sources SET error_reason = NULL WHERE id = ? "
                "AND error_reason = ?",
                (source_id, FILE_MISSING_REASON),
            )


def set_sources_layer_error(
    db_path: Path, source_ids: list[int], error: str | None
) -> None:
    """Write ``layer_error`` without touching any ``*_status`` column.

    ``wiki sync`` needs to clear stale errors after verifying the graph without
    also advancing a layer status (SYSTEM_BEHAVIOR §26.3 — status is computed by
    the compiler, never inferred by another command).

    Chunked like every other bulk id predicate in this module: the caller passes
    an unfiltered ``SELECT id FROM sources`` result, so the ``IN`` list is
    unbounded and would trip SQLite's 999-variable limit on a large vault.
    """
    if not source_ids:
        return
    with connect(db_path) as conn:
        for chunk in _chunks([str(sid) for sid in source_ids]):
            conn.execute(
                "UPDATE sources SET layer_error = ? "
                f"WHERE id IN ({','.join('?' * len(chunk))})",
                (error, *chunk),
            )


def set_sources_layer_status(
    db_path: Path,
    source_ids: list[int],
    layer: str,
    status: str,
    *,
    error: str | None | _UnsetType = None,
) -> None:
    """Bulk update per-layer status for source rows.

    ``error`` behaves as in :func:`set_source_layer_status`.
    """
    if not source_ids:
        return
    if layer not in {"l1", "l2", "l3", "l4"}:
        raise ValueError(f"Invalid layer status key: {layer}")
    column = f"{layer}_status"
    keep_error = isinstance(error, _UnsetType)
    with connect(db_path) as conn:
        for chunk in _chunks([str(sid) for sid in source_ids]):
            placeholders = ",".join("?" * len(chunk))
            if keep_error:
                conn.execute(
                    f"UPDATE sources SET {column} = ? WHERE id IN ({placeholders})",
                    (status, *chunk),
                )
            else:
                conn.execute(
                    f"UPDATE sources SET {column} = ?, layer_error = ? "
                    f"WHERE id IN ({placeholders})",
                    (status, error, *chunk),
                )
def insert_dag_edge(
    db_path: str | Path,
    from_id: str,
    to_id: str,
    edge_type: str,
    source_id: int | str | None,
) -> None:
    """Record a directed edge in the DAG. Idempotent (INSERT OR IGNORE)."""
    with connect(Path(db_path)) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO dag_edges "
            "(id, from_id, to_id, edge_type, source_id, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (f"{from_id}:{to_id}", from_id, to_id, edge_type, source_id, _now_iso()),
        )


def get_dag_edges_for_source(db_path: str | Path, source_id: str) -> list[dict]:
    """Return all dag_edges recorded for a given source_id."""
    with connect(Path(db_path)) as conn:
        rows = conn.execute(
            "SELECT from_id, to_id, edge_type FROM dag_edges WHERE source_id=?",
            (source_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_dag_edges_for_atoms(db_path: str | Path, atom_ids: list[str]) -> list[dict]:
    """Return dag_edges where from_id is one of the given ATM IDs (ATM→CON, source_id=NULL)."""
    if not atom_ids:
        return []
    placeholders = ",".join("?" for _ in atom_ids)
    with connect(Path(db_path)) as conn:
        rows = conn.execute(
            f"SELECT from_id, to_id, edge_type FROM dag_edges WHERE from_id IN ({placeholders})",
            tuple(atom_ids),
        ).fetchall()
        return [dict(r) for r in rows]


def vision_cache_get(db_path: Path, image_hash: str, model: str) -> str | None:
    """Return a cached VLM transcription for (rendered-image hash, model), or None.

    Keyed by model so a Dashboard model switch never serves a prior model's L1 (R12).
    """
    if not db_path.exists():
        return None
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT latex FROM vision_page_cache WHERE image_hash = ? AND model = ?",
            (image_hash, model),
        ).fetchone()
        return row["latex"] if row else None


def vision_cache_put(db_path: Path, image_hash: str, model: str, latex: str) -> None:
    """Upsert a VLM page transcription keyed by (image hash, model)."""
    now = _now_iso()
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO vision_page_cache (image_hash, model, latex, created_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(image_hash, model) DO UPDATE SET "
            "latex = excluded.latex, created_at = excluded.created_at",
            (image_hash, model, latex, now),
        )


def get_page_hashes(db_path: Path) -> dict[str, str]:
    """Load all known page hashes: {wiki_path: content_hash}."""
    if not db_path.exists():
        return {}
    with connect(db_path) as conn:
        rows = conn.execute("SELECT wiki_path, content_hash FROM page_hashes").fetchall()
        return {row["wiki_path"]: row["content_hash"] for row in rows}


def update_page_hash(db_path: Path, wiki_path: str, content_hash: str) -> None:
    """Upsert the hash for a specific wiki page."""
    now = _now_iso()
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO page_hashes (wiki_path, content_hash, last_synced) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(wiki_path) DO UPDATE SET "
            "content_hash = excluded.content_hash, "
            "last_synced = excluded.last_synced",
            (wiki_path, content_hash, now),
        )


def delete_page_hash(db_path: Path, wiki_path: str) -> None:
    """Remove a page hash entry (e.g. if file deleted)."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM page_hashes WHERE wiki_path = ?", (wiki_path,))


def replace_source_pdf_pages(
    db_path: Path,
    source_id: int,
    relpath: str,
    pages: list[dict],
) -> None:
    """Replace page-level PDF provenance rows for one source."""
    from ..db_sync import (
        clear_row_tombstone_on_connection,
        delete_rows_with_tombstones_on_connection,
    )

    now = _now_iso()
    with connect(db_path) as conn:
        delete_rows_with_tombstones_on_connection(
            conn,
            "source_pdf_pages",
            "source_id = ?",
            (source_id,),
        )
        for page in pages:
            page_number = int(page.get("page") or page.get("page_number") or 0)
            if page_number <= 0:
                continue
            metadata = {
                k: v
                for k, v in page.items()
                if k
                not in {"page", "page_number", "content_hash", "char_count", "word_count", "text"}
            }
            conn.execute(
                """
                INSERT INTO source_pdf_pages
                    (source_id, relpath, page_number, content_hash, char_count,
                     word_count, metadata, extracted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    relpath,
                    page_number,
                    str(page.get("content_hash") or ""),
                    int(page.get("char_count") or 0),
                    int(page.get("word_count") or 0),
                    json_dumps(metadata),
                    now,
                ),
            )
            clear_row_tombstone_on_connection(
                conn,
                "source_pdf_pages",
                {
                    "source_id": source_id,
                    "page_number": page_number,
                },
            )


def list_source_pdf_pages(db_path: Path, source_id: int) -> list[dict]:
    """Return PDF page metadata rows for one source."""
    if not db_path.exists():
        return []
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT source_id, relpath, page_number, content_hash, char_count,
                   word_count, metadata, extracted_at
            FROM source_pdf_pages
            WHERE source_id = ?
            ORDER BY page_number ASC
            """,
            (source_id,),
        ).fetchall()
        out: list[dict] = []
        for row in rows:
            item = dict(row)
            metadata_raw = item.get("metadata")
            if metadata_raw:
                try:
                    item["metadata"] = json.loads(metadata_raw)
                except Exception:
                    item["metadata"] = {}
            else:
                item["metadata"] = {}
            out.append(item)
        return out


def record_source_page(
    db_path: Path,
    source_id: int,
    wiki_path: str,
    operation: str,
) -> None:
    """Record that a wiki page was created or updated from a source."""
    from ..db_sync import clear_row_tombstone_on_connection

    now = _now_iso()
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO source_pages (source_id, wiki_path, operation, at)
            VALUES (?, ?, ?, ?)
            """,
            (source_id, wiki_path, operation, now),
        )
        clear_row_tombstone_on_connection(
            conn,
            "source_pages",
            {
                "source_id": source_id,
                "wiki_path": wiki_path,
                "at": now,
            },
        )


def list_source_pages(db_path: Path, source_id: int) -> list[dict]:
    """Return wiki pages recorded as generated from one source."""
    if not db_path.exists():
        return []
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT source_id, wiki_path, operation, at
            FROM source_pages
            WHERE source_id = ?
            ORDER BY at DESC
            """,
            (source_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def json_dumps(value) -> str:

    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def source_path_to_relpath(root: Path, source_path: str) -> str:
    """Convert a source path (absolute or relative) to a vault-relative relpath.

    Handles expanduser and resolve for absolute paths. Falls back to the raw
    string when the path is not inside the vault root.
    """
    if not source_path:
        return ""
    path = Path(source_path).expanduser()
    if path.is_absolute():
        try:
            return str(path.resolve().relative_to(root.resolve()))
        except ValueError:
            return str(source_path)
    return str(source_path)


def get_source_row(
    db_path: Path,
    root: Path,
    *,
    source_id: int | None = None,
    relpath: str = "",
    source_path: str = "",
    content_hash: str = "",
) -> dict[str, Any] | None:
    """Unified source lookup by id, relpath, portable refs,
    logical_source_id, or content_hash (G08-1).

    When ``source_path`` is given and ``relpath`` is empty, the path is
    resolved against ``root`` to produce a relpath first.
    ``content_hash`` is tried last when no other key matches.
    """
    lookup = relpath or source_path
    relpath = relpath or source_path_to_relpath(root, source_path)
    resolved_lookup: str | None = None
    if lookup:
        path = Path(lookup).expanduser()
        if path.is_absolute():
            resolved_lookup = str(path.resolve(strict=False))
    with connect(db_path) as conn:
        if source_id is not None:
            row = conn.execute(
                "SELECT * FROM sources WHERE id = ?", (source_id,)
            ).fetchone()
        elif relpath:
            row = conn.execute(
                """
                SELECT * FROM sources
                WHERE relpath = ?
                   OR external_ref = ?
                   OR external_ref = ?
                   OR import_origin_ref = ?
                   OR import_origin_ref = ?
                   OR logical_source_id = ?
                """,
                (relpath, relpath, resolved_lookup, relpath, resolved_lookup, relpath),
            ).fetchone()
            # Fall back to content_hash when relpath is provided but unmatched.
            if row is None and content_hash:
                row = conn.execute(
                    "SELECT * FROM sources WHERE content_hash = ? LIMIT 1",
                    (content_hash,),
                ).fetchone()
        elif content_hash:
            row = conn.execute(
                "SELECT * FROM sources WHERE content_hash = ? LIMIT 1",
                (content_hash,),
            ).fetchone()
        else:
            row = None
    return dict(row) if row else None


def get_pending_count(db_path: Path) -> int:
    """Count sources with status 'pending' or 'force_pending'."""
    if not db_path.exists():
        return 0
    with connect(db_path) as conn:
        return conn.execute(
            f"SELECT COUNT(*) FROM sources WHERE status IN ('{consts.STATUS_PENDING}', 'force_pending')"
        ).fetchone()[0]
