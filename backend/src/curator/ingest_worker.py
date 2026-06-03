"""Background ingest job worker for v0.2.1."""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Callable

from . import config as cfg
from . import constants as consts
from . import db
from . import ingest_llm
from .llm import build_client

_log = logging.getLogger(__name__)

MAX_RETRIES = 3

# Errors that indicate a transient (retryable) failure vs a permanent one.
_TRANSIENT_SIGNALS = (
    "timeout",
    "connection",
    "rate limit",
    "429",
    "503",
    "overloaded",
    "ollama not running",
)


def _is_transient(error: str) -> bool:
    low = error.lower()
    return any(sig in low for sig in _TRANSIENT_SIGNALS)


class WorkerCallbacks(ingest_llm.IngestCallbacks):
    """Minimal callbacks that update job progress and layer status."""

    def __init__(self, paths: cfg.WikiPaths, job_id: int, source_id: int) -> None:
        self.paths = paths
        self.job_id = job_id
        self.source_id = source_id
        self.pages_seen = 0

    def on_pass1_start(self, fragment_count: int) -> None:
        db.update_job_progress(
            self.paths.state_db,
            self.job_id,
            phase=consts.PHASE_L2,
            progress=0.25,
            progress_current=0,
            progress_total=fragment_count,
        )
        db.set_source_layer_status(self.paths.state_db, self.source_id, "l2", consts.STATUS_RUNNING)

    def on_fragment_written(self, _change) -> None:
        self.pages_seen += 1
        db.update_job_progress(
            self.paths.state_db,
            self.job_id,
            phase=consts.PHASE_L2,
            progress=0.5,
            progress_current=self.pages_seen,
        )

    def on_pass2_start(self, fragment_count: int) -> None:
        db.update_job_progress(
            self.paths.state_db,
            self.job_id,
            phase=consts.PHASE_L3,
            progress=0.75,
            progress_current=0,
            progress_total=fragment_count,
        )

    def on_theme_written(self, _change) -> None:
        self.pages_seen += 1
        db.update_job_progress(
            self.paths.state_db,
            self.job_id,
            phase=consts.PHASE_L3,
            progress=0.9,
            progress_current=self.pages_seen,
        )

    def on_error(self, _error: str) -> None:
        db.update_job_progress(self.paths.state_db, self.job_id, phase=consts.STATUS_ERROR)


def enqueue_l2_l3_for_sources(
    paths: cfg.WikiPaths,
    source_ids: list[int],
    *,
    trigger: str = "wiki_add",
) -> list[int]:
    """Queue L2/L3 background processing for sources whose L1 exists."""
    job_ids: list[int] = []
    if not source_ids:
        return job_ids
    with db.connect(paths.state_db) as conn:
        rows = conn.execute(
            f"SELECT id, relpath FROM sources WHERE id IN ({','.join('?' for _ in source_ids)})",
            tuple(source_ids),
        ).fetchall()
    for row in rows:
        job_ids.append(
            db.enqueue_job(
                paths.state_db,
                int(row["id"]),
                consts.PHASE_L2,
                trigger=trigger,
                source_name=Path(str(row["relpath"])).name,
            )
        )
    return job_ids


