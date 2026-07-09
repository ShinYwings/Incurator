# ruff: noqa: F403,F405
# mypy: disable-error-code=name-defined
"""Insights commands for the `wiki` CLI."""

from __future__ import annotations

from .common import *

insight_app = typer.Typer(
    name="insight",
    help="List, inspect, and promote derived insight candidates.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

@insight_app.command("list")
def insight_list(
    workspace: str = typer.Option("", "--workspace", help="Workspace path."),
    status: str = typer.Option("pending", help="pending|accepted|rejected|promoted|needs_review"),
) -> None:
    """List insight candidates."""
    paths = _resolve_root_or_die()
    ws_id = Path(workspace).name if workspace else None
    rows = db.list_insight_candidates(paths.state_db, workspace_id=ws_id, status=status)
    for r in rows:
        console.print(f"[cyan]{r['id']}[/cyan] [{r['classification']}] {r['statement']}")
    console.print(f"\n[dim]{len(rows)} candidate(s) with status={status}[/dim]")


@insight_app.command("show")
def insight_show(insight_id: str) -> None:
    """Show one insight candidate."""
    paths = _resolve_root_or_die()
    row = db.get_insight_candidate(paths.state_db, insight_id)
    if row is None:
        console.print(f"[red]Unknown insight:[/red] {insight_id}")
        raise typer.Exit(1)
    for k, v in row.items():
        console.print(f"[cyan]{k}[/cyan]: {v}")


@insight_app.command("promote")
def insight_promote(insight_id: str) -> None:
    """Promote an insight candidate to a durable 02_Wiki/ note."""
    from .. import insight_lifecycle
    paths = _resolve_root_or_die()
    try:
        rel = insight_lifecycle.promote_insight(paths, insight_id)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Promoted[/green] → {rel}")

