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
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Callable as _Callable

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

# Primary key column per table. None = composite/handled-separately (always upsert).
_PK_COL: dict[str, str | None] = {
    "sources": "sync_key",
    "atoms": "id",
    "concepts": "id",
    "synthesis_nodes": "id",
    "source_spans": "id",
    "knowledge_units": "id",
    "claim_supports": None,          # composite PK — always upsert
    "compiler_generations": "id",
    "graph_entities": "id",
    "graph_relations": "id",
    "graph_relation_supports": None,  # composite PK — always upsert
    "entity_aliases": "id",
    "entity_merge_proposals": "id",
    "entity_resolution_lineage": None,  # composite PK — always upsert
    "community_reports": "id",
    "memory_paths": "id",
    "prompt_runs": "trace_id",
    "dag_edges": "id",
    "curation_plans": "id",
    "insight_candidates": "id",
    "artifact_dependencies": None,  # composite PK — always upsert
    "synthesis": "id",
    "query_traces": "trace_id",
    "source_pages": None,           # composite PK — always upsert
    "source_pdf_pages": None,       # composite PK — always upsert
    "deleted_records": None,        # composite PK — handled separately
}


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
) -> None:
    """Record a canonical delete in the caller's transaction."""
    if table_name not in SYNC_TABLES or table_name == "deleted_records":
        raise ValueError(f"Table {table_name!r} is not syncable")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    conn.execute(
        "INSERT OR REPLACE INTO deleted_records (table_name, record_id, deleted_at)"
        " VALUES (?, ?, ?)",
        (table_name, record_id, now),
    )


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
    if device_id is not None and (
        not isinstance(device_id, str) or not device_id.strip()
    ):
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
                    if since and updated_col:
                        rows = conn.execute(
                            f"SELECT * FROM {tbl} WHERE {updated_col} >= ?", (since,)
                        ).fetchall()
                    else:
                        rows = conn.execute(f"SELECT * FROM {tbl}").fetchall()

                    count = 0
                    for row in rows:
                        f.write(
                            json.dumps(
                                {"type": "row", "table": tbl, "row": dict(row)}
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
            source_id_map: dict[int, int] = {}

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
                    if result == "inserted":
                        stats.inserted += 1
                    elif result == "updated":
                        stats.updated += 1
                    else:
                        stats.skipped += 1
                else:
                    if row.get("source_id") is not None:
                        remote_source_id = row["source_id"]
                        if remote_source_id not in source_id_map:
                            raise ValueError(
                                f"Table {tbl!r} references unmapped source_id "
                                f"{remote_source_id!r}"
                            )
                        row["source_id"] = source_id_map[remote_source_id]
                    result = _lw_upsert(
                        conn,
                        tbl,
                        row,
                        dry_run=dry_run,
                        primary_keys=table_primary_keys[tbl],
                    )
                    if result == "inserted":
                        stats.inserted += 1
                    elif result == "updated":
                        stats.updated += 1
                    else:
                        stats.skipped += 1

    return stats


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

    # Check if there is already a newer tombstone
    existing_tombstone = conn.execute(
        "SELECT deleted_at FROM deleted_records WHERE table_name = ? AND record_id = ?",
        (table_name, record_id),
    ).fetchone()
    if existing_tombstone and existing_tombstone[0] >= deleted_at:
        return False

    # Check if the local record is newer than the tombstone
    pk_col = _PK_COL.get(table_name)
    updated_col = _UPDATED_AT_COL.get(table_name)
    if table_name == "sources":
        pk_col = "sync_key"
    if pk_col and updated_col:
        local_record = conn.execute(
            f"SELECT {updated_col} FROM {table_name} WHERE {pk_col} = ?",
            (record_id,),
        ).fetchone()
        if local_record and (local_record[0] or "") >= deleted_at:
            return False

    if not dry_run:
        if pk_col:
            conn.execute(f"DELETE FROM {table_name} WHERE {pk_col} = ?", (record_id,))
        else:
            # Composite-PK tables cannot be deleted by a single record_id. The
            # tombstone is still recorded for propagation, but the local row is not
            # removed here — surface it rather than failing silently.
            logger.warning(
                "Tombstone for composite-PK table %r (record_id=%r) recorded but not "
                "applied as a delete; composite-key deletion is unsupported.",
                table_name, record_id,
            )
        # Record tombstone so this device also propagates the deletion on future exports.
        conn.execute(
            "INSERT OR REPLACE INTO deleted_records (table_name, record_id, deleted_at)"
            " VALUES (?, ?, ?)",
            (table_name, record_id, deleted_at),
        )
    return True


def _source_sync_key(row: dict) -> str:
    sync_key = str(row.get("sync_key") or "").strip()
    if sync_key:
        return sync_key
    raise ValueError("Source row is missing sync_key")


def _lw_upsert_source(
    conn: "db.sqlite3.Connection",
    row: dict,
    *,
    dry_run: bool = False,
) -> tuple[str, int]:
    """Merge a source by portable key while preserving the local integer id."""
    sync_key = _source_sync_key(row)
    row["sync_key"] = sync_key
    remote_ts = _REMOTE_TS_FN["sources"](row)
    if _timestamp_key(remote_ts) == datetime.min.replace(tzinfo=timezone.utc):
        raise ValueError("Source row is missing a valid updated_at revision")
    remote_id = row.get("id")
    existing = conn.execute(
        "SELECT * FROM sources WHERE sync_key = ?",
        (sync_key,),
    ).fetchone()
    if existing is None:
        if dry_run:
            return "inserted", int(remote_id or 0)
        insert_row = {key: value for key, value in row.items() if key != "id"}
        _do_insert(conn, "sources", insert_row)
        inserted = conn.execute(
            "SELECT id FROM sources WHERE sync_key = ?",
            (sync_key,),
        ).fetchone()
        if inserted is None:
            raise ValueError(
                f"Source {sync_key!r} conflicts with an existing local relpath"
            )
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
) -> str:
    """Insert or update a row using Last-Write-Wins.

    Returns: 'inserted' | 'updated' | 'skipped'
    """
    pk_col = _PK_COL.get(table_name)
    updated_col = _UPDATED_AT_COL.get(table_name)
    key_columns = primary_keys or ([pk_col] if pk_col else [])

    if key_columns and all(key in row for key in key_columns):
        where = " AND ".join(f"{key} IS ?" for key in key_columns)
        existing = conn.execute(
            f"SELECT * FROM {table_name} WHERE {where}",
            tuple(row[key] for key in key_columns),
        ).fetchone()

        if existing is None:
            if not dry_run:
                _do_insert(conn, table_name, row)
            return "inserted"

        if updated_col:
            local_ts = existing[updated_col] or ""
            remote_ts_fn = _REMOTE_TS_FN.get(table_name)
            remote_ts = remote_ts_fn(row) if remote_ts_fn else (row.get(updated_col) or "")
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


def _do_insert(conn: "db.sqlite3.Connection", table: str, row: dict) -> None:
    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" * len(row))
    conn.execute(f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})", list(row.values()))


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
    export_knowledge(db_path, out)

    state = read_sync_state(internal_dir)
    state["last_export_ts"] = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    write_sync_state(internal_dir, state)
    return out


