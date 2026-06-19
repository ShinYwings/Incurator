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
from . import device_registry
from . import ingest_raw
from . import llm_identity
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


def _source_display_path(row: dict[str, Any]) -> str:
    logical_id = row.get("logical_source_id") or ""
    if logical_id.startswith("zotero:"):
        key = logical_id.split(":", 1)[1]
        return f"zotero://open-pdf/library/items/{key}"
    return row.get("relpath") or ""


def _source_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "relpath": row.get("relpath") or "",
        "source_path": _source_display_path(row),
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


def _search_models_status(search_config: dict[str, Any]) -> dict[str, Any]:
    """Identity + health of the search embed/rerank models, without loading them.

    Lets the Obsidian plugin show which models are in use and whether they are
    ready (file present + runtime importable), and offer a refresh when not.
    """
    from . import model_setup

    sc = search_config or {}
    cache = model_setup.models_cache_dir()
    llama_ok = model_setup.llama_cpp_installed()

    def _resolve(path_key: str, file_key: str) -> tuple[str, bool]:
        explicit = str(sc.get(path_key) or "").strip()
        if explicit:
            return explicit, Path(explicit).exists()
        filename = str(sc.get(file_key) or "").strip()
        cand = cache / filename if filename else None
        present = bool(cand and cand.exists() and cand.stat().st_size > 0)
        return (str(cand) if cand else ""), present

    def _ready(provider: str, present: bool) -> bool:
        if provider == "llama-cpp":
            return bool(present and llama_ok)
        if provider == consts.BACKEND_OLLAMA:
            return True  # ollama model health is reflected by ollamaReachable
        return False

    embed_provider, _, embed_model = str(sc.get("embedding") or "").partition("::")
    rerank_provider, _, rerank_model = str(sc.get("reranker") or "").partition("::")
    embed_path, embed_present = _resolve("embedding_model_path", "embedding_gguf_file")
    rerank_path, rerank_present = _resolve("reranker_model_path", "reranker_gguf_file")
    rerank_enabled = bool(sc.get("rerank", True))

    return {
        "embed": {
            "provider": embed_provider.strip(), "model": embed_model.strip(),
            "path": embed_path, "present": embed_present,
            "ready": _ready(embed_provider.strip(), embed_present),
        },
        "reranker": {
            "provider": rerank_provider.strip(), "model": rerank_model.strip(),
            "path": rerank_path, "present": rerank_present, "enabled": rerank_enabled,
            "ready": rerank_enabled and _ready(rerank_provider.strip(), rerank_present),
        },
        "llama_cpp_installed": llama_ok,
        "cache_dir": str(cache),
    }


def build_status_snapshot(paths: cfg.WikiPaths, config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config if config is not None else cfg.load_config(paths)
    stats = db.get_stats(paths.state_db)
    
    llm_cfg = config.get("llm", {})
    primary_prov, _ = cfg.split_provider_model(llm_cfg.get("primary", ""))
    fb_prov, _ = cfg.split_provider_model(llm_cfg.get("fallback", ""))
    llm_account = {
        "primary": llm_identity.get_llm_account_info(primary_prov) if primary_prov else None,
        "fallback": llm_identity.get_llm_account_info(fb_prov) if fb_prov else None,
    }
    layer_counts = {
        "contexts": _count_md(paths.contexts),
        "atoms": _count_md(paths.atoms),
        "concepts": _count_md(paths.concepts),
        "synthesis": _count_md(paths.synthesis),
    }
    search_version = search.get_version()
    search_config = (config or {}).get("search", {})
    embed_spec = str(search_config.get("embedding") or "")
    embed_provider, _, embed_model = embed_spec.partition("::")
    vector_ready = bool(
        embed_provider and embed_model
        and db.has_search_embeddings(paths.state_db, embed_provider.strip(), embed_model.strip())
    ) if paths.state_db.exists() else False
    search_models = _search_models_status(search_config)
    jobs = build_jobs_snapshot(paths)
    source_layers = _source_layer_counts(paths)
    # devices registry — read only; never writes here
    _registry = device_registry.load_registry(paths.root)
    _local_id = _registry.get("local_device_id")
    _syncthing_folders = _registry.get("syncthing", {}).get("folders", [])
    if not isinstance(_syncthing_folders, list):
        _syncthing_folders = []
        
    _device_list = []
    for did, d in _registry.get("devices", {}).items():
        if not isinstance(d, dict):
            continue
        is_local = (did == _local_id) or (did == "local")
        synced_folders = _syncthing_folders if is_local else [
            f for f in _syncthing_folders
            if isinstance(f.get("device_ids"), list) and did in f["device_ids"]
        ]
        folder_labels = [
            f.get("label") or f.get("id") or f.get("role")
            for f in synced_folders
        ]
        _device_list.append({
            "device_id": did,
            "name": d.get("name") or did[:12],
            "is_local": is_local,
            "platform": d.get("platform") or {},
            "folders": [lbl for lbl in folder_labels if lbl]
        })
    _device_list.sort(key=lambda x: (not x["is_local"], str(x["name"]).lower()))
    return {
        "ok": True,
        "generated_at": _now_iso(),
        "vault_root": str(paths.root),
        "backend_version": __version__,
        "collections": str(paths.collections),
        "wiki_binary": _wiki_binary(),
        # native DB search engine status (v0.3.2)
        "search_engine": "native",
        "search_ready": True,
        "search_version": search_version,
        "vector_ready": vector_ready,
        "search_models": search_models,
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
        "llm_account": llm_account,
        "llm": config.get("llm", {}),
        "search": config.get("search", {}),
        "sync": config.get("sync", {}),
        "curate": config.get("curate", {}),
        "external": config.get("external", {}),
        "persona": config.get("persona", {}),
        "devices": _device_list,
        "local_device_id": _local_id,
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
