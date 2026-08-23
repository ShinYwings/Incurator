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


def _build() -> tuple[Any, Any]:
    from .. import gc as gc_mod

    paths = _resolve_root_or_die()
    return paths, gc_mod.build_plan(paths, _repo_cache_root())


@gc_app.command("plan")
def gc_plan(
    json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON summary.", hidden=True),
) -> None:
    """Show what would be reclaimed — and what grows but is deliberately kept."""
    from .. import gc as gc_mod

    _paths, plan = _build()
    if json_output:
        _print_json({
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

    _paths, plan = _build()
    if not plan.reclaimable:
        if json_output:
            _print_json({"removed": 0, "bytes_freed": 0})
        else:
            _ok("Nothing to reclaim.")
        return

    if not yes and not json_output:
        console.print(
            f"About to delete {len(plan.reclaimable)} cache director(ies), "
            f"{gc_mod._human(plan.bytes_reclaimable)}:"
        )
        for item in plan.reclaimable:
            console.print(f"  {item.path}  [dim]{item.reason}[/dim]")
        if not typer.confirm("Delete them?"):
            _warn("Cancelled; nothing was deleted.")
            raise typer.Exit(code=1)

    removed, freed = gc_mod.sweep(plan.reclaimable)
    if json_output:
        _print_json({"removed": removed, "bytes_freed": freed})
    else:
        _ok(f"Removed {removed} director(ies), freed {gc_mod._human(freed)}.")
