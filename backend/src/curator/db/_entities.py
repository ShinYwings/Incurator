"""Curator state DB — entity repository queries.

Split from the original db.py god-file (DB-2). Schema DDL, migrations, connect(),
and shared constants live in ``db.schema``; this module holds the per-entity query
functions and the ingest job queue, re-exported by ``db/__init__.py``.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable, Mapping

from .schema import (
    _QUARANTINE_REEVAL_TRIGGERS,
    _RELATION_CORROBORATION_THRESHOLD,
    _chunked,
    _maybe_conn,
    _now_iso,
    connect,
)

# =====================================================================
# v0.3.1 curation-native accessors (SCHEMA.md §11)
# =====================================================================


def _new_id(prefix: str) -> str:
    """Generate a typed `<PREFIX>-<UUID8>` id."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _loads_list(raw: Any) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _loads_obj(raw: Any) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}


def _decode_span_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["metadata"] = _loads_obj(data.get("metadata"))
    return data


# --- source_spans ----------------------------------------------------


def upsert_source_span(
    db_path: Path,
    *,
    source_id: int,
    relpath: str,
    span_type: str,
    content_hash: str,
    page_number: int | None = None,
    section_title: str | None = None,
    toc_id: str | None = None,
    start_char: int | None = None,
    end_char: int | None = None,
    text_preview: str = "",
    metadata: dict | None = None,
) -> str:
    """Insert a source span, or return the existing id for the same
    (source_id, content_hash). Span ids are stable across re-parses when the
    exact span text is unchanged."""
    with connect(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM source_spans WHERE source_id = ? AND content_hash = ?",
            (source_id, content_hash),
        ).fetchone()
        if existing:
            return str(existing["id"])
        span_id = _new_id("SPAN")
        conn.execute(
            """
            INSERT INTO source_spans
                (id, source_id, relpath, span_type, page_number, section_title,
                 toc_id, start_char, end_char, content_hash, text_preview,
                 metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                span_id,
                source_id,
                relpath,
                span_type,
                page_number,
                section_title,
                toc_id,
                start_char,
                end_char,
                content_hash,
                text_preview,
                json.dumps(metadata) if metadata else None,
                _now_iso(),
            ),
        )
        return span_id


def list_source_spans(db_path: Path, source_id: int) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM source_spans WHERE source_id = ? ORDER BY "
            "page_number IS NULL, page_number, start_char IS NULL, start_char",
            (source_id,),
        ).fetchall()
        return [_decode_span_row(row) for row in rows]


def get_source_spans_by_ids(db_path: Path, span_ids: list[str]) -> list[dict]:
    if not span_ids:
        return []
    with connect(db_path) as conn:
        placeholders = ",".join("?" for _ in span_ids)
        rows = conn.execute(
            f"SELECT * FROM source_spans WHERE id IN ({placeholders})",
            tuple(span_ids),
        ).fetchall()
        return [_decode_span_row(row) for row in rows]


def sources_for_spans(db_path: Path, span_ids: list[str]) -> list[dict]:
    """Distinct source documents backing the given spans, in first-seen span order.

    Forward provenance trace: ``span_id -> source_spans.source_id ->
    sources.relpath`` (the authoritative source path). High-level abstraction
    records (graph entities/relations, community reports, synthesis nodes)
    aggregate spans from one or MORE sources; this returns every distinct source,
    not just the first, so a multi-source record traces back to all of its
    origins. Unknown span ids and spans whose source row is gone are skipped.
    Returns dicts ``{"source_id": int, "relpath": str}``.
    """
    if not span_ids:
        return []
    spans = {str(span["id"]): span for span in get_source_spans_by_ids(db_path, span_ids)}
    # Collect unique source_ids in first-seen span order, then resolve all their
    # relpaths in a single batched IN query (avoids an N+1 per-source lookup).
    ordered_source_ids: list[int] = []
    seen: set[int] = set()
    for span_id in span_ids:
        span = spans.get(str(span_id))
        if span is None or span.get("source_id") is None:
            continue
        source_id = int(span["source_id"])
        if source_id not in seen:
            seen.add(source_id)
            ordered_source_ids.append(source_id)
    if not ordered_source_ids:
        return []
    placeholders = ",".join("?" for _ in ordered_source_ids)
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT id, relpath FROM sources WHERE id IN ({placeholders})",
            tuple(ordered_source_ids),
        ).fetchall()
    relpath_by_id = {int(row["id"]): str(row["relpath"]) for row in rows}
    return [
        {"source_id": source_id, "relpath": relpath_by_id[source_id]}
        for source_id in ordered_source_ids
        if source_id in relpath_by_id
    ]


def delete_source_spans(
    db_path: Path, span_ids: list[str], *, conn: sqlite3.Connection | None = None
) -> int:
    """Remove stale source spans and their derived support/dependency rows
    (SYSTEM_BEHAVIOR §26.4 / F7 reconciliation). The span rows of an edited
    source are removed rather than left lingering beside their replacements;
    dependent `claim_supports` and `artifact_dependencies` rows are removed in
    the same transaction so the compiler audit finds no dangling references —
    including stale span ids scrubbed from graph entity/relation
    `source_span_ids` arrays (those are L1-anchored, so a removed span must not
    linger there). Returns the number of span rows deleted. Source truth files
    are untouched. Pass ``conn`` to run inside a caller's transaction (atomic
    publish)."""
    if not span_ids:
        return 0
    deleted = 0
    deleted_set = set(span_ids)
    with _maybe_conn(db_path, conn) as c:
        for chunk in _chunked(span_ids):
            placeholders = ",".join("?" for _ in chunk)
            params = tuple(chunk)
            c.execute(
                f"DELETE FROM claim_supports WHERE source_span_id IN ({placeholders})",
                params,
            )
            c.execute(
                "DELETE FROM artifact_dependencies "
                f"WHERE depends_on_type = 'source_span' AND depends_on_id IN ({placeholders})",
                params,
            )
            cur = c.execute(
                f"DELETE FROM source_spans WHERE id IN ({placeholders})", params
            )
            deleted += cur.rowcount
        # Scrub the deleted span ids out of graph entity/relation source_span_ids
        # JSON arrays so no graph record carries a dangling span reference.
        for table in ("graph_entities", "graph_relations"):
            for row in c.execute(
                f"SELECT id, source_span_ids FROM {table}"
            ).fetchall():
                spans = _loads_list(row["source_span_ids"])
                kept = [s for s in spans if s not in deleted_set]
                if len(kept) != len(spans):
                    c.execute(
                        f"UPDATE {table} SET source_span_ids = ? WHERE id = ?",
                        (json.dumps(kept), row["id"]),
                    )
    return deleted


# --- knowledge_units -------------------------------------------------


def upsert_knowledge_unit(
    db_path: Path,
    *,
    unit_type: str,
    canonical_name: str,
    statement: str,
    source_span_ids: list[str],
    source_id: int | None = None,
    confidence: float = 0.0,
    truth_status: str = "source_supported",
    atom_node_id: str | None = None,
    prompt_run_id: str | None = None,
    unit_id: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Insert a typed knowledge unit, or update it in place when `unit_id` is
    given and already exists."""
    now = _now_iso()
    spans_json = json.dumps(source_span_ids)
    with _maybe_conn(db_path, conn) as c:
        if unit_id:
            existing = c.execute(
                "SELECT id FROM knowledge_units WHERE id = ?", (unit_id,)
            ).fetchone()
            if existing:
                c.execute(
                    """
                    UPDATE knowledge_units
                       SET unit_type = ?, canonical_name = ?, statement = ?,
                           source_span_ids = ?, source_id = ?, confidence = ?,
                           truth_status = ?, atom_node_id = ?, prompt_run_id = ?,
                           updated_at = ?
                     WHERE id = ?
                    """,
                    (
                        unit_type, canonical_name, statement, spans_json,
                        source_id, confidence, truth_status, atom_node_id,
                        prompt_run_id, now, unit_id,
                    ),
                )
                return unit_id
        new_unit_id = unit_id or _new_id("KNU")
        c.execute(
            """
            INSERT INTO knowledge_units
                (id, unit_type, canonical_name, statement, source_span_ids,
                 source_id, confidence, truth_status, atom_node_id,
                 prompt_run_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_unit_id, unit_type, canonical_name, statement, spans_json,
                source_id, confidence, truth_status, atom_node_id,
                prompt_run_id, now, now,
            ),
        )
        return new_unit_id


def _decode_unit_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
    return data


def insert_l2_checkpoint(db_path: Path, source_id: int, batch_hash: str) -> None:
    """Record that a batch (identified by its content hash) was successfully persisted."""
    with connect(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO l2_checkpoints (source_id, batch_hash) VALUES (?, ?)",
            (source_id, batch_hash),
        )


def get_l2_checkpoint_hashes(db_path: Path, source_id: int) -> set[str]:
    """Return the set of batch hashes already checkpointed for this source."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT batch_hash FROM l2_checkpoints WHERE source_id = ?", (source_id,)
        ).fetchall()
    return {row["batch_hash"] for row in rows}


def clear_l2_checkpoints(db_path: Path, source_id: int) -> None:
    """Remove all checkpoint records for a source (called when starting fresh)."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM l2_checkpoints WHERE source_id = ?", (source_id,))


def has_l2_checkpoints(db_path: Path, source_id: int) -> bool:
    """Return True if any checkpoint batches are recorded for this source."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM l2_checkpoints WHERE source_id = ? LIMIT 1", (source_id,)
        ).fetchone()
    return row is not None


def list_staged_unit_ids_for_source(db_path: Path, source_id: int) -> list[str]:
    """Return IDs of all staged (unpublished, non-retired) units for this source."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id FROM knowledge_units "
            "WHERE source_id = ? AND generation_id IS NULL AND retired_at IS NULL "
            "ORDER BY created_at",
            (source_id,),
        ).fetchall()
    return [row["id"] for row in rows]


def list_knowledge_units_for_source(db_path: Path, source_id: int) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM knowledge_units WHERE source_id = ? ORDER BY created_at",
            (source_id,),
        ).fetchall()
        return [_decode_unit_row(row) for row in rows]


# --- claim_supports / compiler_generations (Plan B, v0.8.0, SCHEMA §20) ------

SUPPORT_ROLES = frozenset({"primary", "contextual", "formula"})
SUPPORT_STATUSES = frozenset({"unchecked", "verified", "failed", "stale"})
FORMULA_STATUSES = frozenset({
    "not_applicable", "preserved_in_text", "linked_evidence",
    "omitted_incidental", "missing", "uncertain",
})
GENERATION_STATUSES = frozenset({"staged", "authoritative", "discarded"})


def upsert_claim_support(
    db_path: Path,
    *,
    knowledge_unit_id: str,
    source_span_id: str,
    support_role: str,
    support_status: str,
    evidence_hash: str,
    support_reason: str = "",
    validator_trace_id: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Insert or update one minimal-support record (SCHEMA §20.2). Storage only:
    callers (P4 validation) decide roles/statuses; a valid span id is never
    proof of support on its own. Pass ``conn`` to run inside a caller's
    transaction (atomic re-publish)."""
    if support_role not in SUPPORT_ROLES:
        raise ValueError(f"invalid support_role: {support_role!r}")
    if support_status not in SUPPORT_STATUSES:
        raise ValueError(f"invalid support_status: {support_status!r}")
    now = _now_iso()
    with _maybe_conn(db_path, conn) as conn:
        conn.execute(
            """
            INSERT INTO claim_supports
                (knowledge_unit_id, source_span_id, support_role, support_status,
                 support_reason, evidence_hash, validator_trace_id,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (knowledge_unit_id, source_span_id, support_role)
            DO UPDATE SET support_status = excluded.support_status,
                          support_reason = excluded.support_reason,
                          evidence_hash  = excluded.evidence_hash,
                          validator_trace_id = excluded.validator_trace_id,
                          updated_at = excluded.updated_at
            """,
            (knowledge_unit_id, source_span_id, support_role, support_status,
             support_reason, evidence_hash, validator_trace_id, now, now),
        )


