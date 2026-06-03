"""Backend-owned runtime snapshots for the Obsidian plugin dashboard.

The plugin reads these JSON files directly, but backend code is the only writer.
They are cache/snapshot files derived from state.sqlite and generated artifacts;
they are not a second source of truth.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from . import config as cfg
from . import constants as consts
from . import db
from . import ingest_raw
from . import search


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def runtime_dir(paths: cfg.WikiPaths) -> Path:
    return paths.internal / "runtime"


def snapshot_path(paths: cfg.WikiPaths, name: str) -> Path:
    return runtime_dir(paths) / f"{name}.json"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _count_md(folder: Path) -> int:
    if not folder.exists():
        return 0
    return sum(1 for p in folder.glob("*.md") if not p.name.startswith("."))


def _count_raw_files(paths: cfg.WikiPaths) -> int:
    total = 0
    for raw_dir in paths.raw_dirs:
        if raw_dir.exists():
            total += sum(1 for p in raw_dir.rglob("*") if p.is_file() and not p.name.startswith("."))
    return total


def _wiki_binary() -> str | None:
    wiki_bin = shutil.which("wiki")
    if wiki_bin:
        return wiki_bin
    py_dir = Path(sys.executable).parent
    for name in ("wiki", "wiki.exe"):
        candidate = py_dir / name
        if candidate.exists():
            return str(candidate)
    if sys.argv and sys.argv[0]:
        arg0 = Path(sys.argv[0])
        if arg0.name.startswith("wiki"):
            return str(arg0)
    return None


def _job_summary(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job.get("id"),
        "source_id": job.get("source_id"),
        "source_name": job.get("source_name") or "",
        "job_type": job.get("job_type") or "",
        "state": job.get("state") or "",
        "phase": job.get("phase") or "",
        "progress": job.get("progress") or 0.0,
        "progress_current": job.get("progress_current") or 0,
        "progress_total": job.get("progress_total") or 0,
        "started_at": job.get("started_at") or "",
        "finished_at": job.get("finished_at") or "",
        "retry_count": job.get("retry_count") or 0,
        "error": job.get("error") or "",
    }


def build_jobs_snapshot(paths: cfg.WikiPaths) -> dict[str, Any]:
    if not paths.state_db.exists():
        running: list[dict[str, Any]] = []
        queued: list[dict[str, Any]] = []
        done_today: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        cancelled: list[dict[str, Any]] = []
    else:
        running = db.list_ingest_jobs(paths.state_db, states=(consts.STATUS_RUNNING,), limit=20)
        queued = db.list_ingest_jobs(paths.state_db, states=(consts.STATUS_QUEUED,), limit=50)
        done_today = db.get_jobs_done_today(paths.state_db)
        failed = db.list_ingest_jobs(paths.state_db, states=(consts.STATUS_FAILED,), limit=20)
        cancelled = db.list_ingest_jobs(paths.state_db, states=(consts.STATUS_CANCELLED,), limit=20)
    return {
        "ok": True,
        "generated_at": _now_iso(),
        "running": [_job_summary(job) for job in running],
        "queued": [_job_summary(job) for job in queued],
        "done": [_job_summary(job) for job in done_today[:20]],
        "failed": [_job_summary(job) for job in failed],
        "cancelled": [_job_summary(job) for job in cancelled],
        "done_today": len(done_today),
        "idle": len(running) == 0 and len(queued) == 0,
    }


def _source_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "relpath": row.get("relpath") or "",
        "source_path": row.get("relpath") or "",
        "file_type": row.get("file_type") or "",
        "bytes": row.get("bytes") or 0,
        "added_at": row.get("added_at") or "",
        "status": row.get("status") or "",
        "context_id": row.get("context_id") or "",
        "l1_status": row.get("l1_status") or "",
        "l2_status": row.get("l2_status") or "",
        "l3_status": row.get("l3_status") or "",
        "l4_status": row.get("l4_status") or "",
        "layer_error": row.get("layer_error") or "",
        "error_reason": row.get("error_reason") or "",
        "is_reference": bool(row.get("is_reference")),
        "external_path": row.get("external_path") or "",
        "logical_source_id": row.get("logical_source_id") or "",
    }


def _source_layer_counts(paths: cfg.WikiPaths) -> dict[str, int]:
    if not paths.state_db.exists():
        return {"total": 0, "l1_done": 0, "l2_done": 0, "l3_done": 0, "l4_done": 0, "errors": 0}
    with db.connect(paths.state_db) as conn:
        row = conn.execute(
            """
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN l1_status = 'done' THEN 1 ELSE 0 END) AS l1_done,
              SUM(CASE WHEN l2_status = 'done' THEN 1 ELSE 0 END) AS l2_done,
              SUM(CASE WHEN l3_status = 'done' THEN 1 ELSE 0 END) AS l3_done,
              SUM(CASE WHEN l4_status = 'done' THEN 1 ELSE 0 END) AS l4_done,
              SUM(CASE WHEN status = 'error' OR (layer_error IS NOT NULL AND layer_error != '') THEN 1 ELSE 0 END) AS errors
            FROM sources
            """
        ).fetchone()
    return {
        "total": int(row["total"] or 0),
        "l1_done": int(row["l1_done"] or 0),
        "l2_done": int(row["l2_done"] or 0),
        "l3_done": int(row["l3_done"] or 0),
        "l4_done": int(row["l4_done"] or 0),
        "errors": int(row["errors"] or 0),
    }


def build_sources_snapshot(paths: cfg.WikiPaths, *, limit: int = 100) -> dict[str, Any]:
    sources = ingest_raw.list_sources(paths)
    recent = list(reversed(sources))[: max(1, min(int(limit), 500))]
    return {
        "ok": True,
        "generated_at": _now_iso(),
        "total": len(sources),
        "sources": [_source_summary(row) for row in recent],
    }


def build_status_snapshot(paths: cfg.WikiPaths, config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config if config is not None else cfg.load_config(paths)
    stats = db.get_stats(paths.state_db)
    layer_counts = {
        "contexts": _count_md(paths.contexts),
        "atoms": _count_md(paths.atoms),
        "concepts": _count_md(paths.concepts),
        "exhibitions": _count_md(paths.exhibitions),
    }
    qmd_bin = search.get_qmd_binary()
    qmd_version = search.get_version() if search.is_available() else None
    jobs = build_jobs_snapshot(paths)
    source_layers = _source_layer_counts(paths)
    return {
        "ok": True,
        "generated_at": _now_iso(),
        "vault_root": str(paths.root),
        "backend_version": __version__,
        "collections": str(paths.collections),
        "wiki_binary": _wiki_binary(),
        "qmd_binary": str(qmd_bin) if qmd_bin else None,
        "qmd_ready": bool(qmd_bin and search.is_available()),
        "qmd_version": qmd_version,
        "total_pages": sum(layer_counts.values()),
        "layer_counts": layer_counts,
        "raw_source_files": _count_raw_files(paths),
        "sources": source_layers,
        "ingest_runs": stats.get("ingest_runs", 0),
        "tokens": {
            "input": stats.get("total_input_tokens", 0),
            "output": stats.get("total_output_tokens", 0),
            "cost_usd": stats.get("total_cost_usd", 0.0),
        },
        "llm": config.get("llm", {}),
        "search": config.get("search", {}),
        "sync": config.get("sync", {}),
        "curate": config.get("curate", {}),
        "external": config.get("external", {}),
        "persona": config.get("persona", {}),
        "jobs": {
            "running": len(jobs["running"]),
            "queued": len(jobs["queued"]),
            "done_today": jobs["done_today"],
            "idle": jobs["idle"],
        },
    }


def write_runtime_snapshots(paths: cfg.WikiPaths, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write all dashboard runtime snapshots and return the status payload."""
    status = build_status_snapshot(paths, config)
    sources = build_sources_snapshot(paths)
    jobs = build_jobs_snapshot(paths)
    _atomic_write_json(snapshot_path(paths, "status"), status)
    _atomic_write_json(snapshot_path(paths, "sources"), sources)
    _atomic_write_json(snapshot_path(paths, "jobs"), jobs)
    return status
