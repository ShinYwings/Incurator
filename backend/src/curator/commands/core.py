# ruff: noqa: F403,F405
# mypy: disable-error-code=name-defined
"""Root commands for the `wiki` CLI."""

from __future__ import annotations

from .common import *

def reset(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Do not prompt for confirmation.",
    )
) -> None:
    """Reset the Curator vault state while preserving settings.yml.
    
    This deletes the local tracking database/cache and generated Collections.
    Shared settings, sessions, profiles, overview, and correction ledger remain.
    """
    import shutil
    
    if not force:
        confirm = typer.confirm("This will permanently delete all Curator state and generated collections. Are you sure?")
        if not confirm:
            console.print("Reset cancelled.")
            return

    paths = _resolve_root_or_die()
    if not paths:
        _err("Not inside a Curator vault.")
        raise typer.Exit(code=1)
        
    items_to_remove = [
        paths.state_db,
        paths.state_db.with_name(paths.state_db.name + "-wal"),
        paths.state_db.with_name(paths.state_db.name + "-shm"),
        paths.runtime,
        paths.dashboard,
        paths.sync_report,
        paths.event_log,
        paths.staging,
        paths.index,
        paths.collections_dir if hasattr(paths, 'collections_dir') else paths.collections,
    ]
    items_to_remove.extend(paths.internal.glob("build_trace_*.canvas"))
    
    removed = []
    for item in items_to_remove:
        if item.exists():
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                removed.append(
                    str(item.relative_to(paths.root))
                    if item.is_relative_to(paths.root)
                    else str(item)
                )
            except Exception as e:
                _err(f"Failed to remove {item.name}: {e}")
                
    if removed:
        console.print("[green]✓ Reset complete.[/green] Removed:")
        for r in removed:
            console.print(f"  - {r}")
    else:
        console.print("[dim]Vault is already empty.[/dim]")


def version() -> None:
    """Show the incurator version."""
    console.print(f"incurator [bold cyan]{__version__}[/bold cyan]")


def init(
    vault_path: str = typer.Argument(
        ...,
        help="Path to the vault root (where 02_Wiki, 03_Notes, etc. live).",
    ),
    raw_dirs: list[str] = typer.Option(
        [consts.DIR_WIKI, consts.DIR_NOTES, consts.DIR_RESOURCES, consts.DIR_ARCHIVES],
        "--raw",
        "-r",
        help="Source directories to monitor (relative to vault root). Repeatable.",
    ),
    interactive: bool = typer.Option(
        True,
        "--interactive/--no-interactive",
        help="Run interactive LLM setup wizard (default: on). Use --no-interactive for CI/scripting.",
    ),
) -> None:
    """Initialise a Curator project inside an Obsidian vault.

    If the directory already exists (or is an existing Obsidian vault), only
    missing topology directories and .curator/ files are created — nothing is
    overwritten.

    Creates:
      .obsidian/                 — Obsidian vault marker (created if absent)
      00_System/ … 06_Archives/ — Vault topology (created if absent)
      .curator/settings.yml        — project configuration
      <repo>/.cache/vaults/<key>/state.sqlite — local tracking database
      .curator/Collections/      — 01_Contexts/ 02_Atoms/ 03_Concepts/ 04_Synthesis/
      .curator/overview.md       — domain manifest
      .curator/index.md          — DAG routing table
      .curator/log.md            — ingest log
      .curator/ledger.md         — override ledger
    """
    import shutil

    import os
    root = Path(vault_path).resolve()

    # Create vault root if it doesn't exist yet
    if not root.exists():
        try:
            root.mkdir(parents=True)
        except (OSError, PermissionError) as e:
            _err(f"Cannot create vault root '{root}': {e}")
            raise typer.Exit(code=1) from e
        _ok(f"Created vault root: {root}")
    elif root.is_file():
        _err(f"Path '{root}' is a file, not a directory.")
        raise typer.Exit(code=1)
    elif not os.access(root, os.W_OK):
        _err(f"No write permission on '{root}'. Check directory permissions.")
        raise typer.Exit(code=1)

    # Guarantee this is an Obsidian vault (.obsidian/ is the vault marker)
    obsidian_dir = root / ".obsidian"
    if not obsidian_dir.exists():
        obsidian_dir.mkdir()
        _ok("Created Obsidian vault marker: .obsidian/")

    # Auto-install Obsidian plugin if available in the source tree
    plugin_src = Path(__file__).resolve().parents[3] / "plugin"
    if plugin_src.exists():
        plugin_dest = obsidian_dir / "plugins" / "incurator-obsidian-agent"
        plugin_dest.mkdir(parents=True, exist_ok=True)

        build_plugin = False
        if interactive:
            build_plugin = typer.confirm("Build and install the Obsidian plugin for this vault?", default=True)
        else:
            build_plugin = True

        if build_plugin:
            import subprocess
            import os
            console.print("[dim]Building Obsidian plugin via npm... (this may take a moment)[/dim]")
            try:
                # Force OBSIDIAN_PLUGIN_DIR to empty so esbuild.config.mjs outputs to
                # plugin_src/main.js instead of the vault. dotenv reads from ..env directly
                # (bypassing subprocess env), so we must set it to "" rather than just pop it.
                build_env = dict(os.environ)
                build_env["OBSIDIAN_PLUGIN_DIR"] = ""
                subprocess.run(["npm", "install"], cwd=str(plugin_src), check=True, capture_output=True, env=build_env)
                subprocess.run(["npm", "run", "build"], cwd=str(plugin_src), check=True, capture_output=True, env=build_env)
                _ok("Obsidian plugin built successfully.")
            except subprocess.CalledProcessError as e:
                err_msg = e.stderr.decode("utf-8", errors="replace").strip() if e.stderr else ""
                _warn(f"Failed to build Obsidian plugin. npm exit code {e.returncode}.\n[dim]{err_msg}[/dim]")
            except FileNotFoundError:
                _warn("npm command not found. Cannot build Obsidian plugin.")

        copied_any = False
        for fname in ["main.js", "manifest.json", "styles.css"]:
            src_file = plugin_src / fname
            if src_file.exists():
                shutil.copy2(src_file, plugin_dest / fname)
                copied_any = True
        if copied_any:
            _ok(f"Installed Obsidian plugin to {plugin_dest.relative_to(root)}")

    paths = cfg.WikiPaths(
        root=root,
        raw_dirs_override=raw_dirs,
    )
    already_initialized = paths.is_initialized()

    # Always ensure the vault topology exists (idempotent, never overwrites)
    created_dirs: list[str] = []
    for d in cfg.VAULT_TOPOLOGY:
        target = root / d
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            created_dirs.append(d)

    if already_initialized:
        cfg.set_last_root(root)
        console.print()
        console.print(f"[dim cyan]Curator already initialised at {root}[/dim cyan]")
        if created_dirs:
            console.print("[dim]Created missing vault directories:[/dim]")
            for d in created_dirs:
                _ok(d)
        else:
            console.print("[dim]Vault topology is complete — nothing to create.[/dim]")
        console.print()
        _hint("Run [bold]wiki status[/bold] to review current state.")
        raise typer.Exit(code=0)

    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]Initialising incurator[/bold cyan]\n"
            f"[dim]{root}[/dim]",
            border_style="cyan",
        )
    )

    # 1. Build config
    config = dict(cfg.DEFAULT_CONFIG)
    config["paths"] = {
        "raw_dirs": raw_dirs,
        "collections_dir": consts.DEFAULT_COLLECTIONS_DIR,
    }
    config["vault_schema_version"] = consts.VAULT_SCHEMA_VERSION
    # Cloud provider + API keys
    llm = dict(config.get("llm", {}))

    if not interactive:
        # --no-interactive with no flags: skip provider setup entirely
        _hint("LLM provider not configured. Run [bold]wiki config provider[/bold] to set it up.")
    else:
        # Interactive mode: ask user how they want to configure
        console.print()
        console.print("[bold]LLM Provider Setup[/bold]")
        console.print("  [cyan]1[/cyan]  Interactive wizard  [dim](set up now)[/dim]")
        console.print("  [cyan]2[/cyan]  CLI flags           [dim](I'll run `wiki config-provider --primary ...` later)[/dim]")
        console.print()
        choice = typer.prompt("Choose setup method (1/2)", default="1").strip()
        if choice == "1":
            wizard_overrides = _run_init_wizard()
            llm.update(wizard_overrides)
            _offer_install(wizard_overrides, llm)
        else:
            _hint("Run [bold]wiki config provider --primary ollama|antigravity-cli|claude-code|codex-cli|deepseek-api ...[/bold] to configure.")

    if "provider" in llm:
        del llm["provider"]
    config["llm"] = llm

    # 2. Create directory structure
    paths.internal.mkdir(parents=True, exist_ok=True)
    paths.collections.mkdir(parents=True, exist_ok=True)
    for layer in cfg.COLLECTION_LAYERS:
        (paths.collections / layer).mkdir(parents=True, exist_ok=True)

    # 3. Write settings.yml
    cfg.save_config(paths, config)
    _ok(f"Config:    {paths.config_file.relative_to(root)}")

    # 4. Init the state database
    cfg.prepare_machine_state(paths)
    db.init_db(paths.state_db)
    _ok(f"Database:  {paths.state_db}")

    # 5. Copy template files
    templates_dir = Path(__file__).parent / "workspace" / "templates"

    # .gitignore
    gitignore_src = templates_dir / "gitignore.template"
    gitignore_dest = root / ".gitignore"
    if gitignore_src.exists() and not gitignore_dest.exists():
        shutil.copy2(gitignore_src, gitignore_dest)
        _ok(f"Git ignore:  {gitignore_dest.relative_to(root)}")

    # .stignore
    stignore_src = templates_dir / "stignore.template"
    stignore_dest = root / ".stignore"
    if stignore_src.exists() and not stignore_dest.exists():
        shutil.copy2(stignore_src, stignore_dest)
        _ok(f"Sync ignore: {stignore_dest.relative_to(root)}")

    # index.md (in .curator/ root, not Collections/)
    index_src = templates_dir / consts.FILE_INDEX_MD
    if index_src.exists() and not paths.index.exists():
        shutil.copy2(index_src, paths.index)
        _ok(f"Index:     {paths.index.relative_to(root)}")

    # overview.md
    if not paths.overview.exists():
        paths.overview.write_text(
            "---\ntitle: Domain Manifest\ntype: overview\n---\n\n"
            "# .curator/overview.md — Domain Manifest\n\n"
            "*List the knowledge domains tracked in this vault.*\n",
            encoding="utf-8",
        )
        _ok(f"Overview:  {paths.overview.relative_to(root)}")

    # ledger.md
    if not paths.ledger.exists():
        paths.ledger.write_text(
            "---\ntitle: Ledger\ntype: ledger\n---\n\n"
            "# .curator/ledger.md — Override Ledger\n\n"
            "*High-priority human corrections that silently override L1-L4 nodes.*\n",
            encoding="utf-8",
        )
        _ok(f"Ledger:    {paths.ledger.relative_to(root)}")

    # log.md
    if not paths.log.exists():
        paths.log.write_text(
            "---\ntitle: Curator Log\ntype: log\n---\n\n# .curator/log.md — Hash Registry\n\n",
            encoding="utf-8",
        )
        _ok(f"Log:       {paths.log}")

    # v0.3.2+: search is DB-native (FTS5 + vector inside state.sqlite). No
    # external search backend config/index is written; `wiki build` and
    # `wiki reindex` materialize the search corpus directly from the DB.

    # 6. Curator persona interview (requires LLM to be configured)
    if interactive and config.get("llm", {}).get("primary"):
        console.print()
        console.print("[bold]Curator Persona Setup[/bold]")
        console.print("[dim]This shapes how knowledge is verified and synthesized vault-wide.[/dim]")
        try:
            _persona_client = _start_client(config)
            _curator_persona = _run_curator_persona_wizard(_persona_client)
            if _curator_persona is not None:
                import datetime as _dt_persona
                _curator_persona["updated_at"] = _dt_persona.datetime.now().isoformat()
                config["persona"] = _curator_persona
                cfg.save_config(paths, config)
                _ok("Curator persona saved.")
        except Exception as _persona_exc:
            _warn(f"Persona setup skipped: {_persona_exc}")
            _hint("Run [bold]wiki persona update[/bold] later to configure.")

    # 7. Summary
    cfg.set_last_root(root)
    _updated_mcp = _sync_mcp_configs(root)

    console.print()
    console.print("[bold green]Curator initialised![/bold green]")
    console.print()
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim", width=18)
    table.add_column()
    if created_dirs:
        table.add_row("Vault dirs", ", ".join(created_dirs))
    table.add_row("Source dirs", ", ".join(raw_dirs))
    table.add_row("Collections", str(paths.collections.relative_to(root)))
    table.add_row("Config", str(paths.config_file.relative_to(root)))
    table.add_row("LLM backend", describe_backend(config))
    if _updated_mcp:
        table.add_row("MCP configs", f"{len(_updated_mcp)} updated")
    console.print(table)
    console.print()
    if not config.get("llm", {}).get("primary"):
        _hint("LLM provider not set. Run [bold]wiki config provider[/bold] to configure.")
    else:
        _hint("Next: run [bold]wiki add[/bold] to discover sources, then [bold]wiki build[/bold].")