def list_claim_supports(db_path: Path, knowledge_unit_id: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM claim_supports WHERE knowledge_unit_id = ? "
            "ORDER BY support_role, source_span_id",
            (knowledge_unit_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def set_unit_support_status(
    db_path: Path, unit_id: str, status: str, reason: str = "",
    *, conn: sqlite3.Connection | None = None,
) -> None:
    """Update a knowledge unit's claim-level support verdict (SCHEMA §20.1).
    Pass ``conn`` to run inside a caller's transaction (atomic re-publish)."""
    if status not in SUPPORT_STATUSES:
        raise ValueError(f"invalid support_status: {status!r}")
    if status in {"failed", "stale"} and not reason:
        raise ValueError(f"support_status={status!r} requires a non-empty reason")
    with _maybe_conn(db_path, conn) as conn:
        conn.execute(
            "UPDATE knowledge_units SET support_status = ?, support_reason = ?, "
            "updated_at = ? WHERE id = ?",
            (status, reason, _now_iso(), unit_id),
        )


def set_unit_formula_status(
    db_path: Path, unit_id: str, status: str, reason: str = "",
    *, conn: sqlite3.Connection | None = None,
) -> None:
    """Update a knowledge unit's formula lifecycle status (SCHEMA §20.1). Pass
    ``conn`` to run inside a caller's transaction (atomic re-publish)."""
    if status not in FORMULA_STATUSES:
        raise ValueError(f"invalid formula_status: {status!r}")
    with _maybe_conn(db_path, conn) as conn:
        if reason:
            conn.execute(
                "UPDATE knowledge_units SET formula_status = ?, support_reason = ?, "
                "updated_at = ? WHERE id = ?",
                (status, reason, _now_iso(), unit_id),
            )
        else:
            conn.execute(
                "UPDATE knowledge_units SET formula_status = ?, updated_at = ? "
                "WHERE id = ?",
                (status, _now_iso(), unit_id),
            )


def retire_knowledge_unit(
    db_path: Path, unit_id: str, *, conn: sqlite3.Connection | None = None
) -> None:
    """Tombstone a unit retired by source edit/delete/split reconciliation
    (SCHEMA §20.1). Retired rows are never deleted by the compiler and never
    feed downstream stages. Its `claim_supports` rows are removed so the
    compiler audit finds no support row citing a retired unit (§20.5 #3).
    Pass ``conn`` to run inside a caller's transaction (atomic publish)."""
    with _maybe_conn(db_path, conn) as c:
        c.execute(
            "UPDATE knowledge_units SET retired_at = ?, updated_at = ? "
            "WHERE id = ? AND retired_at IS NULL",
            (_now_iso(), _now_iso(), unit_id),
        )
        c.execute(
            "DELETE FROM claim_supports WHERE knowledge_unit_id = ?", (unit_id,)
        )


def list_eligible_knowledge_units(
    db_path: Path, source_id: int | None = None
) -> list[dict]:
    """Active downstream-eligible units: retired_at IS NULL AND
    support_status='verified' (SCHEMA §20.1 eligibility rule). `unchecked`
    legacy rows are intentionally excluded from compiler inputs.

    NOTE (Plan B2): generation-agnostic. Serving callers must use
    :func:`list_serving_units` (authoritative-generation only); the compiler's
    staged build must use :func:`list_generation_units`."""
    sql = (
        "SELECT * FROM knowledge_units "
        "WHERE retired_at IS NULL AND support_status = 'verified'"
    )
    params: tuple = ()
    if source_id is not None:
        sql += " AND source_id = ?"
        params = (source_id,)
    sql += " ORDER BY created_at"
    with connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_decode_unit_row(row) for row in rows]


def list_serving_units(db_path: Path, source_id: int | None = None) -> list[dict]:
    """Units visible to serving surfaces (query / evidence / search materialization)
    — SYSTEM_BEHAVIOR §26.3. Served = `retired_at IS NULL` ∧
    `support_status='verified'` ∧ owned by an `authoritative` generation. A staged
    or discarded generation's units (and any NULL-generation legacy row not yet
    migrated) are excluded by construction."""
    sql = (
        "SELECT ku.* FROM knowledge_units ku "
        "JOIN compiler_generations g ON g.id = ku.generation_id "
        "WHERE ku.retired_at IS NULL AND ku.support_status = 'verified' "
        "AND g.status = 'authoritative'"
    )
    params: tuple = ()
    if source_id is not None:
        sql += " AND ku.source_id = ?"
        params = (source_id,)
    sql += " ORDER BY ku.created_at"
    with connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_decode_unit_row(row) for row in rows]


def list_generation_units(
    db_path: Path, generation_id: str, *, conn: sqlite3.Connection | None = None
) -> list[dict]:
    """The compiler-internal view of ONE generation's verified active units
    (SYSTEM_BEHAVIOR §26.3) — used while building/auditing a staged generation
    before it publishes. Visible to the compiler only, never to serving.
    Pass ``conn`` to read within a caller's transaction (atomic publish)."""
    with _maybe_conn(db_path, conn) as c:
        rows = c.execute(
            "SELECT * FROM knowledge_units WHERE generation_id = ? "
            "AND retired_at IS NULL AND support_status = 'verified' ORDER BY created_at",
            (generation_id,),
        ).fetchall()
    return [_decode_unit_row(row) for row in rows]


def refresh_support_freshness(
    db_path: Path, *, conn: sqlite3.Connection | None = None
) -> set[str]:
    """Re-check every verified claim_supports.evidence_hash against the cited
    span's current content_hash; mark mismatched support rows and their owning
    units `stale` (SYSTEM_BEHAVIOR §26.1 freshness re-check). Returns the set of
    unit ids newly marked stale.

    Pass ``conn`` so the freshness writes join a caller's open transaction (the
    publish gate audits the uncommitted re-validated state — §26.3); without it
    a second connection would block on the caller's write lock."""
    now = _now_iso()
    stale_units: set[str] = set()
    with _maybe_conn(db_path, conn) as conn:
        rows = conn.execute(
            """
            SELECT cs.knowledge_unit_id AS uid, cs.source_span_id AS span,
                   cs.support_role AS role, cs.evidence_hash AS hash,
                   ss.content_hash AS current_hash
            FROM claim_supports cs
            LEFT JOIN source_spans ss ON ss.id = cs.source_span_id
            WHERE cs.support_status = 'verified'
            """
        ).fetchall()
        for r in rows:
            if r["current_hash"] is None or r["current_hash"] != r["hash"]:
                conn.execute(
                    "UPDATE claim_supports SET support_status = 'stale', "
                    "support_reason = ?, updated_at = ? "
                    "WHERE knowledge_unit_id = ? AND source_span_id = ? "
                    "AND support_role = ?",
                    ("cited span content changed or was removed", now,
                     r["uid"], r["span"], r["role"]),
                )
                stale_units.add(r["uid"])
        for uid in stale_units:
            conn.execute(
                "UPDATE knowledge_units SET support_status = 'stale', "
                "support_reason = ?, updated_at = ? "
                "WHERE id = ? AND support_status = 'verified'",
                ("stale support: cited span content changed or was removed", now, uid),
            )
    return stale_units


def create_compiler_generation(
    db_path: Path,
    *,
    prompt_contract_version: str,
    source_id: int | None = None,
) -> str:
    """Open a new staged compiler generation (SCHEMA §20.3). Rows attributed to
    it stay invisible to query/search until it publishes."""
    gen_id = _new_id("GEN")
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO compiler_generations "
            "(id, source_id, status, prompt_contract_version, created_at, audit_json) "
            "VALUES (?, ?, 'staged', ?, ?, '{}')",
            (gen_id, source_id, prompt_contract_version, _now_iso()),
        )
    return gen_id


def get_authoritative_generation(
    db_path: Path, source_id: int | None
) -> dict | None:
    """The single authoritative generation for a source scope, or None."""
    with connect(db_path) as conn:
        if source_id is None:
            row = conn.execute(
                "SELECT * FROM compiler_generations "
                "WHERE source_id IS NULL AND status = 'authoritative' LIMIT 1"
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM compiler_generations "
                "WHERE source_id = ? AND status = 'authoritative' LIMIT 1",
                (source_id,),
            ).fetchone()
    return dict(row) if row else None


