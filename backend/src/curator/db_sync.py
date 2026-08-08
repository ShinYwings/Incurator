"""Cross-device SQLite knowledge synchronization via JSONL export/import.

Usage:
    from curator.db_sync import export_knowledge, import_knowledge, record_tombstone
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, Callable as _Callable, Mapping

from . import db

logger = logging.getLogger(__name__)

SCHEMA_VERSION = db.SCHEMA_VERSION

# Source locators are portable in schema v11, so no source column is protected
# as device-local during LWW merge.
_DEVICE_LOCAL_COLUMNS: dict[str, set[str]] = {}

# Device-local sync bookkeeping lives in the backend cache, outside the synced
# vault. The resolved vault root is hashed to isolate multiple vaults without
# exposing their absolute paths in cache filenames.
SYNC_STATE_DIR = "sync_state"

# Tables exported in this order. deleted_records must be first so tombstones
# are applied before upserts during import.
SYNC_TABLES: list[str] = [
    "deleted_records",
    "sources",
    "source_pages",
    "source_pdf_pages",
    "atoms",
    "concepts",
    "synthesis_nodes",
    "source_spans",
    "knowledge_units",
    "claim_supports",
    "compiler_generations",
    "graph_entities",
    "graph_relations",
    "graph_relation_supports",
    "entity_aliases",
    "entity_merge_proposals",
    "entity_resolution_lineage",
    "community_reports",
    "dag_edges",
    "artifact_dependencies",
    "curation_plans",
    "insight_candidates",
    "prompt_runs",
    "query_traces",
    "memory_paths",
    "synthesis",
]

# Tables that must never appear in an export file.
EXCLUDE_TABLES: frozenset[str] = frozenset([
    "search_embeddings",
    "search_index_meta",
    "ingest_jobs",
    "job_events",
    "page_hashes",
    "search_documents",
    "search_chunks",
    "search_documents_fts",
    "search_documents_fts_tri",
    "schema_version",
    "ingest_runs",
])

# Column used per table to determine which version is newer (LWW).
_UPDATED_AT_COL: dict[str, str] = {
    "sources": "updated_at",
    "atoms": "last_updated",
    "concepts": "last_updated",
    "synthesis_nodes": "updated_at",
    "source_spans": "created_at",
    "knowledge_units": "updated_at",
    "claim_supports": "updated_at",
    "compiler_generations": "updated_at",
    "graph_entities": "updated_at",
    "graph_relations": "updated_at",
    "graph_relation_supports": "updated_at",
    "entity_aliases": "updated_at",
    "entity_merge_proposals": "updated_at",
    # entity_resolution_lineage is intentionally absent: it has no updated_at
    # column (immutable reversal lineage), so it always-upserts on import.
    "community_reports": "updated_at",
    "memory_paths": "created_at",
    "prompt_runs": "created_at",
    "dag_edges": "created_at",
    "curation_plans": "created_at",
    "insight_candidates": "updated_at",
    "artifact_dependencies": "created_at",
    "synthesis": "last_updated",
    "query_traces": "created_at",
    "source_pages": "at",
    "source_pdf_pages": "extracted_at",
    "deleted_records": "deleted_at",
}

# Per-table overrides for computing the remote timestamp from an exported row dict.
# Each callable receives the row dict and returns the effective timestamp string.
_REMOTE_TS_FN: dict[str, _Callable[[dict], str]] = {
    "sources": lambda row: row.get("updated_at") or "",
}


def _span_metadata_stamps(metadata: object) -> list[str]:
    """Every timestamp buried in a source span's ``metadata`` JSON."""
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata or "{}")
        except (ValueError, TypeError):
            return []
    if not isinstance(metadata, dict):
        return []

    stamps: list[str] = []
    loss = metadata.get("loss")
    if isinstance(loss, dict) and loss.get("classified_at"):
        stamps.append(str(loss["classified_at"]))
    recoveries = metadata.get("formula_recovery")
    if isinstance(recoveries, list):
        for candidate in recoveries:
            if isinstance(candidate, dict) and candidate.get("created_at"):
                stamps.append(str(candidate["created_at"]))
    return stamps


def _source_span_revision(row: dict) -> str:
    """Effective LWW clock for a source span.

    `source_spans` has no `updated_at` and its `created_at` is immutable, but
    `metadata` IS mutated in place — by `recover_formula()` (SCHEMA §20.4,
    shipped v0.8.0) and by the `loss` record (§20.4a). Comparing the immutable
    column makes those writes tie, so `_lw_upsert`'s strict `>` skips them and a
    peer silently drops the change; `_local_max_ts` never moves either, so the
    writing device does not even offer it.

    Deriving the revision from the metadata timestamps fixes both halves
    without a new column — this codebase has no `ALTER TABLE` path, so an
    existing vault could not receive one anyway. `created_at` stays in the max,
    so a span with no metadata behaves exactly as before.
    """
    stamps = [str(row.get("created_at") or "")]
    stamps.extend(_span_metadata_stamps(row.get("metadata")))
    return max(stamps, key=_timestamp_key)


# Tables whose LWW clock is not a plain column.
#
# NEVER read `_UPDATED_AT_COL` directly to rank two versions of a row — go
# through `row_revision()` below. Every site that compares timestamps must use
# the same rule, or local and remote get ranked differently and a write is
# dropped on one path while surviving on another. The sites are: the
# `_lw_upsert` comparison, `_local_max_ts` (the export gate), the `--since`
# export filter, `_row_is_blocked_by_tombstone`, `_apply_tombstone`, and
# `clear_row_tombstone_on_connection`.
#: PRAGMA results per table; the schema does not change at runtime.
_UNIQUE_INDEX_CACHE: dict[str, list[tuple[str, ...]]] = {}

_REVISION_FN: dict[str, _Callable[[dict], str]] = {
    "source_spans": _source_span_revision,
}


def row_revision(table_name: str, row: Mapping[str, Any] | dict) -> str:
    """The timestamp that ranks this row against another version of it.

    The single entry point for "how new is this row". For most tables that is
    just `_UPDATED_AT_COL`; for tables in `_REVISION_FN` the column is immutable
    and the real clock is derived (see `_source_span_revision`).
    """
    revision_fn = _REVISION_FN.get(table_name)
    if revision_fn is not None:
        return revision_fn(dict(row))
    remote_ts_fn = _REMOTE_TS_FN.get(table_name)
    if remote_ts_fn is not None:
        return remote_ts_fn(dict(row))
    updated_col = _UPDATED_AT_COL.get(table_name)
    if updated_col is None:
        return ""
    return str(_row_value(row, updated_col, None) or "")


def revision_select_columns(table_name: str) -> str:
    """Columns a query must SELECT for `row_revision` to work on its rows."""
    updated_col = _UPDATED_AT_COL.get(table_name)
    if _REVISION_FN.get(table_name) is not None:
        # Derived clocks read `metadata`, so a bare `SELECT {updated_col}` is
        # not enough to rank the row.
        return "*"
    return updated_col or "*"

# Scalar transport key per table. Composite tables use their full PRAGMA-derived
# primary key for row merge and the closed portable-key registry for tombstones.
_PK_COL: dict[str, str | None] = {
    "sources": "sync_key",
    "atoms": "id",
    "concepts": "id",
    "synthesis_nodes": "id",
    "source_spans": "id",
    "knowledge_units": "id",
    "claim_supports": None,
    "compiler_generations": "id",
    "graph_entities": "id",
    "graph_relations": "id",
    "graph_relation_supports": None,
    "entity_aliases": "id",
    "entity_merge_proposals": "id",
    "entity_resolution_lineage": None,
    "community_reports": "id",
    "memory_paths": "id",
    "prompt_runs": "trace_id",
    "dag_edges": "id",
    "curation_plans": "id",
    "insight_candidates": "id",
    "artifact_dependencies": None,
    "synthesis": "id",
    "query_traces": "trace_id",
    "source_pages": None,
    "source_pdf_pages": None,
    "deleted_records": None,  # composite PK — handled separately
}


@dataclass(frozen=True)
class _CompositeKeySpec:
    transport_fields: tuple[tuple[str, type], ...]
    physical_columns: tuple[str, ...]