def _may_point_elsewhere(stub: Path) -> bool:
    """True when a source might resolve to a file outside the vault.

    Reads only the first bytes rather than parsing frontmatter, because this
    runs once per source on every `wiki status`. A Reference-Mode stub declares
    `type: reference` in its opening frontmatter block; anything else owns its
    bytes in the vault and cannot be behind a folder grant.
    """
    try:
        if stub.suffix.lower() != ".md":
            return True          # a real PDF/asset in place: probe it directly
        with open(stub, "rb") as handle:
            head = handle.read(600)
    except OSError:
        return True              # unreadable stub is itself worth reporting
    return b"type: reference" in head or b"zotero" in head.lower()


def _report_unreadable_sources(paths: cfg.WikiPaths, console: Any) -> None:
    """Name sources whose file exists but cannot be read, once, with the fix.

    A per-job ingest error is the worst place to learn a folder needs granting:
    it recurs, arrives mid-run, and until v0.61.0 said `Cannot parse PDF`, which
    points at the file rather than the permission. Status is where a user looks
    deliberately, so a refusal is reported here with the folder to grant
    (SYSTEM_BEHAVIOR §12.3).

    Resolution goes through `_resolve_reference_source` — the same function
    ingest uses — rather than a query over `logical_source_id`/`external_ref`.
    Those columns are NULL for the very source that prompted this work: its
    Zotero identity lives in the stub's frontmatter, not the source row, so a
    DB-only filter would have reported nothing for the one case that matters.
    """
    import unicodedata

    from ..ingest_raw import _resolve_reference_source
    from ..parsers import ParserAccessDenied
    from .. import file_access

    try:
        with db.connect(paths.state_db) as conn:
            rows = conn.execute("SELECT relpath FROM sources").fetchall()
    except Exception as e:  # noqa: BLE001 - status must never fail on a diagnostic
        logger.debug("unreadable-source scan could not read sources: %s", e)
        return

    # (relpath, resolved path, grant folder). The grant folder travels WITH the
    # denial rather than being re-derived: the exception already carries the one
    # the resolver computed, and re-probing would both discard that and pay the
    # 0.7 ms denial cost a second time for an answer we were handed.
    denied: list[tuple[str, Path, str]] = []
    for row in rows:
        relpath = str(row["relpath"])
        stub = paths.root / relpath
        # Cheap filter first. Resolving a stub means reading and parsing its
        # frontmatter: measured at 123 ms across 44 sources against 1 ms for the
        # probes themselves, and it grows linearly, so a large vault would make
        # `wiki status` visibly slow for a report that concerns only Reference
        # Mode. A source whose own file is readable and is not a reference stub
        # cannot be behind a grant.
        if not _may_point_elsewhere(stub):
            continue
        try:
            resolved = _resolve_reference_source(paths, stub)
        except ParserAccessDenied as e:
            # The resolver now RAISES on a denial rather than degrading, so the
            # signal arrives as an exception here. Catching it under a blanket
            # `except Exception: continue` would have thrown away the one thing
            # this function exists to report -- which it did, until running it
            # showed nothing.
            denied.append((relpath, Path(e.path), e.grant_folder))
            continue
        except Exception as e:  # noqa: BLE001 - one bad stub must not hide the rest
            logger.debug("could not resolve '%s' while scanning: %s", relpath, e)
            continue
        if file_access.probe(resolved) is file_access.Reachability.DENIED:
            root = file_access.grant_root(resolved)
            denied.append((relpath, resolved, str(root) if root else ""))

    if not denied:
        return

    # Collapse rows that name the same file, and SAY SO rather than hiding it.
    # The vault carries one file registered twice -- once NFD (what macOS
    # writes) and once NFC -- which `GROUP BY relpath` cannot see because the
    # bytes differ. Silently deduplicating would make this report tidy while
    # concealing a defect that costs real money: each row runs its own ingest
    # job, so the LLM work is paid twice. Reporting the collision is the point.
    grouped: dict[str, list[tuple[str, Path, str]]] = {}
    for entry in denied:
        grouped.setdefault(unicodedata.normalize("NFC", entry[0]), []).append(entry)
    duplicated = [k for k, v in grouped.items() if len(v) > 1]
    denied = [rows[0] for rows in grouped.values()]

    by_root: dict[str, list[str]] = {}
    for relpath, _resolved, grant in denied:
        by_root.setdefault(grant or "(unknown folder)", []).append(relpath)

    console.print()
    console.print(
        f"[yellow]{len(denied)} source file(s) exist but cannot be read.[/yellow] "
        "They are not missing or damaged — this process lacks permission."
    )
    for root_name, names in by_root.items():
        console.print(f"  [dim]grant access to[/dim] {root_name}")
        for name in names[:5]:
            console.print(f"      {name}")
        if len(names) > 5:
            console.print(f"      … and {len(names) - 5} more")
    console.print(
        "  [dim]System Settings → Privacy & Security → Full Disk Access, "
        "then restart the app.[/dim]"
    )
    if duplicated:
        console.print()
        console.print(
            f"[yellow]{len(duplicated)} of these are registered more than once[/yellow] "
            "under Unicode-different spellings of the same path, so their ingest "
            "work is done twice. Reported here because a byte comparison cannot "
            "see it."
        )


