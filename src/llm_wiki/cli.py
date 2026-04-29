"""Command-line interface for LLM-Wiki.

Stage 1 commands:
    wiki init [PATH]         Scaffold a new wiki project.
    wiki status              Show the current wiki's stats and config.
    wiki version             Show version.

Stage 2 commands:
    wiki add <path> [-r]     Copy a file or folder into raw/, parse, track.
    wiki sources list        List all tracked sources.
    wiki sources show <id>   Show details for one source (with text preview).
    wiki sources rm <id>     Remove a source from tracking.

Later stages add: ingest, query, lint, serve.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from . import config as cfg
from . import db
from . import ingest_llm
from . import ingest_raw
from . import lint as lint_module
from . import query as query_module
from . import search
from .llm import (
    GeminiClient,
    GeminiError,
    LLMError,
    ModelNotFound,
    OllamaClient,
    OllamaNotRunning,
    build_client,
    describe_backend,
)

app = typer.Typer(
    name="wiki",
    help="LLM-Wiki — an LLM-maintained personal knowledge base.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

sources_app = typer.Typer(
    name="sources",
    help="Manage tracked source files in raw/.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
app.add_typer(sources_app, name="sources")

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hint(text: str) -> None:
    """Print a one-liner tip in a subdued style."""
    console.print(f"[dim]💡 {text}[/dim]")


def _err(text: str) -> None:
    console.print(f"[bold red]✗[/bold red] {text}")


def _ok(text: str) -> None:
    console.print(f"[bold green]✓[/bold green] {text}")


def _warn(text: str) -> None:
    console.print(f"[bold yellow]![/bold yellow] {text}")


def _resolve_root_or_die() -> cfg.WikiPaths:
    """Find the wiki project root from cwd or WIKI_ROOT env var."""
    import os
    env_root = os.environ.get("WIKI_ROOT")
    if env_root:
        root_path = Path(env_root).resolve()
        if (root_path / cfg.INTERNAL_DIR / cfg.CONFIG_FILE).exists():
            return cfg.paths_from_config(root_path)
    root = cfg.find_wiki_root()
    if root is None:
        _err("Not inside an LLM-Wiki project.")
        _hint("Run [bold]wiki init[/bold] to create one, or set WIKI_ROOT env var.")
        raise typer.Exit(code=1)
    return cfg.paths_from_config(root)


def _format_bytes(n: int) -> str:
    """Human-readable byte count: 1234 → '1.2 KB'."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.2f} GB"


def _status_style(status: str) -> str:
    return {
        "pending": "yellow",
        "ingested": "green",
        "error": "red",
        "skipped": "dim",
    }.get(status, "white")


# ---------------------------------------------------------------------------
# Stage 1 commands
# ---------------------------------------------------------------------------


@app.command()
def version() -> None:
    """Show the LLM-Wiki version."""
    console.print(f"llm-wiki [bold cyan]{__version__}[/bold cyan]")
