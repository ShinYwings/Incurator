"""Cross-device SQLite knowledge synchronization via JSONL export/import.

Usage:
    from curator.db_sync import export_knowledge, import_knowledge, record_tombstone
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

from . import db

SCHEMA_VERSION = db.SCHEMA_VERSION

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
    "graph_entities",
    "graph_relations",
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
    "sources": "last_ingested",
    "atoms": "last_updated",
    "concepts": "last_updated",
    "synthesis_nodes": "updated_at",
    "source_spans": "created_at",
    "knowledge_units": "updated_at",
    "graph_entities": "updated_at",
    "graph_relations": "updated_at",
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

# Primary key column per table.
_PK_COL: dict[str, str] = {
    "sources": "id",
    "atoms": "id",
    "concepts": "id",
    "synthesis_nodes": "id",
    "source_spans": "id",
    "knowledge_units": "id",
    "graph_entities": "id",
    "graph_relations": "id",
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
    opener: IO[str]
    if compress:
        opener = gzip.open(out_path, "wt", encoding="utf-8")  # type: ignore[assignment]
    else:
        opener = out_path.open("w", encoding="utf-8")

    with opener as f:
        # Header line
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
                        json.dumps({"type": "row", "table": tbl, "row": dict(row)}) + "\n"
                    )
                    count += 1
                stats.rows_by_table[tbl] = count
                stats.total_rows += count

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

        if dry_run:
            # Count without writing
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("type") != "row":
                    continue
                tbl = rec["table"]
                row = rec["row"]
                if tbl == "deleted_records":
                    stats.deleted += 1
                else:
                    stats.inserted += 1  # approximate in dry-run
            return stats

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

                if tbl == "deleted_records":
                    _apply_tombstone(conn, row["table_name"], row["record_id"], row["deleted_at"])
                    stats.deleted += 1
                else:
                    result = _lw_upsert(conn, tbl, row)
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
) -> None:
    """Delete a record from its table and record the tombstone locally."""
    # Check if there is already a newer tombstone
    existing_tombstone = conn.execute(
        "SELECT deleted_at FROM deleted_records WHERE table_name = ? AND record_id = ?",
        (table_name, record_id),
    ).fetchone()
    if existing_tombstone and existing_tombstone[0] >= deleted_at:
        return

    # Check if the local record is newer than the tombstone
    pk_col = _PK_COL.get(table_name)
    updated_col = _UPDATED_AT_COL.get(table_name)
    if pk_col and updated_col:
        local_record = conn.execute(
            f"SELECT {updated_col} FROM {table_name} WHERE {pk_col} = ?",
            (record_id,),
        ).fetchone()
        if local_record and (local_record[0] or "") >= deleted_at:
            return

    if pk_col:
        try:
            conn.execute(f"DELETE FROM {table_name} WHERE {pk_col} = ?", (record_id,))
        except Exception:
            pass
    # Record tombstone so this device also propagates the deletion on future exports.
    conn.execute(
        "INSERT OR REPLACE INTO deleted_records (table_name, record_id, deleted_at)"
        " VALUES (?, ?, ?)",
        (table_name, record_id, deleted_at),
    )


def _lw_upsert(conn: "db.sqlite3.Connection", table_name: str, row: dict) -> str:
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
            _do_insert(conn, table_name, row)
            return "inserted"

        if updated_col:
            local_ts = existing[0] or ""
            remote_ts = row.get(updated_col) or ""
            if remote_ts > local_ts:
                _do_upsert(conn, table_name, row)
                return "updated"
            return "skipped"

        # No updated_at col — always upsert
        _do_upsert(conn, table_name, row)
        return "updated"

    # Composite PK or unknown PK — always upsert (INSERT OR REPLACE) as intended
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


def _do_insert_or_ignore(conn: "db.sqlite3.Connection", table: str, row: dict) -> None:
    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" * len(row))
    conn.execute(
        f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})",
        list(row.values()),
    )