def status(
    json_output: bool = typer.Option(False, "--json", help="Print the live status/sources/jobs payload as machine-readable JSON (used by the plugin dashboard)."),
    refresh: bool = typer.Option(False, "--refresh", help="Refresh the on-disk runtime snapshot cache before displaying (writes to the vault)."),
) -> None:
    """Show the current wiki's stats, paths, and config."""
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    if refresh:
        runtime_state.write_runtime_snapshots(paths, config)

    # An empty database is not the same fact as an empty vault. `state.sqlite`
    # is machine-local and keyed by the vault's resolved path, so a cleared
    # `.cache/`, a new machine, or a RENAMED VAULT all mint a fresh empty one --
    # and zeros here look exactly like a vault nobody has ingested. When the
    # vault still carries a sync journal the knowledge is recoverable, and saying
    # nothing invites a full re-ingest of work that is sitting right there.
    from ..db_sync import describe_recoverable_state

    recoverable = describe_recoverable_state(paths)

    if json_output:
        payload = {
            "status": runtime_state.build_status_snapshot(paths, config),
            "sources": runtime_state.build_sources_snapshot(paths),
            "jobs": runtime_state.build_jobs_snapshot(paths),
        }
        if recoverable:
            payload["recoverable_state"] = recoverable
        _print_json(payload)
        return
    if recoverable:
        console.print(f"[yellow]{recoverable}[/yellow]\n")
    stats = db.get_stats(paths.state_db)

    def _count_md(folder: Path) -> int:
        if not folder.exists():
            return 0
        return sum(1 for p in folder.glob("*.md") if not p.name.startswith("."))

    raw_files = 0
    for raw_dir in paths.raw_dirs:
        if raw_dir.exists():
            raw_files += sum(1 for p in raw_dir.rglob("*") if p.is_file() and not p.name.startswith("."))

    _DEFAULT_MODELS = {
        consts.BACKEND_ANTIGRAVITY_CLI: consts.DEFAULT_ANTIGRAVITY_MODEL,
        consts.BACKEND_CLAUDE_CODE:     consts.DEFAULT_CLAUDE_MODEL,
        consts.BACKEND_CODEX_CLI:       consts.DEFAULT_CODEX_MODEL,
        consts.BACKEND_OLLAMA:          consts.DEFAULT_OLLAMA_MODEL,
    }

    def _get_backend_model(key: str, llm_cfg: dict) -> str:
        for slot in ("primary", "fallback"):
            p, m = cfg.split_provider_model(llm_cfg.get(slot, ""))
            if p == key:
                return m or _DEFAULT_MODELS.get(key, "?")
        return "?"

    def _get_backend_label(key: str, _llm_cfg: dict = {}) -> str:
        if key == consts.BACKEND_OLLAMA:
            return "Ollama"
        elif key == consts.BACKEND_CLAUDE_CODE:
            return "Claude Code"
        elif key == consts.BACKEND_ANTIGRAVITY_CLI:
            return "Antigravity CLI"
        elif key == consts.BACKEND_CODEX_CLI:
            return "Codex CLI"
        return key if key else "?"

    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]incurator[/bold cyan]  [dim]@ {paths.root}[/dim]",
            border_style="cyan",
        )
    )

    cfg_table = Table(title="Config", show_header=False, box=None, padding=(0, 2))
    cfg_table.add_column(style="dim", width=22)
    cfg_table.add_column()
    llm = config.get("llm", {})
    search_cfg = config.get("search", {})

    def _effort_suffix(eff: str) -> str:
        return f"  [dim]· {eff} effort[/dim]" if eff else ""

    primary_prov, primary_model = cfg.split_provider_model(llm.get("primary", ""))
    cfg_table.add_row(
        "Primary",
        f"{_get_backend_label(primary_prov, llm)}  ({primary_model or '?'})"
        f"{_effort_suffix(llm.get('primary_effort', ''))}",
    )

    fb_prov, fb_model = cfg.split_provider_model(llm.get("fallback", ""))
    if fb_prov:
        cfg_table.add_row(
            "Fallback",
            f"{_get_backend_label(fb_prov, llm)}  ({fb_model or '?'})"
            f"{_effort_suffix(llm.get('fallback_effort', ''))}",
        )
    else:
        cfg_table.add_row("Fallback", "none")

    account = llm_identity.get_llm_account_info(primary_prov)
    if account.get("email"):
        acc_text = f"{account['email']}  [dim]({account.get('name', '')})[/dim]"
    else:
        acc_text = account.get("name") or "Unknown"
    cfg_table.add_row("Account", acc_text)

    ollama_cfg = llm.get(consts.BACKEND_OLLAMA, {})
    if primary_prov == consts.BACKEND_OLLAMA or fb_prov == consts.BACKEND_OLLAMA:
        cfg_table.add_row("Ollama host", ollama_cfg.get("host", "?"))

    cfg_table.add_row("Search backend", search_cfg.get("backend", "native"))
    cfg_table.add_row("Reranking", "on" if search_cfg.get("rerank") else "off")
    cfg_table.add_row("Embedding", str(search_cfg.get("embedding") or "[dim]none[/dim]"))
    cfg_table.add_row(
        "Search engine",
        f"[green]{search.get_version()}[/green]  [dim]in-DB FTS5 + vector[/dim]",
    )
    console.print(cfg_table)

    table = Table(title="Sources", show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim", width=22)
    table.add_column()
    table.add_row("Raw source files", str(raw_files))
    table.add_row("Sources tracked (DB)", str(stats["sources_total"]))
    table.add_row("Sources summarized (L1)", str(stats.get("sources_l1_done", 0)))
    table.add_row("Ingest runs", str(stats["ingest_runs"]))
    total_in = stats.get("total_input_tokens", 0)
    total_out = stats.get("total_output_tokens", 0)
    total_cost = stats.get("total_cost_usd", 0.0)
    if total_in or total_out:
        def _fmt_tokens(n: int) -> str:
            if n >= 1_000_000:
                return f"{n / 1_000_000:.1f}M"
            if n >= 1_000:
                return f"{n / 1_000:.1f}K"
            return str(n)
        cost_str = f"  [dim](${total_cost:.4f})[/dim]" if total_cost > 0 else ""
        table.add_row(
            "Total LLM tokens",
            f"in {_fmt_tokens(total_in)} / out {_fmt_tokens(total_out)}{cost_str}",
        )
    console.print(table)

    _report_unreadable_sources(paths, console)

    pages_table = Table(title="Collections", show_header=False, box=None, padding=(0, 2))
    pages_table.add_column(style="dim", width=22)
    pages_table.add_column()

    l1 = _count_md(paths.contexts)
    l2 = _count_md(paths.atoms)
    l3 = _count_md(paths.concepts)
    l4 = _count_md(paths.synthesis)
    pages_table.add_row("L1 Contexts/",     str(l1))
    pages_table.add_row("L2 Atoms/",        str(l2))
    pages_table.add_row("L3 Concepts/",     str(l3))
    pages_table.add_row("L4 Synthesis/",    str(l4))
    pages_table.add_row("[bold]total[/bold]", f"[bold]{l1+l2+l3+l4}[/bold]")
    console.print(pages_table)

    _render_search_index_gap(stats)

    _render_pipeline_status(paths)
    active_jobs = db.list_ingest_jobs(paths.state_db, states=("queued", "running"), limit=8)
    if active_jobs:
        jobs_table = Table(title="Background Jobs", show_header=True, box=None, padding=(0, 1))
        jobs_table.add_column("id", justify="right", style="dim")
        jobs_table.add_column("type", style="cyan")
        jobs_table.add_column("state")
        jobs_table.add_column("phase", style="dim")
        jobs_table.add_column("source")
        for job in active_jobs:
            jobs_table.add_row(
                str(job.get("id", "")),
                str(job.get("job_type", "")),
                str(job.get("state", "")),
                str(job.get("phase", "") or ""),
                str(job.get("source_name", "") or job.get("source_id", "")),
            )
        console.print(jobs_table)
    _render_latest_sync_report_summary(paths)

    try:
        def _silent_cb(node_id): pass
        sync_preflight = lint_module.run_lint(paths, deep=False, client=None, progress_callback=_silent_cb)
        _render_sync_preflight_summary(sync_preflight)
    except Exception as e:
        _warn(f"Sync preflight summary unavailable: {e}")

    console.print()
    if stats["sources_total"] == 0:
        _hint("No sources yet. Add them with [bold]wiki add[/bold]")
    elif stats.get("sources_l1_done", 0) == 0:
        _hint(
            f"{stats['sources_total']} source(s) tracked but not summarized. "
            f"Run [bold]wiki add[/bold] to create L1 Contexts."
        )

    # Only meaningful when something actually runs through agy — and there are
    # TWO independent places that decide that, on different axes.
    #
    # `.curator/config.yml`'s `llm.primary` governs the curation pipeline. The
    # Obsidian plugin's chat agent is governed by its OWN `provider` in
    # `data.json`, and nothing bridges them. Checking only the backend's setting
    # stays silent for a user who runs curation on Ollama and chat on
    # Antigravity — which is exactly the user this warning exists for, since the
    # chat path is what spawns agy and depends on the MCP registration.
    try:
        from .common import agy_mcp_registration_problem, uses_antigravity_anywhere

        _agy_problem = (
            agy_mcp_registration_problem(paths.root)
            if uses_antigravity_anywhere(paths, config)
            else ""
        )
    except Exception as _agy_exc:  # noqa: BLE001 - a health check must not take down `status`
        _agy_problem = ""
        _warn(f"Antigravity wiring check unavailable: {_agy_exc}")
    if _agy_problem:
        _warn(
            f"Antigravity cannot reach this vault's tools. {_agy_problem} "
            "Run [bold]wiki config provider[/bold] to re-register, then ask "
            "the assistant again."
        )

    from .. import migrate as _migrate
    vault_v = _migrate.get_vault_schema_version(paths)
    if vault_v < consts.VAULT_SCHEMA_VERSION:
        _warn(
            f"Vault schema v{vault_v} → backend expects v{consts.VAULT_SCHEMA_VERSION}. "
            "Run [bold]wiki migrate[/bold] to upgrade."
        )


def migrate_vault(
    dry_run: bool = typer.Option(False, "--dry-run", help="Report what would be done without writing."),
    requeue: bool = typer.Option(False, "--requeue", help="Re-queue sources whose Collection files have missing required fields."),
) -> None:
    """Upgrade vault schema to the current backend version.

    Run this after updating the incurator backend to apply any structural
    changes to .curator/settings.yml or Collections/*.md.
    """
    from .. import migrate as _migrate

    paths = _resolve_root_or_die()
    result = _migrate.run_migrations(paths, dry_run=dry_run)

    if result.already_current:
        _ok(f"Vault is up to date (schema v{result.current_version}).")
    else:
        if dry_run:
            console.print(f"[dim]dry-run:[/dim] would migrate vault schema v{result.current_version} → v{result.target_version}")
            for step in result.steps_run:
                console.print(f"  [cyan]{step}[/cyan]")
        else:
            for step in result.steps_run:
                _ok(f"{step}")
            for step, err in result.errors.items():
                _err(f"{step}: {err}")
            if result.ok:
                _ok(f"Vault upgraded to schema v{result.current_version}.")
            else:
                _warn("Migration stopped due to errors. Fix the issues above and re-run.")

    if result.stale_files:
        stale_table = Table(title="Stale Collection Files", show_header=True, box=None, padding=(0, 2))
        stale_table.add_column("File", style="dim")
        stale_table.add_column("Missing fields")
        for sf in result.stale_files[:20]:
            stale_table.add_row(
                str(sf.path.relative_to(paths.root)),
                ", ".join(sorted(sf.missing_fields)),
            )
        if len(result.stale_files) > 20:
            stale_table.add_row(f"… and {len(result.stale_files) - 20} more", "")
        console.print(stale_table)

        if requeue and not dry_run:
            _requeue_stale_sources(paths, result.stale_files)
        else:
            _hint(
                f"{len(result.stale_files)} collection file(s) have missing required fields. "
                "Run [bold]wiki migrate --requeue[/bold] to re-queue their sources for regeneration."
            )
    else:
        if result.already_current:
            console.print("[dim]No stale collection files found.[/dim]")


def add(
    path: Optional[Path] = typer.Argument(
        None, help="Specific file or directory to register. If omitted, scans all raw directories."
    ),
    recursive: bool = typer.Option(
        True,
        "--recursive",
        "-r",
        help="Recursively discover files if path is a directory.",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force re-generation of L1 Contexts even if they exist"
    ),
    no_sync: bool = typer.Option(
        False,
        "--no-sync",
        help="Skip the default sync repair/verification after add.",
    ),
) -> None:
    """Register sources and generate instant L1 Contexts (structural, no LLM).

    If a [path] is provided, only that file or directory is registered.
    If no path is provided, the Curator scans all source directories (02_Wiki,
    03_Notes, 04_Resources) for new or changed files.

    L1 is generated immediately from document structure without an LLM call.
    Run `wiki build` afterwards to extract L2 Atoms + L3 Concepts.
    """
    paths = _resolve_root_or_die()
    if not paths.state_db.exists():
        _err("Vault not fully initialized. Run `wiki init <path>` first.")
        raise typer.Exit(code=1)
    config = cfg.load_config(paths)

    console.print()
    if path:
        console.print(f"[dim]Registering source(s) from {path}...[/dim]")
    else:
        console.print("[dim]Scanning source directories for changes...[/dim]")
    console.print()

    # Phase 1: discover and register new/changed files
    if path:
        discovered = 0
        for file_to_add in ingest_raw.iter_addable_files(path, recursive=recursive):
            outcome = ingest_raw.add_file(paths, file_to_add)
            if outcome.ok:
                discovered += 1
            if outcome.result == ingest_raw.AddResult.ERROR:
                _err(outcome.message)
        removed = 0
        if discovered:
            _ok(f"Registered {discovered} new/changed file(s) from path.")
        else:
            console.print("[dim]No new or changed files found in specified path.[/dim]")
    else:
        discovered, removed = ingest_llm._auto_discover_pending(paths)

    if discovered or removed:
        msg = []
        if discovered:
            msg.append(f"{discovered} new/changed file(s)")
        if removed:
            msg.append(f"{removed} missing file(s) removed")
        _ok("Discovered " + ", ".join(msg) if discovered and not removed else ", ".join(msg))
    else:
        console.print("[dim]No new or changed files found.[/dim]")

    # Phase 2: generate L1 Summaries
    # --force: consider all sources (pending + curated) so deleted summary files
    # are regenerated even when the source content hasn't changed.
    with db.connect(paths.state_db) as conn:
        if force:
            candidate_rows = conn.execute(
                "SELECT id, relpath, content_hash, context_id, l1_status FROM sources "
                "WHERE status IN ('pending', 'force_pending', 'curated', 'error') ORDER BY id ASC"
            ).fetchall()
        else:
            # Always include curated sources too so we can detect missing summary files
            candidate_rows = conn.execute(
                "SELECT id, relpath, content_hash, context_id, l1_status FROM sources "
                "WHERE status IN ('pending', 'force_pending', 'curated') ORDER BY id ASC"
            ).fetchall()

    pending_rows = []
    if force and candidate_rows:
        ids = [row["id"] for row in candidate_rows]
        placeholders = ",".join("?" for _ in ids)
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "UPDATE sources SET status = 'force_pending', error_reason = NULL, "
                "l1_status = 'pending', l2_status = 'pending', "
                "l3_status = 'pending', l4_status = 'pending', layer_error = NULL "
                f"WHERE id IN ({placeholders})",
                ids,
            )
        pending_rows = list(candidate_rows)
    else:
        for row in candidate_rows:
            sid = row["context_id"]
            if not sid:
                pending_rows.append(row)
            else:
                # Smart heal: DB says done but context file was deleted — regenerate
                context_path = paths.contexts / f"{sid}.md"
                if not context_path.exists():
                    pending_rows.append(row)

    has_concepts = any(paths.concepts.glob("*.md")) if paths.concepts.exists() else False
    if not pending_rows and not force:
        if not discovered:
            if has_concepts:
                _hint("All sources have L1 Contexts. Run [bold]wiki build[/bold] for L2/L3/L4 Synthesis.")
            else:
                _hint("All sources have L1 Contexts. Run [bold]wiki build[/bold] to extract L2 Atoms + L3 Concepts.")
        return

    if pending_rows:
        console.print()
        source_label = "selected" if force else "pending"
        console.print(
            f"[dim]Generating L1 Contexts for {len(pending_rows)} {source_label} source(s)...[/dim]"
        )
        console.print()

    # L1 is structural-only — no LLM client is started here. The deeper
    # LLM-heavy L2/L3 extraction is a separate step (`wiki build`).
    summarized = 0
    for row in pending_rows:
        console.print(f"  [dim]summarizing[/dim] {row['relpath']}")
        db.set_source_layer_status(paths.state_db, row["id"], "l1", "running")
        context_id = ingest_raw.generate_l1_structural_context(
            paths,
            source_id=row["id"],
            relpath=row["relpath"],
            content_hash=row["content_hash"],
            existing_context_id=row["context_id"],
        )
        if context_id:
            _ok(f"  L1 [{context_id}] ← {row['relpath']}")
            summarized += 1
        else:
            if not force and row["l1_status"] == "done" and row["context_id"]:
                db.set_source_layer_status(
                    paths.state_db, row["id"], "l1", "done"
                )
                _warn(
                    f"  CTX projection repair failed for {row['relpath']}; "
                    "authoritative L1 DB state was preserved"
                )
            else:
                db.set_source_layer_status(
                    paths.state_db, row["id"], "l1", "error", error="summary_failed"
                )
                _warn(f"  Summary failed for {row['relpath']}")

    if summarized > 0:
        _refresh_search_index(paths, embed=False)
        _invalidate_latest_sync_report(paths, reason="add changed L1")
        if not no_sync:
            _run_sync_report_only(paths, config, reason="add")

    _maybe_auto_export(paths)

    console.print()
    _ok(f"L1 registration complete: {discovered} discovered, {summarized} summarized")
    _hint("Run [bold]wiki build[/bold] to extract L2 Atoms + L3 Concepts.")