@app.command()
def init(
    vault_path: str = typer.Argument(
        ...,
        help="Path to the Obsidian vault (project root).",
    ),
    raw_dirs: list[str] = typer.Option(
        ["03_Resources", "02_Wiki"],
        "--raw",
        "-r",
        help="Directories to scan for source documents (relative to vault root). Repeatable.",
    ),
    wiki_dir: str = typer.Option(
        ".wiki/distilled",
        "--wiki-dir",
        "-w",
        help="Directory for distilled output (relative to vault root).",
    ),
    gemini_api_key: str = typer.Option(
        "",
        "--gemini-api-key",
        "-k",
        help="Gemini API key (stored in per-project config, NOT in source code).",
    ),
) -> None:
    """Initialise an LLM-Wiki project inside an Obsidian vault.

    Creates:
      .wiki/config.yml   — project configuration
      .wiki/state.sqlite — tracking database
      .wiki/distilled/   — Extracted/, Synthesized/, Metadata/ subdirs
      schema/AGENTS.md   — LLM conventions document
    """
    import shutil
    import importlib.resources as pkg_resources

    root = Path(vault_path).resolve()
    if not root.exists():
        _err(f"Vault path does not exist: {root}")
        raise typer.Exit(code=1)

    # Check if already initialised
    paths = cfg.WikiPaths(
        root=root,
        raw_dirs_override=raw_dirs,
        wiki_dir_override=wiki_dir,
    )
    if paths.is_initialized():
        _warn(f"Already initialised at {root}")
        _hint("Delete .wiki/config.yml to re-initialise.")
        raise typer.Exit(code=0)

    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]Initialising LLM-Wiki[/bold cyan]\n"
            f"[dim]{root}[/dim]",
            border_style="cyan",
        )
    )

    # 1. Build config
    config = dict(cfg.DEFAULT_CONFIG)
    config["paths"] = {
        "raw_dirs": raw_dirs,
        "wiki_dir": wiki_dir,
    }
    # Store API key in per-project config (not in source code)
    import os
    resolved_key = gemini_api_key or os.environ.get("GEMINI_API_KEY", "")
    if resolved_key:
        config["llm"] = dict(config.get("llm", {}))
        config["llm"]["gemini_api_key"] = resolved_key

    # 2. Create directory structure
    paths.internal.mkdir(parents=True, exist_ok=True)
    paths.wiki.mkdir(parents=True, exist_ok=True)
    for subdir in cfg.WIKI_SUBDIRS:
        (paths.wiki / subdir).mkdir(parents=True, exist_ok=True)
    paths.schema.mkdir(parents=True, exist_ok=True)

    # 3. Write config.yml
    cfg.save_config(paths, config)
    _ok(f"Config:    {paths.config_file.relative_to(root)}")

    # 4. Init the state database
    db.init_db(paths.state_db)
    _ok(f"Database:  {paths.state_db.relative_to(root)}")

    # 5. Copy template files
    templates_dir = Path(__file__).parent / "templates"

    # AGENTS.md
    agents_src = templates_dir / "AGENTS.md"
    if agents_src.exists() and not paths.agents.exists():
        shutil.copy2(agents_src, paths.agents)
        _ok(f"Schema:    {paths.agents.relative_to(root)}")

    # index.md
    index_src = templates_dir / "index.md"
    if index_src.exists() and not paths.index.exists():
        shutil.copy2(index_src, paths.index)
        _ok(f"Index:     {paths.index.relative_to(root)}")

    # log.md (create empty)
    if not paths.log.exists():
        paths.log.write_text(
            "---\ntitle: Ingest Log\ntype: log\n---\n\n# Ingest Log\n\n",
            encoding="utf-8",
        )
        _ok(f"Log:       {paths.log.relative_to(root)}")

    # 6. Summary
    console.print()
    console.print("[bold green]Wiki initialised![/bold green]")
    console.print()
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim", width=16)
    table.add_column()
    table.add_row("Raw directories", ", ".join(raw_dirs))
    table.add_row("Distilled output", wiki_dir)
    table.add_row("Config", str(paths.config_file.relative_to(root)))
    console.print(table)
    console.print()
    _hint("Next: run [bold]wiki sync[/bold] to discover source files, then [bold]wiki ingest[/bold].")
    console.print()