def publish_compiler_generation(
    db_path: Path, gen_id: str, *, audit_json: str = "{}",
    conn: sqlite3.Connection | None = None,
) -> None:
    """Flip a staged generation to authoritative (SCHEMA §20.3). Discards the
    prior authoritative generation for the same source scope so the
    at-most-one-authoritative invariant holds. The publish GATE (audit
    validation) is enforced by the compiler in P6, not here. Pass ``conn`` to
    flip inside a caller's transaction (atomic publish)."""
    now = _now_iso()
    with _maybe_conn(db_path, conn) as c:
        row = c.execute(
            "SELECT source_id, status FROM compiler_generations WHERE id = ?",
            (gen_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown compiler generation: {gen_id}")
        if row["status"] != "staged":
            raise ValueError(f"generation {gen_id} is not staged (is {row['status']})")
        source_id = row["source_id"]
        if source_id is None:
            c.execute(
                "UPDATE compiler_generations SET status = 'discarded', "
                "discarded_at = ? WHERE source_id IS NULL AND status = 'authoritative'",
                (now,),
            )
        else:
            c.execute(
                "UPDATE compiler_generations SET status = 'discarded', "
                "discarded_at = ? WHERE source_id = ? AND status = 'authoritative'",
                (now, source_id),
            )
        c.execute(
            "UPDATE compiler_generations SET status = 'authoritative', "
            "published_at = ?, audit_json = ? WHERE id = ?",
            (now, audit_json, gen_id),
        )


def discard_compiler_generation(db_path: Path, gen_id: str) -> None:
    """Mark a staged generation discarded after a failed compile (SCHEMA §20.3).
    No partial authoritative publish is representable."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE compiler_generations SET status = 'discarded', discarded_at = ? "
            "WHERE id = ? AND status = 'staged'",
            (_now_iso(), gen_id),
        )


# --- graph_entities / graph_relations --------------------------------


def upsert_graph_entity(
    db_path: Path,
    *,
    canonical_name: str,
    entity_type: str,
    description: str = "",
    source_span_ids: list[str] | None = None,
    knowledge_unit_ids: list[str] | None = None,
    prompt_run_id: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Insert or merge an entity, deduplicated by (canonical_name, entity_type).
    On merge, span/knowledge-unit references are unioned and a non-empty
    description replaces an empty one. Pass ``conn`` to run inside a caller's
    transaction (atomic publish)."""
    now = _now_iso()
    with _maybe_conn(db_path, conn) as conn:
        existing = conn.execute(
            "SELECT * FROM graph_entities WHERE canonical_name = ? AND entity_type = ?",
            (canonical_name, entity_type),
        ).fetchone()
        if existing:
            merged_spans = sorted(
                set(_loads_list(existing["source_span_ids"]))
                | set(source_span_ids or [])
            )
            merged_units = sorted(
                set(_loads_list(existing["knowledge_unit_ids"]))
                | set(knowledge_unit_ids or [])
            )
            new_desc = description or str(existing["description"])
            conn.execute(
                """
                UPDATE graph_entities
                   SET description = ?, source_span_ids = ?,
                       knowledge_unit_ids = ?, updated_at = ?
                 WHERE id = ?
                """,
                (
                    new_desc, json.dumps(merged_spans), json.dumps(merged_units),
                    now, existing["id"],
                ),
            )
            return str(existing["id"])
        entity_id = _new_id("ENT")
        conn.execute(
            """
            INSERT INTO graph_entities
                (id, canonical_name, entity_type, description, source_span_ids,
                 knowledge_unit_ids, prompt_run_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_id, canonical_name, entity_type, description,
                json.dumps(source_span_ids or []),
                json.dumps(knowledge_unit_ids or []),
                prompt_run_id, now, now,
            ),
        )
        return entity_id


def upsert_graph_relation(
    db_path: Path,
    *,
    source_entity_id: str,
    target_entity_id: str,
    relation_type: str,
    description: str = "",
    assertion_source: str = "source_states",
    source_span_ids: list[str] | None = None,
    confidence: float = 0.0,
    prompt_run_id: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Insert a relation. Both endpoints must be declared entities. Pass ``conn``
    to run inside a caller's transaction (atomic publish)."""
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"relation confidence out of range: {confidence}")
    with _maybe_conn(db_path, conn) as conn:
        for endpoint in (source_entity_id, target_entity_id):
            found = conn.execute(
                "SELECT 1 FROM graph_entities WHERE id = ?", (endpoint,)
            ).fetchone()
            if not found:
                raise ValueError(f"relation endpoint is not a declared entity: {endpoint}")
        existing = conn.execute(
            """
            SELECT id FROM graph_relations
            WHERE source_entity_id = ? AND target_entity_id = ? AND relation_type = ?
            """,
            (source_entity_id, target_entity_id, relation_type),
        ).fetchone()
        now = _now_iso()
        if existing:
            conn.execute(
                """
                UPDATE graph_relations
                   SET description = ?, assertion_source = ?, source_span_ids = ?,
                       confidence = ?, updated_at = ?
                 WHERE id = ?
                """,
                (
                    description, assertion_source,
                    json.dumps(source_span_ids or []), confidence, now,
                    existing["id"],
                ),
            )
            return str(existing["id"])
        relation_id = _new_id("REL")
        conn.execute(
            """
            INSERT INTO graph_relations
                (id, source_entity_id, target_entity_id, relation_type, description,
                 assertion_source, source_span_ids, confidence, prompt_run_id,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                relation_id, source_entity_id, target_entity_id, relation_type,
                description, assertion_source, json.dumps(source_span_ids or []),
                confidence, prompt_run_id, now, now,
            ),
        )
        return relation_id


def upsert_graph_relation_support(
    db_path: Path,
    *,
    relation_id: str,
    knowledge_unit_id: str,
    source_span_ids: list[str],
    source_lineage_hash: str,
    assertion_source: str = "source_states",
    confidence: float = 0.0,
    support_status: str = "verified",
    conn: sqlite3.Connection | None = None,
) -> str:
    """Aggregate ONE independent claim-level support onto a relation (§27.2).

    Re-asserting the same proposition ADDS a support; it never overwrites
    (SCHEMA §21.5). The PK ``(relation_id, knowledge_unit_id, support_hash)``
    dedups the SAME unit re-citing the SAME spans — so an idempotent recompile
    leaves the support count unchanged — while ``source_lineage_hash`` is the
    INDEPENDENCE key: a relation reaches the ``active`` floor only with **≥2
    DISTINCT** ``verified`` lineages (§27.2). Copied/forked sources share a
    lineage and therefore count once. Returns the row's ``support_hash``. Pass
    ``conn`` to run inside the caller's atomic publish transaction (§27.8)."""
    if support_status not in SUPPORT_STATUSES:
        raise ValueError(f"invalid support_status: {support_status!r}")
    # Canonicalize the cited spans: dedup THEN sort, so a duplicate span id (from a
    # noisy LLM array or an over-counting caller) cannot make support_hash vary by
    # multiplicity. Two supports citing the same set of spans must hash identically,
    # else the ON-CONFLICT idempotency below silently breaks (a "new" duplicate row).
    spans = sorted(set(source_span_ids or []))
    # Content hash of (proposition, cited spans): dedups re-assertion of the same
    # evidence within a relation. The relation_id already encodes the canonical
    # proposition (upsert_graph_relation dedups on src/tgt/type), so the spans are
    # what distinguish two supports of one relation.
    support_hash = _sha16(["relation_support", relation_id, spans])
    now = _now_iso()
    with _maybe_conn(db_path, conn) as conn:
        conn.execute(
            """
            INSERT INTO graph_relation_supports
                (relation_id, knowledge_unit_id, source_span_ids, assertion_source,
                 confidence, support_status, support_hash, source_lineage_hash,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(relation_id, knowledge_unit_id, support_hash)
            DO UPDATE SET
                support_status = excluded.support_status,
                confidence = excluded.confidence,
                source_lineage_hash = excluded.source_lineage_hash,
                source_span_ids = excluded.source_span_ids,
                assertion_source = excluded.assertion_source,
                updated_at = excluded.updated_at
            """,
            (
                relation_id, knowledge_unit_id, json.dumps(spans), assertion_source,
                confidence, support_status, support_hash, source_lineage_hash,
                now, now,
            ),
        )
    return support_hash


# --- Plan C (v0.9.0, SCHEMA §21.1-§21.4) entity resolution / reversible merges --


def _entity_context(conn: sqlite3.Connection, entity_id: str) -> dict[str, Any]:
    """Fetch the (entity_type, spans, knowledge units, neighbours) context the
    §27.1 merge guards compare. Neighbours are the entities directly linked to
    ``entity_id`` by any relation (either direction)."""
    row = conn.execute(
        "SELECT entity_type, source_span_ids, knowledge_unit_ids "
        "FROM graph_entities WHERE id = ?",
        (entity_id,),
    ).fetchone()
    if row is None:
        return {"entity_type": None, "spans": set(), "units": set(), "neighbours": set()}
    neighbours: set[str] = set()
    for r in conn.execute(
        "SELECT target_entity_id FROM graph_relations WHERE source_entity_id = ?",
        (entity_id,),
    ):
        neighbours.add(str(r[0]))
    for r in conn.execute(
        "SELECT source_entity_id FROM graph_relations WHERE target_entity_id = ?",
        (entity_id,),
    ):
        neighbours.add(str(r[0]))
    return {
        "entity_type": row["entity_type"],
        "spans": set(_loads_list(row["source_span_ids"])),
        "units": set(_loads_list(row["knowledge_unit_ids"])),
        "neighbours": neighbours,
    }


def evaluate_merge_guards(
    db_path: Path,
    *,
    source_entity_id: str,
    target_entity_id: str,
    avoid_merges: Iterable[tuple[str, str]] = (),
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Evaluate the four SYSTEM_BEHAVIOR §27.1 merge guards for a candidate pair
    and return their booleans plus an overall ``verdict``. This is read-only:
    similarity is candidate generation ONLY (Arena decision 3/4), so even an exact
    surface-form match is never auto-accepted here.

    Returned keys:

    - ``type_match`` — both entities share the same ``entity_type``.
    - ``context_overlap`` — they share ≥1 source span, knowledge unit, or graph
      neighbour (the deterministic "above threshold" floor for the gold fixtures).
    - ``no_contradiction`` — no ``contradicts`` relation joins the pair (either
      direction).
    - ``not_avoid_listed`` — the pair is not on the workspace ``avoid_merges`` list.
    - ``verdict`` ∈ {``accept``, ``ambiguous_candidate``, ``rejected``}: a pair on
      ``avoid_merges`` is durable negative knowledge → ``rejected``; ALL four guards
      passing → ``accept``; any other guard failure downgrades the candidate to
      ``ambiguous_candidate`` (it may at most PROPOSE, never auto-fuse).
    """
    if source_entity_id == target_entity_id:
        return {
            "type_match": True,
            "context_overlap": True,
            "no_contradiction": True,
            "not_avoid_listed": True,
            "verdict": "rejected",
        }
    pair = frozenset((source_entity_id, target_entity_id))
    avoid_pairs = {frozenset((s, t)) for s, t in avoid_merges}
    not_avoid_listed = pair not in avoid_pairs
    with _maybe_conn(db_path, conn) as conn:
        src = _entity_context(conn, source_entity_id)
        tgt = _entity_context(conn, target_entity_id)
        type_match = (
            src["entity_type"] is not None
            and src["entity_type"] == tgt["entity_type"]
        )
        context_overlap = bool(
            (src["spans"] & tgt["spans"])
            or (src["units"] & tgt["units"])
            or (src["neighbours"] & tgt["neighbours"])
        )
        no_contradiction = (
            conn.execute(
                "SELECT 1 FROM graph_relations WHERE relation_type = 'contradicts' "
                "AND ((source_entity_id = ? AND target_entity_id = ?) "
                "  OR (source_entity_id = ? AND target_entity_id = ?)) LIMIT 1",
                (source_entity_id, target_entity_id,
                 target_entity_id, source_entity_id),
            ).fetchone()
            is None
        )
    if not not_avoid_listed:
        verdict = "rejected"
    elif type_match and context_overlap and no_contradiction:
        verdict = "accept"
    else:
        verdict = "ambiguous_candidate"
    return {
        "type_match": type_match,
        "context_overlap": context_overlap,
        "no_contradiction": no_contradiction,
        "not_avoid_listed": not_avoid_listed,
        "verdict": verdict,
    }


def propose_entity_merge(
    db_path: Path,
    *,
    source_entity_id: str,
    target_entity_id: str,
    rationale: str,
    evidence: Mapping[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Record a merge proposal (``decision='proposed'``) of ``source_entity_id``
    (origin, merged away) into ``target_entity_id`` (surviving canonical) and
    return the ``DEC-<UUID8>`` decision id. A proposal NEVER rewrites the graph
    (SCHEMA §21.2); only :func:`accept_entity_merge` does."""
    now = _now_iso()
    decision_id = _new_id("DEC")
    payload = json.dumps(dict(evidence or {}), sort_keys=True)
    with _maybe_conn(db_path, conn) as conn:
        conn.execute(
            "INSERT INTO entity_merge_proposals "
            "(id, source_entity_id, target_entity_id, decision, rationale, "
            " evidence_json, created_at, updated_at) "
            "VALUES (?, ?, ?, 'proposed', ?, ?, ?, ?)",
            (decision_id, source_entity_id, target_entity_id, rationale,
             payload, now, now),
        )
    return decision_id


def accept_entity_merge(
    db_path: Path, *, decision_id: str, conn: sqlite3.Connection | None = None
) -> None:
    """Accept a proposed merge (§27.1). Redirects the origin entity onto the
    surviving canonical entity, re-points every relation endpoint that referenced
    the origin, and persists a complete reversible ``entity_resolution_lineage``
    row (SCHEMA §21.3). The origin entity is NEVER deleted — its identity is
    preserved for reversal."""
    now = _now_iso()
    with _maybe_conn(db_path, conn) as conn:
        proposal = conn.execute(
            "SELECT source_entity_id, target_entity_id "
            "FROM entity_merge_proposals WHERE id = ?",
            (decision_id,),
        ).fetchone()
        if proposal is None:
            raise ValueError(f"unknown merge decision: {decision_id}")
        origin = str(proposal["source_entity_id"])
        survivor = str(proposal["target_entity_id"])
        origin_row = conn.execute(
            "SELECT * FROM graph_entities WHERE id = ?", (origin,)
        ).fetchone()
        if origin_row is None:
            raise ValueError(f"merge origin entity not found: {origin}")
        survivor_row = conn.execute(
            "SELECT 1 FROM graph_entities WHERE id = ?", (survivor,)
        ).fetchone()
        if survivor_row is None:
            raise ValueError(f"merge target entity not found: {survivor}")
        # Capture the exact pre-merge origin row + every relation endpoint rewrite
        # so reversal can reconstruct the prior graph byte-for-byte (SCHEMA §21.3).
        relation_rewrites: list[dict[str, str]] = []
        for rel in conn.execute(
            "SELECT id, source_entity_id, target_entity_id FROM graph_relations "
            "WHERE source_entity_id = ? OR target_entity_id = ?",
            (origin, origin),
        ).fetchall():
            if str(rel["source_entity_id"]) == origin:
                relation_rewrites.append(
                    {"relation_id": str(rel["id"]), "field": "source_entity_id",
                     "from": origin, "to": survivor}
                )
            if str(rel["target_entity_id"]) == origin:
                relation_rewrites.append(
                    {"relation_id": str(rel["id"]), "field": "target_entity_id",
                     "from": origin, "to": survivor}
                )
        rewrite_json = json.dumps(
            {"origin_entity": dict(origin_row),
             "relation_rewrites": relation_rewrites},
            sort_keys=True,
        )
        # Apply: re-point relation endpoints onto the survivor (explicit per-column
        # so no column name is interpolated into SQL)...
        for rw in relation_rewrites:
            if rw["field"] == "source_entity_id":
                conn.execute(
                    "UPDATE graph_relations SET source_entity_id = ?, updated_at = ? "
                    "WHERE id = ?",
                    (survivor, now, rw["relation_id"]),
                )
            else:
                conn.execute(
                    "UPDATE graph_relations SET target_entity_id = ?, updated_at = ? "
                    "WHERE id = ?",
                    (survivor, now, rw["relation_id"]),
                )
        # ...redirect the origin entity (never delete it)...
        conn.execute(
            "UPDATE graph_entities SET resolution_state = 'redirected', "
            "redirect_to_entity_id = ?, decision_id = ?, updated_at = ? WHERE id = ?",
            (survivor, decision_id, now, origin),
        )
        # ...persist the reversible lineage...
        conn.execute(
            "INSERT OR REPLACE INTO entity_resolution_lineage "
            "(decision_id, origin_entity_id, canonical_entity_id, rewrite_json) "
            "VALUES (?, ?, ?, ?)",
            (decision_id, origin, survivor, rewrite_json),
        )
        # ...and record the accepted decision.
        conn.execute(
            "UPDATE entity_merge_proposals SET decision = 'accepted', updated_at = ? "
            "WHERE id = ?",
            (now, decision_id),
        )


def reverse_entity_merge(
    db_path: Path, *, decision_id: str, conn: sqlite3.Connection | None = None
) -> None:
    """Reverse a previously accepted merge (§27.1). Replays the §21.3 rewrite
    lineage in reverse — restoring the origin entity to ``canonical`` and every
    relation endpoint to its pre-merge value. The decision row is retained as
    ``reversed`` audit, never hard-deleted; the acceptance test is that reversal
    yields endpoints byte-identical to the pre-merge state."""
    now = _now_iso()
    with _maybe_conn(db_path, conn) as conn:
        lineage_rows = conn.execute(
            "SELECT origin_entity_id, rewrite_json FROM entity_resolution_lineage "
            "WHERE decision_id = ?",
            (decision_id,),
        ).fetchall()
        if not lineage_rows:
            raise ValueError(f"no resolution lineage for decision: {decision_id}")
        for lin in lineage_rows:
            origin = str(lin["origin_entity_id"])
            rewrite = _loads_obj(lin["rewrite_json"])
            for rw in rewrite.get("relation_rewrites", []):
                if rw["field"] == "source_entity_id":
                    conn.execute(
                        "UPDATE graph_relations SET source_entity_id = ?, "
                        "updated_at = ? WHERE id = ?",
                        (rw["from"], now, rw["relation_id"]),
                    )
                else:
                    conn.execute(
                        "UPDATE graph_relations SET target_entity_id = ?, "
                        "updated_at = ? WHERE id = ?",
                        (rw["from"], now, rw["relation_id"]),
                    )
            conn.execute(
                "UPDATE graph_entities SET resolution_state = 'canonical', "
                "redirect_to_entity_id = NULL, decision_id = NULL, updated_at = ? "
                "WHERE id = ?",
                (now, origin),
            )
        conn.execute(
            "UPDATE entity_merge_proposals SET decision = 'reversed', updated_at = ? "
            "WHERE id = ?",
            (now, decision_id),
        )


# --- Plan C (v0.9.0, SCHEMA §21.5/§21.6) relation lifecycle / topology ----------


def detect_bridge_risk_relations(
    db_path: Path, *, conn: sqlite3.Connection | None = None
) -> list[str]:
    """Return the ids of relations that are structural ``bridge_risk`` edges
    (SCHEMA §21.6 / SYSTEM_BEHAVIOR §27.3): a single edge whose removal
    disconnects two otherwise-separate DENSE components.

    Detection is purely TOPOLOGICAL — a cut edge (graph-theory bridge) between two
    components that each have >=2 nodes. It deliberately does NOT threshold on
    ``confidence``: GQ07 (§21.9) proved production confidence is non-discriminative,
    so a raw-confidence filter is a rejected default. Parallel edges between the
    same pair are NOT cut edges (removing one leaves the other), and a low-confidence
    chord inside a dense block is on a cycle and therefore not a cut edge — only a
    genuine cut edge between dense blocks is flagged.

    Self-loops and ``retired`` relations are excluded from the topology.
    """
    with _maybe_conn(db_path, conn) as conn:
        rows = conn.execute(
            "SELECT id, source_entity_id, target_entity_id FROM graph_relations "
            "WHERE source_entity_id != target_entity_id "
            "AND lifecycle_status != 'retired'"
        ).fetchall()

    # Undirected adjacency; each relation row is one undirected edge keyed by its
    # index so parallel relations between a pair are distinct edges (and thus never
    # cut edges of each other).
    adj: dict[str, list[tuple[str, int]]] = defaultdict(list)
    edge_rel: list[str] = []
    for r in rows:
        u, v, rid = (
            str(r["source_entity_id"]),
            str(r["target_entity_id"]),
            str(r["id"]),
        )
        ei = len(edge_rel)
        edge_rel.append(rid)
        adj[u].append((v, ei))
        adj[v].append((u, ei))

    # Component sizes (a bridge's two sides must each be dense: >=2 nodes).
    comp_size: dict[str, int] = {}
    seen: set[str] = set()
    for start in adj:
        if start in seen:
            continue
        queue: deque[str] = deque([start])
        seen.add(start)
        members: list[str] = []
        while queue:
            x = queue.popleft()
            members.append(x)
            for y, _ in adj[x]:
                if y not in seen:
                    seen.add(y)
                    queue.append(y)
        for x in members:
            comp_size[x] = len(members)

    # Iterative Tarjan bridge finding with subtree sizes for the density check.
    disc: dict[str, int] = {}
    low: dict[str, int] = {}
    subsize: dict[str, int] = {}
    visited: set[str] = set()
    timer = 0
    bridges: set[str] = set()
    for root in adj:
        if root in visited:
            continue
        disc[root] = low[root] = timer
        timer += 1
        subsize[root] = 1
        visited.add(root)
        # frame = [node, parent_edge_index, next_neighbour_index]
        stack: list[list] = [[root, -1, 0]]
        while stack:
            frame = stack[-1]
            u, parent_ei, idx = frame
            neighbours = adj[u]
            if idx < len(neighbours):
                frame[2] = idx + 1
                w, ei = neighbours[idx]
                if ei == parent_ei:
                    continue  # do not walk back over the SAME physical edge
                if w not in visited:
                    disc[w] = low[w] = timer
                    timer += 1
                    subsize[w] = 1
                    visited.add(w)
                    stack.append([w, ei, 0])
                else:
                    low[u] = min(low[u], disc[w])
            else:
                stack.pop()
                if stack:
                    parent = stack[-1][0]
                    low[parent] = min(low[parent], low[u])
                    subsize[parent] += subsize[u]
                    if low[u] > disc[parent]:
                        v_side = subsize[u]
                        u_side = comp_size[u] - v_side
                        if v_side >= 2 and u_side >= 2:
                            bridges.add(edge_rel[parent_ei])
    return sorted(bridges)


def compile_relation_lifecycle(
    db_path: Path,
    *,
    relation_id: str,
    bridge_risk_ids: set[str] | None = None,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Compile and persist a single relation's ``lifecycle_status`` and
    ``quarantine_reason`` (SCHEMA §21.5/§21.6, SYSTEM_BEHAVIOR §27.3) and return the
    resulting ``lifecycle_status``.

    Decision order (structural admissibility before support quality):

    1. ``self_loop`` — source == target.
    2. ``endpoint_unresolved`` — an endpoint resolves to a non-canonical
       (``redirected``) entity; endpoints normalize through ACCEPTED resolution
       only (§27.1) before entering topology.
    3. ``contradiction`` — a ``contradicts`` relation joins the same endpoints.
    4. ``bridge_risk`` — the relation is a structural cut edge between two dense
       components (see :func:`detect_bridge_risk_relations`).
    5. Support corroboration over DISTINCT ``verified`` source lineages (§21.5):
       ``0`` -> ``unsupported``; exactly ``1`` -> ``copied_source_only``;
       ``>=2`` -> ``active`` (the §27.2 corroboration threshold). There is no
       ``duplicate_proposition`` outcome — re-assertion aggregates support.

    Pass a precomputed ``bridge_risk_ids`` set (from one
    :func:`detect_bridge_risk_relations` pass) when compiling a whole generation so
    the topology is not recomputed per relation; standalone callers may omit it and
    it is computed lazily only if the earlier checks did not already decide.
    """
    with _maybe_conn(db_path, conn) as conn:
        rel = conn.execute(
            "SELECT source_entity_id, target_entity_id, relation_type "
            "FROM graph_relations WHERE id = ?",
            (relation_id,),
        ).fetchone()
        if rel is None:
            raise ValueError(f"unknown relation: {relation_id}")
        src = str(rel["source_entity_id"])
        tgt = str(rel["target_entity_id"])
        rtype = str(rel["relation_type"])

        status, reason = _classify_relation_lifecycle(
            conn, relation_id, src, tgt, rtype, bridge_risk_ids, db_path
        )

        if status == "active":
            conn.execute(
                "UPDATE graph_relations SET lifecycle_status = 'active', "
                "quarantine_reason = '', reeval_trigger = '', updated_at = ? "
                "WHERE id = ?",
                (_now_iso(), relation_id),
            )
        else:  # quarantined
            conn.execute(
                "UPDATE graph_relations SET lifecycle_status = 'quarantined', "
                "quarantine_reason = ?, reeval_trigger = ?, updated_at = ? "
                "WHERE id = ?",
                (
                    reason,
                    _QUARANTINE_REEVAL_TRIGGERS[reason],
                    _now_iso(),
                    relation_id,
                ),
            )
        return status


def _classify_relation_lifecycle(
    conn: sqlite3.Connection,
    relation_id: str,
    src: str,
    tgt: str,
    rtype: str,
    bridge_risk_ids: set[str] | None,
    db_path: Path,
) -> tuple[str, str]:
    """Return ``(lifecycle_status, quarantine_reason)`` for a relation without
    writing. ``reason`` is ``''`` when the status is ``active``."""
    if src == tgt:
        return "quarantined", "self_loop"

    # Endpoint normalization: an endpoint that is not a canonical entity (it was
    # redirected by an accepted merge but this relation was not re-pointed) cannot
    # enter authoritative topology (§27.3 endpoint normalization).
    for endpoint in (src, tgt):
        state = conn.execute(
            "SELECT resolution_state FROM graph_entities WHERE id = ?",
            (endpoint,),
        ).fetchone()
        if state is not None and str(state[0]) != "canonical":
            return "quarantined", "endpoint_unresolved"

    # Contradiction: a `contradicts` relation joins the same endpoints (either
    # direction), excluding the relation being compiled. This quarantines a NON-
    # contradiction relation (e.g. `extends`) when the graph ALSO asserts the
    # endpoints contradict — an inconsistent pair. A `contradicts` relation is itself
    # exempt: it must not be quarantined by the very rule it embodies, otherwise two
    # mutual `contradicts` edges (A→B and B→A) would quarantine each other (§27.3).
    if rtype != "contradicts":
        contradicted = conn.execute(
            "SELECT 1 FROM graph_relations WHERE relation_type = 'contradicts' "
            "AND id != ? "
            "AND ((source_entity_id = ? AND target_entity_id = ?) "
            "  OR (source_entity_id = ? AND target_entity_id = ?)) LIMIT 1",
            (relation_id, src, tgt, tgt, src),
        ).fetchone()
        if contradicted is not None:
            return "quarantined", "contradiction"

    # Bridge risk (topology): cut edge between two dense components. A structural
    # bridge cannot silently enter communities even if otherwise supported, so this
    # is checked before support promotion.
    if bridge_risk_ids is None:
        bridge_risk_ids = set(detect_bridge_risk_relations(db_path, conn=conn))
    if relation_id in bridge_risk_ids:
        return "quarantined", "bridge_risk"

    # Support corroboration by DISTINCT verified source lineage (§21.5).
    distinct_lineages = conn.execute(
        "SELECT COUNT(DISTINCT source_lineage_hash) FROM graph_relation_supports "
        "WHERE relation_id = ? AND support_status = 'verified'",
        (relation_id,),
    ).fetchone()[0]
    if distinct_lineages == 0:
        return "quarantined", "unsupported"
    if distinct_lineages < _RELATION_CORROBORATION_THRESHOLD:
        return "quarantined", "copied_source_only"
    return "active", ""


def _decode_entity_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
    data["knowledge_unit_ids"] = _loads_list(data.get("knowledge_unit_ids"))
    return data


def _decode_relation_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
    return data


def get_graph_entity(db_path: Path, entity_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM graph_entities WHERE id = ?", (entity_id,)
        ).fetchone()
        return _decode_entity_row(row) if row else None


def find_graph_entities(db_path: Path, name_like: str, limit: int = 12) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM graph_entities WHERE canonical_name LIKE ? "
            "ORDER BY canonical_name LIMIT ?",
            (f"%{name_like}%", limit),
        ).fetchall()
        return [_decode_entity_row(row) for row in rows]


def relation_neighborhood(db_path: Path, entity_ids: list[str]) -> list[dict]:
    """Return relations touching any of the given entities (one hop)."""
    if not entity_ids:
        return []
    with connect(db_path) as conn:
        placeholders = ",".join("?" for _ in entity_ids)
        rows = conn.execute(
            f"""
            SELECT * FROM graph_relations
            WHERE source_entity_id IN ({placeholders})
               OR target_entity_id IN ({placeholders})
            """,
            tuple(entity_ids) + tuple(entity_ids),
        ).fetchall()
        return [_decode_relation_row(row) for row in rows]


# --- community construction (hierarchy fallback) ---------------------


def connected_components(
    db_path: Path,
    *,
    only_active: bool = True,
    conn: sqlite3.Connection | None = None,
) -> list[set[str]]:
    """Return the connected components of the canonical entity graph as a list of
    entity-id sets — the EXPLICIT degraded hierarchy fallback (SYSTEM_BEHAVIOR §27.4,
    Arena decision 10).

    Nodes are the ``canonical`` (§27.1) entities; edges are non-self-loop relations
    between two canonical endpoints. ``only_active=True`` (the default) restricts the
    edge set to ``active`` (§27.3) relations, so a ``quarantined`` noisy bridge or an
    ``unsupported`` edge cannot silently fuse two clusters into one giant component.
    ``only_active=False`` admits every non-``retired`` relation (provisional +
    quarantined) for diagnostics. A ``retired`` reconciliation tombstone (§27.8) is
    NEVER a topology input in either mode, so its endpoints fall apart.

    An entity with no qualifying edge is its own singleton component. The result is
    deterministic — components are sorted by ``(size, sorted members)`` and the
    union always roots at the smaller id — so a fixed graph yields an identical
    partition on repeat runs.
    """
    edge_filter = (
        "lifecycle_status = 'active'" if only_active else "lifecycle_status != 'retired'"
    )
    with _maybe_conn(db_path, conn) as conn:
        node_rows = conn.execute(
            "SELECT id FROM graph_entities WHERE resolution_state = 'canonical' "
            "ORDER BY id"
        ).fetchall()
        edge_rows = conn.execute(
            "SELECT source_entity_id, target_entity_id FROM graph_relations "
            f"WHERE source_entity_id != target_entity_id AND {edge_filter} "
            "ORDER BY id"
        ).fetchall()

    nodes = [str(r["id"]) for r in node_rows]
    canonical = set(nodes)
    parent: dict[str, str] = {n: n for n in nodes}

    def find(x: str) -> str:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:  # path compression
            parent[x], x = root, parent[x]
        return root

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        # Root at the smaller id for a deterministic forest shape.
        parent[max(ra, rb)] = min(ra, rb)

    for r in edge_rows:
        u, v = str(r["source_entity_id"]), str(r["target_entity_id"])
        # Both endpoints must be canonical nodes; a relation onto a redirected or
        # missing entity is not authoritative topology (§27.1/§27.4).
        if u in canonical and v in canonical:
            union(u, v)

    groups: dict[str, set[str]] = defaultdict(set)
    for n in nodes:
        groups[find(n)].add(n)
    return sorted(groups.values(), key=lambda c: (len(c), sorted(c)))


# --- community_reports -----------------------------------------------


def upsert_community_report(
    db_path: Path,
    *,
    community_key: str,
    title: str | None = None,
    summary: str | None = None,
    full_content: str | None = None,
    dependency_hash: str | None = None,
    level: int | None = None,
    findings: list | None = None,
    entity_ids: list[str] | None = None,
    relation_ids: list[str] | None = None,
    source_span_ids: list[str] | None = None,
    rank: float | None = None,
    prompt_run_id: str | None = None,
    member_hash: str | None = None,
    support_hash: str | None = None,
    config_hash: str | None = None,
    parent_community_key: str | None = None,
    clear_retired: bool = True,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Merge-upsert the report for a community key (SCHEMA §21.7).

    Identity is the ``community_key``: an existing row keeps its ``REP-`` id and
    ``created_at``. Every column defaults to ``None`` meaning *preserve the existing
    value* (or the table default on first insert), so the deterministic rebuild
    skeleton (structural columns + ``member_hash``/``support_hash``/``config_hash``)
    and the LLM prose pass (``title``/``summary``/``findings``) can write the SAME
    row without clobbering each other. ``clear_retired`` un-retires a re-emitted
    community (a present community key is never simultaneously retired). Pass
    ``conn`` to run inside a caller's atomic publish transaction (§27.8)."""
    now = _now_iso()

    def _pick(provided: Any, column: str, default: Any) -> Any:
        if provided is not None:
            return provided
        if existing is not None and existing[column] is not None:
            return existing[column]
        return default

    with _maybe_conn(db_path, conn) as conn:
        existing = conn.execute(
            "SELECT * FROM community_reports WHERE community_key = ?",
            (community_key,),
        ).fetchone()
        report_id = str(existing["id"]) if existing else _new_id("REP")
        created_at = str(existing["created_at"]) if existing else now
        retired_at = None if clear_retired else (
            existing["retired_at"] if existing is not None else None
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO community_reports
                (id, community_key, level, title, summary, full_content,
                 finding_json, entity_ids, relation_ids, source_span_ids, rank,
                 prompt_run_id, dependency_hash, created_at, updated_at,
                 parent_community_key, config_hash, member_hash, support_hash,
                 retired_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                community_key,
                _pick(level, "level", 0),
                _pick(title, "title", ""),
                _pick(summary, "summary", ""),
                _pick(full_content, "full_content", ""),
                json.dumps(findings) if findings is not None
                else _pick(None, "finding_json", "[]"),
                json.dumps(entity_ids) if entity_ids is not None
                else _pick(None, "entity_ids", "[]"),
                json.dumps(relation_ids) if relation_ids is not None
                else _pick(None, "relation_ids", "[]"),
                json.dumps(source_span_ids) if source_span_ids is not None
                else _pick(None, "source_span_ids", "[]"),
                _pick(rank, "rank", 0.0),
                _pick(prompt_run_id, "prompt_run_id", None),
                _pick(dependency_hash, "dependency_hash", ""),
                created_at,
                now,
                _pick(parent_community_key, "parent_community_key", None),
                _pick(config_hash, "config_hash", ""),
                _pick(member_hash, "member_hash", ""),
                _pick(support_hash, "support_hash", ""),
                retired_at,
            ),
        )
        return report_id


def _decode_report_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["findings"] = _loads_list(data.pop("finding_json", "[]"))
    data["entity_ids"] = _loads_list(data.get("entity_ids"))
    data["relation_ids"] = _loads_list(data.get("relation_ids"))
    data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
    return data


def list_community_reports(
    db_path: Path, *, level: int | None = None, include_retired: bool = False
) -> list[dict]:
    """List community reports. By default RETIRED communities are excluded — a
    retired/stale report never serves and never feeds synthesis (§27.5). Pass
    ``include_retired=True`` for the audit/diagnostic view."""
    retired_clause = "" if include_retired else "retired_at IS NULL"
    with connect(db_path) as conn:
        clauses = [c for c in (retired_clause,) if c]
        params: tuple = ()
        if level is not None:
            clauses.append("level = ?")
            params = (level,)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM community_reports {where} ORDER BY rank DESC, level",
            params,
        ).fetchall()
        return [_decode_report_row(row) for row in rows]


def get_community_report(db_path: Path, report_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM community_reports WHERE id = ?", (report_id,)
        ).fetchone()
        return _decode_report_row(row) if row else None


# --- Plan C (v0.9.0) graph-generation compiler: claim-grounded reports ----------
# §27.5/§27.8. The deterministic core that compiles the authoritative graph into
# content/config-derived community reports and reconciles a one-source change to
# its measured downstream closure. LLM report PROSE is layered on top (the pipeline
# fills title/summary/findings by community_key); the GROUNDING, IDENTITY, and
# CLOSURE computed here are deterministic and need no model.

# Until the P5 hierarchy benchmark freezes a richer config, the shipped partition is
# the degraded filtered-connected-components fallback (§27.4); its config identity is
# content-derived from this constant so a fixed (graph, config) is reproducible.
_GRAPH_FALLBACK_CONFIG = {
    "algorithm": "connected_components",
    "only_active": True,
    "corroboration_threshold": _RELATION_CORROBORATION_THRESHOLD,
    "seed": 0,
    "version": 1,
}


def _sha16(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


def graph_config_hash() -> str:
    """Content-derived identity of the active hierarchy/partition config (§21.7)."""
    return _sha16(_GRAPH_FALLBACK_CONFIG)


def rebuild_graph_generation(
    db_path: Path,
    *,
    config_hash: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Deterministically (re)compile the authoritative graph into claim-grounded
    community reports (SYSTEM_BEHAVIOR §27.5/§27.8), inside one atomic transaction:

    1. Compile every non-retired relation's lifecycle (§27.3) with one shared
       bridge-risk topology pass, so the ``active`` set reflects current support.
    2. Build communities from ``connected_components(only_active=True)`` (§27.4),
       keeping only multi-node components (a lone node yields no community).
    3. Derive content/config identity per community (§21.7): ``member_hash`` over the
       sorted canonical members, ``support_hash`` over the eligible verified
       active-support set, ``community_key = f(level, member_hash, support_hash,
       config_hash)``, and ``dependency_hash`` over the active-canonical-support
       closure.
    4. Merge-upsert one ``community_reports`` row per ``community_key`` — the
       structural skeleton citing the EXACT active relations and the eligible-support
       span closure. There is NO whole-community-span fallback: a community with no
       eligible active support emits no report (§27.5).
    5. Retire (set ``retired_at``) every prior non-retired report whose
       ``community_key`` is absent from the rebuilt set, before synthesis consumes
       it (§27.5).
    6. Record precise ``artifact_dependencies`` for each report over its active
       relations and support spans.

    Idempotent: an unchanged rebuild yields identical keys, so the same ``REP-`` ids
    are reused and nothing is retired — no count amplification (§27.8). Returns
    ``{communities, reports, retired, community_keys}``.
    """
    cfg_hash = config_hash if config_hash is not None else graph_config_hash()
    with _maybe_conn(db_path, conn) as conn:
        # (1) compile lifecycle for all non-retired relations with one bridge pass.
        bridge_ids = set(detect_bridge_risk_relations(db_path, conn=conn))
        for r in conn.execute(
            "SELECT id FROM graph_relations WHERE lifecycle_status != 'retired' "
            "ORDER BY id"
        ).fetchall():
            compile_relation_lifecycle(
                db_path, relation_id=str(r["id"]),
                bridge_risk_ids=bridge_ids, conn=conn,
            )

        # (2) active communities (multi-node only — a singleton is no community).
        components = [
            c for c in connected_components(db_path, only_active=True, conn=conn)
            if len(c) >= 2
        ]
        # Bucket the graph with a FIXED number of bulk queries instead of one
        # per-community `IN (?, …)` query: arbitrary-length member / relation / span
        # lists would otherwise blow past SQLITE_MAX_VARIABLE_NUMBER for a large
        # community or source and crash the compiler. One pass each over active
        # relations, verified supports, and canonical entities; the rest is grouped in
        # Python. Map every canonical member to its community index first.
        comp_of: dict[str, int] = {}
        for idx, members_set in enumerate(components):
            for m in members_set:
                comp_of[str(m)] = idx

        comp_rels: dict[int, list[sqlite3.Row]] = defaultdict(list)
        for r in conn.execute(
            "SELECT id, source_entity_id, target_entity_id, relation_type, description "
            "FROM graph_relations WHERE lifecycle_status = 'active' "
            "AND source_entity_id != target_entity_id ORDER BY id"
        ).fetchall():
            si = comp_of.get(str(r["source_entity_id"]))
            ti = comp_of.get(str(r["target_entity_id"]))
            if si is not None and si == ti:  # active edges always join one community
                comp_rels[si].append(r)

        supports_by_rel: dict[str, list[sqlite3.Row]] = defaultdict(list)
        for s in conn.execute(
            "SELECT relation_id, support_hash, source_lineage_hash, source_span_ids "
            "FROM graph_relation_supports WHERE support_status = 'verified' "
            "ORDER BY relation_id, source_lineage_hash, support_hash"
        ).fetchall():
            supports_by_rel[str(s["relation_id"])].append(s)

        entity_content: dict[str, sqlite3.Row] = {}
        for e in conn.execute(
            "SELECT id, canonical_name, entity_type, description FROM graph_entities "
            "WHERE resolution_state = 'canonical'"
        ).fetchall():
            entity_content[str(e["id"])] = e

        current_keys: list[str] = []
        for idx, members_set in enumerate(components):
            members = sorted(members_set)
            rel_rows = comp_rels.get(idx, [])  # pre-ordered by id from the bulk query
            active_rel_ids = [str(r["id"]) for r in rel_rows]
            if not active_rel_ids:
                continue  # no eligible active claim support -> no report (§27.5)

            # (3) eligible verified support closure for those active relations —
            # flattened from the single bulk fetch in (rel_id asc, lineage asc, hash
            # asc) order, byte-identical to the prior per-community
            # ORDER BY relation_id, source_lineage_hash, support_hash.
            support_rows = [
                s for rid in active_rel_ids for s in supports_by_rel.get(rid, [])
            ]
            support_keys = [
                [str(s["relation_id"]), str(s["source_lineage_hash"]),
                 str(s["support_hash"])]
                for s in support_rows
            ]
            span_ids = sorted({
                sid for s in support_rows
                for sid in _loads_list(s["source_span_ids"])
            })

            member_hash = _sha16(members)
            support_hash = _sha16(support_keys)
            level = 0
            community_key = "comm-" + hashlib.sha256(
                f"{level}|{member_hash}|{support_hash}|{cfg_hash}".encode("utf-8")
            ).hexdigest()[:12]
            # dependency_hash is over the active-canonical-support closure CONTENT
            # (entities/relations/spans, §27.5 fresh dependencies) — distinct from the
            # community_key IDENTITY (membership + support set + config, §21.7). So an
            # input entity's content edit re-stales the report without changing its
            # identity, while a membership/support change restructures the community.
            entity_payload = []
            for mid in members:
                e = entity_content.get(mid)
                if e is None:
                    entity_payload.append([mid, "", "", ""])
                else:
                    entity_payload.append([
                        mid, str(e["canonical_name"] or ""),
                        str(e["entity_type"] or ""), str(e["description"] or ""),
                    ])
            dependency_hash = _sha16({
                "entities": entity_payload,
                "relations": [
                    [str(r["id"]), str(r["relation_type"]),
                     str(r["description"] or "")]
                    for r in rel_rows
                ],
                "support": support_keys,
                "spans": span_ids,
                "config": cfg_hash,
            })

            # Skip the write for an UNCHANGED community: a non-retired row already
            # carrying this content-derived community_key AND the identical
            # dependency_hash has an unchanged identity and content closure, so
            # re-emitting it would only churn updated_at and rewrite its dependency
            # rows (write amplification + spurious downstream sync). The rebuild is a
            # true no-op for it (§27.8 — unchanged rebuild has no amplification).
            existing = conn.execute(
                "SELECT dependency_hash, retired_at FROM community_reports "
                "WHERE community_key = ?",
                (community_key,),
            ).fetchone()
            if (
                existing is not None
                and existing["retired_at"] is None
                and str(existing["dependency_hash"]) == dependency_hash
            ):
                current_keys.append(community_key)
                continue

            report_id = upsert_community_report(
                db_path,
                community_key=community_key,
                level=level,
                entity_ids=members,
                relation_ids=active_rel_ids,
                source_span_ids=span_ids,
                member_hash=member_hash,
                support_hash=support_hash,
                config_hash=cfg_hash,
                dependency_hash=dependency_hash,
                conn=conn,
            )
            current_keys.append(community_key)

            # (6) precise dependencies (idempotent: PK is artifact+dep+type).
            for rid in active_rel_ids:
                record_artifact_dependency(
                    db_path, artifact_id=report_id,
                    artifact_type="community_report", depends_on_id=rid,
                    depends_on_type="relation", dependency_hash=dependency_hash,
                    conn=conn,
                )
            for sid in span_ids:
                record_artifact_dependency(
                    db_path, artifact_id=report_id,
                    artifact_type="community_report", depends_on_id=sid,
                    depends_on_type="source_span", dependency_hash=dependency_hash,
                    conn=conn,
                )

        # (5) retire stale communities absent from the rebuilt set, before synthesis.
        keyset = set(current_keys)
        now = _now_iso()
        retired = 0
        for row in conn.execute(
            "SELECT id, community_key FROM community_reports WHERE retired_at IS NULL"
        ).fetchall():
            if str(row["community_key"]) not in keyset:
                conn.execute(
                    "UPDATE community_reports SET retired_at = ?, updated_at = ? "
                    "WHERE id = ?",
                    (now, now, row["id"]),
                )
                retired += 1

    return {
        "communities": len(current_keys),
        "reports": len(current_keys),
        "retired": retired,
        "community_keys": sorted(current_keys),
    }


def reconcile_source_change(
    db_path: Path,
    *,
    source_id: int,
    removed_span_ids: list[str] | None = None,
    config_hash: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Reconcile the graph/report closure after a source edit/delete (§27.8).

    The closure is MEASURED, not assumed:

    1. Verified relation supports whose span basis intersects ``removed_span_ids``
       (this source's removed spans) are marked ``stale`` — their source basis
       disappeared.
    2. :func:`rebuild_graph_generation` recompiles lifecycle, so a relation dropping
       below the §21.5 corroboration floor (>=2 independent verified source
       lineages) leaves the ``active`` set, the communities whose active
       membership/support changed retire, and dependent reports regenerate or
       retire.

    A community untouched by the change keeps its content-derived ``community_key``
    and ``REP-`` id — no collateral churn. Returns the measured closure: the rebuild
    summary plus ``stale_supports`` and the reconciled ``source_id``."""
    removed_list = list(dict.fromkeys(removed_span_ids or []))  # dedup, keep order
    removed = set(removed_list)
    with _maybe_conn(db_path, conn) as conn:
        stale_supports = 0
        if removed:
            now = _now_iso()
            # Push the scope filter down into SQLite instead of loading the whole
            # verified support layer into Python: an OR of `source_span_ids LIKE`
            # restricts the payload to rows whose JSON span array MIGHT carry a removed
            # span. The needle is `json.dumps(sid)` (the exact JSON string literal,
            # incl. quotes and any `\"`/`\\` escaping) so it matches how the array was
            # serialized — a raw `"%sid%"` would silently MISS a span id containing a
            # quote/backslash (false negative -> under-staling, which the Python guard
            # below cannot recover). The quoting keeps prefixes distinct (`"SPAN-1"`
            # never matches `["SPAN-10"]`). LIKE clauses are CHUNKED under
            # SQLITE_MAX_VARIABLE_NUMBER so deleting a source with thousands of spans
            # cannot crash the query. The exact set-intersection then confirms exact
            # membership, so a LIKE over-match (a `%`/`_` wildcard in an id) never
            # over-stales; LIKE wildcards only broaden, so the real row is never missed.
            candidates: dict[tuple, sqlite3.Row] = {}
            for chunk in _chunked(removed_list):
                like_clause = " OR ".join("source_span_ids LIKE ?" for _ in chunk)
                like_params = tuple(f"%{json.dumps(sid)}%" for sid in chunk)
                for row in conn.execute(
                    "SELECT relation_id, knowledge_unit_id, support_hash, "
                    "source_span_ids FROM graph_relation_supports "
                    f"WHERE support_status = 'verified' AND ({like_clause})",
                    like_params,
                ).fetchall():
                    candidates[
                        (row["relation_id"], row["knowledge_unit_id"],
                         row["support_hash"])
                    ] = row
            for row in candidates.values():
                if set(_loads_list(row["source_span_ids"])) & removed:
                    conn.execute(
                        "UPDATE graph_relation_supports SET support_status = 'stale', "
                        "updated_at = ? WHERE relation_id = ? "
                        "AND knowledge_unit_id = ? AND support_hash = ?",
                        (now, row["relation_id"], row["knowledge_unit_id"],
                         row["support_hash"]),
                    )
                    stale_supports += 1
        summary = rebuild_graph_generation(db_path, config_hash=config_hash, conn=conn)
    return {**summary, "stale_supports": stale_supports, "source_id": source_id}


# --- graph audit (read-only invariants) -----------------------------------
# SYSTEM_BEHAVIOR §27.6 / SCHEMA §21.8. A READ-ONLY assertion pass over the
# authoritative graph/report state. It NEVER writes — it runs both as the
# graph/report publish gate inside the rebuild transaction and on demand via
# `wiki lint` (the Graph Quality section). Each returned mapping carries a `code`
# (one of GRAPH_AUDIT_CODES) and the offending artifact's `subject_id`; an empty
# list means the served graph is clean. Output is sorted by (code, subject_id) for
# deterministic reporting.

# Frozen graph-audit violation codes (the schema-level §21.8 invariants this phase
# enforces). The broader §27.6 invariants that depend on GQ07 relation-quality
# labels (homonym false merges, mixed claim generations) remain benchmark-later and
# are NOT asserted here yet — adding speculative untested checks would risk false
# positives (§21.9).
GRAPH_AUDIT_CODES = frozenset(
    {
        "active_relation_insufficient_support",
        "reference_to_redirected_entity",
        "endpoint_not_canonical",
        "quarantined_relation_missing_reason",
        "report_finding_without_active_support",
    }
)


def graph_audit(
    db_path: Path, *, conn: sqlite3.Connection | None = None
) -> list[dict]:
    """Read-only graph/report invariant audit (SYSTEM_BEHAVIOR §27.6 / SCHEMA §21.8).

    Returns the list of violations (empty == clean). Each violation is a mapping
    with a frozen ``code``, the offending artifact's ``subject_id``, and a human
    ``detail``. The four enforced invariants:

    1. ``active_relation_insufficient_support`` — an ``active`` relation backed by
       fewer than 2 distinct ``verified`` source lineages (below the §21.5
       corroboration floor).
    2. ``reference_to_redirected_entity`` / ``endpoint_not_canonical`` — an
       ``active`` relation whose source/target endpoint is not a canonical entity
       (specifically ``redirected``, or any other non-canonical state).
    3. ``quarantined_relation_missing_reason`` — a ``quarantined`` relation missing
       its reason code and/or re-eval trigger (§27.3: quarantine is never an opaque
       discard pile).
    4. ``report_finding_without_active_support`` — a served (non-retired) community
       report that cites a relation (top-level or per-finding) that is not
       ``active`` (§27.6 report freshness).
    """
    violations: list[dict] = []
    with _maybe_conn(db_path, conn) as conn:
        entity_state = {
            str(r["id"]): str(r["resolution_state"])
            for r in conn.execute(
                "SELECT id, resolution_state FROM graph_entities"
            ).fetchall()
        }
        verified_lineages = {
            str(r["relation_id"]): int(r["n"])
            for r in conn.execute(
                "SELECT relation_id, COUNT(DISTINCT source_lineage_hash) AS n "
                "FROM graph_relation_supports WHERE support_status = 'verified' "
                "GROUP BY relation_id"
            ).fetchall()
        }
        rel_status: dict[str, str] = {}
        for r in conn.execute(
            "SELECT id, source_entity_id, target_entity_id, lifecycle_status, "
            "quarantine_reason, reeval_trigger FROM graph_relations ORDER BY id"
        ).fetchall():
            rid = str(r["id"])
            status = str(r["lifecycle_status"])
            rel_status[rid] = status
            if status == "active":
                lineages = verified_lineages.get(rid, 0)
                if lineages < _RELATION_CORROBORATION_THRESHOLD:
                    violations.append({
                        "code": "active_relation_insufficient_support",
                        "subject_id": rid,
                        "detail": (
                            f"{lineages} verified independent source lineages "
                            f"(< {_RELATION_CORROBORATION_THRESHOLD})"
                        ),
                    })
                for endpoint in (
                    str(r["source_entity_id"]), str(r["target_entity_id"])
                ):
                    state = entity_state.get(endpoint)
                    # ONLY an explicitly-canonical endpoint is admissible. A missing
                    # endpoint (state is None — a dangling reference to an entity that
                    # does not exist in graph_entities) is NOT canonical and must be
                    # flagged: whitelisting None would silently ignore a broken
                    # authoritative reference (§27.6 "0 endpoints that are not
                    # canonical entities").
                    if state == "canonical":
                        continue
                    code = (
                        "reference_to_redirected_entity"
                        if state == "redirected"
                        else "endpoint_not_canonical"
                    )
                    detail = (
                        f"endpoint {endpoint} does not exist in graph_entities "
                        "(dangling reference)"
                        if state is None
                        else f"endpoint {endpoint} resolution_state={state}"
                    )
                    violations.append({
                        "code": code,
                        "subject_id": rid,
                        "detail": detail,
                    })
            elif status == "quarantined":
                reason = str(r["quarantine_reason"] or "")
                trigger = str(r["reeval_trigger"] or "")
                if not reason or not trigger:
                    violations.append({
                        "code": "quarantined_relation_missing_reason",
                        "subject_id": rid,
                        "detail": (
                            "quarantined relation missing reason code "
                            "and/or re-eval trigger"
                        ),
                    })

        for rep in conn.execute(
            "SELECT id, relation_ids, finding_json FROM community_reports "
            "WHERE retired_at IS NULL ORDER BY id"
        ).fetchall():
            cited: set[str] = {str(x) for x in _loads_list(rep["relation_ids"])}
            for finding in _loads_list(rep["finding_json"]):
                if isinstance(finding, dict):
                    cited.update(str(x) for x in (finding.get("relation_ids") or []))
            # A cited relation that is missing or not `active` is not eligible claim
            # support. `.get(rid)` defaults to None (missing) so a dangling citation
            # is flagged too.
            stale = sorted(c for c in cited if rel_status.get(c) != "active")
            if stale:
                violations.append({
                    "code": "report_finding_without_active_support",
                    "subject_id": str(rep["id"]),
                    "detail": f"cites non-active relations: {stale}",
                })

    violations.sort(key=lambda v: (v["code"], v["subject_id"]))
    return violations


# --- memory_paths ----------------------------------------------------


def record_memory_path(
    db_path: Path,
    *,
    query_hash: str,
    route: str,
    path: list[dict],
    start_node_id: str = "",
    score: float = 0.0,
    source_span_ids: list[str] | None = None,
) -> str:
    with connect(db_path) as conn:
        path_id = _new_id("MPATH")
        conn.execute(
            """
            INSERT INTO memory_paths
                (id, query_hash, route, start_node_id, path_json, score,
                 source_span_ids, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                path_id, query_hash, route, start_node_id, json.dumps(path),
                score, json.dumps(source_span_ids or []), _now_iso(),
            ),
        )
        return path_id


def list_memory_paths(db_path: Path, query_hash: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM memory_paths WHERE query_hash = ? ORDER BY score DESC",
            (query_hash,),
        ).fetchall()
        out = []
        for row in rows:
            data = dict(row)
            data["path"] = _loads_list(data.pop("path_json", "[]"))
            data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
            out.append(data)
        return out


# --- prompt_runs -----------------------------------------------------


def record_prompt_run(
    db_path: Path,
    *,
    prompt_id: str,
    prompt_version: str,
    family: str,
    role: str = "",
    model_provider: str = "",
    model_name: str = "",
    input_hash: str,
    source_ids: list[int] | None = None,
    source_span_ids: list[str] | None = None,
    curate_spec_hash: str = "",
    query_trace_id: str | None = None,
) -> str:
    """Start a prompt run. Returns the PTR- trace id; status begins 'pending'."""
    with connect(db_path) as conn:
        trace_id = _new_id("PTR")
        conn.execute(
            """
            INSERT INTO prompt_runs
                (trace_id, prompt_id, prompt_version, family, role,
                 model_provider, model_name, input_hash, source_ids,
                 source_span_ids, curate_spec_hash, query_trace_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace_id, prompt_id, prompt_version, family, role,
                model_provider, model_name, input_hash,
                json.dumps(source_ids or []), json.dumps(source_span_ids or []),
                curate_spec_hash, query_trace_id, _now_iso(),
            ),
        )
        return trace_id


def finish_prompt_run(
    db_path: Path,
    trace_id: str,
    *,
    output_hash: str = "",
    validator_status: str = "ok",
    validator_errors: list[str] | None = None,
    retry_count: int = 0,
    latency_ms: int | None = None,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE prompt_runs
               SET output_hash = ?, validator_status = ?, validator_errors = ?,
                   retry_count = ?, latency_ms = ?, finished_at = ?
             WHERE trace_id = ?
            """,
            (
                output_hash, validator_status,
                json.dumps(validator_errors or []), retry_count, latency_ms,
                _now_iso(), trace_id,
            ),
        )


def _decode_prompt_run_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["validator_errors"] = _loads_list(data.get("validator_errors"))
    data["source_ids"] = _loads_list(data.get("source_ids"))
    data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
    return data


def get_prompt_run(db_path: Path, trace_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM prompt_runs WHERE trace_id = ?", (trace_id,)
        ).fetchone()
        return _decode_prompt_run_row(row) if row else None


def list_prompt_runs_for_query(db_path: Path, query_trace_id: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM prompt_runs WHERE query_trace_id = ? ORDER BY created_at",
            (query_trace_id,),
        ).fetchall()
        return [_decode_prompt_run_row(row) for row in rows]


# --- curation_plans --------------------------------------------------


def record_curation_plan(
    db_path: Path,
    *,
    workspace_id: str,
    curate_spec_hash: str,
    route: str,
    source_policy: dict,
    retrieval_policy: dict,
    workspace_path: str = "",
    project: str = "",
    prompt_profile: str = "",
    evidence_plan: dict | None = None,
    prompt_run_id: str | None = None,
) -> str:
    with connect(db_path) as conn:
        plan_id = _new_id("PLAN")
        conn.execute(
            """
            INSERT INTO curation_plans
                (id, workspace_id, workspace_path, project, curate_spec_hash,
                 route, source_policy_json, retrieval_policy_json, prompt_profile,
                 evidence_plan_json, prompt_run_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id, workspace_id, workspace_path, project, curate_spec_hash,
                route, json.dumps(source_policy), json.dumps(retrieval_policy),
                prompt_profile, json.dumps(evidence_plan or {}), prompt_run_id,
                _now_iso(),
            ),
        )
        return plan_id


def _decode_plan_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["source_policy"] = _loads_obj(data.pop("source_policy_json", "{}"))
    data["retrieval_policy"] = _loads_obj(data.pop("retrieval_policy_json", "{}"))
    data["evidence_plan"] = _loads_obj(data.pop("evidence_plan_json", "{}"))
    return data


def get_curation_plan(db_path: Path, workspace_id: str) -> dict | None:
    """Return the most recent curation plan for a workspace."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM curation_plans WHERE workspace_id = ? "
            "ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (workspace_id,),
        ).fetchone()
        return _decode_plan_row(row) if row else None


# --- insight_candidates ----------------------------------------------


def create_insight_candidate(
    db_path: Path,
    *,
    classification: str,
    statement: str,
    workspace_id: str = "",
    source_event_id: str = "",
    evidence: list | None = None,
    affected_node_ids: list[str] | None = None,
    confidence: float = 0.0,
    status: str = "pending",
    prompt_run_id: str | None = None,
) -> str:
    now = _now_iso()
    with connect(db_path) as conn:
        ins_id = _new_id("INS")
        conn.execute(
            """
            INSERT INTO insight_candidates
                (id, workspace_id, source_event_id, classification, statement,
                 evidence_json, affected_node_ids, confidence, status,
                 prompt_run_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ins_id, workspace_id, source_event_id, classification, statement,
                json.dumps(evidence or []), json.dumps(affected_node_ids or []),
                confidence, status, prompt_run_id, now, now,
            ),
        )
        return ins_id


def _decode_insight_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["evidence"] = _loads_list(data.pop("evidence_json", "[]"))
    data["affected_node_ids"] = _loads_list(data.get("affected_node_ids"))
    return data


def list_insight_candidates(
    db_path: Path,
    *,
    workspace_id: str | None = None,
    status: str = "pending",
) -> list[dict]:
    clauses = []
    params: list[object] = []
    if workspace_id is not None:
        clauses.append("workspace_id = ?")
        params.append(workspace_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM insight_candidates{where} ORDER BY created_at DESC",
            tuple(params),
        ).fetchall()
        return [_decode_insight_row(row) for row in rows]


def get_insight_candidate(db_path: Path, insight_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM insight_candidates WHERE id = ?", (insight_id,)
        ).fetchone()
        return _decode_insight_row(row) if row else None


def update_insight_candidate_status(
    db_path: Path, insight_id: str, *, status: str
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE insight_candidates SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now_iso(), insight_id),
        )


# --- artifact_dependencies -------------------------------------------


def record_artifact_dependency(
    db_path: Path,
    *,
    artifact_id: str,
    artifact_type: str,
    depends_on_id: str,
    depends_on_type: str,
    dependency_hash: str,
    conn: sqlite3.Connection | None = None,
) -> None:
    with _maybe_conn(db_path, conn) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO artifact_dependencies
                (artifact_id, artifact_type, depends_on_id, depends_on_type,
                 dependency_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id, artifact_type, depends_on_id, depends_on_type,
                dependency_hash, _now_iso(),
            ),
        )


def dependents_of(db_path: Path, depends_on_id: str) -> list[dict]:
    """Return artifacts that depend on the given record (for invalidation)."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM artifact_dependencies WHERE depends_on_id = ?",
            (depends_on_id,),
        ).fetchall()
        return [dict(row) for row in rows]


# --- synthesis_nodes (L4 shared synthesis) ---------------------------


def upsert_synthesis_node(
    db_path: Path,
    *,
    title: str,
    statement: str,
    dependency_hash: str,
    full_content: str = "",
    community_report_ids: list[str] | None = None,
    concept_ids: list[str] | None = None,
    source_span_ids: list[str] | None = None,
    confidence: float = 0.0,
    prompt_run_id: str | None = None,
    node_id: str | None = None,
) -> str:
    """Insert or replace a shared synthesis node (SYN-)."""
    now = _now_iso()
    with connect(db_path) as conn:
        existing = None
        if node_id:
            existing = conn.execute(
                "SELECT created_at FROM synthesis_nodes WHERE id = ?", (node_id,)
            ).fetchone()
        syn_id = node_id or _new_id("SYN")
        created_at = str(existing["created_at"]) if existing else now
        conn.execute(
            """
            INSERT OR REPLACE INTO synthesis_nodes
                (id, title, statement, full_content, community_report_ids,
                 concept_ids, source_span_ids, confidence, prompt_run_id,
                 dependency_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                syn_id, title, statement, full_content,
                json.dumps(community_report_ids or []), json.dumps(concept_ids or []),
                json.dumps(source_span_ids or []), confidence, prompt_run_id,
                dependency_hash, created_at, now,
            ),
        )
        return syn_id


def _decode_synthesis_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["community_report_ids"] = _loads_list(data.get("community_report_ids"))
    data["concept_ids"] = _loads_list(data.get("concept_ids"))
    data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
    return data


def list_synthesis_nodes(db_path: Path) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM synthesis_nodes ORDER BY confidence DESC, created_at"
        ).fetchall()
        return [_decode_synthesis_row(row) for row in rows]


def get_synthesis_node(db_path: Path, node_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM synthesis_nodes WHERE id = ?", (node_id,)
        ).fetchone()
        return _decode_synthesis_row(row) if row else None


def clear_synthesis_nodes(db_path: Path) -> None:
    """Delete every synthesis node (the shared L4 layer is regenerated wholesale)."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM synthesis_nodes")


# ---------------------------------------------------------------------------
# v0.3.2 DB-native search accessors (SCHEMA §11.12–§11.16)
# ---------------------------------------------------------------------------


def upsert_search_document(
    db_path: Path,
    *,
    record_type: str,
    record_id: str,
    body: str,
    content_hash: str,
    dependency_hash: str,
    doc_id: str | None = None,
    source_id: int | None = None,
    projection_path: str = "",
    title: str = "",
    language: str = "",
    provenance: dict | None = None,
) -> str:
    """Insert/replace one row of the authoritative search corpus and re-index FTS."""
    did = doc_id or f"DOC-{record_type}-{record_id}"
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO search_documents
                (doc_id, record_type, record_id, source_id, projection_path, title,
                 body, language, content_hash, dependency_hash, provenance_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                did, record_type, record_id, source_id, projection_path, title,
                body, language, content_hash, dependency_hash,
                json.dumps(provenance or {}), _now_iso(),
            ),
        )
        for tbl in ("search_documents_fts", "search_documents_fts_tri"):
            conn.execute(f"DELETE FROM {tbl} WHERE doc_id = ?", (did,))
            conn.execute(
                f"INSERT INTO {tbl} (title, body, record_type, record_id, doc_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (title, body, record_type, record_id, did),
            )
    return did


def _decode_search_document(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["provenance"] = _loads_obj(data.pop("provenance_json", "{}"))
    return data


def get_search_document(db_path: Path, doc_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM search_documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        return _decode_search_document(row) if row else None


def list_search_documents(db_path: Path) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM search_documents ORDER BY doc_id").fetchall()
        return [_decode_search_document(r) for r in rows]


def delete_search_document(db_path: Path, doc_id: str) -> None:
    """Delete a search document (cascades chunks/embeddings) and its FTS rows."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM search_documents WHERE doc_id = ?", (doc_id,))
        for tbl in ("search_documents_fts", "search_documents_fts_tri"):
            conn.execute(f"DELETE FROM {tbl} WHERE doc_id = ?", (doc_id,))