_COMPOSITE_KEY_SPECS: dict[str, _CompositeKeySpec] = {
    "source_pages": _CompositeKeySpec(
        (
            ("source_sync_key", str),
            ("wiki_path", str),
            ("at", str),
        ),
        ("source_id", "wiki_path", "at"),
    ),
    "source_pdf_pages": _CompositeKeySpec(
        (
            ("source_sync_key", str),
            ("page_number", int),
        ),
        ("source_id", "page_number"),
    ),
    "claim_supports": _CompositeKeySpec(
        (
            ("knowledge_unit_id", str),
            ("source_span_id", str),
            ("support_role", str),
        ),
        ("knowledge_unit_id", "source_span_id", "support_role"),
    ),
    "graph_relation_supports": _CompositeKeySpec(
        (
            ("relation_id", str),
            ("knowledge_unit_id", str),
            ("support_hash", str),
        ),
        ("relation_id", "knowledge_unit_id", "support_hash"),
    ),
    "entity_resolution_lineage": _CompositeKeySpec(
        (
            ("decision_id", str),
            ("origin_entity_id", str),
        ),
        ("decision_id", "origin_entity_id"),
    ),
    "artifact_dependencies": _CompositeKeySpec(
        (
            ("artifact_id", str),
            ("depends_on_id", str),
            ("depends_on_type", str),
        ),
        ("artifact_id", "depends_on_id", "depends_on_type"),
    ),
}


def _canonical_composite_key(
    table_name: str,
    key: Mapping[str, object],
) -> str:
    spec = _COMPOSITE_KEY_SPECS.get(table_name)
    if spec is None:
        raise ValueError(f"Table {table_name!r} has no composite tombstone key")

    expected = {name: value_type for name, value_type in spec.transport_fields}
    actual_fields = set(key)
    expected_fields = set(expected)
    if actual_fields != expected_fields:
        missing = sorted(expected_fields - actual_fields)
        extra = sorted(actual_fields - expected_fields)
        detail = []
        if missing:
            detail.append(f"missing fields: {', '.join(missing)}")
        if extra:
            detail.append(f"unknown fields: {', '.join(extra)}")
        raise ValueError(
            f"Invalid composite tombstone for {table_name!r}: {'; '.join(detail)}"
        )

    normalized: dict[str, object] = {}
    for name, value_type in spec.transport_fields:
        value = key[name]
        if type(value) is not value_type:
            raise ValueError(
                f"Invalid composite tombstone for {table_name!r}: "
                f"{name} must be {value_type.__name__}"
            )
        if value_type is str and not str(value):
            raise ValueError(
                f"Invalid composite tombstone for {table_name!r}: "
                f"{name} must not be empty"
            )
        normalized[name] = value

    return json.dumps(
        {"key": normalized, "v": 1},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate JSON field {name!r}")
        result[name] = value
    return result


def _decode_composite_key(
    table_name: str,
    token: str,
) -> dict[str, object]:
    try:
        payload = json.loads(token, object_pairs_hook=_unique_json_object)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            f"Invalid composite tombstone for {table_name!r}: "
            f"record_id {token!r} is not supported canonical JSON ({exc})"
        ) from exc
    if type(payload) is not dict or set(payload) != {"key", "v"}:
        raise ValueError(
            f"Invalid composite tombstone for {table_name!r}: "
            "payload must contain exactly 'key' and 'v'"
        )
    if type(payload["v"]) is not int or payload["v"] != 1:
        raise ValueError(
            f"Invalid composite tombstone for {table_name!r}: "
            f"unsupported token version {payload['v']!r}"
        )
    key = payload["key"]
    if type(key) is not dict:
        raise ValueError(
            f"Invalid composite tombstone for {table_name!r}: key must be an object"
        )
    canonical = _canonical_composite_key(table_name, key)
    if token != canonical:
        raise ValueError(
            f"Invalid composite tombstone for {table_name!r}: "
            "record_id is valid JSON but not canonical"
        )
    return key


_MISSING = object()


def _row_value(
    row: Mapping[str, Any],
    name: str,
    default: object = _MISSING,
) -> Any:
    try:
        return row[name]
    except (IndexError, KeyError):
        if default is _MISSING:
            raise
        return default


def _record_key_for_row(
    conn: "db.sqlite3.Connection",
    table_name: str,
    row: Mapping[str, Any],
    *,
    source_sync_key: str | None = None,
) -> str:
    spec = _COMPOSITE_KEY_SPECS.get(table_name)
    if spec is None:
        pk_col = _PK_COL.get(table_name)
        if not pk_col:
            raise ValueError(f"Table {table_name!r} has no transport key")
        value = _row_value(row, pk_col, None)
        token = str(value or "")
        if not token:
            raise ValueError(
                f"Table {table_name!r} row is missing transport key {pk_col!r}"
            )
        return token

    key: dict[str, object] = {}
    for field_name, _value_type in spec.transport_fields:
        if field_name == "source_sync_key":
            if source_sync_key is None:
                source_id = _row_value(row, "source_id", None)
                source = conn.execute(
                    "SELECT sync_key FROM sources WHERE id = ?",
                    (source_id,),
                ).fetchone()
                if source is None or not str(source["sync_key"] or ""):
                    raise ValueError(
                        f"Table {table_name!r} row references unknown local "
                        f"source_id {source_id!r}"
                    )
                source_sync_key = str(source["sync_key"])
            key[field_name] = source_sync_key
        else:
            value = _row_value(row, field_name, _MISSING)
            if value is _MISSING:
                raise ValueError(
                    f"Table {table_name!r} row is missing key field {field_name!r}"
                )
            key[field_name] = value
    return _canonical_composite_key(table_name, key)


def _physical_key_for_token(
    conn: "db.sqlite3.Connection",
    table_name: str,
    token: str,
) -> tuple[tuple[str, ...], tuple[object, ...] | None]:
    spec = _COMPOSITE_KEY_SPECS.get(table_name)
    if spec is None:
        pk_col = _PK_COL.get(table_name)
        if not pk_col:
            raise ValueError(f"Table {table_name!r} has no transport key")
        return (pk_col,), (token,)

    key = _decode_composite_key(table_name, token)
    values: list[object] = []
    for column in spec.physical_columns:
        if column == "source_id":
            source = conn.execute(
                "SELECT id FROM sources WHERE sync_key = ?",
                (key["source_sync_key"],),
            ).fetchone()
            if source is None:
                return spec.physical_columns, None
            values.append(int(source["id"]))
        else:
            values.append(key[column])
    return spec.physical_columns, tuple(values)


def _validate_tombstone_token(table_name: str, token: object) -> str:
    if not isinstance(token, str) or not token:
        raise ValueError(
            f"Invalid tombstone for {table_name!r}: record_id must be a non-empty string"
        )
    if table_name in _COMPOSITE_KEY_SPECS:
        _decode_composite_key(table_name, token)
    return token


def _require_timestamp(value: object, *, context: str) -> str:
    if (
        not isinstance(value, str)
        or _timestamp_key(value) == datetime.min.replace(tzinfo=timezone.utc)
    ):
        raise ValueError(f"{context} must be a valid timestamp")
    return value


@dataclass
class ExportStats:
    total_rows: int = 0
    rows_by_table: dict[str, int] = field(default_factory=dict)


@dataclass
class ImportStats:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    deleted: int = 0
    #: Rows the database refused (malformed or truncated peer export). Counted
    #: separately because reporting them as `inserted` claims data arrived that
    #: was silently dropped (B2).
    rejected: int = 0
    dry_run: bool = False


class SyncError(RuntimeError):
    """Base error for a sync pass that must be surfaced to callers."""


class SyncStateError(SyncError):
    """The existing device-local sync state cannot be trusted."""


class AutosyncError(SyncError):
    """A peer or conflict file could not complete its sync step."""


