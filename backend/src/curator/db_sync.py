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
    # compiler_generations is intentionally absent: it has no updated_at column
    # (status transitions in place), so it always-upserts on import — the latest
    # exported authoritative-generation status wins (SCHEMA §20.3).
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
# Needed when the SQL-side LWW expression (in _UPDATED_AT_COL) is a COALESCE/expression
# rather than a plain column name, so row.get(updated_col) would return None.
# Each callable receives the row dict and returns the effective timestamp string.
_REMOTE_TS_FN: dict[str, _Callable[[dict], str]] = {
    "sources": lambda row: (
        row.get("updated_at")
        or row.get("last_ingested")
        or row.get("added_at")
        or ""
    ),
}

# Primary key column per table. None = composite/handled-separately (always upsert).
_PK_COL: dict[str, str | None] = {
    "sources": "id",
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


def record_tombstone(db_path: Path, table_name: str, record_id: str) -> None:
    """Record that a canonical row was deleted on this device."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with db.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO deleted_records (table_name, record_id, deleted_at)"
            " VALUES (?, ?, ?)",
            (table_name, record_id, now),
        )


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
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def write_sync_state(internal_dir: Path, state: dict) -> None:
    """Persist this device's local sync bookkeeping."""
    p = _sync_state_path(internal_dir)
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
    stats = ExportStats()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

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

        with db.connect(db_path) as conn:
            existing_tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }

            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("type") != "row":
                    continue
                tbl = rec["table"]
                if tbl not in existing_tables:
                    continue
                row: dict = rec["row"]
                if tbl == "sources" and not row.get("updated_at"):
                    legacy_ts = row.get("last_ingested") or row.get("added_at") or ""
                    normalized_legacy_ts = (
                        f"{legacy_ts[:19]}.000Z"
                        if isinstance(legacy_ts, str)
                        and len(legacy_ts) == 20
                        and legacy_ts.endswith("Z")
                        else legacy_ts
                    )
                    row["updated_at"] = (
                        normalized_legacy_ts
                        if _timestamp_key(normalized_legacy_ts) > _timestamp_key("")
                        else datetime.now(timezone.utc).isoformat(
                            timespec="milliseconds"
                        ).replace("+00:00", "Z")
                    )

                if tbl == "deleted_records":
                    applied = _apply_tombstone(conn, row["table_name"], row["record_id"], row["deleted_at"], dry_run=dry_run)
                    if applied:
                        stats.deleted += 1
                else:
                    result = _lw_upsert(conn, tbl, row, dry_run=dry_run)
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
    if pk_col and updated_col:
        local_record = conn.execute(
            f"SELECT {updated_col} FROM {table_name} WHERE {pk_col} = ?",
            (record_id,),
        ).fetchone()
        if local_record and (local_record[0] or "") >= deleted_at:
            return False

    if not dry_run:
        if pk_col:
            try:
                conn.execute(f"DELETE FROM {table_name} WHERE {pk_col} = ?", (record_id,))
            except Exception:
                pass
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


def _lw_upsert(conn: "db.sqlite3.Connection", table_name: str, row: dict, dry_run: bool = False) -> str:
    """Insert or update a row using Last-Write-Wins.

    Returns: 'inserted' | 'updated' | 'skipped'
    """
    pk_col = _PK_COL.get(table_name)
    updated_col = _UPDATED_AT_COL.get(table_name)

    if pk_col and pk_col in row:
        existing = conn.execute(
            f"SELECT {updated_col} FROM {table_name} WHERE {pk_col} = ?"
            if updated_col
            else f"SELECT 1 FROM {table_name} WHERE {pk_col} = ?",
            (row[pk_col],),
        ).fetchone()

        if existing is None:
            if not dry_run:
                _do_insert(conn, table_name, row)
            return "inserted"

        if updated_col:
            local_ts = existing[0] or ""
            remote_ts_fn = _REMOTE_TS_FN.get(table_name)
            remote_ts = remote_ts_fn(row) if remote_ts_fn else (row.get(updated_col) or "")
            if remote_ts > local_ts:
                if not dry_run:
                    _preserve_device_local(conn, table_name, row)
                    _do_upsert(conn, table_name, row)
                return "updated"
            return "skipped"

        # No updated_at col — always upsert
        if not dry_run:
            _preserve_device_local(conn, table_name, row)
            _do_upsert(conn, table_name, row)
        return "updated"

    # Composite PK or unknown PK — always upsert (INSERT OR REPLACE) as intended
    if not dry_run:
        _do_upsert(conn, table_name, row)
    return "updated"


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


def import_all_peers(
    internal_dir: Path,
    db_path: Path,
    *,
    dry_run: bool = False,
    dir_name: str = "sync",
) -> dict[str, ImportStats]:
    """Import every peer file whose mtime advanced since the last import.

    Never imports this device's own file (loop safety). Records per-peer
    `last_imported_mtime` in sync_state so a re-run is a cheap no-op and a
    late-arriving Syncthing delivery is picked up exactly once.
    """
    results: dict[str, ImportStats] = {}
    state = read_sync_state(internal_dir)
    peers: dict = state.setdefault("peers", {})

    for f in _peer_files(internal_dir, dir_name=dir_name):
        mtime = f.stat().st_mtime
        rec = peers.get(f.name, {})
        if not dry_run and rec.get("last_imported_mtime") == mtime:
            continue
        stats = import_knowledge(db_path, f, dry_run=dry_run)
        results[f.name] = stats
        if not dry_run:
            peers[f.name] = {"last_imported_mtime": mtime}

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
    archive = internal_dir / "runtime" / "sync_conflicts"
    archive.mkdir(parents=True, exist_ok=True)
    try:
        cf.rename(archive / cf.name)
    except Exception:
        pass


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
    result.conflicts = [c.name for c in conflicts]

    # Conflict files are LWW-mergeable; import then archive (real runs only).
    if not dry_run:
        for cf in conflicts:
            try:
                result.imported[cf.name] = import_knowledge(db_path, cf)
            except Exception:
                continue
            _archive_conflict(cf, internal_dir)

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