def clear_search_corpus(db_path: Path) -> None:
    """Drop the entire derived search corpus (rebuilt by `wiki reindex`)."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM search_documents")  # cascades chunks → embeddings
        conn.execute("DELETE FROM search_documents_fts")
        conn.execute("DELETE FROM search_documents_fts_tri")


def fts_search(
    db_path: Path,
    match: str,
    *,
    trigram: bool = False,
    limit: int = 50,
) -> list[dict]:
    """BM25 lexical search over one FTS table. Lower bm25() = more relevant.

    Returns rows: doc_id, record_type, record_id, title, score (rank, ascending).
    """
    table = "search_documents_fts_tri" if trigram else "search_documents_fts"
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT doc_id, record_type, record_id, title, bm25({table}) AS score
            FROM {table}
            WHERE {table} MATCH ?
            ORDER BY score
            LIMIT ?
            """,
            (match, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_search_chunk(
    db_path: Path,
    *,
    chunk_id: str,
    doc_id: str,
    record_type: str,
    record_id: str,
    chunk_index: int,
    char_start: int,
    char_end: int,
    text: str,
    input_hash: str,
    source_span_ids: list[str] | None = None,
    provenance: dict | None = None,
) -> str:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO search_chunks
                (chunk_id, doc_id, record_type, record_id, chunk_index, char_start,
                 char_end, text, input_hash, source_span_ids, provenance_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk_id, doc_id, record_type, record_id, chunk_index, char_start,
                char_end, text, input_hash, json.dumps(source_span_ids or []),
                json.dumps(provenance or {}),
            ),
        )
    return chunk_id