def record_tombstone_on_connection(
    conn: "db.sqlite3.Connection",
    table_name: str,
    record_id: str,
    *,
    deleted_at: str | None = None,
) -> None:
    """Record a canonical delete in the caller's transaction."""
    if table_name not in SYNC_TABLES or table_name == "deleted_records":
        raise ValueError(f"Table {table_name!r} is not syncable")
    record_id = _validate_tombstone_token(table_name, record_id)
    now = deleted_at or datetime.now(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    now = _require_timestamp(
        now,
        context=f"Tombstone for {table_name!r} deleted_at",
    )
    existing = conn.execute(
        "SELECT deleted_at FROM deleted_records "
        "WHERE table_name = ? AND record_id = ?",
        (table_name, record_id),
    ).fetchone()
    if existing is not None and _timestamp_key(existing["deleted_at"]) >= _timestamp_key(
        now
    ):
        return
    conn.execute(
        "INSERT OR REPLACE INTO deleted_records (table_name, record_id, deleted_at)"
        " VALUES (?, ?, ?)",
        (table_name, record_id, now),
    )


def record_row_tombstone_on_connection(
    conn: "db.sqlite3.Connection",
    table_name: str,
    row: Mapping[str, Any],
    *,
    deleted_at: str | None = None,
) -> str:
    """Record the portable key of a row being hard-deleted by a local writer."""
    token = _record_key_for_row(conn, table_name, row)
    record_tombstone_on_connection(
        conn,
        table_name,
        token,
        deleted_at=deleted_at,
    )
    return token


def clear_row_tombstone_on_connection(
    conn: "db.sqlite3.Connection",
    table_name: str,
    row: Mapping[str, Any],
) -> None:
    """Make an explicit local reinsert newer than its exact tombstone."""
    token = _record_key_for_row(conn, table_name, row)
    tombstone = conn.execute(
        "SELECT deleted_at FROM deleted_records "
        "WHERE table_name = ? AND record_id = ?",
        (table_name, token),
    ).fetchone()
    if tombstone is None:
        return

    updated_col = _UPDATED_AT_COL.get(table_name)
    if updated_col is None:
        raise ValueError(
            f"Cannot reinsert tombstoned immutable row in {table_name!r}"
        )
    key_columns, key_values = _physical_key_for_token(
        conn,
        table_name,
        token,
    )
    if key_values is None:
        return
    where = " AND ".join(f"{column} IS ?" for column in key_columns)
    current = conn.execute(
        f"SELECT {revision_select_columns(table_name)} FROM {table_name} WHERE {where}",
        key_values,
    ).fetchone()
    if current is None:
        return
    deleted_at = _require_timestamp(
        tombstone["deleted_at"],
        context=f"Tombstone for {table_name!r} deleted_at",
    )
    current_revision = _require_timestamp(
        row_revision(table_name, dict(current)),
        context=f"Table {table_name!r} row revision",
    )
    if _timestamp_key(deleted_at) >= _timestamp_key(current_revision):
        # The row must end up strictly newer than the tombstone that cleared it.
        # For a derived clock the write still lands on the physical column; the
        # derivation takes the max, so bumping it is enough to win.
        successor = db.strict_successor_timestamp(deleted_at, current_revision)
        conn.execute(
            f"UPDATE {table_name} SET {updated_col} = ? WHERE {where}",
            (successor, *key_values),
        )
        # A timestamp that is itself part of the primary key changes the
        # row's identity. Preserve the old-key tombstone; the new row no
        # longer conflicts with it.
        if updated_col in key_columns:
            return

    conn.execute(
        "DELETE FROM deleted_records WHERE table_name = ? AND record_id = ?",
        (table_name, token),
    )


def delete_rows_with_tombstones_on_connection(
    conn: "db.sqlite3.Connection",
    table_name: str,
    where_sql: str,
    params: tuple[object, ...],
    *,
    deleted_at: str | None = None,
) -> int:
    """Delete selected composite rows and record their portable keys atomically.

    ``where_sql`` is supplied only by static application call sites. JSONL input
    never reaches this helper.
    """
    if table_name not in _COMPOSITE_KEY_SPECS:
        raise ValueError(f"Table {table_name!r} is not a composite-key table")
    rows = conn.execute(
        f"SELECT * FROM {table_name} WHERE {where_sql}",
        params,
    ).fetchall()
    tokens = [_record_key_for_row(conn, table_name, row) for row in rows]
    cursor = conn.execute(
        f"DELETE FROM {table_name} WHERE {where_sql}",
        params,
    )
    for token in tokens:
        record_tombstone_on_connection(
            conn,
            table_name,
            token,
            deleted_at=deleted_at,
        )
    return cursor.rowcount


def record_tombstone(db_path: Path, table_name: str, record_id: str) -> None:
    """Record that a canonical row was deleted on this device."""
    with db.connect(db_path) as conn:
        record_tombstone_on_connection(conn, table_name, record_id)


# ---------------------------------------------------------------------------
# Device-local sync state (backend .cache/config — outside the vault)
# ---------------------------------------------------------------------------


def _sync_state_path(internal_dir: Path) -> Path:
    from . import config as cfg

    vault_root = internal_dir.parent.expanduser().resolve(strict=False)
    vault_key = hashlib.sha256(str(vault_root).encode("utf-8")).hexdigest()[:16]
    return cfg.get_global_config_dir() / SYNC_STATE_DIR / f"{vault_key}.json"


def read_sync_state(internal_dir: Path) -> dict:
    """Read this device's local sync bookkeeping (device_id, peer high-water marks)."""
    p = _sync_state_path(internal_dir)
    try:
        p.stat()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise SyncStateError(f"Cannot inspect sync state {p}: {exc}") from exc
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SyncStateError(f"Cannot read sync state {p}: {exc}") from exc
    _validate_sync_state(state, p)
    return state


def _validate_sync_state(state: object, path: Path) -> None:
    if not isinstance(state, dict):
        raise SyncStateError(f"Invalid sync state {path}: root must be an object")

    device_id = state.get("device_id")
    if not isinstance(device_id, str) or not device_id.strip():
        raise SyncStateError(
            f"Invalid sync state {path}: device_id must be a non-empty string"
        )

    last_export_ts = state.get("last_export_ts")
    if last_export_ts is not None and (
        not isinstance(last_export_ts, str) or not last_export_ts.strip()
    ):
        raise SyncStateError(
            f"Invalid sync state {path}: last_export_ts must be a non-empty string"
        )

    peers = state.get("peers")
    if peers is None:
        return
    if not isinstance(peers, dict):
        raise SyncStateError(f"Invalid sync state {path}: peers must be an object")
    for peer_name, peer_state in peers.items():
        if not isinstance(peer_name, str) or not peer_name:
            raise SyncStateError(
                f"Invalid sync state {path}: peer names must be non-empty strings"
            )
        if not isinstance(peer_state, dict):
            raise SyncStateError(
                f"Invalid sync state {path}: peer {peer_name!r} must be an object"
            )
        export_id = peer_state.get("last_export_id")
        if export_id is not None and (
            not isinstance(export_id, str) or not export_id.strip()
        ):
            raise SyncStateError(
                f"Invalid sync state {path}: peer {peer_name!r} last_export_id "
                "must be a non-empty string"
            )


def write_sync_state(internal_dir: Path, state: dict) -> None:
    """Persist this device's local sync bookkeeping."""
    p = _sync_state_path(internal_dir)
    _validate_sync_state(state, p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)


def get_device_id(internal_dir: Path) -> str:
    """Return this device's stable id, generating + persisting one on first use."""
    state = read_sync_state(internal_dir)
    device_id = state.get("device_id")
    if not device_id:
        device_id = uuid.uuid4().hex[:12]
        state["device_id"] = device_id
        write_sync_state(internal_dir, state)
    return device_id


def export_knowledge(
    db_path: Path,
    out_path: Path,
    *,
    tables: list[str] | None = None,
    since: str | None = None,
    compress: bool = False,
) -> ExportStats:
    """Export canonical tables to a JSONL file.

    Args:
        db_path: Path to state.sqlite.
        out_path: Destination .jsonl (or .jsonl.gz if compress=True).
        tables: Restrict to these table names (default: all SYNC_TABLES).
        since: ISO timestamp — export only rows with updated_at >= since.
        compress: Write gzip-compressed output.
    """
    export_tables = tables if tables is not None else SYNC_TABLES
    invalid_tables = set(export_tables) - set(SYNC_TABLES)
    if invalid_tables:
        raise ValueError(
            f"Tables are not syncable: {', '.join(sorted(invalid_tables))}"
        )
    stats = ExportStats()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    export_id = uuid.uuid4().hex

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_name(
        f".{out_path.name}.{uuid.uuid4().hex}.tmp"
    )
    opener: IO[str]
    if compress:
        opener = gzip.open(tmp_path, "wt", encoding="utf-8")  # type: ignore[assignment]
    else:
        opener = tmp_path.open("w", encoding="utf-8")

    try:
        with opener as f:
            f.write(
                json.dumps({
                    "type": "header",
                    "schema_version": SCHEMA_VERSION,
                    "export_id": export_id,
                    "exported_at": now,
                }) + "\n"
            )

            with db.connect(db_path) as conn:
                existing_tables = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }

                for tbl in export_tables:
                    if tbl not in existing_tables:
                        continue
                    updated_col = _UPDATED_AT_COL.get(tbl)
                    if since and updated_col and _REVISION_FN.get(tbl) is not None:
                        # `wiki db export --since` is user-facing. Filtering on
                        # the raw column would exclude a span whose metadata was
                        # edited after `since` but whose immutable `created_at`
                        # predates it — silently omitting exactly the writes
                        # this table's derived revision exists to carry.
                        since_key = _timestamp_key(since)
                        rows = [
                            row
                            for row in conn.execute(f"SELECT * FROM {tbl}").fetchall()
                            if _timestamp_key(row_revision(tbl, dict(row))) >= since_key
                        ]
                    elif since and updated_col:
                        rows = conn.execute(
                            f"SELECT * FROM {tbl} WHERE {updated_col} >= ?", (since,)
                        ).fetchall()
                    else:
                        rows = conn.execute(f"SELECT * FROM {tbl}").fetchall()

                    count = 0
                    for row in rows:
                        row_payload = dict(row)
                        if tbl == "deleted_records":
                            target_table = row_payload.get("table_name")
                            if (
                                target_table not in SYNC_TABLES
                                or target_table == "deleted_records"
                            ):
                                raise ValueError(
                                    f"Tombstone table {target_table!r} is not syncable"
                                )
                            _validate_tombstone_token(
                                target_table,
                                row_payload.get("record_id"),
                            )
                            _require_timestamp(
                                row_payload.get("deleted_at"),
                                context=(
                                    f"Tombstone for {target_table!r} deleted_at"
                                ),
                            )
                        f.write(
                            json.dumps(
                                {"type": "row", "table": tbl, "row": row_payload}
                            ) + "\n"
                        )
                        count += 1
                    stats.rows_by_table[tbl] = count
                    stats.total_rows += count
        os.replace(tmp_path, out_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    return stats


def import_knowledge(
    db_path: Path,
    in_path: Path,
    *,
    dry_run: bool = False,
) -> ImportStats:
    """Import a JSONL export file into the local database using LWW conflict resolution.

    Args:
        db_path: Path to target state.sqlite.
        in_path: Source .jsonl or .jsonl.gz file.
        dry_run: If True, calculate stats without writing anything.
    """
    stats = ImportStats(dry_run=dry_run)

    opener: IO[str]
    if in_path.suffix == ".gz":
        opener = gzip.open(in_path, "rt", encoding="utf-8")  # type: ignore[assignment]
    else:
        opener = in_path.open("r", encoding="utf-8")

    with opener as f:
        header_line = f.readline().strip()
        if not header_line:
            raise ValueError("Empty export file")
        header = json.loads(header_line)
        if header.get("type") != "header":
            raise ValueError("Missing header row in export file")
        file_version = header.get("schema_version")
        if file_version != SCHEMA_VERSION:
            raise ValueError(
                f"schema_version mismatch: file has {file_version}, local is {SCHEMA_VERSION}"
            )
        if not header.get("export_id"):
            raise ValueError("Missing export_id in export header")

        with db.connect(db_path) as conn:
            existing_tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            table_info = {
                table: conn.execute(f"PRAGMA table_info({table})").fetchall()
                for table in SYNC_TABLES
                if table in existing_tables
            }
            table_columns = {
                table: {str(col["name"]) for col in columns}
                for table, columns in table_info.items()
            }
            table_primary_keys = {
                table: [
                    str(col["name"])
                    for col in sorted(columns, key=lambda col: int(col["pk"]))
                    if int(col["pk"]) > 0
                ]
                for table, columns in table_info.items()
            }
            source_id_map: dict[int, int | None] = {}
            source_sync_keys: dict[int, str] = {}
            planned_source_inserts: set[int] = set()
            # Sources the database refused. Their child rows are LOST, not
            # merely skipped: there is no parent to attach them to, so nothing
            # ever inserts them. Counting 500 orphaned spans as "skipped" while
            # reporting "1 rejected" understates the loss by 500.
            rejected_source_ids: set[int] = set()

            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("type") != "row":
                    continue
                tbl = rec.get("table")
                if tbl not in SYNC_TABLES:
                    raise ValueError(f"Table {tbl!r} is not syncable")
                if tbl not in existing_tables:
                    raise ValueError(f"Sync table {tbl!r} does not exist locally")
                row = rec.get("row")
                if not isinstance(row, dict):
                    raise ValueError(f"Invalid row payload for table {tbl!r}")
                unknown_columns = set(row) - table_columns[tbl]
                if unknown_columns:
                    raise ValueError(
                        f"Table {tbl!r} has unknown columns: "
                        f"{', '.join(sorted(unknown_columns))}"
                    )
                if tbl == "deleted_records":
                    target_table = row.get("table_name")
                    if target_table not in SYNC_TABLES or target_table == "deleted_records":
                        raise ValueError(
                            f"Tombstone table {target_table!r} is not syncable"
                        )
                    applied = _apply_tombstone(
                        conn,
                        target_table,
                        row["record_id"],
                        row["deleted_at"],
                        dry_run=dry_run,
                    )
                    if applied:
                        stats.deleted += 1
                elif tbl == "sources":
                    remote_id = row.get("id")
                    result, local_id = _lw_upsert_source(
                        conn,
                        row,
                        dry_run=dry_run,
                    )
                    if isinstance(remote_id, int):
                        source_id_map[remote_id] = local_id
                        source_sync_keys[remote_id] = _source_sync_key(row)
                        if dry_run and result == "inserted":
                            planned_source_inserts.add(remote_id)
                        if result == "rejected":
                            rejected_source_ids.add(remote_id)
                    if result == "inserted":
                        stats.inserted += 1
                    elif result == "updated":
                        stats.updated += 1
                    elif result == "rejected":
                        stats.rejected += 1
                    else:
                        stats.skipped += 1
                else:
                    source_sync_key: str | None = None
                    parent_will_be_inserted = False
                    if row.get("source_id") is not None:
                        remote_source_id = row["source_id"]
                        if remote_source_id not in source_id_map:
                            raise ValueError(
                                f"Table {tbl!r} references unmapped source_id "
                                f"{remote_source_id!r}"
                            )
                        local_source_id = source_id_map[remote_source_id]
                        if local_source_id is None:
                            # A rejected parent means this row is lost too; any
                            # other None is an ordinary skip (e.g. tombstoned).
                            if remote_source_id in rejected_source_ids:
                                stats.rejected += 1
                            else:
                                stats.skipped += 1
                            continue
                        source_sync_key = source_sync_keys[remote_source_id]
                        composite_spec = _COMPOSITE_KEY_SPECS.get(tbl)
                        parent_will_be_inserted = (
                            remote_source_id in planned_source_inserts
                            and composite_spec is not None
                            and any(
                                field == "source_sync_key"
                                for field, _value_type in composite_spec.transport_fields
                            )
                        )
                        row["source_id"] = local_source_id
                    result = _lw_upsert(
                        conn,
                        tbl,
                        row,
                        dry_run=dry_run,
                        primary_keys=table_primary_keys[tbl],
                        source_sync_key=source_sync_key,
                        parent_will_be_inserted=parent_will_be_inserted,
                    )
                    if result == "inserted":
                        stats.inserted += 1
                    elif result == "updated":
                        stats.updated += 1
                    elif result == "rejected":
                        stats.rejected += 1
                    else:
                        stats.skipped += 1
            if not dry_run:
                _reconcile_authoritative_generations(conn)

    return stats


def _reconcile_authoritative_generations(conn: "db.sqlite3.Connection") -> None:
    """Restore the single-authoritative-generation invariant after a merge.

    Independent replicas can legitimately export different authoritative
    generations for the same portable source. Prefer a generation whose audit
    fingerprint matches the LWW source row, then the newest published row.
    Retire authored topology owned only by losing generations so imported stale
    structure cannot remain active.
    """
    rows = conn.execute(
        "SELECT g.id, g.source_id, g.audit_json, g.published_at, g.updated_at, "
        "g.created_at, s.id AS live_source_id, s.content_hash "
        "FROM compiler_generations g "
        "LEFT JOIN sources s ON s.id = g.source_id "
        "WHERE g.status = 'authoritative'"
    ).fetchall()
    by_source: dict[int | None, list[Any]] = {}
    for row in rows:
        source_id = int(row["source_id"]) if row["source_id"] is not None else None
        by_source.setdefault(source_id, []).append(row)

    now = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    for source_id, generations in by_source.items():
        def winner_key(row: Any) -> tuple[Any, ...]:
            try:
                audit = json.loads(str(row["audit_json"] or "{}"))
            except (TypeError, ValueError):
                audit = {}
            if not isinstance(audit, dict):
                audit = {}
            matches_source = (
                row["content_hash"] is not None
                and audit.get("content_hash") == row["content_hash"]
            )
            return (
                matches_source,
                _timestamp_key(row["published_at"]),
                _timestamp_key(row["updated_at"]),
                _timestamp_key(row["created_at"]),
                str(row["id"]),
            )

        owned_relation_ids: set[str] = set()
        if source_id is not None:
            owned_relation_ids = {
                str(row[0])
                for row in conn.execute(
                    "SELECT r.id FROM graph_relations r "
                    "JOIN compiler_generations g ON g.id = r.generation_id "
                    "WHERE r.edge_class = 'authored' AND g.source_id = ?",
                    (source_id,),
                ).fetchall()
            }

        source_missing = source_id is not None and all(
            generation["live_source_id"] is None for generation in generations
        )
        winner: Any | None = None
        winner_membership: set[str] = set()
        newly_added_ids: set[str] = set()
        if source_missing:
            losing_ids = sorted(str(row["id"]) for row in generations)
        else:
            winner = max(generations, key=winner_key)
            losing_ids = sorted(
                str(row["id"])
                for row in generations
                if row["id"] != winner["id"]
            )
            winner_relation_ids = _generation_authored_relation_ids(winner)
            winner_membership = set(winner_relation_ids or ())
            prior_memberships: list[set[str]] = []
            prior_membership_known = True
            for generation in generations:
                if generation["id"] == winner["id"]:
                    continue
                relation_ids = _generation_authored_relation_ids(generation)
                if relation_ids is None:
                    prior_membership_known = False
                else:
                    prior_memberships.append(set(relation_ids))
            if losing_ids:
                common_prior_membership = (
                    set.intersection(*prior_memberships)
                    if prior_membership_known and prior_memberships
                    else set()
                )
                newly_added_ids = (
                    winner_membership - common_prior_membership
                    if prior_membership_known
                    else winner_membership
                )

        relation_revisions: list[str] = []
        for relation_id in sorted(owned_relation_ids | winner_membership):
            relation_row = conn.execute(
                "SELECT updated_at FROM graph_relations WHERE id = ?",
                (relation_id,),
            ).fetchone()
            if relation_row is not None:
                relation_revisions.append(str(relation_row["updated_at"] or ""))
        revision = db.strict_successor_timestamp(
            now,
            *(str(row["updated_at"] or "") for row in generations),
            *relation_revisions,
        )
        if losing_ids:
            placeholders = ",".join("?" for _ in losing_ids)
            conn.execute(
                "UPDATE compiler_generations SET status = 'discarded', "
                "discarded_at = ?, updated_at = ? "
                f"WHERE id IN ({placeholders})",
                (revision, revision, *losing_ids),
            )
        newly_active_ids: list[str] = []
        if winner is not None:
            for relation_id in sorted(winner_membership):
                row = conn.execute(
                    "SELECT edge_class, generation_id, lifecycle_status, "
                    "quarantine_reason FROM graph_relations WHERE id = ?",
                    (relation_id,),
                ).fetchone()
                if row is None or str(row["edge_class"]) != "authored":
                    continue
                lifecycle_status = str(row["lifecycle_status"])
                needs_repair = (
                    str(row["generation_id"] or "") != str(winner["id"])
                    or lifecycle_status in {"provisional", "retired"}
                    or (
                        lifecycle_status == "quarantined"
                        and str(row["quarantine_reason"]) == "unsupported"
                    )
                )
                status = lifecycle_status
                if needs_repair:
                    conn.execute(
                        "UPDATE graph_relations SET generation_id = ?, "
                        "lifecycle_status = 'provisional', quarantine_reason = '', "
                        "reeval_trigger = '', updated_at = ? WHERE id = ?",
                        (winner["id"], revision, relation_id),
                    )
                    # Authored classification returns before any path-backed
                    # bridge-risk lookup, so a placeholder Path is sufficient
                    # for this conn-owned reconciliation.
                    status = db.compile_relation_lifecycle(
                        Path("."),
                        relation_id=relation_id,
                        conn=conn,
                    )
                    conn.execute(
                        "UPDATE graph_relations SET updated_at = ? WHERE id = ?",
                        (revision, relation_id),
                    )
                if status == "active" and relation_id in newly_added_ids:
                    newly_active_ids.append(relation_id)
            db.retire_community_reports_for_relation_endpoints_on_connection(
                conn,
                newly_active_ids,
                now=revision,
            )
        db.retire_graph_relations_on_connection(
            conn,
            owned_relation_ids - winner_membership,
            now=revision,
        )


def _generation_authored_relation_ids(row: Any) -> tuple[str, ...] | None:
    return db.generation_authored_relation_ids(row["audit_json"])


def _apply_tombstone(
    conn: "db.sqlite3.Connection",
    table_name: str,
    record_id: str,
    deleted_at: str,
    dry_run: bool = False,
) -> bool:
    """Delete a record from its table and record the tombstone locally.
    Returns True if the tombstone would be applied."""
    if table_name not in SYNC_TABLES or table_name == "deleted_records":
        raise ValueError(f"Table {table_name!r} is not syncable")
    record_id = _validate_tombstone_token(table_name, record_id)
    deleted_at = _require_timestamp(
        deleted_at,
        context=f"Tombstone for {table_name!r} deleted_at",
    )

    # Check if there is already a newer tombstone
    existing_tombstone = conn.execute(
        "SELECT deleted_at FROM deleted_records WHERE table_name = ? AND record_id = ?",
        (table_name, record_id),
    ).fetchone()
    if existing_tombstone and _timestamp_key(
        existing_tombstone[0]
    ) >= _timestamp_key(deleted_at):
        return False

    # Check if the local record is newer than the tombstone
    updated_col = _UPDATED_AT_COL.get(table_name)
    key_columns, key_values = _physical_key_for_token(
        conn,
        table_name,
        record_id,
    )
    where = " AND ".join(f"{column} IS ?" for column in key_columns)
    if key_values is not None and updated_col:
        # A locally-newer row survives an incoming delete. Ranking a span by its
        # immutable `created_at` here would let a tombstone destroy a metadata
        # edit made after the delete — on the default `wiki db import` path.
        local_record = conn.execute(
            f"SELECT {revision_select_columns(table_name)} FROM {table_name} "
            f"WHERE {where}",
            key_values,
        ).fetchone()
        if local_record and _timestamp_key(
            row_revision(table_name, dict(local_record))
        ) > _timestamp_key(deleted_at):
            return False

    if not dry_run:
        if table_name == "sources" and key_values is not None:
            _delete_source_by_sync_key(
                conn,
                record_id,
                deleted_at=deleted_at,
            )
        elif key_values is not None:
            conn.execute(
                f"DELETE FROM {table_name} WHERE {where}",
                key_values,
            )
        # Record tombstone so this device also propagates the deletion on future exports.
        conn.execute(
            "INSERT OR REPLACE INTO deleted_records (table_name, record_id, deleted_at)"
            " VALUES (?, ?, ?)",
            (table_name, record_id, deleted_at),
        )
    return True


def _delete_source_by_sync_key(
    conn: "db.sqlite3.Connection",
    sync_key: str,
    *,
    deleted_at: str,
) -> None:
    source = conn.execute(
        "SELECT id FROM sources WHERE sync_key = ?",
        (sync_key,),
    ).fetchone()
    if source is None:
        return
    source_id = int(source["id"])
    from .db.sources import _delete_source_on_connection

    _delete_source_on_connection(
        conn,
        source_id,
        observed_revision=deleted_at,
    )


def _source_sync_key(row: dict) -> str:
    sync_key = str(row.get("sync_key") or "").strip()
    if sync_key:
        return sync_key
    raise ValueError("Source row is missing sync_key")


def _row_is_blocked_by_tombstone(
    conn: "db.sqlite3.Connection",
    table_name: str,
    row: Mapping[str, Any],
    *,
    dry_run: bool,
    source_sync_key: str | None = None,
) -> bool:
    token = _record_key_for_row(
        conn,
        table_name,
        row,
        source_sync_key=source_sync_key,
    )
    tombstone = conn.execute(
        "SELECT deleted_at FROM deleted_records "
        "WHERE table_name = ? AND record_id = ?",
        (table_name, token),
    ).fetchone()
    if tombstone is None:
        return False

    deleted_at = _require_timestamp(
        tombstone["deleted_at"],
        context=f"Tombstone for {table_name!r} deleted_at",
    )
    updated_col = _UPDATED_AT_COL.get(table_name)
    if updated_col is None:
        return True
    # Tombstone-vs-edit is LWW too: an edit genuinely newer than the delete must
    # resurrect the row. Ranking a span by its immutable `created_at` would make
    # every later metadata edit look older than any tombstone.
    incoming_revision = _require_timestamp(
        row_revision(table_name, dict(row)),
        context=f"Table {table_name!r} row revision",
    )
    if _timestamp_key(deleted_at) >= _timestamp_key(incoming_revision):
        return True
    if not dry_run:
        conn.execute(
            "DELETE FROM deleted_records WHERE table_name = ? AND record_id = ?",
            (table_name, token),
        )
    return False


def _lw_upsert_source(
    conn: "db.sqlite3.Connection",
    row: dict,
    *,
    dry_run: bool = False,
) -> tuple[str, int | None]:
    """Merge a source by portable key while preserving the local integer id.

    Returns the same outcome vocabulary as `_lw_upsert`, including
    'rejected' with a `None` id when the database refused the row.
    """
    sync_key = _source_sync_key(row)
    row["sync_key"] = sync_key
    remote_ts = _REMOTE_TS_FN["sources"](row)
    if _timestamp_key(remote_ts) == datetime.min.replace(tzinfo=timezone.utc):
        raise ValueError("Source row is missing a valid updated_at revision")
    if _row_is_blocked_by_tombstone(
        conn,
        "sources",
        row,
        dry_run=dry_run,
    ):
        return "skipped", None
    remote_id = row.get("id")
    existing = conn.execute(
        "SELECT * FROM sources WHERE sync_key = ?",
        (sync_key,),
    ).fetchone()
    if existing is None:
        if dry_run:
            return "inserted", int(remote_id or 0)
        insert_row = {key: value for key, value in row.items() if key != "id"}
        outcome = _do_insert(conn, "sources", insert_row)
        if outcome == "duplicate":
            # This relpath is already registered under a different sync_key —
            # both devices added the same file independently. The source is
            # present; reuse the local id so the peer's child rows attach to it
            # instead of being orphaned.
            local = conn.execute(
                "SELECT id FROM sources WHERE relpath = ?",
                (row.get("relpath"),),
            ).fetchone()
            if local is not None:
                return "skipped", int(local[0])
            return "rejected", None
        if outcome == "rejected":
            # The database refused this row — a relpath already taken under a
            # different sync_key, or a constraint violation from a truncated
            # peer export. Report it, do not raise: nothing catches per row, so
            # raising rolls the whole file back and takes every well-formed row
            # with it, and the peer's checkpoint is never recorded so the same
            # file re-fails on every retry. That is the wedge B2 exists to
            # remove. A source with no local id yields `None`, which the caller
            # already handles by skipping its child rows.
            return "rejected", None
        inserted = conn.execute(
            "SELECT id FROM sources WHERE sync_key = ?",
            (sync_key,),
        ).fetchone()
        if inserted is None:
            return "rejected", None
        return "inserted", int(inserted[0])

    local_id = int(existing["id"])
    local_ts = existing["updated_at"] or ""
    if _timestamp_key(remote_ts) <= _timestamp_key(local_ts):
        return "skipped", local_id
    if not dry_run:
        update_row = {
            key: value
            for key, value in row.items()
            if key not in {"id", "sync_key"}
        }
        assignments = ", ".join(f"{key} = ?" for key in update_row)
        conn.execute(
            f"UPDATE sources SET {assignments} WHERE id = ?",
            (*update_row.values(), local_id),
        )
    return "updated", local_id


def _lw_upsert(
    conn: "db.sqlite3.Connection",
    table_name: str,
    row: dict,
    dry_run: bool = False,
    *,
    primary_keys: list[str] | None = None,
    source_sync_key: str | None = None,
    parent_will_be_inserted: bool = False,
) -> str:
    """Insert or update a row using Last-Write-Wins.

    Returns: 'inserted' | 'updated' | 'skipped' | 'rejected'

    'rejected' means the database refused the row — it is NOT stored.
    Callers must never fold it into 'skipped': skipped rows are already
    present, rejected rows are lost, and only one of those needs saying.
    """
    pk_col = _PK_COL.get(table_name)
    updated_col = _UPDATED_AT_COL.get(table_name)
    key_columns = primary_keys or ([pk_col] if pk_col else [])

    if key_columns and all(key in row for key in key_columns):
        if _row_is_blocked_by_tombstone(
            conn,
            table_name,
            row,
            dry_run=dry_run,
            source_sync_key=source_sync_key,
        ):
            return "skipped"
        if parent_will_be_inserted:
            return "inserted"
        where = " AND ".join(f"{key} IS ?" for key in key_columns)
        existing = conn.execute(
            f"SELECT * FROM {table_name} WHERE {where}",
            tuple(row[key] for key in key_columns),
        ).fetchone()

        if existing is None:
            if not dry_run:
                outcome = _do_insert(conn, table_name, row)
                if outcome == "duplicate":
                    # An equivalent row is already here under a different id.
                    # Present, not lost — see _do_insert.
                    return "skipped"
                if outcome == "rejected":
                    return "rejected"
            return "inserted"

        if updated_col:
            # One rule, both sides — see row_revision().
            local_ts = row_revision(table_name, dict(existing))
            remote_ts = row_revision(table_name, row)
            if _timestamp_key(remote_ts) > _timestamp_key(local_ts):
                if not dry_run:
                    _preserve_device_local(conn, table_name, row)
                    _do_upsert(conn, table_name, row)
                return "updated"
            return "skipped"

        local_row = {key: existing[key] for key in row}
        if local_row == row:
            return "skipped"

        # Immutable tables without a revision clock still need deterministic
        # convergence. The same primary key should normally mean the same row;
        # if corrupted peers disagree, retain the lexicographically greater
        # canonical payload on both sides instead of alternating forever.
        remote_key = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
        local_key = json.dumps(
            local_row, sort_keys=True, separators=(",", ":"), default=str
        )
        if remote_key <= local_key:
            return "skipped"
        if not dry_run:
            _preserve_device_local(conn, table_name, row)
            _do_upsert(conn, table_name, row)
        return "updated"

    # Current-schema exports always include every primary-key column. Refuse to
    # guess identity for malformed rows because blind replacement breaks
    # idempotence and can create cross-device export ping-pong.
    if primary_keys:
        missing = ", ".join(key for key in primary_keys if key not in row)
        raise ValueError(
            f"Table {table_name!r} row is missing primary-key columns: {missing}"
        )

    # A table with no declared primary key has no safe transport identity.
    # Existing schema-v12 sync tables all declare one; keep this defensive path
    # content-idempotent for forward-compatible callers.
    clauses = " AND ".join(f"{key} IS ?" for key in row)
    existing = conn.execute(
        f"SELECT 1 FROM {table_name} WHERE {clauses} LIMIT 1",
        tuple(row.values()),
    ).fetchone()
    if existing is not None:
        return "skipped"
    if not dry_run:
        _do_upsert(conn, table_name, row)
    return "inserted"


def _do_insert(conn: "db.sqlite3.Connection", table: str, row: dict) -> str:
    """Insert a peer row. Returns 'inserted' | 'duplicate' | 'rejected'.

    `duplicate` is NOT a loss and must never be reported as one. Several synced
    tables carry a UNIQUE constraint beyond their transport key —
    `graph_entities(canonical_name, entity_type)`, `source_spans(source_id,
    content_hash)`, `sources.relpath` — while the key lookup matches on a
    surrogate `id`/`sync_key`. Two devices that independently extract the same
    entity mint different ids, so the peer's row looks new by key and collides
    on content. The data is already here; the ids simply never converge, so
    calling that a refusal would fire on every sync forever and train the user
    to ignore the counter that exists to warn them about real loss.

    The old `INSERT OR IGNORE` collapsed all three outcomes into silence, and
    the caller reported every one as `inserted` — telling the user data arrived
    that was dropped. A savepoint plus SQLite's own constraint name separates
    them without guessing.
    """
    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" * len(row))
    cursor = conn.execute(
        f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})",
        list(row.values()),
    )
    if cursor.rowcount > 0:
        return "inserted"
    # OR IGNORE, not a savepoint + IntegrityError: `db.connect` commits only on
    # a clean exit, and issuing SAVEPOINT opens a transaction whose RELEASE
    # commits everything before it — which would break the all-or-nothing
    # rollback a malformed peer file depends on.
    return "duplicate" if _unique_conflict_exists(conn, table, row) else "rejected"


