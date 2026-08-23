# ruff: noqa: F403,F405
# mypy: disable-error-code=name-defined
"""Gc commands for the `wiki` CLI."""

from __future__ import annotations

from .common import *

gc_app = typer.Typer(
    name="gc",
    help="Reclaim disk that carries no cross-device meaning, and report what grows but must be kept.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)


def _repo_cache_root() -> Path:
    """The `.cache/` that holds the per-vault namespaces.

    `get_vault_cache_dir` builds `<cache>/vaults/<key>`, so its parent's parent
    is the root the sweep walks. Derived from the same function rather than
    rebuilt, so the two cannot drift apart.
    """
    from .. import config as _cfg

    return _cfg.get_vault_cache_dir(Path("/nonexistent")).parent.parent


def _build() -> tuple[Any, Any, dict]:
    from .. import config as _cfg
    from .. import gc as gc_mod

    paths = _resolve_root_or_die()
    config = _cfg.load_config(paths)
    return paths, gc_mod.build_plan(paths, _repo_cache_root()), config


@gc_app.command("plan")
def gc_plan(
    json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON summary.", hidden=True),
) -> None:
    """Show what would be reclaimed — and what grows but is deliberately kept."""
    from .. import gc as gc_mod

    paths, plan, config = _build()
    sessions_n, sessions_bytes = gc_mod.plan_session_prune(paths, config)
    runs_keep = gc_mod.prompt_runs_keep(config)
    runs_n = gc_mod.plan_prompt_run_cap(paths.state_db, runs_keep)
    if json_output:
        _print_json({
            "sessions_prunable": sessions_n,
            "prompt_runs_prunable": runs_n,
            "reclaimable": [
                {"path": str(i.path), "bytes": i.bytes, "reason": i.reason}
                for i in plan.reclaimable
            ],
            "bytes_reclaimable": plan.bytes_reclaimable,
            "retained": [
                {"label": r.label, "amount": r.amount, "reason": r.reason}
                for r in plan.retained
            ],
        })
        return

    if plan.reclaimable:
        console.print(
            f"[bold]Reclaimable[/bold] — {len(plan.reclaimable)} item(s), "
            f"{gc_mod._human(plan.bytes_reclaimable)}"
        )
        for item in plan.reclaimable:
            console.print(f"  {gc_mod._human(item.bytes):>9}  {item.path.name}  [dim]{item.reason}[/dim]")
        console.print("\nRun [bold]wiki gc run[/bold] to remove them.")
    else:
        _ok("Nothing to reclaim.")

    days = gc_mod._session_retention_days(config)
    if sessions_bytes:
        console.print("\n[bold]Chat history[/bold]")
        if days <= 0:
            console.print(
                f"  [cyan].curator/sessions.json[/cyan] — {gc_mod._human(sessions_bytes)}, "
                f"retention [bold]off[/bold] (nothing is ever removed)"
            )
            console.print(
                "    [dim]Set a window with `wiki config set gc.sessions_retention_days 90` "
                "(30/90/180/365). Chats are your own writing, so the default keeps them "
                "forever. A window removes them on EVERY device, not just this one.[/dim]"
            )
        else:
            console.print(
                f"  [cyan].curator/sessions.json[/cyan] — {gc_mod._human(sessions_bytes)}, "
                f"keeping {days} days; [bold]{sessions_n}[/bold] session(s) past the window"
            )

    console.print("\n[bold]LLM call log[/bold]")
    total_runs = gc_mod._row_count(paths.state_db, "prompt_runs")
    if runs_keep <= 0:
        console.print(
            f"  [cyan]prompt_runs[/cyan] — {total_runs:,} rows, cap [bold]off[/bold]"
        )
        console.print(
            "    [dim]Set one with `wiki config set gc.prompt_runs_keep 1000`. Runs "
            "still referenced by a report, unit, entity or relation are ALWAYS kept — "
            "deleting one would silently re-bill a finished L3 report. Removal "
            "applies to every device you sync with.[/dim]"
        )
    else:
        console.print(
            f"  [cyan]prompt_runs[/cyan] — {total_runs:,} rows, keeping {runs_keep:,} "
            f"unreferenced; [bold]{runs_n:,}[/bold] over the cap"
        )

    if plan.retained:
        console.print("\n[bold]Grows, and deliberately kept[/bold]")
        for r in plan.retained:
            console.print(f"  [cyan]{r.label}[/cyan] — {r.amount}")
            console.print(f"    [dim]{r.reason}[/dim]")


@gc_app.command("run")
def gc_run(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON summary.", hidden=True),
) -> None:
    """Delete the reclaimable items. Nothing synced is ever touched."""
    from .. import gc as gc_mod

    paths, plan, config = _build()
    sessions_n, _bytes = gc_mod.plan_session_prune(paths, config)
    runs_n = gc_mod.plan_prompt_run_cap(paths.state_db, gc_mod.prompt_runs_keep(config))
    if not plan.reclaimable and not sessions_n and not runs_n:
        if json_output:
            _print_json({"removed": 0, "bytes_freed": 0})
        else:
            _ok("Nothing to reclaim.")
        return

    if not yes and not json_output:
        if plan.reclaimable:
            console.print(
                f"About to delete {len(plan.reclaimable)} cache director(ies), "
                f"{gc_mod._human(plan.bytes_reclaimable)}:"
            )
            for item in plan.reclaimable:
                console.print(f"  {item.path}  [dim]{item.reason}[/dim]")
        if sessions_n:
            _warn(
                f"{sessions_n} chat session(s) are past your retention window. "
                f"Removing them takes effect on EVERY device you sync with, not "
                f"just this one, and cannot be undone."
            )
        if runs_n:
            _warn(
                f"{runs_n:,} unreferenced LLM call record(s) are over your cap. "
                f"Removing them applies to EVERY device you sync with. Runs still "
                f"referenced by an artifact are kept regardless."
            )
        if not typer.confirm("Proceed?"):
            _warn("Cancelled; nothing was deleted.")
            raise typer.Exit(code=1)

    removed, freed = gc_mod.sweep(plan.reclaimable)
    try:
        pruned = gc_mod.prune_sessions(paths, config)
    except gc_mod.UnreadableSessionStore as exc:
        # Report and leave it alone. Rewriting a store we cannot parse would
        # destroy whatever it holds, and the cache sweep above is unrelated.
        pruned = 0
        _warn(f"Chat store left untouched: sessions.json is unreadable ({exc}).")
    runs_removed = gc_mod.apply_prompt_run_cap(paths.state_db, gc_mod.prompt_runs_keep(config))
    if json_output:
        _print_json({"removed": removed, "bytes_freed": freed, "sessions_pruned": pruned, "prompt_runs_pruned": runs_removed})
    else:
        if removed:
            _ok(f"Removed {removed} director(ies), freed {gc_mod._human(freed)}.")
        if pruned:
            _ok(f"Removed {pruned} chat session(s) past the retention window.")
        if runs_removed:
            _ok(f"Removed {runs_removed:,} unreferenced LLM call record(s).")
        if not removed and not pruned and not runs_removed:
            _ok("Nothing to reclaim.")