def _decode_search_chunk(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
    data["provenance"] = _loads_obj(data.pop("provenance_json", "{}"))
    return data


def list_search_chunks_for_doc(db_path: Path, doc_id: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM search_chunks WHERE doc_id = ? ORDER BY chunk_index", (doc_id,)
        ).fetchall()
        return [_decode_search_chunk(r) for r in rows]


def get_search_chunk(db_path: Path, chunk_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM search_chunks WHERE chunk_id = ?", (chunk_id,)
        ).fetchone()
        return _decode_search_chunk(row) if row else None


def upsert_search_embedding(
    db_path: Path,
    *,
    chunk_id: str,
    provider: str,
    model: str,
    dim: int,
    vector: bytes,
    input_hash: str,
    dependency_hash: str,
    status: str = "ready",
    error: str = "",
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO search_embeddings
                (chunk_id, provider, model, dim, vector, input_hash, dependency_hash,
                 status, error, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chunk_id, provider, model, dim, vector, input_hash, dependency_hash,
             status, error, _now_iso()),
        )


def get_search_embeddings(db_path: Path, provider: str, model: str) -> list[dict]:
    """Return all ready embeddings for one provider/model (chunk_id, dim, vector)."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT chunk_id, dim, vector, input_hash, dependency_hash FROM search_embeddings "
            "WHERE provider = ? AND model = ? AND status = 'ready'",
            (provider, model),
        ).fetchall()
        return [dict(r) for r in rows]


def has_search_embeddings(db_path: Path, provider: str, model: str) -> bool:
    """Cheap probe: True if any ready embedding exists for this provider/model."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM search_embeddings WHERE provider = ? AND model = ? "
            "AND status = 'ready' LIMIT 1",
            (provider, model),
        ).fetchone()
        return row is not None