def build(
    wait: bool = typer.Option(
        False,
        "--wait",
        help="Run L2/L3 synchronously now instead of queuing to the background worker.",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Rebuild L2/L3 even if they already exist."
    ),
    no_sync: bool = typer.Option(
        False, "--no-sync", help="Skip the default sync repair/verification after build."
    ),
) -> None:
    """Build L2 Atoms + L3 Concepts from registered L1 Contexts.

    `wiki add` registers sources and generates instant L1 (structural, no LLM).
    This command runs the deeper, LLM-heavy extraction. By default the work is
    queued to the background worker (processed when MCP is active, or run
    `wiki jobs run` to drain the queue now); use --wait to run it synchronously.
    """
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)

    # Collect L1-ready sources that still need L2/L3.
    with db.connect(paths.state_db) as conn:
        if force:
            rows = conn.execute(
                "SELECT id, relpath FROM sources WHERE l1_status = 'done' ORDER BY id ASC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, relpath FROM sources "
                "WHERE l1_status = 'done' "
                "AND (l2_status IN ('pending', 'error') OR l3_status IN ('pending', 'error')) "
                "ORDER BY id ASC"
            ).fetchall()
    source_ids = [int(r["id"]) for r in rows]

    if force:
        for sid in source_ids:
            db.set_source_layer_status(paths.state_db, sid, "l2", "pending")
            db.set_source_layer_status(paths.state_db, sid, "l3", "pending")

    if not source_ids and not force:
        if not wait:
            from .. import ingest_worker
            ingest_worker.enqueue_l3_global(paths, trigger="wiki_build")
            _ok("No pending L1/L2 sources. Queued global L3 Concept clustering.")
            _spawn_background_worker(paths)
        else:
            console.print()
            console.print("[dim]No pending sources. Running global L3 Concept clustering...[/dim]")
            client = _start_client(config)
            try:
                ingest_llm.run_l3_from_existing_atoms(paths, client, ingest_llm.IngestCallbacks)
                _ok("Global L3 clustering complete.")
            finally:
                client.close()
            # Ensure embeddings are current even when nothing new was built (item 14).
            _refresh_search_index(paths, embed=True)
            _maybe_auto_export(paths)
        return

    # Default: enqueue to the background worker (non-blocking).
    if not wait:
        from .. import ingest_worker

        job_ids = ingest_worker.enqueue_l2_l3_for_sources(
            paths, source_ids, trigger="wiki_build"
        )
        console.print()
        _ok(f"Queued {len(job_ids)} L2/L3 job(s).")
        _spawn_background_worker(paths)
        return

    # Synchronous build — the only path that starts an LLM client.
    console.print()
    console.print("[dim]Building L2 Atoms + L3 Concepts...[/dim]")
    console.print()
    client = _start_client(config)
    try:
        l3_results = ingest_llm.run_l1_to_l3(
            paths,
            client,
            lambda: CliIngestCallbacks(mode="batch"),
            mode="batch",
            auto_discover=False,
            force=force,
        )
        atoms_created = sum(r.fragments_created for r in l3_results if r.ok)
        atoms_updated = sum(r.fragments_updated for r in l3_results if r.ok)
        console.print()
        _ok(f"Build complete: {atoms_created} atoms created, {atoms_updated} updated")

        # Always refresh the vector index (item 14). update_index is
        # fingerprinted/idempotent, so this is cheap when embeddings are already
        # current, but it guarantees an already-built vault with stale/missing
        # embeddings never silently stays FTS5-only.
        _refresh_search_index(paths, embed=True)

        if atoms_created or atoms_updated:
            _invalidate_latest_sync_report(paths, reason="build changed L2-L3")

            # Progressively reinforce Curator persona from newly observed domains
            new_ctx_ids = [
                ch.id for r in l3_results if r.ok
                for ch in r.changes if ch.layer == consts.LAYER_L1
            ]
            if new_ctx_ids:
                new_domains = ingest_llm._collect_domains_from_contexts(paths, new_ctx_ids)
                _maybe_auto_evolve_curator_persona(paths, config, client, new_domains)

            if not no_sync:
                _run_sync_report_only(paths, config, reason="build")

        _hint("Ask a question with [bold]wiki query \"<your question>\"[/bold]")
    finally:
        if client is not None:
            client.close()

    _maybe_auto_export(paths)


