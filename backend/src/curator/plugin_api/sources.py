from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .. import config as cfg
from .. import db, ingest_raw, search, source_tools

def source_row(
    paths: cfg.WikiPaths,
    *,
    source_id: int | None = None,
    relpath: str = "",
    source_path: str = "",
) -> dict[str, Any] | None:
    return db.get_source_row(
        paths.state_db,
        paths.root,
        source_id=source_id,
        relpath=relpath,
        source_path=source_path,
    )


def source_dict(
    paths: cfg.WikiPaths,
    row: dict[str, Any],
    config: dict,
    *,
    light: bool = False,
) -> dict[str, Any]:
    source_id = int(row["id"])
    pages = db.list_source_pdf_pages(paths.state_db, source_id)
    generated = db.list_source_pages(paths.state_db, source_id)

    if light:
        out = dict(row)
        expected_hash = str(row.get("content_hash") or "")
        path = source_tools._row_path(paths, row)
        pending_jobs = db.get_pending_jobs_for_source(paths.state_db, source_id)
        out.update(
            {
                "state": source_tools.derive_source_state(row, pending_jobs),
                "message": "Cached status from database.",
                "current_path": str(path),
                "current_hash": expected_hash,
                "requires_rebind": False,
                "registered": True,
                "source_id": source_id,
                "l1_complete": str(row.get("l1_status") or "") == "done",
                "l2_complete": str(row.get("l2_status") or "") == "done",
                "l3_complete": str(row.get("l3_status") or "") == "done",
                "l4_complete": str(row.get("l4_status") or "") == "done",
                "jobs_pending": pending_jobs,
            }
        )
    else:
        out = source_tools.source_status(paths, row, config)

    out["pdf_page_count"] = len(pages)
    out["page_count"] = len(pages)
    out["generated_pages"] = generated
    return out


def source_status(
    paths: cfg.WikiPaths,
    *,
    file_hash: str = "",
    source_id: int | None = None,
    relpath: str = "",
    source_path: str = "",
    file_path: str = "",
    path: str = "",
    status_filter: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    config = cfg.load_config(paths)
    stats = db.get_stats(paths.state_db)

    if file_hash:
        with db.connect(paths.state_db) as conn:
            row = conn.execute(
                "SELECT * FROM sources WHERE content_hash = ? ORDER BY id DESC LIMIT 1",
                (file_hash,),
            ).fetchone()
        if row is None:
            return {
                "registered": False,
                "source_id": None,
                "l1_complete": False,
                "l2_complete": False,
                "l3_complete": False,
                "l4_complete": False,
                "jobs_pending": [],
            }
        source = source_dict(paths, dict(row), config)
        return {
            "registered": True,
            "source_id": int(row["id"]),
            "relpath": row["relpath"],
            "source_path": row["relpath"],
            "l1_complete": source.get("l1_complete", False),
            "l2_complete": source.get("l2_complete", False),
            "l3_complete": source.get("l3_complete", False),
            "l4_complete": source.get("l4_complete", False),
            "jobs_pending": source.get("jobs_pending", []),
            "source": source,
        }

    lookup_path = relpath or source_path or file_path or path
    if source_id is not None or lookup_path:
        row = source_row(paths, source_id=source_id, relpath=relpath, source_path=lookup_path)
        if row is None:
            return {
                "state": "untracked",
                "error": "Source not found",
                "source_path": lookup_path,
                "stats": stats,
            }
        return {"stats": stats, "source": source_dict(paths, row, config)}

    query_sql = "SELECT * FROM sources"
    params: tuple[Any, ...] = ()
    if status_filter:
        query_sql += " WHERE status = ?"
        params = (status_filter,)
    query_sql += " ORDER BY id ASC LIMIT ?"
    params = (*params, max(1, min(int(limit), 500)))

    with db.connect(paths.state_db) as conn:
        rows = conn.execute(query_sql, params).fetchall()
    return {
        "stats": stats,
        "sources": [source_dict(paths, dict(row), config, light=True) for row in rows],
        "count": len(rows),
    }


def import_source(
    paths: cfg.WikiPaths,
    *,
    file_path: str = "",
    zotero_attachment_key: str = "",
    zotero_custom_paths: str = "",
    policy: str = "mirror_03_to_04",
    destination: str = "",
    dry_run: bool = False,
    logical_source_id: str = "",
) -> dict[str, Any]:
    if not file_path and zotero_attachment_key:
        from .. import zotero_tools

        resolved = zotero_tools.resolve_pdf(zotero_attachment_key, paths, zotero_custom_paths)
        if not resolved.get("ok") or not resolved.get("path"):
            return {
                "ok": False,
                "state": str(resolved.get("state") or "zotero_pdf_unavailable"),
                "error": str(resolved.get("error") or "Zotero PDF not found"),
                "zotero_attachment_key": zotero_attachment_key,
                "resolution": resolved,
            }
        file_path = str(resolved["path"])
        effective_key = str(resolved.get("attachment_key") or zotero_attachment_key)
        zotero_attachment_key = effective_key
        logical_source_id = logical_source_id or f"zotero:{effective_key}"
    if not file_path:
        return {"ok": False, "state": "missing_path", "error": "No source file path or Zotero attachment key provided"}

    outcome = ingest_raw.import_source_file(
        paths,
        Path(file_path),
        policy=policy,
        destination=destination or None,
        dry_run=dry_run,
        logical_source_id=logical_source_id,
    )
    return {
        "ok": outcome.result in {ingest_raw.AddResult.ADDED, ingest_raw.AddResult.DEDUPED},
        "result": outcome.result.value,
        "dry_run": dry_run,
        "policy": policy,
        "source_id": outcome.source_id,
        "relpath": outcome.relpath,
        "source_path": str(outcome.source_path),
        "zotero_attachment_key": zotero_attachment_key,
        "title": outcome.title,
        "file_type": outcome.file_type,
        "bytes": outcome.bytes,
        "word_count": outcome.word_count,
        "message": outcome.message,
    }


def register_source(
    paths: cfg.WikiPaths,
    *,
    source_id: int | None = None,
    relpath: str = "",
    source_path: str = "",
    file_path: str = "",
    path: str = "",
    force: bool = False,
    build: bool = True,
    asset_dir: str = "",
) -> dict[str, Any]:
    lookup_path = relpath or source_path or file_path or path
    row = source_row(paths, source_id=source_id, relpath=relpath, source_path=lookup_path)
    if row is None:
        return {"state": "untracked", "error": "Source not found", "source_path": lookup_path}

    source_id_int = int(row["id"])
    if force:
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "UPDATE sources SET status = 'force_pending', error_reason = NULL, "
                "l1_status = 'pending', l2_status = 'pending', "
                "l3_status = 'pending', l4_status = 'pending', layer_error = NULL "
                "WHERE id = ?",
                (source_id_int,),
            )
        row["context_id"] = None

    context_id = row.get("context_id")
    if force or not context_id or not (paths.contexts / f"{context_id}.md").exists():
        db.set_source_layer_status(paths.state_db, source_id_int, "l1", "running")
        context_id = ingest_raw.generate_l1_structural_context(
            paths,
            source_id=source_id_int,
            relpath=str(row["relpath"]),
            content_hash=str(row["content_hash"]),
            existing_context_id=None if force else row.get("context_id"),
            asset_dir=asset_dir or None,
        )
        if not context_id:
            if not force and row.get("l1_status") == "done" and row.get("context_id"):
                db.set_source_layer_status(paths.state_db, source_id_int, "l1", "done")
                return {
                    "ok": True,
                    "state": source_tools.derive_source_state(row),
                    "source_id": source_id_int,
                    "context_id": row.get("context_id"),
                    "l2_l3_queued": False,
                    "job_ids": [],
                    "jobs_pending": [],
                    "warnings": [
                        "CTX projection repair failed; authoritative L1 DB state was preserved"
                    ],
                }
            return {"ok": False, "source_id": source_id_int, "error": "L1 generation failed"}

    warnings: list[str] = []
    try:
        search.update_index(paths, embed=False)
    except (OSError, sqlite3.Error, search.SearchBackendError) as exc:
        warnings.append(f"Search index refresh skipped: {type(exc).__name__}: {exc}")

    job_ids: list[int] = []
    if build:
        from ..ingest_worker import enqueue_l2_l3_for_sources

        job_ids = enqueue_l2_l3_for_sources(paths, [source_id_int])

    state = "queued" if job_ids else "l1_ready"
    return {
        "ok": True,
        "state": state,
        "source_id": source_id_int,
        "context_id": context_id,
        "l2_l3_queued": bool(job_ids),
        "job_ids": job_ids,
        "jobs_pending": db.get_pending_jobs_for_source(paths.state_db, source_id_int),
        "warnings": warnings,
    }