def _unique_index_columns(
    conn: "db.sqlite3.Connection", table: str
) -> list[tuple[str, ...]]:
    """Column tuples of every UNIQUE index on `table`, including the implicit PK."""
    cached = _UNIQUE_INDEX_CACHE.get(table)
    if cached is not None:
        return cached
    groups: list[tuple[str, ...]] = []
    for index in conn.execute(f"PRAGMA index_list({table})").fetchall():
        if not index["unique"]:
            continue
        # A PARTIAL unique index only constrains rows matching its WHERE clause,
        # which cannot be evaluated here. Treating it as unconditional would
        # blame it for a refusal it could not have caused and report a lost row
        # as an already-present duplicate — the silent-loss direction. Skipping
        # it can only make the classifier fall through to `rejected`, which is
        # the safe way to be wrong.
        if index["partial"]:
            continue
        cols = tuple(
            str(part["name"])
            for part in conn.execute(f"PRAGMA index_info({index['name']})")
            if part["name"] is not None
        )
        if cols:
            groups.append(cols)
    _UNIQUE_INDEX_CACHE[table] = groups
    return groups


def _unique_conflict_exists(
    conn: "db.sqlite3.Connection", table: str, row: dict
) -> bool:
    """True when a row already present collides with `row` on a UNIQUE index.

    Distinguishes "already here under a different surrogate id" from "the
    database refused this row". Asked of the schema rather than inferred from an
    exception message, so it stays correct as constraints change.
    """
    for cols in _unique_index_columns(conn, table):
        if any(col not in row for col in cols):
            continue
        # SQLite treats NULLs as DISTINCT in a UNIQUE index, so an index with a
        # NULL in this row can never be what refused it. Matching NULL to NULL
        # with `IS` would blame this index and report a genuinely lost row as an
        # already-present duplicate — a real loss turned into silence, the exact
        # failure this counter exists to surface. Mirror SQLite, do not guess.
        if any(row[col] is None for col in cols):
            continue
        where = " AND ".join(f"{col} = ?" for col in cols)
        found = conn.execute(
            f"SELECT 1 FROM {table} WHERE {where} LIMIT 1",
            tuple(row[col] for col in cols),
        ).fetchone()
        if found is not None:
            return True
    return False


