# ruff: noqa: F403,F405
# mypy: disable-error-code=name-defined
"""Sources commands for the `wiki` CLI."""

from __future__ import annotations

from .common import *

source_app = typer.Typer(
    name="source",
    help="Inspect and manage tracked sources.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

@source_app.command("ls")
@source_app.command("list", hidden=True)
def sources_list_cmd(
    status_filter: str = typer.Option(
        None,
        "--status",
        "-s",
        help="Only show sources with this status (pending|force_pending|curated|error).",
    ),
) -> None:
    """List all tracked sources."""
    paths = _resolve_root_or_die()
    ingest_llm._mark_existing_l3_done_if_present(paths)
    runtime_state.write_runtime_snapshots(paths)
    rows = ingest_raw.list_sources(paths, status_filter=status_filter)

    if not rows:
        console.print()
        if status_filter:
            _warn(f"No sources with status '{status_filter}'")
        else:
            _warn("No sources tracked yet.")
            _hint("Discover them with [bold]wiki add[/bold]")
        return

    _ERROR_REASON_LABEL = {
        "empty_file":  ("empty/unreadable",  "wiki add error — file has no extractable text"),
        "missing_context": ("missing L1",    "wiki add error — L1 Context is missing or invalid"),
        "parse_error": ("parse failed",       "wiki add error — file could not be parsed"),
        "llm_error":   ("LLM error",          "wiki build error — LLM call failed"),
        "invalid_atom_output": ("bad atom",   "wiki add error — L2 Atom output was invalid"),
    }

    table = Table(
        title=f"Sources ({len(rows)})",
        show_header=True,
        header_style="bold",
        row_styles=["", "dim"],
    )
    table.add_column("#", justify="right", style="cyan", width=5)
    table.add_column("Type", width=6)
    table.add_column("Size", justify="right", width=9)
    table.add_column("Added", width=10)
    table.add_column("Status", width=18)
    table.add_column("L1", justify="center", width=8)
    table.add_column("L2", justify="center", width=8)
    table.add_column("L3", justify="center", width=8)
    table.add_column("L4", justify="center", width=8)
    table.add_column("Path", overflow="fold")

    def _layer_status_cell(value: str | None) -> str:
        value = value or "pending"
        style = {
            "done": "green",
            "running": "cyan",
            "error": "red",
            "pending": "yellow",
            "skipped": "dim",
        }.get(value, "white")
        label = {
            "done": "done",
            "running": "run",
            "error": "err",
            "pending": "pend",
            "skipped": "skip",
        }.get(value, value[:4])
        return f"[{style}]{label}[/{style}]"

    error_rows: list[dict] = []
    layer_error_rows: list[dict] = []
    for row in rows:
        added_short = row["added_at"][:10] if row["added_at"] else ""
        status = row["status"]
        error_reason = row["error_reason"] if "error_reason" in row.keys() else None
        layer_error = row["layer_error"] if "layer_error" in row.keys() else None
        if status == "error" and error_reason:
            label, _ = _ERROR_REASON_LABEL.get(error_reason, (error_reason, ""))
            status_styled = f"[red]error: {label}[/red]"
            error_rows.append(dict(row))
        else:
            status_styled = f"[{_status_style(status)}]{status}[/{_status_style(status)}]"
        if layer_error and any(
            (row[f"{layer}_status"] if f"{layer}_status" in row.keys() else "") == "error"
            for layer in ("l1", "l2", "l3", "l4")
        ):
            layer_error_rows.append(dict(row))
        table.add_row(
            str(row["id"]),
            row["file_type"],
            _format_bytes(row["bytes"]),
            added_short,
            status_styled,
            _layer_status_cell(row["l1_status"] if "l1_status" in row.keys() else None),
            _layer_status_cell(row["l2_status"] if "l2_status" in row.keys() else None),
            _layer_status_cell(row["l3_status"] if "l3_status" in row.keys() else None),
            _layer_status_cell(row["l4_status"] if "l4_status" in row.keys() else None),
            row["relpath"],
        )

    console.print()
    console.print(table)

    # Per-error hints
    if error_rows or layer_error_rows:
        console.print()
        console.rule("[red]Error details[/red]")
        shown_reasons: set[str] = set()
        for row in error_rows:
            reason = row.get("error_reason") or ""
            _, desc = _ERROR_REASON_LABEL.get(reason, (reason, "unknown error"))
            console.print(f"  [cyan]#{row['id']}[/cyan]  {row['relpath']}")
            console.print(f"       [red]{desc}[/red]")
            if reason == "empty_file":
                console.print(f"       [dim]→ The file has no extractable text (scanned PDF?). "
                               f"Run [bold]wiki source rm {row['id']}[/bold] to remove it.[/dim]")
            elif reason == "missing_context":
                console.print("       [dim]→ Re-run [bold]wiki add --force[/bold] to regenerate L1 Contexts.[/dim]")
            elif reason in ("parse_error", "llm_error"):
                console.print(f"       [dim]→ Re-try with [bold]wiki source retry {row['id']}[/bold][/dim]")
            shown_reasons.add(reason)
        for row in layer_error_rows:
            if row.get("status") == "error":
                continue
            layer_error = row.get("layer_error") or ""
            failed_layers = [
                layer.upper()
                for layer in ("l1", "l2", "l3", "l4")
                if row.get(f"{layer}_status") == "error"
            ]
            console.print(f"  [cyan]#{row['id']}[/cyan]  {row['relpath']}")
            console.print(
                f"       [red]{', '.join(failed_layers)} layer error — {layer_error}[/red]"
            )
            if layer_error == "concept_clustering_failed":
                console.print(
                    "       [dim]→ L2 Atoms were written, but L3 Concept clustering failed. "
                    "Re-run [bold]wiki add --force[/bold] after fixing the LLM/JSON issue.[/dim]"
                )
        console.print()
    else:
        console.print()


@source_app.command("show")
def sources_show_cmd(
    source_id: int = typer.Argument(..., help="The source ID (from `wiki source ls`)."),
    preview_chars: int = typer.Option(
        800,
        "--preview",
        "-p",
        help="Number of characters of parsed text to preview.",
    ),
) -> None:
    """Show details for one source, including a text preview."""
    paths = _resolve_root_or_die()
    row = ingest_raw.get_source(paths, source_id)
    if row is None:
        _err(f"No source with id {source_id}")
        raise typer.Exit(code=1)

    # Re-parse the file to get title and a preview — we don't store parsed text
    # in the DB to keep it small. This is cheap (local file).
    from .. import parsers

    file_path = paths.root / row["relpath"]
    if not file_path.exists():
        _err(f"Source file missing from disk: {file_path}")
        raise typer.Exit(code=1)

    try:
        parsed = parsers.parse(file_path)
    except parsers.ParserError as e:
        _err(f"Parse failed: {e}")
        raise typer.Exit(code=1)

    console.print()
    console.print(
        Panel.fit(
            f"[bold]#{row['id']}[/bold]  [cyan]{parsed.title}[/cyan]",
            border_style="cyan",
        )
    )

    meta_table = Table(show_header=False, box=None, padding=(0, 2))
    meta_table.add_column(style="dim", width=16)
    meta_table.add_column()
    meta_table.add_row("Path", row["relpath"])
    meta_table.add_row("Type", parsed.file_type)
    meta_table.add_row("Size", _format_bytes(row["bytes"]))
    meta_table.add_row("Words", f"{parsed.word_count:,}")
    meta_table.add_row("Added", row["added_at"])
    meta_table.add_row("Status", f"[{_status_style(row['status'])}]{row['status']}[/{_status_style(row['status'])}]")
    meta_table.add_row("Hash", row["content_hash"][:16] + "…")
    if row["last_ingested"]:
        meta_table.add_row("Last ingested", row["last_ingested"])
    for k, v in parsed.metadata.items():
        if k == "pdf_pages" and isinstance(v, list):
            meta_table.add_row(k, f"{len(v)} page(s)")
        elif k == "pdf_images" and isinstance(v, list):
            meta_table.add_row(k, f"{len(v)} image(s)")
        else:
            meta_table.add_row(k, str(v)[:80])
    console.print(meta_table)

    console.print()
    console.print("[dim]── text preview ──[/dim]")
    preview = parsed.text[:preview_chars]
    if len(parsed.text) > preview_chars:
        preview += f"\n\n[dim]… ({len(parsed.text) - preview_chars:,} more characters)[/dim]"
    console.print(preview)
    console.print()


@source_app.command("rm")
def sources_rm_cmd(
    source_id: int = typer.Argument(..., help="The source ID to remove."),
    delete_file: bool = typer.Option(
        False,
        "--delete-file",
        help="Also delete the source file from raw directories.",
    ),
    keep_file: bool = typer.Option(
        False,
        "--keep-file",
        help="Deprecated no-op: source files are kept by default.",
        hidden=True,
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the confirmation prompt.",
    ),
) -> None:
    """Remove a source from tracking (and optionally delete the file)."""
    paths = _resolve_root_or_die()
    row = ingest_raw.get_source(paths, source_id)
    if row is None:
        _err(f"No source with id {source_id}")
        raise typer.Exit(code=1)

    if keep_file:
        console.print("[yellow]Warning:[/yellow] --keep-file is deprecated (files are kept by default). This flag is ignored.")
    effective_delete = delete_file
    if not yes:
        action = "remove from tracking AND delete file" if effective_delete else "remove from tracking"
        confirm = typer.confirm(
            f"About to {action}: #{source_id} {row['relpath']}. Proceed?"
        )
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(code=0)

    ok, msg = ingest_raw.remove_source(paths, source_id, delete_file=effective_delete)
    if ok:
        _ok(msg)
    else:
        _err(msg)
        raise typer.Exit(code=1)


@source_app.command("retry")
def sources_retry_cmd(
    source_id: Optional[int] = typer.Argument(
        None,
        help="Specific source ID to retry. If omitted, retries all sources with aggregate or layer errors.",
    ),
) -> None:
    """Retry errored sources: re-runs wiki add depending on error type.

    \b
      empty_file/missing_context → re-runs L1 Context generation
      parse_error → re-runs full L1→L3 pipeline (atoms + concepts)
      llm_error   → re-runs full L1→L3 pipeline (atoms + concepts)
    """
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)

    rows = _load_retryable_source_rows(paths, source_id)

    if not rows:
        _ok("No errored sources or layer errors found.")
        return

    add_rows = [r for r in rows if _source_retry_is_l1(r)]
    curate_rows = [r for r in rows if _source_retry_is_build(r)]
    known_ids = {int(r["id"]) for r in add_rows + curate_rows}
    unknown_rows = [r for r in rows if int(r["id"]) not in known_ids]

    console.print()
    console.print(f"[bold]Retrying {len(rows)} errored source(s)…[/bold]")

    # ── Re-add (empty_file) ──────────────────────────────────────────────────
    if add_rows:
        console.print()
        console.print(f"[dim]  Phase: re-generating L1 Contexts for {len(add_rows)} source(s)…[/dim]")
        client = None if _instant_l1_enabled(config) else _start_client(config)
        try:
            ids = [row["id"] for row in add_rows]
            placeholders = ",".join("?" for _ in ids)
            with db.connect(paths.state_db) as conn:
                conn.execute(
                    "UPDATE sources SET status = 'pending', error_reason = NULL, "
                    "l1_status = 'pending', l2_status = 'pending', "
                    "l3_status = 'pending', l4_status = 'pending', layer_error = NULL "
                    f"WHERE id IN ({placeholders})",
                    ids,
                )
            for row in add_rows:
                console.print(f"  [dim]summarizing[/dim] {row['relpath']}")
                context_id = ingest_raw.generate_l1_summary(
                    paths,
                    source_id=row["id"],
                    relpath=row["relpath"],
                    content_hash=row["content_hash"],
                    client=client,
                    config=config,
                    existing_context_id=row["context_id"],
                )
                if context_id:
                    _ok(f"  L1 [{context_id}] ← {row['relpath']}")
                else:
                    _warn(f"  Still failed: {row['relpath']}")
        finally:
            if client is not None:
                client.close()

    # ── Re-add L1-L3 (parse_error / llm_error) ──────────────────────────────
    if curate_rows:
        console.print()
        console.print(f"[dim]{describe_backend(config)}…[/dim]")
        client = _start_client(config)
        try:
            ids = [row["id"] for row in curate_rows]
            placeholders = ",".join("?" for _ in ids)
            with db.connect(paths.state_db) as conn:
                conn.execute(
                    "UPDATE sources SET status = 'force_pending', error_reason = NULL, "
                    "l2_status = 'pending', l3_status = 'pending', "
                    "l4_status = 'pending', layer_error = NULL "
                    f"WHERE id IN ({placeholders})",
                    ids,
                )
            l3_results = ingest_llm.run_l1_to_l3(
                paths, client,
                lambda: CliIngestCallbacks(mode="batch"),
                mode="batch",
                auto_discover=False,
            )
            for result in l3_results:
                if result.ok:
                    _ok(f"  Retried #{result.source_id}")
                else:
                    _warn(f"  Still failed #{result.source_id}: {result.error}")
        finally:
            client.close()

    # ── Unknown error_reason ─────────────────────────────────────────────────
    for row in unknown_rows:
        _warn(f"  #{row['id']} has unknown error_reason '{row['error_reason']}' — skipping.")

    console.print()
    _hint("Run [bold]wiki source ls -s error[/bold] to check remaining errors.")