def _peer_files(internal_dir: Path, *, dir_name: str = "sync") -> list[Path]:
    """All peer export files (dev-*.jsonl) excluding this device's own file and any
    Syncthing conflict files (handled separately)."""
    sync_dir = _sync_dir(internal_dir, dir_name=dir_name)
    if not sync_dir.is_dir():
        return []
    own = f"dev-{get_device_id(internal_dir)}.jsonl"
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

    Returns ``None`` for incompatible peer files so ``import_all_peers`` can skip
    them without attempting a partial import.
    """
    try:
        opener: IO[str]
        if path.suffix == ".gz":
            opener = gzip.open(path, "rt", encoding="utf-8")  # type: ignore[assignment]
        else:
            opener = path.open("r", encoding="utf-8")
        with opener as handle:
            line = handle.readline().strip()
    except (OSError, ValueError):
        logger.warning("Could not read peer export file: %s", path)
        return None
    if not line:
        logger.warning("Empty peer export file: %s", path)
        return None
    try:
        header = json.loads(line)
        if not isinstance(header, dict):
            logger.warning("Peer export header is not a JSON object: %s", path)
            return None
    except json.JSONDecodeError:
        logger.warning("Malformed JSON header in peer export: %s", path)
        return None
    if header.get("type") != "header":
        logger.warning("Missing header row in peer export: %s", path)
        return None
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
        logger.warning(
            "Peer export %s has no export_id; skipping.",
            path.name,
        )
        return None
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
    state = read_sync_state(internal_dir)
    peers: dict = state.setdefault("peers", {})

    for f in _peer_files(internal_dir, dir_name=dir_name):
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
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


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
    so it stops re-triggering the conflict notice and is not re-synced."""
    from . import config as cfg

    archive = (
        cfg.get_vault_cache_dir(internal_dir.parent)
        / "runtime"
        / "sync_conflicts"
    )
    archive.mkdir(parents=True, exist_ok=True)
    cf.rename(archive / cf.name)


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