def _do_upsert(conn: "db.sqlite3.Connection", table: str, row: dict) -> None:
    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" * len(row))
    conn.execute(
        f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})",
        list(row.values()),
    )


def _preserve_device_local(conn: "db.sqlite3.Connection", table_name: str, row: dict) -> None:
    """Before updating an existing row, keep this device's device-local columns.

    Only preserves when a non-NULL local value exists, so genuinely new info still
    flows through for vault-local (non-reference) rows whose column is NULL.
    """
    cols = _DEVICE_LOCAL_COLUMNS.get(table_name)
    if not cols:
        return
    pk_col = _PK_COL.get(table_name)
    if not pk_col or pk_col not in row:
        return
    col_list = ", ".join(cols)
    local = conn.execute(
        f"SELECT {col_list} FROM {table_name} WHERE {pk_col} = ?",
        (row[pk_col],),
    ).fetchone()
    if local is None:
        return
    for col in cols:
        local_val = local[col]
        if local_val is not None:
            row[col] = local_val


# ---------------------------------------------------------------------------
# One-writer-per-file auto-sync (P2)
# ---------------------------------------------------------------------------


def _sync_dir(internal_dir: Path, *, dir_name: str = "sync") -> Path:
    return internal_dir / dir_name


def export_for_device(
    internal_dir: Path,
    db_path: Path,
    *,
    dir_name: str = "sync",
) -> Path:
    """Write this device's full snapshot to .curator/<dir>/dev-<device_id>.jsonl.

    One-writer-per-file: a device only ever writes its OWN file, so Syncthing never
    produces write-write conflicts under normal operation. A full snapshot (not a
    delta) is written so a late-joining peer always receives the complete view this
    device holds — including rows it previously imported from other peers.

    Returns the path written. Records `last_export_ts` in sync_state for mismatch
    detection.
    """
    device_id = get_device_id(internal_dir)
    sync_dir = _sync_dir(internal_dir, dir_name=dir_name)
    sync_dir.mkdir(parents=True, exist_ok=True)
    out = sync_dir / f"dev-{device_id}.jsonl"

    # Stamp the moment the snapshot is READ, not the moment it finished being
    # written. `local_has_unexported_changes` treats anything older than this
    # stamp as already exported, so stamping afterwards silently swallows every
    # row mutated while the export was running — a window that widens with the
    # vault, i.e. exactly when there is most to lose. The value is recorded only
    # after a successful export, so a failed one does not claim to have shipped
    # anything.
    snapshot_ts = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    export_knowledge(db_path, out)

    state = read_sync_state(internal_dir)
    state["last_export_ts"] = snapshot_ts
    write_sync_state(internal_dir, state)
    return out