def run_next_job(paths: cfg.WikiPaths, config: dict | None = None) -> dict:
    """Claim and run one queued job synchronously.

    Scopes L2 extraction to the specific claimed source_id. After L2 succeeds,
    if no other L2 jobs remain queued, triggers global L3 concept clustering.
    Retries transient failures up to MAX_RETRIES times before marking failed.
    """
    job = db.claim_next_job(paths.state_db)
    if job is None:
        return {"ok": True, "job": None, "message": "No queued jobs."}

    job_id = int(job["id"])
    job_type = str(job.get("job_type") or consts.PHASE_L2)
    source_id = int(job["source_id"])
    retry_count = int(job.get("retry_count") or 0)
    config = config or cfg.load_config(paths)
    client = build_client(config)

    try:
        if job_type != consts.PHASE_L2:
            raise ValueError(f"Unsupported job_type: {job_type}")

        db.update_job_progress(paths.state_db, job_id, phase="starting", progress=0.05)
        callbacks = WorkerCallbacks(paths, job_id, source_id)

        # L2: extract atoms for this specific source only
        result = ingest_llm.ingest_source(
            paths,
            source_id,
            client,
            callbacks,
            mode="batch",
        )

        if result.error:
            raise RuntimeError(result.error)

        pages_created = result.pages_created
        pages_updated = result.pages_updated

        # L3: run global concept clustering only when no other L2 jobs are waiting.
        # This prevents redundant clustering after each individual source job.
        remaining_l2 = db.count_active_l2_jobs(paths.state_db)
        # subtract 1 because this job is still marked 'running' in the count
        if remaining_l2 <= 1:
            _log.info("No pending L2 jobs after source %d; triggering L3 clustering.", source_id)
            db.update_job_progress(paths.state_db, job_id, phase=consts.PHASE_L3, progress=0.75)
            try:
                l3_changes = ingest_llm.run_l3_from_existing_atoms(
                    paths, client, lambda: WorkerCallbacks(paths, job_id, source_id)
                )
                pages_created += sum(1 for c in l3_changes if c.operation == "created")
                pages_updated += sum(1 for c in l3_changes if c.operation == "updated")
            except Exception as l3_err:
                # L3 failure is non-fatal for the job: L2 already committed
                _log.warning("L3 clustering failed (non-fatal): %s", l3_err)
                db.set_source_layer_status(
                    paths.state_db, source_id, "l3", consts.STATUS_ERROR, error=str(l3_err)
                )

        in_tok, out_tok = 0, 0
        try:
            get_usage = getattr(client, "get_and_reset_token_usage", None)
            if callable(get_usage):
                result_usage = get_usage()
                in_tok, out_tok = int(result_usage[0]), int(result_usage[1])
        except Exception:
            pass

        db.mark_job_done(
            paths.state_db,
            job_id,
            pages_created=pages_created,
            pages_updated=pages_updated,
        )
        if in_tok or out_tok:
            db.accumulate_job_tokens(paths.state_db, job_id, in_tok, out_tok)
        return {
            "ok": True,
            "job": job,
            "pages_created": pages_created,
            "pages_updated": pages_updated,
            "source_id": source_id,
        }

    except Exception as exc:
        error_str = str(exc)
        if retry_count < MAX_RETRIES and _is_transient(error_str):
            _log.warning(
                "Transient error on job %d (retry %d/%d): %s",
                job_id, retry_count + 1, MAX_RETRIES, error_str,
            )
            db.requeue_job_for_retry(paths.state_db, job_id, retry_count + 1, error_str)
        else:
            db.mark_job_failed(paths.state_db, job_id, error_str)
            db.set_source_layer_status(
                paths.state_db, source_id, "l2", consts.STATUS_ERROR, error=error_str
            )
        return {"ok": False, "job": job, "error": error_str}
    finally:
        try:
            client.close()
        except Exception:
            pass


def run_queued_jobs(
    paths: cfg.WikiPaths,
    config: dict | None = None,
    *,
    limit: int | None = None,
) -> list[dict]:
    """Run queued jobs until the queue is empty or limit is reached."""
    results: list[dict] = []
    count = 0
    while limit is None or count < limit:
        result = run_next_job(paths, config)
        if result.get("job") is None:
            break
        results.append(result)
        count += 1
    return results