def rebind_source(
    paths: cfg.WikiPaths,
    *,
    source_id: int | None = None,
    logical_source_id: str = "",
    source_path: str = "",
    file_path: str = "",
    path: str = "",
    new_path: str = "",
    apply: bool = False,
    update_hash: bool = True,
) -> dict[str, Any]:
    lookup_path = source_path or file_path or path or logical_source_id
    row = source_row(paths, source_id=source_id, source_path=lookup_path)
    if row is None:
        return {
            "ok": False,
            "state": "untracked",
            "error": "Source not found",
            "source_path": lookup_path,
        }
    if not new_path:
        return {"ok": False, "state": "error", "error": "new_path is required", "source_id": row["id"]}
    try:
        return source_tools.rebind_source(
            paths,
            row,
            Path(new_path),
            apply=apply,
            update_hash=update_hash,
        )
    except Exception as exc:
        return {"ok": False, "state": "error", "error": str(exc), "source_id": row["id"]}


def search_sources(
    paths: cfg.WikiPaths,
    *,
    query_text: str,
    source_id: int | None = None,
    source_path: str = "",
    file_path: str = "",
    path: str = "",
    relpath: str = "",
    limit: int = 8,
) -> dict[str, Any]:
    lookup_path = relpath or source_path or file_path or path
    if source_id is None and lookup_path:
        row = source_row(paths, source_path=lookup_path)
        if row is None:
            return {
                "hits": [],
                "count": 0,
                "state": "untracked",
                "error": "Source not found",
                "source_path": lookup_path,
            }
        source_id = int(row["id"])
    hits = search.search_source_pages(
        paths,
        query_text,
        source_id=source_id,
        limit=max(1, min(int(limit), 50)),
    )
    return {
        "hits": [
            {
                "source_id": hit.source_id,
                "relpath": hit.relpath,
                "file_type": hit.file_type,
                "page": hit.page_number,
                "score": hit.score,
                "title": hit.title,
                "snippet": hit.snippet,
            }
            for hit in hits
        ],
        "count": len(hits),
    }