def _peer_files(
    internal_dir: Path,
    *,
    dir_name: str = "sync",
    own_device_id: str | None = None,
) -> list[Path]:
    """All peer export files (dev-*.jsonl) excluding this device's own file and any
    Syncthing conflict files (handled separately)."""
    sync_dir = _sync_dir(internal_dir, dir_name=dir_name)
    if not sync_dir.is_dir():
        return []
    own = f"dev-{own_device_id or get_device_id(internal_dir)}.jsonl"
    peers = []
    for f in sorted(sync_dir.glob("dev-*.jsonl")):
        if f.name == own:
            continue
        if ".sync-conflict-" in f.name:
            continue
        peers.append(f)
    return peers


def _read_export_id(path: Path) -> str | None:
    """Read the export_id from a peer file's header.

    Returns ``None`` only for a well-formed incompatible-schema peer. Corrupt
    current-schema input is surfaced so autosync cannot silently stop applying
    a peer forever.
    """
    try:
        opener: IO[str]
        if path.suffix == ".gz":
            opener = gzip.open(path, "rt", encoding="utf-8")  # type: ignore[assignment]
        else:
            opener = path.open("r", encoding="utf-8")
        with opener as handle:
            line = handle.readline().strip()
    except (OSError, ValueError) as exc:
        raise AutosyncError(
            f"Peer snapshot {path.name} header could not be read: {exc}"
        ) from exc
    if not line:
        raise AutosyncError(f"Peer snapshot {path.name} is empty")
    try:
        header = json.loads(line)
        if not isinstance(header, dict):
            raise AutosyncError(
                f"Peer snapshot {path.name} header is not a JSON object"
            )
    except json.JSONDecodeError as exc:
        raise AutosyncError(
            f"Peer snapshot {path.name} has a malformed JSON header"
        ) from exc
    if header.get("type") != "header":
        raise AutosyncError(f"Peer snapshot {path.name} is missing its header row")
    # Schema mismatch — peer has not upgraded yet; skip until they re-export.
    file_version = header.get("schema_version")
    if file_version != SCHEMA_VERSION:
        logger.info(
            "Skipping peer export %s: schema_version %s (local is %s)",
            path.name, file_version, SCHEMA_VERSION,
        )
        return None
    export_id = header.get("export_id")
    if not isinstance(export_id, str) or not export_id:
        raise AutosyncError(
            f"Peer snapshot {path.name} has no valid export_id"
        )
    return export_id


