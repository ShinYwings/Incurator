"""Config-aware schema-v10 portable-path migration."""

from __future__ import annotations

import re
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import config as cfg
from . import db, db_sync, ingest_raw, path_refs, zotero_tools


@dataclass
class PortableMigrationResult:
    ok: bool
    dry_run: bool
    rows: list[dict[str, object]] = field(default_factory=list)
    backup_dir: str = ""
    error: str = ""


def _is_absolute(value: str) -> bool:
    return (
        value.startswith(("/", "\\\\", "file:///"))
        or bool(re.match(r"^[A-Za-z]:[\\/]", value))
    )


def _stub_relpath(source_id: int, source_path: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9가-힣._-]+", "-", source_path.stem).strip("-")
    stem = stem[:80] or "external-source"
    return f"04_Resources/References/{stem}-ref-{source_id}.md"


def _backup(paths: cfg.WikiPaths, sync_files: list[Path]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = cfg.get_global_config_dir().parent / "migrations" / "v0.29.0" / stamp
    target.mkdir(parents=True, exist_ok=False)
    shutil.copy2(paths.state_db, target / paths.state_db.name)
    for item in sync_files:
        shutil.copy2(item, target / item.name)
    return target


def migrate_portable_paths(
    paths: cfg.WikiPaths,
    *,
    apply: bool = False,
) -> PortableMigrationResult:
    if not paths.state_db.exists():
        return PortableMigrationResult(ok=True, dry_run=not apply)

    conn = sqlite3.connect(paths.state_db)
    conn.row_factory = sqlite3.Row
    try:
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(sources)").fetchall()
        }
        if {"external_ref", "import_origin_ref"} <= columns:
            return PortableMigrationResult(ok=True, dry_run=not apply)
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, relpath, external_path, import_origin,
                       logical_source_id, is_reference
                FROM sources
                WHERE relpath LIKE '/%'
                   OR external_path IS NOT NULL
                   OR import_origin IS NOT NULL
                ORDER BY id
                """
            ).fetchall()
        ]
        config = cfg.load_config(paths)
        roots = path_refs.configured_roots(config)
        changes: list[dict[str, object]] = []
        for row in rows:
            source_id = int(row["id"])
            raw_path = str(
                row.get("external_path")
                or row.get("import_origin")
                or (row.get("relpath") if _is_absolute(str(row.get("relpath") or "")) else "")
            )
            source_path = Path(raw_path).expanduser() if raw_path else None
            logical = str(row.get("logical_source_id") or "")
            zotero_key = ""
            if logical.startswith("zotero:"):
                zotero_key = logical.split(":", 1)[1]
            elif source_path is not None:
                zotero_key = zotero_tools.attachment_key_for_path(source_path, paths)
            external_ref: str | None = None
            if zotero_key:
                logical = f"zotero:{zotero_key}"
            elif source_path is not None:
                try:
                    external_ref = path_refs.encode_path(source_path, roots)
                except ValueError as exc:
                    return PortableMigrationResult(
                        ok=False,
                        dry_run=not apply,
                        rows=changes,
                        error=f"source #{source_id}: {exc}",
                    )
            relpath = str(row.get("relpath") or "")
            if _is_absolute(relpath):
                if source_path is None:
                    return PortableMigrationResult(
                        ok=False,
                        dry_run=not apply,
                        rows=changes,
                        error=f"source #{source_id}: absolute relpath has no source locator",
                    )
                relpath = _stub_relpath(source_id, source_path)
            changes.append(
                {
                    "source_id": source_id,
                    "old_path": raw_path,
                    "relpath": relpath,
                    "logical_source_id": logical,
                    "external_ref": external_ref,
                }
            )
        if not apply:
            return PortableMigrationResult(ok=True, dry_run=True, rows=changes)

        conn.execute("PRAGMA wal_checkpoint(FULL)")
        sync_dir = paths.internal / "sync"
        sync_files = sorted(sync_dir.glob("*.jsonl")) if sync_dir.exists() else []
        backup_dir = _backup(paths, sync_files)

        conn.execute("BEGIN IMMEDIATE")
        for change in changes:
            source_id = int(str(change["source_id"]))
            old_relpath = str(
                next(row["relpath"] for row in rows if int(row["id"]) == source_id)
            )
            relpath = str(change["relpath"])
            portable = change["external_ref"]
            conn.execute(
                """
                UPDATE sources
                SET relpath = ?, external_path = ?, import_origin = ?,
                    logical_source_id = ?
                WHERE id = ?
                """,
                (
                    relpath,
                    portable,
                    portable,
                    change["logical_source_id"],
                    source_id,
                ),
            )
            for table in ("source_pdf_pages", "source_spans"):
                conn.execute(
                    f"UPDATE {table} SET relpath = ? WHERE source_id = ? AND relpath = ?",
                    (relpath, source_id, old_relpath),
                )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return PortableMigrationResult(ok=False, dry_run=not apply, error=str(exc))
    finally:
        conn.close()

    for change in changes:
        relpath = str(change["relpath"])
        stub = paths.root / relpath
        if not stub.exists():
            source_path = Path(str(change["old_path"]))
            ingest_raw._write_reference_stub(
                stub,
                source=source_path,
                title=source_path.stem,
                logical_source_id=str(change["logical_source_id"]),
                external_ref=(
                    str(change["external_ref"])
                    if change["external_ref"] is not None
                    else None
                ),
            )

    db.init_db(paths.state_db)
    for item in sync_files:
        item.unlink(missing_ok=True)
    if sync_files:
        db_sync.export_knowledge(paths.state_db, sync_files[0])
    return PortableMigrationResult(
        ok=True,
        dry_run=False,
        rows=changes,
        backup_dir=str(backup_dir),
    )