def update(
    force: bool = typer.Option(
        False, "--force", "-f", help="Rebuild L1 Contexts and L2/L3 even if they already exist."
    ),
    no_sync: bool = typer.Option(
        False, "--no-sync", help="Skip the final deductive verification (sync) pass."
    ),
) -> None:
    """Bring the vault fully up to date in one step.

    Runs the whole ingest pipeline synchronously: discover + register sources and
    generate L1 (`add`), extract L2 Atoms + L3 Concepts and refresh the vector
    index (`build --wait`, which now always embeds), then verify the DAG and
    rebuild routing tables (`sync`). Use the individual `add` / `build` /
    `reindex` / `sync` commands for finer control.
    """
    paths = _resolve_root_or_die()
    console.print()
    console.print("[bold]Updating vault[/bold] — add → build → embed → sync")

    global _AUTO_EXPORT_DEFERRED
    _AUTO_EXPORT_DEFERRED = True
    try:
        # 1. Discover sources + instant L1 (defer verification to the final sync).
        add_cmd = _cli_override("add")
        if add_cmd is None:
            add_cmd = add
        add_cmd(path=None, recursive=True, force=force, no_sync=True)
        # 2. L2/L3 synchronously; build always refreshes embeddings idempotently.
        build_cmd = _cli_override("build")
        if build_cmd is None:
            build_cmd = build
        build_cmd(wait=True, force=force, no_sync=True)
        # 3. Single deductive verification + routing rebuild at the end. Run
        #    non-interactively so the one-shot pipeline never blocks on a prompt.
        if not no_sync:
            sync_cmd = _cli_override("sync")
            if sync_cmd is None:
                sync_cmd = sync
            sync_cmd(
                node_id=None,
                dry_run=False,
                reemit=False,
                no_fix=False,
                deep=False,
                no_deep=False,
                no_interactive=True,
                full=False,
                backward=False,
            )
    finally:
        _AUTO_EXPORT_DEFERRED = False

    _maybe_auto_export(paths)

    console.print()
    _ok("Vault up to date.")