def import_all_peers(
    internal_dir: Path,
    db_path: Path,
    *,
    dry_run: bool = False,
    dir_name: str = "sync",
) -> dict[str, ImportStats]:
    """Import every peer file whose export id differs from the last import.

    Never imports this device's own file (loop safety). Records per-peer
    `last_export_id` in sync_state so a re-run is a cheap no-op and a
    late-arriving Syncthing delivery is picked up exactly once.
    """
    results: dict[str, ImportStats] = {}
    # Initialize identity before taking the mutable state snapshot. Otherwise a
    # first-run `_peer_files()` call can persist an id after `state` was read as
    # `{}`, and the final peer checkpoint write would overwrite that new id.
    own_device_id = get_device_id(internal_dir)
    state = read_sync_state(internal_dir)
    peers: dict = state.setdefault("peers", {})

    for f in _peer_files(
        internal_dir, dir_name=dir_name, own_device_id=own_device_id
    ):
        export_id = _read_export_id(f)
        if export_id is None:
            # Legacy or incompatible peer file — skip until peer re-exports.
            continue
        rec = peers.get(f.name, {})
        if rec.get("last_export_id") == export_id:
            continue
        try:
            stats = import_knowledge(db_path, f, dry_run=dry_run)
        except Exception as exc:
            raise AutosyncError(
                f"Peer snapshot {f.name} import failed: {exc}"
            ) from exc
        results[f.name] = stats
        if not dry_run:
            peers[f.name] = {"last_export_id": export_id}

    if not dry_run:
        write_sync_state(internal_dir, state)
    return results


