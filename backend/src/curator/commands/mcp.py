# ruff: noqa: F403,F405
# mypy: disable-error-code=name-defined
"""Mcp commands for the `wiki` CLI."""

from __future__ import annotations

from .common import *

mcp_app = typer.Typer(
    name="mcp",
    help="Run the Incurator MCP server or print client configuration snippets.",
    # NOT `no_args_is_help=True`: Typer applies that BEFORE the callback runs, so
    # a bare `wiki mcp` exited 2 with a usage screen instead of serving — which
    # is exactly how every MCP client is documented to launch it
    # (`"command": "wiki", "args": ["mcp"]`). The server was therefore
    # unstartable by any client since v0.34.0. `mcp_callback` already prints
    # that same usage text when stdin is a TTY, so interactive users still get
    # help; a piped client gets a server.
    add_completion=False,
    rich_markup_mode="rich",
)

@mcp_app.callback(invoke_without_command=True)
def mcp_callback(ctx: typer.Context) -> None:
    """Default `wiki mcp` (no subcommand) starts the stdio server.

    `invoke_without_command=True` is required for that to happen at all: without
    it Typer rejects a bare `wiki mcp` with "Missing command" before this
    function runs, so the server could never start from the documented client
    config (`"args": ["mcp"]`).
    """
    if ctx.invoked_subcommand is not None:
        return

    # Guard: running interactively from a terminal is almost certainly a mistake.
    # Print usage instead of starting a raw JSON-RPC server into a TTY.
    import sys as _sys
    if _sys.stdin.isatty():
        console.print("[bold]wiki mcp[/bold] — Incurator MCP server (stdio transport)")
        console.print()
        console.print("This command is meant to be started by an MCP client (Claude Code,")
        console.print("Antigravity CLI, etc.), not run directly in a terminal.")
        console.print()
        console.print("[bold]Setup:[/bold]")
        console.print("  [dim]wiki mcp install[/dim]   — print config snippet to paste into your MCP client")
        console.print("  [dim]wiki mcp connect --agent claude-code --workspace <path>[/dim]")
        console.print()
        console.print("[bold]Manual start (for debugging):[/bold]")
        console.print("  [dim]VAULT_ROOT=<vault> wiki mcp 2>/dev/null[/dim]   — pipe output to an MCP client")
        raise typer.Exit(0)

    paths = _resolve_root_or_die()
    # Pin VAULT_ROOT so the server picks up the same vault even if MCP clients
    # spawn it from an unrelated cwd.
    import os as _os
    _os.environ["VAULT_ROOT"] = str(paths.root)
    try:
        from ..mcp import server as mcp_server
    except ImportError as e:
        _err(str(e))
        _hint(
            "Run [bold]./setup.sh[/bold] from the repository root — it installs "
            "the mcp extra into [cyan]<repo>/.venv[/cyan]."
        )
        raise typer.Exit(code=1)
    mcp_server.serve_stdio()


@mcp_app.command("connect")
def mcp_connect_cmd(
    agent: str = typer.Option(
        ...,
        "--agent",
        help="Agent runtime: codex | claude-code | antigravity.",
    ),
    workspace: Path = typer.Option(
        ...,
        "--workspace",
        help="Workspace directory to connect to incurator MCP.",
    ),
    force_curate: bool = typer.Option(
        False,
        "--force-curate",
        help="Overwrite curate.yml from template values.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes", "-y",
        help="Accept template defaults without prompting.",
    ),
    project: Optional[str] = typer.Option(None, "--project", help="curate.yml project id."),
    description: Optional[str] = typer.Option(None, "--description", help="curate.yml description."),
    min_confidence: float = typer.Option(0.60, "--min-confidence", help="curate.yml confidence floor."),
) -> None:
    """Prepare workspace rules and print an MCP snippet for one agent runtime."""
    try:
        agent = normalize_agent(agent)
    except ValueError:
        _err("Invalid --agent. Use: codex | claude-code | antigravity")
        raise typer.Exit(code=1)
    if agent == "none":
        _err("Invalid --agent. Use: codex | claude-code | antigravity")
        raise typer.Exit(code=1)

    paths = _resolve_root_or_die()
    workspace = workspace.expanduser().resolve()
    data = _collect_curate_template_data(
        path=workspace,
        vault_root=paths.root,
        yes=yes,
        project=project,
        description=description,
        min_confidence=min_confidence,
    )
    result = prepare_workspace(
        vault_root=paths.root,
        workspace=workspace,
        agent=agent,
        curate_data=data,
        force_curate=force_curate,
        install_rules=True,
    )

    _print_workspace_prepare_result(result)
    console.print()
    console.print(
        Panel.fit(
            f"[bold]incurator MCP connect[/bold]\n"
            f"[dim]agent: {agent}\n"
            f"vault: {paths.root}\n"
            f"workspace: {workspace}[/dim]",
            border_style="cyan",
        )
    )
    console.print(render_mcp_snippet(vault_root=paths.root, workspace=workspace))
    console.print()
    _hint("Paste this into the selected agent's MCP settings, then restart the agent.")