def sync(
    node_id: Optional[str] = typer.Argument(
        None,
        help="Target node (CTX-/ATM-/CON-/SYN-). Omit for global verification.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Report gaps without fixing or rebuilding routing tables.",
    ),
    reemit: bool = typer.Option(
        False,
        "--reemit",
        help="Re-emit the derived L2/L3 markdown corpus (ATM/CON) from the "
             "authoritative DB records and refresh DB-native search. Use after DB corrections.",
    ),
    no_fix: bool = typer.Option(
        False,
        "--no-fix",
        help="Report-only mode: do not apply structural or logical repairs.",
    ),
    deep: bool = typer.Option(
        False,
        "--deep",
        help="Force full LLM logical verification (Mode C) even without manual changes.",
    ),
    no_deep: bool = typer.Option(
        False,
        "--no-deep",
        help="Skip LLM contradiction detection entirely (fast structural check only).",
    ),
    no_interactive: bool = typer.Option(
        False,
        "--no-interactive",
        help="Run contradiction detection but only report — do not prompt for resolution.",
    ),
    full: bool = typer.Option(
        False,
        "--full",
        help="Run the full structural + LLM verification path instead of the v0.2.1 incremental fast path.",
    ),
    backward: bool = typer.Option(
        False,
        "--backward",
        help="Run correction-aware verification/repair explicitly.",
    ),
) -> None:
    """Run deductive verification and rebuild routing tables.

    \b
    Mode A (no node_id): global reverse verification — traces L4 Synthesis back
    to L1 Contexts and flags any logical discontinuities.

    Mode B (node_id given): targeted bidirectional propagation — traces upstream
    to L1 and downstream to L4 Synthesis from the given node, flagging broken references.

    By default, wiki sync runs LLM contradiction detection and prompts for
    interactive resolution when a TTY is present. Use --no-deep to skip the
    LLM step entirely, or --no-interactive to report only without prompting.

    By default sync applies safe structural repairs and logical backprop repairs,
    then re-verifies the affected graph. Use --no-fix or --dry-run for report-only
    behavior.

    Finishes by rebuilding index.md, ledger.md, log.md, and overview.md unless
    --dry-run is given.
    """
    from .. import sync as sync_module

    class CliSyncCallbacks(sync_module.SyncCallbacks):
        def on_node_check(self, node_id: str):
            console.print(f"  [dim]Verifying {node_id}...[/dim]", end="\r")

        def on_node_repair(self, node_id: str, rebuilt_count: int = 0, message: Optional[str] = None):
            console.print(" " * 60, end="\r")
            detail = f" ({message})" if message else ""
            console.print(f"  [green]✓[/green] [bold]{node_id}[/bold] repaired{detail}.")

    cb = CliSyncCallbacks()

    paths = _resolve_root_or_die()
    db.init_db(paths.state_db)
    config = cfg.load_config(paths)
    console.print()
    console.rule("[bold cyan]Sync — Deductive Verification[/bold cyan]")

    # v0.3.1: re-emit the derived L2/L3 markdown corpus from the DB (DB is truth).
    if reemit:
        from ..pipeline import compile as _compile

        counts = _compile.reemit_projections(paths)
        _refresh_search_index(paths)
        _ok(f"Re-emitted derived corpus from DB: {counts['atoms']} atoms, "
            f"{counts['concepts']} concepts; search refreshed.")
        _maybe_auto_export(paths)
        return

    if not any([node_id, dry_run, no_fix, deep, no_deep, no_interactive, full, backward]):
        result = sync_module.run_incremental_sync(paths, client=None, config=config)
        changed_count = len(result.get("changed_nodes", []))
        affected_count = len(result.get("affected_nodes", []))
        if changed_count:
            console.print(
                f"[dim]Incremental sync: {changed_count} changed node(s), "
                f"{affected_count} downstream node(s) affected.[/dim]"
            )
            _hint("Run [bold]wiki sync --full[/bold] for LLM logical verification.")
        else:
            console.print("[dim]Incremental sync: no body-hash changes detected.[/dim]")
        _ok("Routing tables rebuilt (incremental).")
        # The DEFAULT sync path must publish the device snapshot too — only
        # hooking the full path made bare `wiki sync` silently skip the export
        # (PR #78 review).
        _maybe_auto_export(paths)
        return

    if backward:
        _warn("Direct generated-L4 backprop was removed in v0.3.1.")
        _hint("Use MCP [bold]curator_propose_correction[/bold] for reviewed corrections.")
        raise typer.Exit(code=1)

    # 0. Change detection (Manual changes)
    change_report = sync_module.scan_for_changes(paths)
    dirty_nodes = change_report.modified + change_report.new
    dirty_node_ids = [Path(ref).stem for ref in dirty_nodes]
    logical_target_ids = [node_id] if node_id else dirty_node_ids
    if change_report.total_changes() > 0:
        msg = f"[dim]Changes detected: {len(change_report.modified)} modified, {len(change_report.new)} new, {len(change_report.deleted)} deleted[/dim]"
        console.print(msg)
    else:
        console.print(f"[dim]No manual changes detected (cached {change_report.unchanged_count} pages)[/dim]")

    # 1. Full Static Verification (Always runs for everyone)
    if node_id:
        console.print(f"[dim]Mode B: targeted structural verification for {node_id}...[/dim]")
        gaps = sync_module.run_mode_b(paths, node_id, callbacks=cb)
    else:
        console.print("[dim]Mode A: global structural verification (L4 → L1)...[/dim]")
        gaps = sync_module.run_mode_a(paths, callbacks=cb)
    
    console.print("[dim]Fast structural lint verification...[/dim]")
    structural_report = lint_module.run_lint(paths, deep=False, client=None, progress_callback=cb.on_node_check)
    console.print(" " * 60, end="\r")

    should_fix = not no_fix and not dry_run
    client = None if no_deep else _start_client(config)
    
    try:
        structural_fixed = 0
        rebuilt = 0
        if should_fix:
            # Backfill §26.2b loss records onto spans stored before the check
            # existed. Deterministic, idempotent, no provider call — it only
            # re-derives a verdict from text already in the DB, which is why it
            # belongs with the static repairs rather than behind its own command.
            from ..pipeline.source_spans import backfill_span_loss

            loss_backfilled = backfill_span_loss(paths.state_db)
            if loss_backfilled:
                _ok(
                    f"Recorded {loss_backfilled} unreadable region(s) that predate "
                    f"the extraction-loss check."
                )

            console.print("[dim]Applying safe structural lint repairs...[/dim]")
            # Static repairs (deterministic)
            fixed_count = lint_module.apply_fixes(paths, structural_report.issues, progress_callback=cb.on_node_check)
            gap_fixed = sync_module.repair_structural_gaps(paths, gaps, callbacks=cb)
            nested_fixed = sync_module.repair_nested_frontmatter(paths, callbacks=cb)
            
            structural_fixed = fixed_count + gap_fixed + nested_fixed
            if structural_fixed > 0:
                structural_report = lint_module.run_lint(paths, deep=False, client=None, progress_callback=cb.on_node_check)
                # Any node that was fixed is now also 'dirty' for deep verification
                # (Optional optimization: only if we think structural fix needs logical re-verify)

            # 2. Targeted LLM-based repairs (only for dirty/requested nodes)
            target_pages = []
            if node_id:
                subdir = sync_module._subdir_for_id(node_id)
                if subdir:
                    relpath = f"{subdir}/{node_id}.md"
                    if relpath not in target_pages:
                        target_pages.append(relpath)
            else:
                target_pages = list(dirty_nodes)
                
            if client is not None:
                llm_fixed = lint_module.apply_llm_fixes(
                    paths, structural_report.issues, client,
                    progress_callback=cb.on_node_check,
                    limit_to=target_pages
                )
                structural_fixed += llm_fixed
            
            if structural_fixed > 0:
                structural_report = lint_module.run_lint(paths, deep=False, client=None, progress_callback=cb.on_node_check)
                structural_report.auto_fixed = structural_fixed
                gaps = sync_module.run_mode_b(paths, node_id) if node_id else sync_module.run_mode_a(paths, callbacks=cb)
                console.print(" " * 60, end="\r")
                _ok(f"{structural_fixed} safe structural lint issue(s) fixed.")

        structural_issues = structural_report.errors + structural_report.warnings
        needs_review = structural_report.needs_review
        blocked_node_ids = _sync_blocked_node_ids(structural_report)

        # Gate both deep lint and Mode C on whether there are dirty nodes or --deep.
        run_llm_verification = (not no_deep) and (bool(logical_target_ids) or deep)
        # Contradiction detection runs by default unless --no-deep
        run_contradiction_check = not no_deep
        # Interactive mode: prompt for resolution when TTY present and --no-interactive not set
        run_interactive = run_contradiction_check and not no_interactive and _interactive()

        # 3. Targeted Deep Lint Verification (LLM contradiction check)
        contradiction_issues: list = []
        if run_contradiction_check:
            try:
                target_pages = []
                if node_id:
                    subdir = sync_module._subdir_for_id(node_id)
                    if subdir:
                        relpath = f"{subdir}/{node_id}.md"
                        if relpath not in target_pages:
                            target_pages.append(relpath)
                else:
                    target_pages = list(dirty_nodes)

                deep_report = lint_module.run_lint(
                    paths, deep=True, client=client,
                    progress_callback=cb.on_node_check,
                    # When run_llm_verification is active, scan all; else scope to dirty
                    limit_to=target_pages if not (run_llm_verification or deep) else None,
                )
                console.print(" " * 60, end="\r")
                from ..lint import CheckId as _CheckId
                for issue in deep_report.issues:
                    if issue not in structural_report.issues:
                        structural_report.issues.append(issue)
                    if issue.check == _CheckId.CONTRADICTION:
                        contradiction_issues.append(issue)
                structural_issues = structural_report.errors + structural_report.warnings
                needs_review = structural_report.needs_review
                blocked_node_ids = _sync_blocked_node_ids(structural_report)
            except Exception as e:
                _warn(f"Contradiction/equivalence scan unavailable: {e}")

        # 3b. Interactive contradiction resolution wizard
        if run_interactive and contradiction_issues:
            _contradiction_resolution_wizard(paths, client, contradiction_issues)
        if structural_issues:
            console.print()
            _warn(
                f"{len(structural_issues)} structural lint issue(s) detected "
                "(safe repairs run by default; use [bold]wiki sync[/bold] again after review):"
            )
            for issue in structural_issues[:20]:
                console.print(
                    f"  [yellow]•[/yellow] [{issue.severity.value}] "
                    f"[cyan]{issue.page}[/cyan]: {issue.message}"
                )
            if len(structural_issues) > 20:
                console.print(f"  [dim]...and {len(structural_issues) - 20} more[/dim]")
            if needs_review:
                _warn(f"{len(needs_review)} issue(s) need review; unresolved links were not deleted.")
            if blocked_node_ids:
                _warn(
                    f"{len(blocked_node_ids)} node(s) have structural review items; "
                    "related logical checks will be skipped."
                )

        structural_gaps = list(gaps)
        if not run_llm_verification:
            console.print(
                "[dim]Mode C: skipped — no manual changes detected. "
                "Use [bold]--deep[/bold] to force full LLM verification.[/dim]"
            )
            logic_gaps: list = []
            logical_fixed = 0
            rebuilt = 0
        else:  # run_llm_verification
            console.print("[dim]Mode C: LLM logical deduction verification...[/dim]")

            # --- GENERATIVE BACKPROP INTERCEPT ---
            if backward and should_fix:
                # To do backprop, we first need to know what the gaps are.
                # Mode C normally runs inside repair_logical_gaps, but we can run a quick pass first
                # or just run it, collect gaps, do backprop, and then run repair.
                console.print("[bold cyan]⮌ Executing Multi-Agent Generative Backpropagation...[/bold cyan]")
                initial_gaps = sync_module.run_mode_c(
                    paths, client, blocked_node_ids=blocked_node_ids, target_node_ids=logical_target_ids if not deep else None, callbacks=cb
                )
                if initial_gaps:
                    new_atoms = sync_module.apply_generative_backprop(paths, client, initial_gaps, callbacks=cb)
                    if new_atoms:
                        console.print(f"[dim]  → synthesized {len(new_atoms)} new L2 Atom(s).[/dim]")
                        # We must re-verify because the DAG changed
                        console.print("[dim]Re-verifying logical gaps after Generative Backprop...[/dim]")

            if should_fix:
                logic_gaps, repair_result = sync_module.repair_logical_gaps(
                    paths,
                    client,
                    blocked_node_ids=blocked_node_ids,
                    target_node_ids=logical_target_ids if not deep else None,
                    max_iterations=2,
                    callbacks=cb,
                )
                console.print(" " * 60, end="\r")
                rebuilt = repair_result.rebuilt_downstream
                logical_fixed = repair_result.fixed
                if logical_fixed or rebuilt:
                    _ok(
                        f"Logical sync repaired {logical_fixed} node(s) and rebuilt "
                        f"{rebuilt} downstream page(s)."
                    )
            else:
                logic_gaps = sync_module.run_mode_c(
                    paths,
                    client,
                    blocked_node_ids=blocked_node_ids,
                    target_node_ids=logical_target_ids if not deep else None,
                    callbacks=cb,
                )
                console.print(" " * 60, end="\r")
                logical_fixed = 0
        gaps = structural_gaps + logic_gaps
        fixed_for_report = int(getattr(structural_report, "auto_fixed", 0) or 0) + logical_fixed
        if not dry_run:
            _write_latest_sync_report(
                paths,
                reason="sync" if should_fix else "sync --no-fix",
                structural_report=structural_report,
                structural_gaps=structural_gaps,
                logic_gaps=logic_gaps,
                fixed=fixed_for_report,
                rebuilt=rebuilt,
            )

        if gaps:
            console.print()
            _warn(f"{len(gaps)} verification gap(s) remain:")
            for gap in gaps:
                console.print(f"  [yellow]•[/yellow] [{gap.layer}] [bold]{gap.node_id}[/bold]: {gap.message}")
                if gap.reasoning:
                    console.print(f"    [dim]{gap.reasoning}[/dim]")
            if not dry_run:
                _mark_layer_status_from_sync_gaps(paths, gaps)
                _warn("Layer status updated from remaining sync gaps.")
        else:
            console.print()
            if structural_issues:
                _warn("No logical gaps detected, but structural lint issues remain.")
            else:
                if not dry_run:
                    _mark_clean_sync_status(paths)
                _ok("No logical or structural gaps detected.")

        if gaps and not dry_run:
            _hint("Review remaining gaps, then rerun [bold]wiki sync[/bold].")
    finally:
        if client is not None:
            client.close()

    if not dry_run:
        # Update page hashes in DB for next fast sync
        sync_module.update_all_page_hashes(paths)
        sync_module.finalize_routing_tables(paths)
        _ok("Routing tables rebuilt (index.md, ledger.md, log.md, overview.md).")
        _maybe_auto_export(paths)
    else:
        _hint("--dry-run: routing tables not modified.")