@app.command()
def status() -> None:
    """Show the current wiki's stats, paths, and config."""
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    stats = db.get_stats(paths.state_db)

    def _count_md(folder: Path) -> int:
        if not folder.exists():
            return 0
        return sum(1 for p in folder.glob("*.md") if not p.name.startswith("."))

    sources_pages = _count_md(paths.wiki / "Metadata")
    entities_pages = _count_md(paths.wiki / "Extracted")
    synthesis_pages = _count_md(paths.wiki / "Synthesized")

    raw_files = 0
    for raw_dir in paths.raw_dirs:
        if raw_dir.exists():
            raw_files += sum(1 for p in raw_dir.rglob("*") if p.is_file() and not p.name.startswith("."))

    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]LLM-Wiki[/bold cyan]  [dim]@ {paths.root}[/dim]",
            border_style="cyan",
        )
    )

    table = Table(title="Project", show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim", width=22)
    table.add_column()
    table.add_row("Raw sources (files)", str(raw_files))
    table.add_row("Sources tracked (DB)", str(stats["sources_total"]))
    table.add_row("Sources ingested", str(stats["sources_ingested"]))
    table.add_row("Ingest runs", str(stats["ingest_runs"]))
    console.print(table)

    pages_table = Table(title="Wiki pages", show_header=False, box=None, padding=(0, 2))
    pages_table.add_column(style="dim", width=22)
    pages_table.add_column()
    pages_table.add_row("Metadata/", str(sources_pages))
    pages_table.add_row("Extracted/", str(entities_pages))
    pages_table.add_row("Synthesized/", str(synthesis_pages))
    pages_table.add_row(
        "[bold]total[/bold]",
        f"[bold]{sources_pages + entities_pages + synthesis_pages}[/bold]",
    )
    console.print(pages_table)

    cfg_table = Table(title="Config", show_header=False, box=None, padding=(0, 2))
    cfg_table.add_column(style="dim", width=22)
    cfg_table.add_column()
    llm = config.get("llm", {})
    search_cfg = config.get("search", {})
    cfg_table.add_row("LLM provider", llm.get("provider", "?"))
    cfg_table.add_row("LLM model", llm.get("model", "?"))
    cfg_table.add_row("LLM host", llm.get("host", "?"))
    cfg_table.add_row("Search backend", search_cfg.get("backend", "?"))
    cfg_table.add_row("Reranking", "on" if search_cfg.get("rerank") else "off")
    # Show QMD binary availability
    if search.is_available():
        version = search.get_version() or "installed"
        cfg_table.add_row("QMD binary", f"[green]{version}[/green]")
    else:
        cfg_table.add_row("QMD binary", "[red]not installed[/red]")
    console.print(cfg_table)

    console.print()
    if stats["sources_total"] == 0:
        _hint("No sources yet. Sync them with [bold]wiki sync[/bold]")
    elif stats["sources_ingested"] == 0:
        _hint(
            f"{stats['sources_total']} source(s) tracked but not ingested. "
            f"Stage 3 will add [bold]wiki ingest[/bold] to process them with the LLM."
        )


# ---------------------------------------------------------------------------
# Stage 2 commands
# ---------------------------------------------------------------------------


@app.command()
def sync() -> None:
    """Sync raw directories with the tracking DB.
    
    Discovers new files, updates changed files, and flags deleted files.
    """
    paths = _resolve_root_or_die()
    
    console.print()
    console.print(f"[dim]Scanning raw directories for changes...[/dim]")
    console.print()

    # Reuse the auto-discover logic from ingest_llm, but exposed directly
    discovered = ingest_llm._auto_discover_pending(paths)
    
    if discovered:
        _ok(f"Synced {discovered} files. Check status with [bold]wiki status[/bold]")
    else:
        console.print("[dim]No changes found.[/dim]")


@sources_app.command("list")
def sources_list_cmd(
    status_filter: str = typer.Option(
        None,
        "--status",
        "-s",
        help="Only show sources with this status (pending|ingested|error).",
    ),
) -> None:
    """List all tracked sources."""
    paths = _resolve_root_or_die()
    rows = ingest_raw.list_sources(paths, status_filter=status_filter)

    if not rows:
        console.print()
        if status_filter:
            _warn(f"No sources with status '{status_filter}'")
        else:
            _warn("No sources tracked yet.")
            _hint("Discover them with [bold]wiki sync[/bold]")
        return

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
    table.add_column("Status", width=9)
    table.add_column("Path", overflow="fold")

    for row in rows:
        added_short = row["added_at"][:10] if row["added_at"] else ""
        status = row["status"]
        status_styled = f"[{_status_style(status)}]{status}[/{_status_style(status)}]"
        table.add_row(
            str(row["id"]),
            row["file_type"],
            _format_bytes(row["bytes"]),
            added_short,
            status_styled,
            row["relpath"],
        )

    console.print()
    console.print(table)
    console.print()


@sources_app.command("show")
def sources_show_cmd(
    source_id: int = typer.Argument(..., help="The source ID (from `wiki sources list`)."),
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
    from . import parsers

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
        meta_table.add_row(k, str(v)[:80])
    console.print(meta_table)

    console.print()
    console.print("[dim]── text preview ──[/dim]")
    preview = parsed.text[:preview_chars]
    if len(parsed.text) > preview_chars:
        preview += f"\n\n[dim]… ({len(parsed.text) - preview_chars:,} more characters)[/dim]"
    console.print(preview)
    console.print()


@sources_app.command("rm")
def sources_rm_cmd(
    source_id: int = typer.Argument(..., help="The source ID to remove."),
    keep_file: bool = typer.Option(
        False,
        "--keep-file",
        help="Only remove from tracking; don't delete the file from raw/.",
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

    if not yes:
        action = "remove from tracking" if keep_file else "remove from tracking AND delete file"
        confirm = typer.confirm(
            f"About to {action}: #{source_id} {row['relpath']}. Proceed?"
        )
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(code=0)

    ok, msg = ingest_raw.remove_source(paths, source_id, delete_file=not keep_file)
    if ok:
        _ok(msg)
    else:
        _err(msg)
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Stage 3 — LLM ingest
# ---------------------------------------------------------------------------


class CliIngestCallbacks(ingest_llm.IngestCallbacks):
    """Rich terminal rendering of ingest progress."""

    def __init__(self, mode: str = "interactive") -> None:
        self.mode = mode
        self._stream_active = False
        self._stream_char_count = 0

    def on_start(self, source_id: int, source_title: str, file_path: str) -> None:
        console.print()
        console.rule(f"[bold cyan]Source #{source_id}[/bold cyan]  {source_title}")
        console.print(f"[dim]{file_path}[/dim]")

    def on_parsing(self) -> None:
        console.print("[dim]  parsing…[/dim]")

    def on_extracting(self) -> None:
        console.print("[dim]  extracting atomic concepts (thinking mode)…[/dim]")

    def on_extracted(self, extraction: ingest_llm.Extraction) -> None:
        console.print()
        console.print(f"[bold]Title:[/bold] {extraction.title}")
        console.print(f"[bold]Slug:[/bold]  [cyan]{extraction.source_slug}[/cyan]")
        console.print()
        console.print(f"[bold]Summary:[/bold]")
        console.print(f"  [dim]{extraction.summary}[/dim]")
        console.print()

        if extraction.key_takeaways:
            console.print("[bold]Key takeaways:[/bold]")
            for t in extraction.key_takeaways:
                console.print(f"  [dim]•[/dim] {t}")
            console.print()

        if extraction.extracted:
            console.print(f"[bold]Extracted Atomic Concepts[/bold] ({len(extraction.extracted)}):")
            for e in extraction.extracted:
                console.print(
                    f"  [green]+[/green] [cyan]{e.slug}[/cyan] [dim]({e.type})[/dim]  {e.name}"
                )
            console.print()

        if extraction.tags:
            console.print(f"[bold]Tags:[/bold] [dim]{', '.join(extraction.tags)}[/dim]")
            console.print()

    def on_extraction_failed(self, error: str) -> None:
        _warn(f"Extraction returned bad JSON. Retrying: {error[:200]}")

    def ask_confirm(self, extraction: ingest_llm.Extraction) -> bool:
        if self.mode == "batch":
            return True
        total_pages = len(extraction.extracted) + 1
        return typer.confirm(
            f"File these? Will create/update ~{total_pages} wiki pages.",
            default=True,
        )

    def on_drafting_page(self, kind: str, slug: str, operation: str) -> None:
        console.print()
        op_color = "green" if operation == "created" else "yellow"
        console.print(
            f"[{op_color}]{operation}[/{op_color}] [dim]{kind}[/dim] "
            f"[cyan]{slug}[/cyan]"
        )
        console.print("[dim]┄[/dim]" * 60)
        self._stream_active = True
        self._stream_char_count = 0

    def on_stream_chunk(self, chunk: str) -> None:
        if self._stream_active:
            console.print(chunk, end="", style="dim", highlight=False)
            self._stream_char_count += len(chunk)

    def on_page_written(self, page: ingest_llm.PageChange) -> None:
        if self._stream_active:
            console.print()
            console.print("[dim]┄[/dim]" * 60)
            self._stream_active = False

    def on_finalizing(self) -> None:
        console.print()
        console.print("[dim]finalizing (committing files, rebuilding index, appending log)…[/dim]")

    def on_complete(self, result: ingest_llm.IngestResult) -> None:
        console.print()
        if result.skipped:
            _warn(f"Skipped by user: {result.source_title}")
            return
        _ok(
            f"Ingested [bold]{result.source_title}[/bold] — "
            f"{result.pages_created} created, {result.pages_updated} updated"
        )

    def on_error(self, error: str) -> None:
        console.print()
        _err(error)


@app.command()
def ingest(
    source_id: Optional[int] = typer.Argument(
        None,
        help="Specific source ID to ingest. If omitted, processes all pending sources.",
    ),
    batch: bool = typer.Option(
        False,
        "--batch",
        help="Skip the interactive confirmation prompt for each source.",
    ),
    no_discover: bool = typer.Option(
        False,
        "--no-discover",
        help="Don't auto-scan raw/ for untracked files before ingesting.",
    ),
    no_thinking: bool = typer.Option(
        False,
        "--no-thinking",
        help="Disable Qwen3 thinking mode in Pass 1 (faster, slightly lower quality).",
    ),
) -> None:
    """Ingest pending sources: extract entities/concepts, write wiki pages.

    The pipeline runs three LLM passes per source:
      1. Extraction (thinking mode) — structured JSON
      2. Page drafting — one page per entity/concept with streaming output
      3. Source summary page

    Then rebuilds index.md and appends to log.md.
    """
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    llm_cfg = config.get("llm", {})

    # Build the right client based on system RAM
    console.print()
    console.print(f"[dim]{describe_backend(config)}…[/dim]")
    try:
        client = build_client(config)
        client.ensure_ready()
    except (OllamaNotRunning, ModelNotFound, GeminiError) as e:
        _err(str(e))
        raise typer.Exit(code=1)
    except LLMError as e:
        _err(f"LLM check failed: {e}")
        raise typer.Exit(code=1)

    provider_label = "Gemini" if isinstance(client, GeminiClient) else f"Ollama [{llm_cfg.get('model', 'deepseek-r1:14b')}]"
    _ok(f"LLM ready · [bold]{provider_label}[/bold]")

    mode = "batch" if batch else "interactive"
    thinking = not no_thinking

    try:
        if source_id is not None:
            # Single source
            cb = CliIngestCallbacks(mode=mode)
            result = ingest_llm.ingest_source(
                paths,
                source_id,
                client,
                cb,
                mode=mode,
                thinking_for_extraction=thinking,
            )
            results = [result]
        else:
            # All pending (with auto-discovery)
            results = ingest_llm.ingest_pending(
                paths,
                client,
                lambda: CliIngestCallbacks(mode=mode),
                mode=mode,
                auto_discover=not no_discover,
                thinking_for_extraction=thinking,
            )
    finally:
        client.close()

    if not results:
        console.print()
        _warn("No pending sources to ingest.")
        _hint("Sync sources with [bold]wiki sync[/bold] first.")
        return

    console.print()
    console.rule("[bold]Ingest summary[/bold]")
    ok_count = sum(1 for r in results if r.ok)
    skipped_count = sum(1 for r in results if r.skipped)
    error_count = sum(1 for r in results if r.error)
    total_created = sum(r.pages_created for r in results)
    total_updated = sum(r.pages_updated for r in results)

    parts = []
    if ok_count:
        parts.append(f"[green]{ok_count} ingested[/green]")
    if skipped_count:
        parts.append(f"[yellow]{skipped_count} skipped[/yellow]")
    if error_count:
        parts.append(f"[red]{error_count} errors[/red]")
    console.print("  " + " · ".join(parts))
    console.print(
        f"  [dim]total pages: {total_created} created, {total_updated} updated[/dim]"
    )
    console.print()

    if ok_count > 0:
        # Auto-rebuild the search index so queries find the new pages
        if search.is_available():
            console.print()
            console.print("[dim]Updating search index…[/dim]")
            try:
                search.update_index(paths, embed=True)
                _ok("Search index updated")
            except search.SearchBackendError as e:
                _warn(f"Search index update failed: {e}")
                _hint("You can retry manually later — ingest is already committed.")
        else:
            _hint(
                "qmd not installed — search index not updated. "
                "Install: [bold]npm install -g @tobilu/qmd[/bold]"
            )

        console.print()
        _hint("Open the vault in Obsidian and check the graph view!")
        _hint("Run [bold]wiki status[/bold] to see updated page counts.")
        _hint("Ask a question with [bold]wiki query \"<your question>\"[/bold]")


# ---------------------------------------------------------------------------
# Stage 4 — query
# ---------------------------------------------------------------------------


class CliQueryCallbacks(query_module.QueryCallbacks):
    """Rich terminal rendering of query progress."""

    def __init__(self) -> None:
        self._stream_active = False

    def on_start(self, question: str, mode: str) -> None:
        console.print()
        console.rule(f"[bold cyan]Query[/bold cyan]")
        console.print(f"[bold]Q:[/bold] {question}")
        console.print(f"[dim]mode: {mode}[/dim]")
        console.print()

    def on_classifying_intent(self) -> None:
        console.print("[dim]  understanding question…[/dim]")

    def on_intent_classified(self, intent: str) -> None:
        if intent == "chitchat":
            console.print("[dim]  → casual question, no search needed[/dim]")
        else:
            console.print("[dim]  → wiki question, searching…[/dim]")

    def on_chitchat_reply(self, reply: str) -> None:
        console.print()
        console.print("[dim]" + "─" * 72 + "[/dim]")
        console.print(reply)
        console.print("[dim]" + "─" * 72 + "[/dim]")
        console.print()

    def on_searching(self) -> None:
        console.print("[dim]  searching wiki (BM25 + vector + rerank)…[/dim]")

    def on_search_done(self, results) -> None:
        if not len(results):
            return
        console.print(f"[dim]  found {len(results)} relevant page(s):[/dim]")
        for i, hit in enumerate(results.hits, start=1):
            score_color = (
                "green" if hit.score > 0.7 else "yellow" if hit.score > 0.4 else "dim"
            )
            path = hit.full_path or hit.path
            title = hit.title or path
            console.print(
                f"    [dim]{i}.[/dim] [{score_color}]{hit.score:.2f}[/{score_color}] "
                f"[cyan]{path}[/cyan]  [dim]{title[:60]}[/dim]"
            )

    def on_no_results(self) -> None:
        console.print()
        _warn("No matching wiki pages found.")

    def on_synthesizing(self) -> None:
        console.print()
        console.print("[dim]  synthesizing answer…[/dim]")
        console.print("[dim]" + "─" * 72 + "[/dim]")
        self._stream_active = True

    def on_stream_chunk(self, chunk: str) -> None:
        if self._stream_active:
            console.print(chunk, end="", highlight=False)

    def on_saved(self, saved_path: str) -> None:
        if self._stream_active:
            console.print()
            self._stream_active = False
        console.print()
        _ok(f"Saved answer as [cyan]{saved_path}[/cyan]")

    def on_complete(self, result) -> None:
        if self._stream_active:
            console.print()
            console.print("[dim]" + "─" * 72 + "[/dim]")
            self._stream_active = False
        console.print()

    def on_error(self, error: str) -> None:
        if self._stream_active:
            console.print()
            self._stream_active = False
        console.print()
        _err(error)


@app.command()
def query(
    question: str = typer.Argument(..., help="The question to ask the wiki."),
    mode: str = typer.Option(
        "hybrid",
        "--mode",
        help="Search mode: hybrid | lex | vec",
    ),
    lex: bool = typer.Option(
        False,
        "--lex",
        help="Shortcut for --mode lex (BM25 only, fastest).",
    ),
    vec: bool = typer.Option(
        False,
        "--vec",
        help="Shortcut for --mode vec (vector only).",
    ),
    limit: int = typer.Option(
        8, "--limit", "-n", help="Max number of search hits to consider."
    ),
    min_score: float = typer.Option(
        0.0, "--min-score", help="Drop hits below this score."
    ),
    no_rerank: bool = typer.Option(
        False, "--no-rerank", help="Skip LLM reranking in hybrid mode."
    ),
    save_as: Optional[str] = typer.Option(
        None,
        "--save-as",
        help="Save the answer as wiki/Synthesized/<slug>.md and update the index.",
    ),
    scope: str = typer.Option(
        "wiki",
        "--scope",
        help="Search scope: wiki (LLM-summarized pages), raw (original docs), or hybrid (both).",
    ),
    no_intent_classify: bool = typer.Option(
        False,
        "--no-intent-classify",
        help="Skip intent classification step (saves ~3 sec per query).",
    ),
) -> None:
    """Ask a question: search the wiki, synthesize an answer with citations.

    The query pipeline runs:
      1. QMD search (BM25 + vector + rerank by default)
      2. Load the top N matching pages
      3. Qwen3 synthesizes a cited answer, streamed to the terminal
      4. Optionally save the answer as a synthesis page
    """
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    llm_cfg = config.get("llm", {})

    # Resolve search mode shortcuts
    if lex:
        mode = "lex"
    elif vec:
        mode = "vec"
    if mode not in ("hybrid", "lex", "vec"):
        _err(f"Invalid mode '{mode}'. Use hybrid, lex, or vec.")
        raise typer.Exit(code=1)

    if scope not in ("wiki", "raw", "hybrid"):
        _err(f"Invalid scope '{scope}'. Use wiki, raw, or hybrid.")
        raise typer.Exit(code=1)

    # Sanity checks
    if not search.is_available():
        _err("qmd is not installed.")
        _hint("Install it with: [bold]npm install -g @tobilu/qmd[/bold]")
        raise typer.Exit(code=1)

    # Warn if wiki is empty
    wiki_pages = sum(
        1
        for sub in ("entities", "concepts", "sources", "synthesis")
        for _ in (paths.wiki / sub).glob("*.md")
        if (paths.wiki / sub).exists()
    )
    if wiki_pages == 0:
        _err("Wiki has no pages yet.")
        _hint("Run [bold]wiki ingest[/bold] first to create pages.")
        raise typer.Exit(code=1)

    # Build the right client based on system RAM
    console.print()
    console.print(f"[dim]{describe_backend(config)}…[/dim]")
    try:
        client = build_client(config)
        client.ensure_ready()
    except (OllamaNotRunning, ModelNotFound, GeminiError) as e:
        _err(str(e))
        raise typer.Exit(code=1)
    except LLMError as e:
        _err(f"LLM check failed: {e}")
        raise typer.Exit(code=1)

    provider_label = "Gemini" if isinstance(client, GeminiClient) else f"Ollama [{llm_cfg.get('model', 'deepseek-r1:14b')}]"
    _ok(f"LLM ready · [bold]{provider_label}[/bold]")

    callbacks = CliQueryCallbacks()
    try:
        result = query_module.run_query(
            paths,
            client,
            question,
            callbacks,
            mode=mode,
            limit=limit,
            min_score=min_score,
            rerank=not no_rerank,
            save_as=save_as,
            scope=scope,
            classify_intent_first=not no_intent_classify,
        )
    finally:
        client.close()

    if result.error and not result.answer:
        raise typer.Exit(code=1)


@app.command()
def reindex() -> None:
    """Force a full rebuild of the QMD search index.

    Normally this runs automatically after `wiki ingest`, so you only need
    this if the index gets out of sync (e.g. you edited wiki pages manually).
    """
    paths = _resolve_root_or_die()
    if not search.is_available():
        _err("qmd is not installed.")
        _hint("Install it with: [bold]npm install -g @tobilu/qmd[/bold]")
        raise typer.Exit(code=1)

    console.print()
    console.print("[dim]Rebuilding search index (this may take a minute)…[/dim]")
    try:
        search.update_index(paths, embed=True)
        _ok("Search index rebuilt")
    except search.SearchBackendError as e:
        _err(f"Index rebuild failed: {e}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Stage 5 — lint
# ---------------------------------------------------------------------------


_SEVERITY_STYLE = {
    lint_module.Severity.ERROR: ("bold red", "✗"),
    lint_module.Severity.WARNING: ("yellow", "!"),
    lint_module.Severity.INFO: ("cyan", "i"),
}


def _render_lint_report_terminal(report: lint_module.LintReport) -> None:
    """Pretty-print a LintReport to the terminal using Rich."""
    console.print()
    # Summary panel
    score = report.health_score
    score_color = "green" if score >= 80 else "yellow" if score >= 50 else "red"
    summary_lines = [
        f"[bold]Health score:[/bold] [{score_color}]{score}/100[/{score_color}]",
        f"[bold]Pages checked:[/bold] {report.pages_checked}",
        f"[bold]Duration:[/bold] {report.duration_seconds:.2f}s",
        "",
        f"  [red]{len(report.errors)} errors[/red]"
        f" · [yellow]{len(report.warnings)} warnings[/yellow]"
        f" · [cyan]{len(report.infos)} infos[/cyan]",
    ]
    if report.auto_fixed:
        summary_lines.append(f"  [green]auto-fixed: {report.auto_fixed}[/green]")
    console.print(
        Panel.fit("\n".join(summary_lines), title="Lint Report", border_style="cyan")
    )

    if not report.issues:
        console.print()
        _ok("No issues found. Your wiki is in good shape!")
        return

    # Group by severity → display
    def _render_group(
        title: str, issues: list[lint_module.LintIssue], color: str
    ) -> None:
        if not issues:
            return
        console.print()
        console.rule(f"[bold {color}]{title} ({len(issues)})[/bold {color}]")

        # Group by page for cleaner reading
        by_page: dict[str, list[lint_module.LintIssue]] = {}
        for issue in issues:
            by_page.setdefault(issue.page, []).append(issue)

        for page, page_issues in by_page.items():
            console.print(f"\n  [cyan]{page}[/cyan]")
            for issue in page_issues:
                style, glyph = _SEVERITY_STYLE[issue.severity]
                # Escape any brackets in the message since wikilinks look
                # like Rich markup tags
                from rich.markup import escape as _escape
                safe_msg = _escape(issue.message)
                safe_suggestion = _escape(issue.suggestion) if issue.suggestion else ""
                console.print(
                    f"    [{style}]{glyph}[/{style}] "
                    f"[dim]{issue.check.value}:[/dim] {safe_msg}"
                )
                if safe_suggestion:
                    console.print(f"      [dim]→ {safe_suggestion}[/dim]")
                if issue.fixable:
                    console.print(
                        f"      [green dim]✓ auto-fixable[/green dim]"
                    )

    _render_group("Errors", report.errors, "red")
    _render_group("Warnings", report.warnings, "yellow")
    _render_group("Info", report.infos, "cyan")


@app.command()
def lint(
    deep: bool = typer.Option(
        False,
        "--deep",
        help="Run LLM-powered contradiction detection (slower, requires Ollama).",
    ),
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Auto-fix trivial issues (malformed wikilinks, noise in sources).",
    ),
    save: bool = typer.Option(
        False,
        "--save",
        help="Save the report as wiki/Synthesized/lint-report-YYYY-MM-DD.md",
    ),
    max_pairs: int = typer.Option(
        10,
        "--max-pairs",
        help="Max page pairs to check in --deep mode.",
    ),
) -> None:
    """Lint the wiki for broken links, orphans, missing pages, and more.

    Fast checks (default) run entirely in Python and finish in seconds.
    Use --deep to also scan page pairs for contradictions using Qwen3.
    """
    paths = _resolve_root_or_die()

    # If --deep, verify LLM backend up front
    client: OllamaClient | GeminiClient | None = None
    if deep:
        config = cfg.load_config(paths)
        console.print(f"[dim]{describe_backend(config)}…[/dim]")
        try:
            client = build_client(config)
            client.ensure_ready()
        except (OllamaNotRunning, ModelNotFound, GeminiError, LLMError) as e:
            _err(str(e))
            _hint("Fast-only lint still works without an LLM — omit --deep.")
            raise typer.Exit(code=1)
        llm_label = "Gemini" if isinstance(client, GeminiClient) else client.model
        _ok(f"LLM ready · [bold]{llm_label}[/bold]")

    try:
        console.print()
        if deep:
            console.print("[dim]Running fast checks + contradiction detection…[/dim]")
        else:
            console.print("[dim]Running fast checks…[/dim]")

        report = lint_module.run_lint(paths, deep=deep, client=client)
    finally:
        if client is not None:
            client.close()

    # Auto-fix before displaying
    if fix:
        fixed_count = lint_module.apply_fixes(paths, report.issues)
        report.auto_fixed = fixed_count
        if fixed_count > 0:
            # Rebuild inventory + re-run checks so the report reflects post-fix state
            report = lint_module.run_lint(paths, deep=False, client=None)
            report.auto_fixed = fixed_count

    _render_lint_report_terminal(report)

    # Save as a synthesis page
    if save:
        today = lint_module.page_writer.today_iso()  # reuse helper
        slug = f"lint-report-{today}"
        target_path = paths.wiki / "synthesis" / f"{slug}.md"
        content = lint_module.render_report_markdown(report, paths)
        lint_module.page_writer.write_page(target_path, content)
        # Rebuild index so the new page shows up
        lint_module.page_writer.rebuild_index(paths, today)
        console.print()
        _ok(f"Saved report to [cyan]Synthesized/{slug}.md[/cyan]")

    # Exit code: 1 if there are errors, 0 otherwise (for CI use)
    if report.errors:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Stage 6 — web UI
# ---------------------------------------------------------------------------


@app.command()
def serve(
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Bind address. Default 127.0.0.1 (localhost only).",
    ),
    port: int = typer.Option(
        8000,
        "--port",
        "-p",
        help="Port to listen on.",
    ),
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="Don't auto-open the browser on startup.",
    ),
    reload: bool = typer.Option(
        False,
        "--reload",
        help="Auto-reload on code changes (development only).",
    ),
) -> None:
    """Start the LLM-Wiki web UI on localhost.

    The UI provides a dashboard, source browser, ingest interface, query
    interface, and lint dashboard. It runs locally and binds to 127.0.0.1
    by default — no external access, no auth required.
    """
    paths = _resolve_root_or_die()

    # Verify the project looks healthy before launching
    if not paths.wiki.exists():
        _err(f"Wiki folder not found at {paths.wiki}")
        _hint("Run `wiki init` first to scaffold the project.")
        raise typer.Exit(code=1)

    # Lazy import — avoid loading FastAPI/uvicorn unless we're actually serving
    try:
        import uvicorn

        from .webapp.main import create_app
    except ImportError as e:
        _err(f"Web UI dependencies not installed: {e}")
        _hint("Install with: uv pip install -e .")
        raise typer.Exit(code=1)

    app_instance = create_app(paths)

    url = f"http://{host}:{port}"
    console.print()
    console.print(
        Panel.fit(
            f"[bold]LLM-Wiki[/bold] web UI starting…\n\n"
            f"  URL: [bold cyan]{url}[/bold cyan]\n"
            f"  Project: [dim]{paths.root}[/dim]\n\n"
            f"[dim]Press Ctrl+C to stop.[/dim]",
            title="🚀 Serve",
            border_style="cyan",
        )
    )

    # Open browser shortly after the server starts
    if not no_browser:
        import threading
        import time
        import webbrowser

        def _open_browser() -> None:
            time.sleep(1.2)  # let uvicorn finish binding
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Thread(target=_open_browser, daemon=True).start()

    # Run uvicorn. We pass the app instance directly (not a string) so the
    # paths injection survives. Reload mode requires a string import path,
    # so it's not supported here — that's fine, the wiki is small and a
    # restart is instant.
    if reload:
        _hint("--reload not supported with paths injection; ignoring.")

    try:
        uvicorn.run(
            app_instance,
            host=host,
            port=port,
            log_level="warning",  # quiet — we don't need every request logged
            access_log=False,
        )
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")


def main() -> None:
    """Entry point used by the `wiki` console script."""
    app()


if __name__ == "__main__":
    main()
