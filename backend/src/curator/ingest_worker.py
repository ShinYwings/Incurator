"""Background ingest job worker for v0.2.1."""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Callable

from . import config as cfg
from .db import job_events
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
    """Callbacks that update job progress, layer status, and job history.

    ``update_job_progress`` overwrites the job row, so a reader only ever sees
    the latest phase. That makes a stalled job and a working one look identical:
    both sit at the same phase and percentage indefinitely. Each callback below
    therefore also appends to ``job_events``, which is append-only — the
    difference between "no new events for ten minutes" and "an event a second
    ago" is the whole signal, and it did not exist.
    """

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
        self._event("status", phase=consts.PHASE_L2, fragments=fragment_count)

    def on_fragment_written(self, _change) -> None:
        self.pages_seen += 1
        db.update_job_progress(
            self.paths.state_db,
            self.job_id,
            phase=consts.PHASE_L2,
            progress=0.5,
            progress_current=self.pages_seen,
        )
        self._event("extracted", phase=consts.PHASE_L2, done=self.pages_seen)

    def on_pass2_start(self, fragment_count: int) -> None:
        db.update_job_progress(
            self.paths.state_db,
            self.job_id,
            phase=consts.PHASE_L3,
            progress=0.75,
            progress_current=0,
            progress_total=fragment_count,
        )
        self._event("status", phase=consts.PHASE_L3, fragments=fragment_count)

    def on_theme_written(self, _change) -> None:
        self.pages_seen += 1
        db.update_job_progress(
            self.paths.state_db,
            self.job_id,
            phase=consts.PHASE_L3,
            progress=0.9,
            progress_current=self.pages_seen,
        )
        self._event("chunk", phase=consts.PHASE_L3, done=self.pages_seen)

    def on_error(self, _error: str) -> None:
        db.update_job_progress(self.paths.state_db, self.job_id, phase=consts.STATUS_ERROR)
        self._event("error", message=str(_error)[:500])

    def _event(self, kind: str, **data: object) -> None:
        """Record one history entry. Never raises — see append_job_event."""
        job_events.append(self.paths.state_db, self.job_id, kind, data)


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