def get_index_meta(db_path: Path, key: str, default: str | None = None) -> str | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM search_index_meta WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row else default


def set_index_meta(db_path: Path, key: str, value: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO search_index_meta (key, value) VALUES (?, ?)",
            (key, value),
        )


def new_query_trace_id() -> str:
    """Generate a durable QTR- query trace id without writing a row."""
    return _new_id("QTR")


def insert_query_trace(
    db_path: Path,
    *,
    route: str,
    question_hash: str,
    workspace_id: str = "default",
    route_reason: str = "",
    evidence: list | None = None,
    source_span_ids: list[str] | None = None,
    community_report_ids: list[str] | None = None,
    synthesis_node_ids: list[str] | None = None,
    memory_path_ids: list[str] | None = None,
    prompt_trace_ids: list[str] | None = None,
    insight_candidate_ids: list[str] | None = None,
    retrieval_trace: dict | None = None,
    warnings: list[str] | None = None,
    latency_ms: int | None = None,
    trace_id: str | None = None,
    created_at: str | None = None,
) -> str:
    """Persist a durable QTR- query trace. Returns the trace_id."""
    tid = trace_id or _new_id("QTR")
    ts = created_at or _now_iso()
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO query_traces
                (trace_id, workspace_id, question_hash, route, route_reason,
                 evidence_json, source_span_ids, community_report_ids,
                 synthesis_node_ids, memory_path_ids, prompt_trace_ids,
                 insight_candidate_ids, retrieval_trace_json, warnings_json,
                 latency_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tid, workspace_id, question_hash, route, route_reason,
                json.dumps(evidence or []), json.dumps(source_span_ids or []),
                json.dumps(community_report_ids or []), json.dumps(synthesis_node_ids or []),
                json.dumps(memory_path_ids or []), json.dumps(prompt_trace_ids or []),
                json.dumps(insight_candidate_ids or []), json.dumps(retrieval_trace or {}),
                json.dumps(warnings or []), latency_ms, ts,
            ),
        )
    return tid


