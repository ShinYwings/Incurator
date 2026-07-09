# ruff: noqa: F403,F405
# mypy: disable-error-code=name-defined
"""Db commands for the `wiki` CLI."""

from __future__ import annotations

from .common import *

db_app = typer.Typer(
    name="db",
    help="Cross-device knowledge synchronization via JSONL export and import.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

@db_app.command("export")
def db_export(
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        "-o",
        help="Output .jsonl file path. Defaults to .curator/export-YYYYMMDD.jsonl.",
    ),
    since: Optional[str] = typer.Option(
        None,
        "--since",
        help="Only export rows updated at or after this ISO datetime.",
    ),
    compress: bool = typer.Option(False, "--compress", help="Write gzip-compressed .jsonl.gz output."),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON summary.", hidden=True),
) -> None:
    """Export the knowledge DB to a JSONL file for cross-device transfer."""
    import datetime as _dt
    from curator.db_sync import export_knowledge

    paths = _resolve_root_or_die()
    if out is None:
        date_str = _dt.date.today().strftime("%Y%m%d")
        out = paths.internal / f"export-{date_str}.jsonl"
        if compress:
            out = out.with_suffix(".jsonl.gz")

    stats = export_knowledge(paths.state_db, out, since=since, compress=compress)

    if json_output:
        _print_json({"out": str(out), "total_rows": stats.total_rows, "by_table": stats.rows_by_table})
    else:
        console.print(f"[green]Exported {stats.total_rows} rows → {out}[/green]")
        for tbl, count in stats.rows_by_table.items():
            if count:
                console.print(f"  {tbl}: {count}")


@db_app.command("import")
def db_import(
    path: Path = typer.Argument(..., help="Path to .jsonl or .jsonl.gz export file."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing to DB."),
    skip_reindex: bool = typer.Option(False, "--skip-reindex", help="Skip automatic wiki reindex after import."),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON summary.", hidden=True),
) -> None:
    """Import a JSONL export file into the local knowledge DB (LWW merge)."""
    from curator.db_sync import import_knowledge

    if not path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        raise typer.Exit(1)

    paths = _resolve_root_or_die()
    try:
        stats = import_knowledge(paths.state_db, path, dry_run=dry_run)
    except ValueError as e:
        console.print(f"[red]Import failed: {e}[/red]")
        raise typer.Exit(1)

    summary = {
        "dry_run": dry_run,
        "inserted": stats.inserted,
        "updated": stats.updated,
        "skipped": stats.skipped,
        "deleted": stats.deleted,
    }

    if json_output:
        _print_json(summary)
    else:
        tag = "[dim](dry-run)[/dim] " if dry_run else ""
        console.print(
            f"[green]{tag}Import complete:[/green] "
            f"+{stats.inserted} inserted, ~{stats.updated} updated, "
            f"{stats.skipped} skipped, {stats.deleted} deleted"
        )

    if not dry_run and not skip_reindex:
        console.print("[dim]Running wiki reindex…[/dim]")
        _refresh_search_index(paths)


@db_app.command("autosync")
def db_autosync(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing to DB or sync files."),
    skip_reindex: bool = typer.Option(False, "--skip-reindex", help="Skip wiki reindex after import."),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON summary.", hidden=True),
) -> None:
    """Bidirectional cross-device sync: import peers (+ merge conflict files), then
    export this device's snapshot if anything changed (one-writer-per-file)."""
    from curator.db_sync import autosync

    paths = _resolve_root_or_die()
    res = autosync(paths.internal, paths.state_db, dry_run=dry_run)

    total = sum(
        s.inserted + s.updated + s.deleted for s in res.imported.values()
    )
    summary = {
        "dry_run": res.dry_run,
        "imported_files": len(res.imported),
        "inserted": sum(s.inserted for s in res.imported.values()),
        "updated": sum(s.updated for s in res.imported.values()),
        "deleted": sum(s.deleted for s in res.imported.values()),
        "conflicts": res.conflicts,
        "exported": res.exported,
        "would_export": res.would_export,
    }

    if json_output:
        _print_json(summary)
    else:
        tag = "[dim](dry-run)[/dim] " if dry_run else ""
        console.print(
            f"[green]{tag}Auto-sync:[/green] "
            f"+{summary['inserted']} inserted, ~{summary['updated']} updated, "
            f"{summary['deleted']} deleted from {summary['imported_files']} peer file(s)"
        )
        if res.conflicts:
            console.print(f"[yellow]Merged {len(res.conflicts)} Syncthing conflict file(s).[/yellow]")
        if res.exported:
            console.print(f"[dim]Exported snapshot → {res.exported}[/dim]")
        elif dry_run and res.would_export:
            console.print(
                "[yellow]Export pending:[/yellow] local knowledge is newer than "
                "this device's snapshot — a real run would export."
            )

    if not dry_run and not skip_reindex and total:
        console.print("[dim]Running wiki reindex…[/dim]")
        _refresh_search_index(paths)