def query(
    question: Optional[str] = typer.Argument(
        None,
        help="The question to ask the wiki. If omitted, enters interactive chat mode (press Enter on empty line to exit).",
    ),
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
        0.6, "--min-score", help="Drop hits below this score."
    ),
    no_rerank: bool = typer.Option(
        False, "--no-rerank", help="Skip LLM reranking in hybrid mode."
    ),
    scope: str = typer.Option(
        "all",
        "--scope",
        help="Restrict to a single Curator layer: all | contexts | atoms | concepts | synthesis.",
    ),
    route: str = typer.Option(
        "auto",
        "--route",
        help="v0.3.1 curation-native route: auto | local | global | explore | "
             "source-section. Routes through the QueryOrchestrator "
             "(DB graph + DB-native search) with a QTR trace.",
    ),
    no_intent_classify: bool = typer.Option(
        False,
        "--no-intent-classify",
        help="Skip intent classification step (saves ~3 sec per query).",
    ),
    workspace: Optional[Path] = typer.Option(
        None,
        "--workspace",
        help="Path to a workspace directory containing curate.yml. Defaults to WORKSPACE_PATH or current workspace.",
    ),
) -> None:
    """Ask a question: search the wiki, synthesize an answer with citations.

    Without an argument, enters interactive chat mode. Type an empty line to exit.
    Within a session you can say 'save to wiki' / 'save' etc. to promote the
    last answer into 02_Wiki under an auto-determined category folder.

    Querying never writes to the DAG. Sessionless Q&A returns an answer + trace
    only; durable artifacts come from an explicit promotion to 02_Wiki. To feed
    a correction back into the graph, use the insight lifecycle
    ([bold]wiki insights[/bold]) or [bold]wiki sync --backward[/bold].

    The query pipeline:
      1. Translate question to English (for non-English input)
      2. QueryOrchestrator routing over DB graph + DB-native search
      3. Synthesize a cited answer with a QTR trace
      4. Optionally promote to 02_Wiki
    """
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    workspace = _resolve_curate_workspace(workspace)
    from ..curate_yml import CurationPolicyError, resolve_curate_policy

    # Reject an invalid selected workspace before starting a provider or entering
    # the REPL. ContextService resolves it again at execution time so a file that
    # changes after this UX preflight still cannot bypass the authoritative gate.
    try:
        resolve_curate_policy(workspace)
    except CurationPolicyError as exc:
        _err(f"Query configuration failed: {exc}")
        raise typer.Exit(code=1) from None

    # Resolve search mode shortcuts
    if lex:
        mode = "lex"
    elif vec:
        mode = "vec"
    if mode not in ("hybrid", "lex", "vec"):
        _err(f"Invalid mode '{mode}'. Use hybrid, lex, or vec.")
        raise typer.Exit(code=1)

    # Warn on flags that are not yet wired to the QueryOrchestrator.
    # --lex/--vec mutate `mode` before this point, so check them explicitly
    # and only report --mode when neither shortcut was used.
    _noop_used: list[str] = []
    if lex:
        _noop_used.append("--lex")
    elif vec:
        _noop_used.append("--vec")
    elif mode != "hybrid":
        _noop_used.append("--mode")
    if limit != 8:
        _noop_used.append("--limit")
    if min_score != 0.6:
        _noop_used.append("--min-score")
    if no_rerank:
        _noop_used.append("--no-rerank")
    if scope != "all":
        _noop_used.append("--scope")
    if no_intent_classify:
        _noop_used.append("--no-intent-classify")
    if _noop_used:
        _warn(
            f"{', '.join(_noop_used)}: these flags are not yet wired to the "
            "QueryOrchestrator and will have no effect on retrieval."
        )

    if scope not in ("all", "contexts", "atoms", "concepts", "synthesis"):
        _err(
            f"Invalid scope '{scope}'. Use all, contexts, atoms, concepts, or synthesis."
        )
        raise typer.Exit(code=1)

    collection_pages = 0
    for layer_dir in (paths.contexts, paths.atoms, paths.concepts, paths.synthesis):
        if layer_dir.exists():
            collection_pages += sum(
                1 for p in layer_dir.glob("*.md") if not p.name.startswith(".")
            )
    if collection_pages == 0:
        _err("Curator collections are empty.")
        _hint("Run [bold]wiki add[/bold] then [bold]wiki build[/bold] first.")
        raise typer.Exit(code=1)

    console.print()
    console.print(f"[dim]{describe_backend(config)}…[/dim]")
    client = _start_client(config)

    run_kwargs = dict(
        mode=mode,
        limit=limit,
        min_score=min_score,
        rerank=not no_rerank,
        scope=scope,
        classify_intent_first=not no_intent_classify,
        workspace_path=str(workspace) if workspace is not None else None,
        route=route,
    )

    callbacks = CliQueryCallbacks()
    had_failure = False

    try:
        had_failure = _run_query_repl(
            paths, client, callbacks, run_kwargs,
            initial_question=question,
        )
    except CurationPolicyError as exc:
        _err(f"Query configuration failed: {exc}")
        raise typer.Exit(code=1) from None
    finally:
        client.close()
    if had_failure:
        raise typer.Exit(code=1)


