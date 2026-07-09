# ruff: noqa: F403,F405
# mypy: disable-error-code=name-defined
"""Persona commands for the `wiki` CLI."""

from __future__ import annotations

from .common import *

persona_app = typer.Typer(help="Manage the Curator and Artist personas.")

@persona_app.callback(invoke_without_command=True)
def persona_main(ctx: typer.Context) -> None:
    """Show or manage the vault persona."""
    if ctx.invoked_subcommand is None:
        _show_curator_persona()


@persona_app.command("update")
def persona_update(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace name under 01_Workspaces/"),
) -> None:
    """Re-run the persona interview and update settings.yml or curate.yml."""
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    client = _start_client(config)

    if workspace:
        ws_path = paths.root / consts.DIR_WORKSPACES / workspace
        curate_file = ws_path / consts.FILE_CURATE_YML
        if not curate_file.exists():
            typer.echo(f"No curate.yml found at {curate_file}", err=True)
            raise typer.Exit(1)
        import yaml as _yaml
        raw = _yaml.safe_load(curate_file.read_text(encoding="utf-8")) or {}
        project = raw.get("project", workspace)
        typer.echo(f"Updating Artist persona for: {project}")
        persona = _run_artist_persona_wizard(client, project)
        if persona is not None:
            import datetime as _dt
            persona["updated_at"] = _dt.datetime.now().isoformat()
            raw["persona"] = persona
            curate_file.write_text(
                _yaml.dump(raw, sort_keys=False, default_flow_style=False, allow_unicode=True),
                encoding="utf-8",
            )
            typer.echo(f"Artist persona updated in {curate_file}")
        else:
            typer.echo("Persona update skipped.")
    else:
        typer.echo("Updating Curator persona...")
        from .. import ingest_llm as _il
        recent_domains = _il.read_recent_domains(paths)
        persona = _run_curator_persona_wizard(client, current_persona=config.get("persona", {}), recent_domains=recent_domains)
        if persona is not None:
            import datetime as _dt
            persona["updated_at"] = _dt.datetime.now().isoformat()
            config["persona"] = persona
            cfg.save_config(paths, config)
            typer.echo("Curator persona updated in settings.yml")
        else:
            typer.echo("Persona update skipped.")