def _decode_query_trace(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["evidence"] = _loads_list(data.pop("evidence_json", "[]"))
    for key in (
        "source_span_ids", "community_report_ids", "synthesis_node_ids",
        "memory_path_ids", "prompt_trace_ids", "insight_candidate_ids",
    ):
        data[key] = _loads_list(data.get(key))
    data["retrieval_trace"] = _loads_obj(data.pop("retrieval_trace_json", "{}"))
    data["warnings"] = _loads_list(data.pop("warnings_json", "[]"))
    return data


def list_query_traces(
    db_path: Path, workspace_id: str | None = None, limit: int = 50
) -> list[dict]:
    with connect(db_path) as conn:
        if workspace_id:
            rows = conn.execute(
                "SELECT * FROM query_traces WHERE workspace_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (workspace_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM query_traces ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_decode_query_trace(r) for r in rows]


def get_query_trace(db_path: Path, trace_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM query_traces WHERE trace_id = ?", (trace_id,)
        ).fetchone()
        return _decode_query_trace(row) if row else None


def get_query_trace_by_context_pack(db_path: Path, pack_id: str) -> dict | None:
    """Fetch the query trace whose ContextService root pack id matches ``pack_id``.

    Prefer SQLite JSON extraction so filtering happens in the database. Some
    SQLite builds may omit JSON1, so fall back to a narrow LIKE candidate query
    followed by exact decoded validation. The fallback avoids the old recent-trace
    scan and only decodes rows whose JSON contains the requested pack id string.
    """
    if not pack_id:
        return None
    with connect(db_path) as conn:
        try:
            row = conn.execute(
                """
                SELECT * FROM query_traces
                WHERE json_extract(retrieval_trace_json, '$.context_service.pack_id') = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (pack_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
        if row is not None:
            return _decode_query_trace(row)

        candidates = conn.execute(
            """
            SELECT * FROM query_traces
            WHERE retrieval_trace_json LIKE ?
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (f"%{pack_id}%",),
        ).fetchall()
    for candidate in candidates:
        decoded = _decode_query_trace(candidate)
        context = (decoded.get("retrieval_trace") or {}).get("context_service")
        if isinstance(context, dict) and context.get("pack_id") == pack_id:
            return decoded
    return None