def reindex(
    embed: bool = typer.Option(
        False, "--embed", help="Also (re)generate chunk embeddings for vector search."
    ),
) -> None:
    """Force a full rebuild of the DB-native search index.

    Normally this runs automatically after `wiki build`, so you only need this
    if the index gets out of sync. Pass `--embed` to also generate vector
    embeddings (requires a configured embedder, e.g. Ollama `bge-m3`); without it
    search runs FTS5-only until embeddings exist.
    """
    from ..retrieval import embedding, materializer, providers

    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    search_config = config.get("search", {})

    console.print()
    console.print("[dim]Rebuilding DB-native search index...[/dim]")
    try:
        result = materializer.materialize_search_documents(paths.state_db, search_config)
        embedding_summary = ""
        if embed:
            identity = providers.embedding_identity(search_config)
            if identity is not None:
                provider, model = identity
                total, ready = embedding.current_embedding_coverage(
                    paths.state_db, provider, model
                )
            else:
                total, ready = 0, -1
            ollama_host = (config.get("llm", {}).get("ollama", {}) or {}).get("host")
            if total == ready and providers.embedding_identity_available(
                search_config,
                ollama_host=ollama_host,
            ):
                embedding_summary = f", 0 new embeddings, {ready} reused"
            else:
                embedder = providers.build_embedder(search_config, ollama_host=ollama_host)
                emb = embedding.embed_corpus(paths.state_db, embedder)
                embedding_summary = (
                    f", {emb.embedded} new embeddings, {emb.skipped} reused"
                )
                if emb.degraded or emb.warning:
                    _warn(emb.warning or "vector embeddings unavailable (FTS5-only)")
        _ok(
            "Search index rebuilt: "
            f"{result.documents} documents, {result.chunks} chunks"
            f"{embedding_summary}"
        )
    except Exception as e:
        _err(f"Index rebuild failed: {e}")
        raise typer.Exit(code=1)


def lint(
    deep: bool = typer.Option(
        False,
        "--deep",
        help="Run LLM-powered contradiction detection (slower, requires LLM).",
    ),
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Auto-fix safe structural issues; unresolved broken links are kept for review.",
    ),
    save: bool = typer.Option(
        False,
        "--save",
        help="Save the report as .curator/Collections/04_Synthesis/SYN-lint-YYYY-MM-DD.md",
    ),
    max_pairs: int = typer.Option(
        10,
        "--max-pairs",
        help="Max page pairs to check in --deep mode.",
    ),
    refresh_manifests: bool = typer.Option(
        False,
        "--refresh-manifests",
        help="Rebuild index/overview/ledger and append a log entry before linting (writes to the vault).",
    ),
) -> None:
    """Lint the wiki for broken links, orphans, missing pages, and more.

    Fast checks (default) run entirely in Python and finish in seconds.
    Use --deep to also scan page pairs for contradictions (requires LLM).
    Plain lint is read-only; use --fix/--save/--refresh-manifests for mutations.
    """
    paths = _resolve_root_or_die()

    if fix or save or refresh_manifests:
        from .. import page_writer as _pw
        from .. import ingest_llm as _ingest
        today = _pw.today_iso()
        _pw.rebuild_index(paths, today)
        _ingest.update_overview(paths)
        _ingest.update_ledger(paths)
        _pw.append_log_entry(
            paths,
            today,
            "lint",
            "system",
            ["Ran wiki lint and updated all manifests"],
        )

    # Start LLM client for --deep and/or --fix
    client = None
    if deep or fix:
        config = cfg.load_config(paths)
        console.print(f"[dim]{describe_backend(config)}…[/dim]")
        try:
            client = _start_client(config)
        except Exception as e:
            if deep:
                raise
            console.print(f"[yellow]! LLM unavailable ({e}). --fix will use simple repairs only.[/yellow]")

    try:
        console.print()
        if deep:
            console.print("[dim]Running fast checks + contradiction detection…[/dim]")
        else:
            console.print("[dim]Running fast checks…[/dim]")

        def _lint_cb(node_id: str):
            console.print(f"  [dim]Linting {node_id}...[/dim]", end="\r")

        report = lint_module.run_lint(paths, deep=deep, client=client, progress_callback=_lint_cb, apply_flags=fix)
        console.print(" " * 60, end="\r")

        # Auto-fix: LLM relinking first, then deterministic non-destructive fixes.
        if fix:
            llm_fixed = 0
            if client is not None:
                console.print("[dim]Running LLM-based safe link reconnection…[/dim]")
                llm_fixed = lint_module.apply_llm_fixes(paths, report.issues, client)
                if llm_fixed > 0:
                    report = lint_module.run_lint(paths, deep=False, client=None, progress_callback=_lint_cb)
                    console.print(" " * 60, end="\r")

            fixed_count = lint_module.apply_fixes(paths, report.issues)
            total_fixed = llm_fixed + fixed_count
            report.auto_fixed = total_fixed
            if fixed_count > 0:
                report = lint_module.run_lint(paths, deep=False, client=None, progress_callback=_lint_cb)
                console.print(" " * 60, end="\r")
                report.auto_fixed = total_fixed

    finally:
        if client is not None:
            client.close()

    _render_lint_report_terminal(report)

    # Save as an L4 Synthesis page
    if save:
        import uuid as _uuid
        today = lint_module.page_writer.today_iso()
        cur_id = f"lint-{today}-{_uuid.uuid4().hex[:4]}"
        reports_dir = paths.internal / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        target_path = reports_dir / f"{cur_id}.md"
        content = lint_module.render_report_markdown(report, paths)
        target_path.write_text(content, encoding="utf-8")
        console.print()
        _ok(f"Saved report to [cyan].curator/reports/{cur_id}.md[/cyan]")

    # Exit code: 1 if there are errors, 0 otherwise (for CI use)
    if report.errors:
        raise typer.Exit(code=1)


def register_core_commands(root_app: typer.Typer) -> None:
    root_app.command('reset')(reset)
    root_app.command()(version)
    root_app.command()(init)
    root_app.command()(status)
    root_app.command('migrate')(migrate_vault)
    root_app.command()(add)
    root_app.command()(build)
    root_app.command()(update)
    root_app.command()(sync)
    root_app.command()(query)
    root_app.command()(reindex)
    root_app.command('lint')(lint)