def enqueue_l3_global(
    paths: cfg.WikiPaths,
    *,
    trigger: str = "wiki_build",
) -> int:
    """Queue a standalone global L3 clustering job (source_id=0 sentinel)."""
    return db.enqueue_job(
        paths.state_db,
        0,  # sentinel: no specific source
        consts.PHASE_L3,
        trigger=trigger,
        source_name="Global L3 Clustering",
    )


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
    source_id = int(job["source_id"] or 0)
    retry_count = int(job.get("retry_count") or 0)
    config = config or cfg.load_config(paths)
    client = build_client(config)

    try:
        if job_type == consts.PHASE_L3:
            db.update_job_progress(paths.state_db, job_id, phase=consts.PHASE_L3, progress=0.1)
            try:
                l3_changes = ingest_llm.run_l3_from_existing_atoms(
                    paths, client, lambda: WorkerCallbacks(paths, job_id, 0)
                )
                pages_created = sum(1 for c in l3_changes if c.operation == "created")
                pages_updated = sum(1 for c in l3_changes if c.operation == "updated")
                db.mark_job_done(paths.state_db, job_id, pages_created=pages_created, pages_updated=pages_updated)
                # How a job ENDED is the part a reader most often needs, and the
                # row alone cannot say how far it got before it stopped.
                job_events.append(
                    paths.state_db, job_id, "done",
                    {"pages_created": pages_created, "pages_updated": pages_updated},
                )
                return {
                    "ok": True,
                    "job": job,
                    "pages_created": pages_created,
                    "pages_updated": pages_updated,
                    "source_id": 0,
                }
            except Exception as l3_err:
                # KEEP broad: clustering can fail many ways; surface (log + re-raise
                # as RuntimeError) so the outer job handler records the failure.
                _log.error("Global L3 clustering failed: %s", l3_err)
                raise RuntimeError(str(l3_err))

        if job_type != consts.PHASE_L2:
            raise ValueError(f"Unsupported job_type: {job_type}")

        db.update_job_progress(paths.state_db, job_id, phase=consts.PHASE_L2, progress=0.1,
                               progress_current=0, progress_total=1)

        # L2: compile knowledge units + graph for this source (v0.3.1 pipeline).
        from .pipeline import compile as _compile
        from . import runtime_state

        cr = _compile.compile_source_l2(paths, client, source_id)
        if not cr.ok:
            raise RuntimeError(cr.error or "L2 compile failed")
        db.set_source_layer_status(paths.state_db, source_id, "l2", consts.STATUS_DONE)
        ingest_llm._mark_source_status(paths, source_id, "curated")

        # Update progress to reflect L2 complete; progress_total = atoms created
        pages_created = len(cr.atom_ids)
        db.update_job_progress(paths.state_db, job_id, phase=consts.PHASE_L2, progress=0.5,
                               progress_current=pages_created, progress_total=max(1, pages_created))
        # Write snapshot so the plugin dashboard sees the L2-done state immediately.
        try:
            runtime_state.write_runtime_snapshots(paths)
        except Exception as e:
            # KEEP broad: the dashboard snapshot is best-effort observability and
            # must never fail the committed L2 job; log instead of swallowing.
            _log.debug("Runtime snapshot write failed after L2 (non-fatal): %s", e)

        pages_updated = 0

        # L3: run global concept clustering only when no other L2 jobs are waiting.
        # This prevents redundant clustering after each individual source job.
        remaining_l2 = db.count_active_l2_jobs(paths.state_db)
        # subtract 1 because this job is still marked 'running' in the count
        if remaining_l2 <= 1:
            _log.info("No pending L2 jobs after source %d; triggering L3 clustering.", source_id)
            db.update_job_progress(paths.state_db, job_id, phase=consts.PHASE_L3, progress=0.75)
            try:
                runtime_state.write_runtime_snapshots(paths)
            except Exception as e:
                # KEEP broad: best-effort dashboard snapshot before L3; non-fatal.
                _log.debug("Runtime snapshot write failed before L3 (non-fatal): %s", e)
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
        except Exception as e:
            # KEEP broad: token accounting is best-effort telemetry across
            # heterogeneous clients; never fail the job over usage parsing.
            _log.debug("Token usage accounting failed (non-fatal): %s", e)

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
        # KEEP broad: this is the job error boundary — any failure is surfaced
        # (logged, requeued if transient or marked failed, returned as ok=False);
        # never silently swallowed. Central to the v0.27.2 fail-fast resilience.
        error_str = str(exc)
        if retry_count < MAX_RETRIES and _is_transient(error_str):
            _log.warning(
                "Transient error on job %d (retry %d/%d): %s",
                job_id, retry_count + 1, MAX_RETRIES, error_str,
            )
            db.requeue_job_for_retry(paths.state_db, job_id, retry_count + 1, error_str)
        else:
            db.mark_job_failed(paths.state_db, job_id, error_str)
            job_events.append(paths.state_db, job_id, "error", {"message": error_str[:500]})
            if source_id:
                db.set_source_layer_status(
                    paths.state_db, source_id, "l2", consts.STATUS_ERROR, error=error_str
                )
        return {"ok": False, "job": job, "error": error_str}
    finally:
        # Re-derive the runtime snapshot on EVERY exit path. The two writes above
        # are mid-run (`running: [this job]`); without one here the last file on
        # disk keeps this job running forever after it ends, because none of the
        # terminal transitions — mark_job_done / mark_job_failed /
        # requeue_job_for_retry — touches it. The plugin's chat status bar polls
        # this snapshot and nothing else, so a stale `running` is a spinner that
        # never stops while `wiki jobs list` (which reads the DB) shows nothing.
        # It belongs in `finally`, not next to each transition: an exception
        # after the DB write would otherwise leave the same stale file behind.
        try:
            from . import runtime_state

            runtime_state.write_runtime_snapshots(paths)
        except Exception as e:
            # KEEP broad: the snapshot is best-effort observability and must
            # never fail a job whose DB state is already committed.
            _log.debug("Runtime snapshot write on job exit failed (non-fatal): %s", e)
        try:
            from . import db_sync

            db_sync.maybe_auto_export(paths)
        except Exception as e:
            _log.debug("Auto-sync export after worker mutation failed: %s", e)
        try:
            client.close()
        except Exception as e:
            # KEEP broad: best-effort client teardown in finally; must not mask
            # the job's real result/exception.
            _log.debug("Client close failed (non-fatal): %s", e)


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
        """Overwrite the machine-local dashboard cache with current job status.

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

            dashboard = self.paths.dashboard
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
        # `recover_stale_jobs` is itself a terminal transition — it clears jobs a
        # crashed process left marked `running`. Re-derive the JSON snapshot here
        # too: `_write_dashboard` below only writes the markdown build-status
        # page, so without this a crash with no follow-up job leaves the plugin
        # polling a `running` entry the DB no longer has.
        try:
            from . import runtime_state

            runtime_state.write_runtime_snapshots(self.paths)
        except Exception as e:
            # KEEP broad: best-effort observability; never block the worker loop.
            _log.debug("Runtime snapshot write at worker start failed (non-fatal): %s", e)
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
