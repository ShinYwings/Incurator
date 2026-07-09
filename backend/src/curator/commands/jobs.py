# ruff: noqa: F403,F405
# mypy: disable-error-code=name-defined
"""Jobs commands for the `wiki` CLI."""

from __future__ import annotations

from .common import *

jobs_app = typer.Typer(
    name="jobs",
    help="Inspect and run queued background ingest jobs.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

@jobs_app.command("list")
def jobs_list(
    all: bool = typer.Option(False, "--all", help="Show completed and failed jobs too."),
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum jobs to show."),
) -> None:
    """List background ingest jobs."""
    paths = _resolve_root_or_die()
    runtime_state.write_runtime_snapshots(paths)
    states = None if all else ("queued", "running")
    jobs = db.list_ingest_jobs(paths.state_db, states=states, limit=limit)
    if not jobs:
        console.print("[dim]No background jobs.[/dim]")
        return
    table = Table(title="Background Jobs", show_header=True, box=None, padding=(0, 1))
    table.add_column("id", justify="right", style="dim")
    table.add_column("source", justify="right")
    table.add_column("type", style="cyan")
    table.add_column("state")
    table.add_column("phase", style="dim")
    table.add_column("progress", justify="right")
    table.add_column("name")
    for job in jobs:
        progress = job.get("progress")
        progress_text = f"{float(progress or 0.0) * 100:.0f}%"
        table.add_row(
            str(job.get("id", "")),
            str(job.get("source_id", "")),
            str(job.get("job_type", "")),
            str(job.get("state", "")),
            str(job.get("phase", "") or ""),
            progress_text,
            str(job.get("source_name", "") or ""),
        )
    console.print(table)


@jobs_app.command("run")
def jobs_run(
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Maximum jobs to run."),
) -> None:
    """Run queued L2/L3 jobs in the foreground."""
    from .. import ingest_worker

    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    # Recover any jobs left in 'running' state from a previous crashed worker.
    recovered = db.recover_stale_jobs(paths.state_db)
    if recovered:
        _ok(f"Recovered {recovered} stale job(s) back to queue.")
    results = ingest_worker.run_queued_jobs(paths, config, limit=limit)
    if not results:
        _ok("No queued jobs.")
    else:
        ok_count = sum(1 for result in results if result.get("ok"))
        failed = [result for result in results if not result.get("ok")]
        _ok(f"Processed {ok_count} job(s).")
        for result in failed:
            job = result.get("job") or {}
            _err(f"Job #{job.get('id')} failed: {result.get('error')}")
    # Always refresh the search index — including vector embeddings — even when
    # the queue was already empty. Otherwise a vault whose L2/L3 finished but
    # whose embeddings never completed (interrupted daemon, FTS-only `add`) has
    # no automatic path to vectors and degrades to FTS5-only until a manual
    # `wiki reindex --embed`. update_index is fingerprinted/idempotent, so this
    # is cheap when embeddings are already current.
    _refresh_search_index(paths, embed=True)
    # The detached daemon spawned by a non-`--wait` build runs this command, so
    # the export hook here covers background-queued mutations too (LWW-gated:
    # an empty drain exports nothing).
    _maybe_auto_export(paths)


@jobs_app.command("cancel")
def jobs_cancel(job_id: int = typer.Argument(..., help="Queued job id to cancel.")) -> None:
    """Cancel a queued background job."""
    paths = _resolve_root_or_die()
    if db.cancel_job(paths.state_db, job_id):
        runtime_state.write_runtime_snapshots(paths)
        _ok(f"Cancelled job #{job_id}.")
        return
    _err(f"Job #{job_id} is not queued or does not exist.")
    raise typer.Exit(1)


@jobs_app.command("rerun")
def jobs_rerun(job_id: int = typer.Argument(..., help="Completed, failed, or cancelled job id to rerun.")) -> None:
    """Requeue a completed, failed, or cancelled background job."""
    paths = _resolve_root_or_die()
    existing = db.get_ingest_job(paths.state_db, job_id)
    if existing is None:
        _err(f"Job #{job_id} does not exist.")
        raise typer.Exit(1)
    if existing["state"] == consts.STATUS_QUEUED:
        runtime_state.write_runtime_snapshots(paths)
        _ok(f"Job #{job_id} is already queued.")
        return
    if existing["state"] == consts.STATUS_RUNNING:
        _err(f"Job #{job_id} is currently running and cannot be rerun.")
        raise typer.Exit(1)
    if db.rerun_job(paths.state_db, job_id):
        runtime_state.write_runtime_snapshots(paths)
        _ok(f"Requeued job #{job_id}.")
        return
    _err(f"Job #{job_id} is not done, failed, or cancelled.")
    raise typer.Exit(1)