def detect_conflict_files(internal_dir: Path, *, dir_name: str = "sync") -> list[Path]:
    """Return any Syncthing conflict files in the sync dir (`*.sync-conflict-*`).

    A conflict file is just another LWW-mergeable export; callers import it as an
    ordinary peer and then archive it. Its mere presence warrants a UI notice.
    """
    sync_dir = _sync_dir(internal_dir, dir_name=dir_name)
    if not sync_dir.is_dir():
        return []
    return sorted(sync_dir.glob("*.sync-conflict-*"))


def _timestamp_key(value: object) -> datetime:
    if not isinstance(value, str):
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _local_max_ts(db_path: Path) -> str:
    """The newest LWW timestamp across all canonical tables (for mismatch detection).

    deleted_records IS included: a delete-only change records nothing but a
    tombstone, and excluding it meant the export gate never fired for deletions,
    so peers never saw them (PR #78 review).
    """
    newest = ""
    with db.connect(db_path) as conn:
        existing = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for tbl, col in _UPDATED_AT_COL.items():
            if tbl not in existing:
                continue
            revision_fn = _REVISION_FN.get(tbl)
            if revision_fn is not None:
                # MAX(col) cannot see a clock that lives inside a JSON column,
                # so the export gate would never fire for a metadata-only write.
                #
                # Scan ONLY the rows that carry metadata. This runs on a hot,
                # default-on path — `maybe_auto_export` calls it once per ingest
                # job — so materializing and JSON-decoding every span would make
                # a batch ingest O(jobs x total_spans). Rows without metadata
                # derive exactly `created_at`, which the indexed MAX below
                # already covers.
                row = conn.execute(f"SELECT MAX({col}) FROM {tbl}").fetchone()
                if row and row[0] and _timestamp_key(row[0]) > _timestamp_key(newest):
                    newest = row[0]
                for span in conn.execute(
                    f"SELECT * FROM {tbl} WHERE metadata IS NOT NULL"
                ):
                    stamp = row_revision(tbl, dict(span))
                    if stamp and _timestamp_key(stamp) > _timestamp_key(newest):
                        newest = stamp
                continue
            row = conn.execute(f"SELECT MAX({col}) FROM {tbl}").fetchone()
            if row and row[0] and _timestamp_key(row[0]) > _timestamp_key(newest):
                newest = row[0]
    return newest


def local_has_unexported_changes(internal_dir: Path, db_path: Path) -> bool:
    """True if the local DB may have rows not yet in this device's snapshot.

    Timestamps have SECOND precision, so a mutation stamped in the same second
    as `last_export_ts` is indistinguishable from one exported in that second —
    strict `>` would silently strand it until an unrelated later mutation
    (PR #78 review). `>=` errs toward one redundant (idempotent, LWW-safe)
    re-export instead; the extra export stamps a later `last_export_ts`, so the
    churn self-terminates as soon as the wall clock leaves that second.
    """
    last = read_sync_state(internal_dir).get("last_export_ts")
    if not last:
        return True
    newest = _local_max_ts(db_path)
    return bool(newest) and _timestamp_key(newest) >= _timestamp_key(last)


def maybe_auto_export(paths) -> Path | None:
    """Best-effort default-on export hook for non-CLI mutation paths."""
    from . import config as cfg

    block = (cfg.load_config(paths).get("auto_sync") or {})
    if not block.get("enabled"):
        return None
    if not local_has_unexported_changes(paths.internal, paths.state_db):
        return None
    return export_for_device(
        paths.internal, paths.state_db, dir_name=block.get("dir", "sync")
    )


def _archive_conflict(cf: Path, internal_dir: Path) -> None:
    """Move a merged conflict file out of the synced dir into local runtime storage,
    so it stops re-triggering the conflict notice and is not re-synced.

    Source and destination are different trees BY DESIGN — the vault lives on
    synced storage (iCloud, Syncthing, a network mount), the cache is
    repo-local — so they are routinely on different filesystems. `Path.rename`
    raises `OSError(EXDEV)` there, `autosync` turns that into an
    `AutosyncError`, and the file stays put: every later run re-imports the same
    conflict and fails again. One un-archivable file wedges sync for that vault
    permanently. `shutil.move` falls back to copy+unlink across filesystems.

    The destination name is made unique rather than overwritten. A conflict file
    holds data that has not been merged anywhere else; silently replacing one
    with another of the same name destroys it.
    """
    from . import config as cfg

    archive = (
        cfg.get_vault_cache_dir(internal_dir.parent)
        / "runtime"
        / "sync_conflicts"
    )
    archive.mkdir(parents=True, exist_ok=True)

    target = archive / cf.name
    if target.exists():
        stem, suffix = cf.stem, cf.suffix
        index = 2
        while target.exists():
            target = archive / f"{stem}.{index}{suffix}"
            index += 1

    shutil.move(str(cf), str(target))


@dataclass
class AutosyncResult:
    imported: dict[str, ImportStats] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    exported: str | None = None
    dry_run: bool = False
    # Whether an export ran (real run) / would run (dry run). Surfacing this in
    # --dry-run makes a stale never-exported snapshot visible without mutating
    # anything (the v0.30.0 "5 vs 31 sources" incident was invisible because
    # dry-run only reported import counts).
    would_export: bool = False


def autosync(
    internal_dir: Path,
    db_path: Path,
    *,
    dry_run: bool = False,
    dir_name: str = "sync",
) -> AutosyncResult:
    """One-shot bidirectional sync: import peers (+ merge/archive conflict files),
    then export this device's snapshot only if anything actually changed.

    Loop-safe: never imports own file; export is skipped when nothing changed, and
    even when it runs, peers ignore this device's file and re-import is mtime-gated.
    """
    result = AutosyncResult(dry_run=dry_run)
    conflicts = detect_conflict_files(internal_dir, dir_name=dir_name)

    # Conflict files are LWW-mergeable; import then archive (real runs only).
    if not dry_run:
        for cf in conflicts:
            try:
                stats = import_knowledge(db_path, cf)
            except Exception as exc:
                raise AutosyncError(
                    f"Conflict file {cf.name} import failed: {exc}"
                ) from exc
            try:
                _archive_conflict(cf, internal_dir)
            except Exception as exc:
                raise AutosyncError(
                    f"Conflict file {cf.name} archive failed: {exc}"
                ) from exc
            result.imported[cf.name] = stats
            result.conflicts.append(cf.name)

    result.imported.update(
        import_all_peers(internal_dir, db_path, dry_run=dry_run, dir_name=dir_name)
    )

    changed = any(
        s.inserted or s.updated or s.deleted for s in result.imported.values()
    )
    result.would_export = changed or local_has_unexported_changes(
        internal_dir, db_path
    )
    if not dry_run and result.would_export:
        result.exported = export_for_device(
            internal_dir, db_path, dir_name=dir_name
        ).name
    return result
