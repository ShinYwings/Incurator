# ruff: noqa: F403,F405
# mypy: disable-error-code=name-defined
"""Workspace commands for the `wiki` CLI."""

from __future__ import annotations

from .common import *

workspace_app = typer.Typer(
    name="workspace",
    help="Manage workspace curate.yml Knowledge Requirement Specifications.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

testbed_app = typer.Typer(
    name="testbed",
    help="[Dev Only] Manage development testbed environments and scenarios.",
    hidden=True,
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

@workspace_app.command("init")
def workspace_init(
    path: Path = typer.Argument(..., help="Path for the new workspace directory."),
    agent: str = typer.Option(
        consts.BACKEND_CLAUDE_CODE,
        "--agent",
        help="Agent runtime: codex | claude-code | antigravity | none.",
    ),
    no_rules: bool = typer.Option(
        False,
        "--no-rules",
        help="Only create/sync curate.yml; do not install agent rules.",
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
    """Scaffold or sync a workspace with curate.yml and agent rules."""
    path = path.expanduser().resolve()
    paths = _resolve_root_or_die(hint_path=path)
    project_name = project or default_project_name(path)

    # 1. Interactive agent selection (which agent rules to install)
    _agent_explicit = agent != consts.BACKEND_CLAUDE_CODE
    if not yes and _interactive() and not _agent_explicit:
        agent = typer.prompt(
            "Agent runtime",
            default=consts.BACKEND_CLAUDE_CODE,
            prompt_suffix=" [claude-code/codex/antigravity/none]: ",
        ).strip() or consts.BACKEND_CLAUDE_CODE

    try:
        agent = normalize_agent(agent)
    except ValueError:
        _err("Invalid --agent. Use: codex | claude-code | antigravity | none")
        raise typer.Exit(code=1)

    # 1b. Show scenario-appropriate intro message
    _scenario = detect_workspace_scenario(path, agent)
    if _scenario == "agent-only":
        console.print()
        console.print(
            f"[cyan]Found existing [bold]{agent}[/bold] setup.[/cyan] "
            "Integrating Curator knowledge navigation..."
        )
    elif _scenario == "full":
        console.print()
        console.print("[dim]Curator is already integrated here. Updating rules to latest templates.[/dim]")

    # 1c. Agent-only: try LLM-assisted integration of Curator into existing rule file
    _llm_integrated = False
    if _scenario == "agent-only" and not no_rules and agent != "none":
        _llm_integrated = _try_llm_rule_integration(
            path=path,
            agent=agent,
            paths=paths,
            yes=yes,
        )

    # 2. Artist Persona wizard → collects domain, description, topics
    #    Results populate curate.yml so manual prompts are not needed.
    persona: dict | None = None
    if not yes and _interactive():
        console.print()
        console.print("[bold]Artist Persona Setup[/bold]")
        console.print("[dim]The wizard will configure both the persona and curate.yml for this workspace.[/dim]")
        _ws_config = cfg.load_config(paths)
        try:
            _ws_client = _start_client(_ws_config)
        except (Exception, SystemExit) as _llm_exc:
            _warn(f"Could not start LLM for persona wizard: {_llm_exc}")
            _hint("Falling back to manual prompts.")
            _ws_client = None
        if _ws_client is not None:
            try:
                persona = _run_artist_persona_wizard(_ws_client, project_name)
            except (Exception, SystemExit) as _exc:
                _warn(f"Persona wizard failed: {_exc}")
                _hint("Falling back to manual prompts.")
            finally:
                _ws_client.close()

    # 3. Build curate.yml data — from persona output or manual prompts
    if persona is not None:
        data = CurateTemplateData(
            project=project_name,
            description=persona.get("goal", f"Knowledge workspace for {path.name}"),
            min_confidence=persona.get("confidence", {}).get("low_threshold", min_confidence),
        )
        # Source selection is not part of the persona wizard — ask separately
        if not yes and _interactive():
            data.include_patterns = _ask_source_dirs(paths.root)
    else:
        # Fallback: manual prompts (--yes or LLM unavailable)
        data = _collect_curate_template_data(
            path=path,
            vault_root=paths.root,
            yes=yes,
            project=project,
            description=description,
            min_confidence=min_confidence,
        )

    # 4. Scaffold workspace files
    result = prepare_workspace(
        vault_root=paths.root,
        workspace=path,
        agent=agent,
        curate_data=data,
        force_curate=force_curate,
        install_rules=not no_rules,
        install_managed_block=not _llm_integrated,
    )
    _print_workspace_prepare_result(result)

    # 5. Save persona into curate.yml
    if persona is not None:
        try:
            import yaml as _yaml_ws
            import datetime as _dt_ws
            _curate_file = path / consts.FILE_CURATE_YML
            _raw_curate = _yaml_ws.safe_load(_curate_file.read_text(encoding="utf-8")) or {}
            persona["updated_at"] = _dt_ws.datetime.now().isoformat()
            _raw_curate["persona"] = persona
            _curate_file.write_text(
                _yaml_ws.dump(_raw_curate, sort_keys=False, default_flow_style=False, allow_unicode=True),
                encoding="utf-8",
            )
            _ok("Artist persona saved to curate.yml")
        except Exception as _save_exc:
            _warn(f"Could not save persona: {_save_exc}")

    # 6. Auto-register MCP settings for Claude Code agents
    if agent == consts.BACKEND_CLAUDE_CODE:
        try:
            from ..workspace.provisioner import merge_mcp_settings
            settings_path = paths.root / ".claude" / "settings.json"
            merge_mcp_settings(settings_path, vault_root=paths.root, workspace=path)
            console.print("  [green]✓[/green] MCP settings updated at [dim].claude/settings.json[/dim]")
        except Exception as e:
            console.print(f"  [yellow]Warning:[/yellow] Could not update .claude/settings.json: {e}")
            console.print(f"  Set WORKSPACE_PATH={path} before running the MCP server to enable scoped search.")
    else:
        console.print(f"  Set WORKSPACE_PATH={path} before running the MCP server to enable scoped search.")


@workspace_app.command("list")
def workspace_list() -> None:
    """List all workspaces with curate.yml under the vault's 01_Workspaces/."""
    from ..curate_yml import find_workspaces
    from rich.table import Table

    paths = _resolve_root_or_die()
    workspaces = find_workspaces(paths.root)

    if not workspaces:
        console.print("[dim]No workspaces with curate.yml found under 01_Workspaces/.[/dim]")
        console.print("  Use [bold]wiki workspace init <path>[/bold] to create one.")
        raise typer.Exit(0)

    table = Table(title="Workspaces with curate.yml", show_header=True, header_style="bold")
    table.add_column("Project", style="cyan")
    table.add_column("Path", style="dim")
    table.add_column("Domains")
    table.add_column("min_confidence")

    for ws_path, spec in workspaces:
        try:
            rel = ws_path.relative_to(paths.root)
        except ValueError:
            rel = ws_path
        persona_domain = spec.persona.domain or spec.persona.subdomain or ""
        domains = persona_domain if persona_domain else "[dim]—[/dim]"
        table.add_row(
            spec.project,
            str(rel),
            domains,
            f"{spec.min_confidence:.2f}",
        )

    console.print(table)


@testbed_app.command(name="init")
def testbed_init(
    scenario: str = typer.Argument("testbed_template", help="Scenario name from tests/scenarios/"),
    force: bool = typer.Option(False, "--force", "-f", help="Recreate the testbed."),
    llm: Optional[str] = typer.Option(None, "--llm", help="Primary LLM provider (ollama|antigravity-cli|cloud|claude-code)"),
    model: Optional[str] = typer.Option(None, "--model", help="Specific model name to use for the provider."),
):
    """Initialize a testbed vault using a specific scenario."""
    from .. import testbed_manager
    try:
        root = testbed_manager.init_testbed(scenario, force=force, llm_provider=llm, llm_model=model)
        _ok(f"Testbed initialized at [bold]{root}[/bold] using scenario [cyan]{scenario}[/cyan].")
        _hint("Run commands with [bold]VAULT_ROOT=testbed wiki ...[/bold]")
    except Exception as e:
        _err(str(e))
        raise typer.Exit(1)


@testbed_app.command(name="list")
def testbed_list():
    """List available testbed scenarios."""
    from .. import testbed_manager
    scenarios = testbed_manager.list_scenarios()
    if not scenarios:
        _warn("No scenarios found in tests/scenarios/.")
        return

    table = Table(title="Available Testbed Scenarios", box=None)
    table.add_column("Scenario Name", style="cyan")
    for s in sorted(scenarios):
        table.add_row(s)
    console.print(table)