class IngestWorker(threading.Thread):
    """Daemon thread intended to run inside the MCP server process."""

    def __init__(
        self,
        paths: cfg.WikiPaths,
        config_loader: Callable[[], dict] | None = None,
        *,
        poll_seconds: float = 10.0,
    ) -> None:
        super().__init__(daemon=True, name="incurator-ingest-worker")
        self.paths = paths
        self.config_loader = config_loader or (lambda: cfg.load_config(paths))
        self.poll_seconds = poll_seconds
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def _write_dashboard(self) -> None:
        """Overwrite .curator/dashboard.md with current job status.

        Called at job start, completion, and failure. Obsidian live preview
        auto-rerenders on file change — no extra plugin polling needed.
        """
        try:
            running = db.list_ingest_jobs(self.paths.state_db, states=(consts.STATUS_RUNNING,), limit=20)
            queued = db.list_ingest_jobs(self.paths.state_db, states=(consts.STATUS_QUEUED,), limit=20)
            done_today = db.get_jobs_done_today(self.paths.state_db)

            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            lines = ["# Incurator Build Status", f"*{now}*", ""]

            if running:
                lines += ["## Active", "| Source | Phase | Progress |", "|--------|-------|----------|"]
                for job in running:
                    cur = job.get("progress_current") or 0
                    total = job.get("progress_total") or 0
                    prog = f"{cur}/{total}" if total else "…"
                    name = job.get("source_name") or str(job.get("source_id", "?"))
                    lines.append(f"| {name} | {job.get('job_type', '')} | {prog} |")
            else:
                lines.append("## Active — idle")

            if queued:
                lines += ["", "## Queue", "| Source | Phase |", "|--------|-------|"]
                for job in queued:
                    name = job.get("source_name") or str(job.get("source_id", "?"))
                    lines.append(f"| {name} | {job.get('job_type', '')} |")

            if done_today:
                total_created = sum(int(j.get("pages_created") or 0) for j in done_today)
                total_updated = sum(int(j.get("pages_updated") or 0) for j in done_today)
                lines += [
                    "",
                    "## Completed Today",
                    f"{len(done_today)} jobs · {total_created} pages created · {total_updated} updated",
                ]

            dashboard = self.paths.internal / consts.FILE_DASHBOARD_MD
            dashboard.parent.mkdir(parents=True, exist_ok=True)
            tmp = dashboard.with_suffix(".tmp")
            tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
            tmp.replace(dashboard)
        except Exception as exc:
            _log.debug("dashboard write failed (non-fatal): %s", exc)

    def _write_build_canvas(self, source_id: int, source_slug: str) -> None:
        """Write an Obsidian Canvas JSON showing the DAG edges for one source.

        Obsidian renders .canvas files natively — no extra plugin needed.
        Generated after L3 completes so ATM→CON edges are recorded.
        """
        try:
            # First pass: source-specific edges (CTX→ATM, source_id set)
            edges = list(db.get_dag_edges_for_source(self.paths.state_db, str(source_id)))
            if not edges:
                return

            ctx_ids: set[str] = set()
            atm_ids: set[str] = set()
            con_ids: set[str] = set()
            exh_ids: set[str] = set()

            def _classify(nid: str) -> None:
                if nid.startswith(f"{consts.PREFIX_L1}-"):
                    ctx_ids.add(nid)
                elif nid.startswith(f"{consts.PREFIX_L2}-"):
                    atm_ids.add(nid)
                elif nid.startswith(f"{consts.PREFIX_L3}-"):
                    con_ids.add(nid)
                elif nid.startswith(f"{consts.PREFIX_L4}-"):
                    exh_ids.add(nid)

            for edge in edges:
                _classify(str(edge["from_id"]))
                _classify(str(edge["to_id"]))

            # Second pass: ATM→CON edges (source_id=NULL, global clustering)
            if atm_ids:
                downstream = db.get_dag_edges_for_atoms(self.paths.state_db, list(atm_ids))
                for edge in downstream:
                    _classify(str(edge["from_id"]))
                    _classify(str(edge["to_id"]))
                edges.extend(downstream)

            LAYER_X = {consts.PREFIX_L1: 0, consts.PREFIX_L2: 320, consts.PREFIX_L3: 640, consts.PREFIX_L4: 960}
            COLORS = {consts.PREFIX_L1: "1", consts.PREFIX_L2: "3", consts.PREFIX_L3: "4", consts.PREFIX_L4: "6"}
            SUBDIRS = {
                consts.PREFIX_L1: consts.LAYER_L1,
                consts.PREFIX_L2: consts.LAYER_L2,
                consts.PREFIX_L3: consts.LAYER_L3,
                consts.PREFIX_L4: consts.LAYER_L4,
            }

            def _node(nid: str, prefix: str, x: int, y: int) -> dict:
                return {
                    "id": nid,
                    "type": "file",
                    "file": f".curator/Collections/{SUBDIRS[prefix]}/{nid}.md",
                    "x": x,
                    "y": y,
                    "width": 220,
                    "height": 60,
                    "color": COLORS[prefix],
                }

            nodes = []
            for i, nid in enumerate(sorted(ctx_ids)):
                nodes.append(_node(nid, consts.PREFIX_L1, LAYER_X[consts.PREFIX_L1], i * 90))
            for i, nid in enumerate(sorted(atm_ids)):
                nodes.append(_node(nid, consts.PREFIX_L2, LAYER_X[consts.PREFIX_L2], i * 90))
            for i, nid in enumerate(sorted(con_ids)):
                nodes.append(_node(nid, consts.PREFIX_L3, LAYER_X[consts.PREFIX_L3], i * 150))
            for i, nid in enumerate(sorted(exh_ids)):
                nodes.append(_node(nid, consts.PREFIX_L4, LAYER_X[consts.PREFIX_L4], i * 150))

            canvas_edges = [
                {
                    "id": f"e_{e['from_id']}_{e['to_id']}",
                    "fromNode": e["from_id"],
                    "toNode": e["to_id"],
                    "label": e["edge_type"],
                }
                for e in edges
            ]

            slug = re.sub(r"[^\w\-]", "_", source_slug)[:40]
            out_path = self.paths.staging / "canvas" / f"build_trace_{slug}.canvas"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = out_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps({"nodes": nodes, "edges": canvas_edges}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(out_path)
            _log.info("Canvas written: %s", out_path.name)
        except Exception as exc:
            _log.debug("Canvas write failed (non-fatal): %s", exc)

    def run(self) -> None:
        db.recover_stale_jobs(self.paths.state_db)
        self._write_dashboard()
        while not self._stop_event.is_set():
            result = run_next_job(self.paths, self.config_loader())
            self._write_dashboard()
            if result.get("ok") and result.get("source_id") is not None:
                source_id = int(result["source_id"])
                job = result.get("job") or {}
                slug = str(job.get("source_name") or f"source_{source_id}")
                self._write_build_canvas(source_id, slug)
            if result.get("job") is None:
                self._stop_event.wait(self.poll_seconds)