@mcp_app.command("install")
def mcp_install_cmd(
    target: str = typer.Argument(
        "all",
        help="claude | antigravity | obsidian | all. `obsidian` WRITES; others print.",
    ),
) -> None:
    """Print MCP config snippets, or register the server for the Obsidian plugin.

    `claude` / `antigravity` / `all` only PRINT a snippet to paste manually.

    `obsidian` is different and does WRITE: the plugin's `data.json` is owned by
    Obsidian rather than hand-edited, and without an entry there the sidechat has
    no curator tools at all — both the tool injection and the system-prompt
    section describing them are gated on a configured server whose name contains
    "incurator". The write is idempotent and preserves every other setting.
    """
    paths = _resolve_root_or_die()
    try:
        from ..mcp import server as mcp_server
    except ImportError as e:
        _err(str(e))
        _hint(
            "Run [bold]./setup.sh[/bold] from the repository root — it installs "
            "the mcp extra into [cyan]<repo>/.venv[/cyan]."
        )
        raise typer.Exit(code=1)

    snippets = mcp_server.render_install_snippets(paths)
    target = target.lower()
    if target not in (consts.CLOUD_CLAUDE, consts.CLOUD_ANTIGRAVITY, "obsidian", "all"):
        _err(f"Unknown target '{target}'. Use claude | antigravity | obsidian | all.")
        raise typer.Exit(code=1)

    if target == "obsidian":
        try:
            report = mcp_server.install_obsidian_mcp_server(paths)
        except (FileNotFoundError, ValueError) as e:
            _err(str(e))
            raise typer.Exit(code=1)
        console.print()
        console.rule("[bold]Obsidian plugin[/bold]")
        verb = {
            "added": "Registered",
            "updated": "Updated",
            "unchanged": "Already registered",
        }[report["action"]]
        _ok(f"{verb} the incurator MCP server in [cyan]{report['path']}[/cyan]")
        console.print(f"  command: [cyan]{report['entry']['command']}[/cyan] mcp")
        console.print(f"  VAULT_ROOT: [cyan]{report['entry']['env']['VAULT_ROOT']}[/cyan]")
        console.print()
        _hint(report["warning"])
        return

    console.print()
    console.print(
        Panel.fit(
            f"[bold]incurator MCP install[/bold]\n[dim]vault: {paths.root}[/dim]",
            border_style="cyan",
        )
    )

    if target in (consts.CLOUD_CLAUDE, "all"):
        console.print()
        console.rule("[bold]Claude Code / Desktop[/bold]")
        console.print(
            "Paste into one of:\n"
            "  • Claude Code:    [cyan]~/.claude/settings.json[/cyan]\n"
            "  • Claude Desktop: [cyan]~/Library/Application Support/Claude/claude_desktop_config.json[/cyan] (macOS)\n"
            "                    [cyan]%APPDATA%\\Claude\\claude_desktop_config.json[/cyan] (Windows)"
        )
        console.print()
        console.print(snippets[consts.CLOUD_CLAUDE])

    if target in (consts.CLOUD_ANTIGRAVITY, "all"):
        console.print()
        console.rule("[bold]Antigravity[/bold]")
        console.print(
            "Paste into:\n"
            "  • [cyan]~/.antigravity/settings.json[/cyan]"
        )
        console.print()
        console.print(snippets[consts.CLOUD_ANTIGRAVITY])

    console.print()
    _hint(
        "If your client merges with existing `mcpServers`, add only the "
        "[bold]incurator[/bold] entry."
    )
    _hint("After pasting, restart the agent so it reloads MCP config.")

