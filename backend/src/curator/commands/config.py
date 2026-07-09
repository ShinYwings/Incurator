# ruff: noqa: F403,F405
# mypy: disable-error-code=name-defined
"""Config commands for the `wiki` CLI."""

from __future__ import annotations

from .common import *

config_app = typer.Typer(
    name="config",
    help="Configure the LLM provider and Ollama models.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

config_secret_app = typer.Typer(
    name="secret",
    help="Manage local encrypted backend secrets.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
config_app.add_typer(config_secret_app, name="secret")

config_models_app = typer.Typer(
    name="models",
    help="Discover and select Ollama models (local or remote).",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
config_app.add_typer(config_models_app, name="models")

@config_app.command("get")
def config_get(
    key: str = typer.Argument(..., help="Dot-separated config key, e.g. external.path_roots.zotero_data"),
    global_only: bool = typer.Option(False, "--global", help="Read from global config only."),
) -> None:
    """Print a config key value from the merged (global + project) config.

    \b
      wiki config get external.path_roots.zotero_data
      wiki config get llm.primary
    """
    import json as _json

    if global_only:
        raw: dict = {}
        global_cfg_file = cfg.get_global_config_dir() / consts.FILE_GLOBAL_CONFIG_YML
        if global_cfg_file.exists():
            import yaml as _yaml
            with global_cfg_file.open("r", encoding="utf-8") as f:
                raw = _yaml.safe_load(f) or {}
    else:
        try:
            paths = _resolve_root_or_die()
            raw = cfg.load_config(paths)
        except SystemExit:
            raw = {}
            global_cfg_file = cfg.get_global_config_dir() / consts.FILE_GLOBAL_CONFIG_YML
            if global_cfg_file.exists():
                import yaml as _yaml
                with global_cfg_file.open("r", encoding="utf-8") as f:
                    raw = _yaml.safe_load(f) or {}

    parts = key.split(".")
    val: object = raw
    for part in parts:
        if isinstance(val, dict):
            val = val.get(part)
        else:
            val = None
            break

    if val is None:
        console.print("[dim](not set)[/dim]")
    elif isinstance(val, (dict, list)):
        console.print(_json.dumps(val, indent=2, ensure_ascii=False))
    else:
        console.print(str(val))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Dot-separated config key, e.g. external.path_roots.zotero_data"),
    value: str = typer.Argument(..., help="Value to set. Lists use JSON: '[\"path1\",\"path2\"]'"),
    append: bool = typer.Option(False, "--append", help="Append to an existing list instead of replacing."),
    global_cfg: bool = typer.Option(True, "--global/--local", help="Write to global config (default) or project config."),
) -> None:
    """Set a config key in the global or project config file.

    \b
      wiki config set external.path_roots.zotero_data "$HOME/Zotero"
      wiki config set external.zotero.root_keys '["zotero_data"]'
      wiki config set --local llm.primary ollama
    """
    import json as _json
    import yaml as _yaml

    # Determine target config file
    paths: cfg.WikiPaths | None = None
    if global_cfg:
        config_dir = cfg.get_global_config_dir()
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / consts.FILE_GLOBAL_CONFIG_YML
    else:
        paths = _resolve_root_or_die()
        config_file = paths.config_file

    existing: dict = {}
    if config_file.exists():
        with config_file.open("r", encoding="utf-8") as f:
            existing = _yaml.safe_load(f) or {}

    # Parse value: try JSON first, then treat as plain string
    try:
        parsed_value: object = _json.loads(value)
    except (ValueError, TypeError):
        parsed_value = str(value).replace("~", str(Path.home()))

    # Navigate/create nested dict and apply
    parts = key.split(".")
    target = existing
    for part in parts[:-1]:
        if not isinstance(target.get(part), dict):
            target[part] = {}
        target = target[part]  # type: ignore[assignment]

    leaf = parts[-1]
    if append:
        current = target.get(leaf)
        if isinstance(current, list):
            existing_list = current
        elif current is not None:
            existing_list = [current]
        else:
            existing_list = []
        items = parsed_value if isinstance(parsed_value, list) else [parsed_value]
        for item in items:
            if item not in existing_list:
                existing_list.append(item)
        target[leaf] = existing_list
    else:
        target[leaf] = parsed_value

    with config_file.open("w", encoding="utf-8") as f:
        _yaml.safe_dump(existing, f, sort_keys=False, default_flow_style=False, allow_unicode=True)

    scope = "global" if global_cfg else "project"
    console.print(f"[green]✓[/green] {scope} config updated: [bold]{key}[/bold] = {_json.dumps(parsed_value, ensure_ascii=False)}")
    console.print(f"[dim]  {config_file}[/dim]")

    # Refresh runtime snapshots so the plugin dashboard picks up the change
    # immediately without an extra `wiki status` round-trip.
    import sqlite3 as _sqlite3

    try:
        refresh_paths = paths
        if refresh_paths is None:
            root = cfg.find_wiki_root()
            refresh_paths = cfg.paths_from_config(root) if root else None
        if refresh_paths:
            runtime_state.write_runtime_snapshots(refresh_paths, cfg.load_config(refresh_paths))
    except (OSError, _sqlite3.Error, _yaml.YAMLError) as exc:
        # Best-effort: the config write already succeeded and was confirmed to the
        # user, so a refresh failure (DB locked by the plugin → sqlite3.Error,
        # malformed merged config → yaml.YAMLError, FS errors → OSError) must warn,
        # never crash the command. CLI-only users don't need the snapshot.
        _warn(f"Runtime snapshot refresh skipped: {type(exc).__name__}: {exc}")


@config_app.command("provider")
def config_provider(
    primary: str = typer.Option(
        "",
        "--primary", "-p",
        help="Primary backend: ollama | claude-code | antigravity-cli | codex-cli | deepseek-api",
    ),
    model: str = typer.Option(
        "",
        "--model", "-m",
        help="Model name (e.g. qwen2.5:7b, gpt-5.5, claude-sonnet-4-6).",
    ),
    effort: str = typer.Option(
        "",
        "--effort", "-e",
        help="Reasoning effort for the primary model (low|medium|high|xhigh|max), CLI-dependent.",
    ),
    host: str = typer.Option(
        "",
        "--host",
        help="Ollama host URL (e.g. http://localhost:11434).",
    ),
    api_key_env: str = typer.Option(
        "",
        "--api-key-env",
        help="Environment variable that holds the API key for API-key providers (DeepSeek default: DEEPSEEK_API_KEY).",
    ),
    api_key: str = typer.Option(
        "",
        "--api-key",
        help="API key for API-key providers. Prefer --api-key-env for shared machines.",
    ),
    base_url: str = typer.Option(
        "",
        "--base-url",
        help="Base URL for API-key providers (DeepSeek default: https://api.deepseek.com).",
    ),
) -> None:
    """Reconfigure the LLM provider for the current project.

    Run without flags for the interactive wizard, or pass flags to set directly:

    \b
      wiki config provider --primary ollama --model qwen2.5:7b
      wiki config provider --primary codex-cli --model gpt-5.5 --effort high
      wiki config provider --primary deepseek-api --model deepseek-v4-flash
      wiki config provider --primary deepseek-api --model deepseek-v4-pro --api-key-env DEEPSEEK_API_KEY
      wiki config provider --primary antigravity-cli
      wiki config provider --primary claude-code
    """
    paths = _resolve_root_or_die()
    current_config = cfg.load_config(paths)
    llm = dict(current_config.get("llm", {}))

    any_flag = bool(primary or model or host or effort or api_key_env or api_key or base_url)

    if any_flag:
        overrides = {}
        _valid_primary = (
            consts.BACKEND_OLLAMA,
            consts.BACKEND_CLAUDE_CODE,
            consts.BACKEND_ANTIGRAVITY_CLI,
            consts.BACKEND_CODEX_CLI,
            consts.BACKEND_DEEPSEEK_API,
        )

        # Resolve provider
        provider = primary or (
            consts.BACKEND_DEEPSEEK_API
            if (api_key_env or api_key or base_url)
            else consts.BACKEND_OLLAMA
        )
        if provider not in _valid_primary:
            _warn(f"Unknown --primary '{provider}'. Use: {' | '.join(_valid_primary)}")
            raise typer.Exit(code=1)

        if host:
            llm.setdefault(consts.BACKEND_OLLAMA, {})["host"] = host
        if provider == consts.BACKEND_DEEPSEEK_API:
            deepseek_cfg = llm.setdefault(consts.BACKEND_DEEPSEEK_API, {})
            if api_key_env:
                deepseek_cfg["api_key_env"] = api_key_env
            elif "api_key_env" not in deepseek_cfg:
                deepseek_cfg["api_key_env"] = "DEEPSEEK_API_KEY"
            if api_key:
                from .. import secret_store

                deepseek_cfg["api_key_secret"] = secret_store.set_secret(
                    secret_store.DEFAULT_DEEPSEEK_SECRET,
                    api_key,
                )
                deepseek_cfg.pop("api_key", None)
            if base_url:
                deepseek_cfg["base_url"] = base_url
            elif "base_url" not in deepseek_cfg:
                deepseek_cfg["base_url"] = "https://api.deepseek.com"

        # Effort is set by the --effort flag, or chosen interactively below.
        primary_effort = effort

        if model:
            # Model provided directly via flag
            llm["primary"] = cfg.join_provider_model(provider, model)
        else:
            # Offer interactive model selection for cloud backends
            if provider in (consts.BACKEND_CLAUDE_CODE, consts.BACKEND_ANTIGRAVITY_CLI, consts.BACKEND_CODEX_CLI, consts.BACKEND_DEEPSEEK_API):
                console.print()
                console.print(f"[bold]{provider} Model Selection[/bold]")
                sel_model, sel_effort = _pick_cloud_model(provider, llm)
                llm["primary"] = cfg.join_provider_model(provider, sel_model or "")
                if not primary_effort:
                    primary_effort = sel_effort
            elif provider == consts.BACKEND_OLLAMA:
                if not model:
                    sel_model = _pick_ollama_model(llm.get(consts.BACKEND_OLLAMA, {}).get("host", consts.DEFAULT_OLLAMA_HOST))
                    llm["primary"] = cfg.join_provider_model(provider, sel_model)
                else:
                    llm["primary"] = cfg.join_provider_model(provider, model)
            else:
                llm["primary"] = provider

        llm["primary_effort"] = primary_effort
        overrides["primary"] = llm["primary"]
    else:
        # Interactive wizard
        overrides = _run_init_wizard()
        llm.update(overrides)

    llm.pop("provider", None)
    current_config["llm"] = llm
    # Persist the provider change FIRST so it always sticks, then offer the
    # optional (interactive-only) tool/model install. Previously the offer ran
    # before the save, so a non-interactive caller (the Obsidian dashboard) that
    # aborted at the prompt lost the change entirely.
    cfg.save_config(paths, current_config)
    _offer_install(overrides, llm)

    console.print()
    console.print("[bold green]Provider settings saved.[/bold green]")
    console.print(f"[dim]Backend: {describe_backend(current_config)}[/dim]")
    console.print()

    # Refresh runtime snapshots so the plugin dashboard picks up the change.
    import sqlite3 as _sqlite3

    try:
        runtime_state.write_runtime_snapshots(paths, current_config)
    except (OSError, _sqlite3.Error) as exc:
        # Best-effort (see config_set): expected snapshot write/DB failures must
        # warn, not crash the already-applied provider change.
        _warn(f"Runtime snapshot refresh skipped: {type(exc).__name__}: {exc}")


@config_secret_app.command("list")
def config_secret_list() -> None:
    """List local encrypted backend secrets with masked values."""
    from .. import secret_store

    secrets = secret_store.list_secrets()
    if not secrets:
        console.print("[dim]No local encrypted secrets stored.[/dim]")
        return
    for reference, masked in secrets.items():
        console.print(f"{reference}\t{masked}")


@config_secret_app.command("delete")
def config_secret_delete(
    reference: str = typer.Argument(..., help="Secret reference, e.g. secret:deepseek-api-key."),
) -> None:
    """Delete a local encrypted backend secret."""
    from .. import secret_store

    if secret_store.delete_secret(reference):
        console.print(f"[green]Deleted[/green] {reference}")
    else:
        console.print(f"[yellow]No such secret[/yellow] {reference}")


@config_models_app.command("list")
def models_list(
    host: str = typer.Option(
        "",
        "--host",
        "-H",
        help="Ollama host URL to query (overrides config). Only used when primary provider is ollama.",
    ),
    show_all: bool = typer.Option(
        False,
        "--all",
        help="Show all recommended and available models (default: show only active).",
    ),
) -> None:
    """List models for the configured LLM provider.

    By default, only shows currently active/configured models.
    Use --all to see the full catalogue and recommendations.
    """
    import os
    env_root = os.environ.get("VAULT_ROOT")
    discovered = None
    
    if env_root:
        discovered = Path(env_root).resolve()
    else:
        # Walk up from CWD
        discovered = cfg.find_wiki_root()
        # Fallback to last successful root (same as wiki status)
        if not discovered:
            last = cfg.get_last_root()
            if last and (last / consts.INTERNAL_DIR).exists():
                discovered = last

    if discovered is not None and (discovered / consts.INTERNAL_DIR).exists():
        paths = cfg.paths_from_config(discovered)
        llm_cfg = cfg.load_config(paths).get("llm", {})
    else:
        # If still not found, we will show all recommendations
        llm_cfg = {}
        show_all = True
    
    primary_raw = llm_cfg.get("primary", "")
    primary, _ = cfg.split_provider_model(primary_raw)
    active_only = not show_all
    any_found = False

    _CLOUD_BACKENDS = (
        consts.BACKEND_CLAUDE_CODE,
        consts.BACKEND_ANTIGRAVITY_CLI,
        consts.BACKEND_CODEX_CLI,
        consts.BACKEND_DEEPSEEK_API,
    )

    # 1. Show Primary Backend models
    if primary in _CLOUD_BACKENDS:
        any_found = _show_cloud_models(primary, llm_cfg, active_only=active_only)
    elif primary == consts.BACKEND_OLLAMA or (not primary and host):
        target_host = host or llm_cfg.get(consts.BACKEND_OLLAMA, {}).get("host", consts.DEFAULT_OLLAMA_HOST)
        any_found = _show_ollama_installed(target_host, llm_cfg, active_only=active_only)
        if not any_found and primary == consts.BACKEND_OLLAMA and not active_only:
            _hint("Start Ollama with [bold]ollama serve[/bold] or set [bold]llm.ollama.host[/bold] in config.")
    else:
        if not active_only:
            console.print("[dim]Primary backend not set. Showing all curated recommendations:[/dim]" if not primary
                          else f"[yellow]Unknown primary '{primary}'. Showing all curated recommendations.[/yellow]")

    if active_only:
        if not any_found:
            if not discovered:
                console.print(f"\n[yellow]Not inside a wiki project.[/yellow] (cwd: {Path.cwd()})")
                console.print("Use [bold]wiki config models list --all[/bold] to see all recommendations.")
            else:
                console.print("\n[bold]Current Active Configuration[/bold]")
                console.print(f"  Primary: [cyan]{primary_raw or '(not set)'}[/cyan]")
        return

    # 2. Show recommendations for other providers
    console.print("\n[bold dim]--- Recommended Models (Global) ---[/bold dim]")
    for cp in _CLOUD_BACKENDS:
        if cp != primary:
            _show_cloud_models(cp, llm_cfg)
    ollama_host = host or llm_cfg.get(consts.BACKEND_OLLAMA, {}).get("host", consts.DEFAULT_OLLAMA_HOST)
    _show_recommended_models(ollama_host)


@config_models_app.command("use")
def models_use(
    model: str = typer.Argument(
        None, help="Model tag to activate. Omit to pick interactively from the model list."
    ),
    host: str = typer.Option(
        "",
        "--host",
        "-H",
        help="Ollama host to verify model availability (default: from config). Ollama only.",
    ),
) -> None:
    """Set the active model in project config.

    For Ollama: shows recommendation list; pulls the model if not yet downloaded.
    For cloud providers (claude-code/antigravity-cli): shows curated list and saves
    the selection to the appropriate config key (e.g. claude_model, antigravity_model).
    """
    import subprocess

    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    llm_cfg = config.get("llm", {})

    primary_raw = llm_cfg.get("primary", "")
    primary, _ = cfg.split_provider_model(primary_raw)

    # --- Cloud providers ---
    if primary and primary != consts.BACKEND_OLLAMA:
        if host:
            console.print("[dim]--host is an Ollama-only option. Ignoring.[/dim]")
        if primary not in (
            consts.BACKEND_CLAUDE_CODE,
            consts.BACKEND_ANTIGRAVITY_CLI,
            consts.BACKEND_CODEX_CLI,
            consts.BACKEND_DEEPSEEK_API,
        ):
            _err(f"Unknown primary '{primary}'.")
            raise typer.Exit(code=1)

        sel_effort = ""
        if not model:
            model, sel_effort = _pick_cloud_model(primary, llm_cfg)
            if not model:
                console.print("[dim]Cancelled.[/dim]")
                raise typer.Exit()
        else:
            # Model passed directly via flag — default the effort for it.
            from curator.models import get_default_effort
            _prov_name = {
                consts.BACKEND_ANTIGRAVITY_CLI: consts.CLOUD_ANTIGRAVITY,
                consts.BACKEND_CLAUDE_CODE:     consts.CLOUD_CLAUDE,
                consts.BACKEND_CODEX_CLI:        consts.CLOUD_OPENAI,
            }.get(primary, "")
            sel_effort = get_default_effort(_prov_name, model)
        # Write in new 'provider::model' format
        config.setdefault("llm", {})["primary"] = cfg.join_provider_model(primary, model)
        config["llm"]["primary_effort"] = sel_effort
        cfg.save_config(paths, config)
        _ok(
            f"Model set: [bold]{model}[/bold] "
            f"→  {paths.config_file.relative_to(paths.root)}"
        )
        _hint("Run [bold]wiki add[/bold] to start using the new model.")
        return

    # --- Ollama ---
    target_host = host or llm_cfg.get(consts.BACKEND_OLLAMA, {}).get("host", consts.DEFAULT_OLLAMA_HOST)

    # No model given → show recommendation table and prompt interactively
    if not model:
        _show_recommended_models(target_host)
        console.print()
        model = typer.prompt(
            "  Enter model tag (Enter = Cancel)",
            default="",
            show_default=False,
        ).strip()
        if not model:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit()

    available = list_models_on_host(target_host, timeout=5.0)

    if available:
        if not any(m == model or m.startswith(model) for m in available):
            console.print(f"[dim]Model '{model}' not found locally — pulling…[/dim]")
            try:
                subprocess.run([consts.BACKEND_OLLAMA, "pull", model], check=True)
            except FileNotFoundError:
                _warn("'ollama' CLI not found in PATH. Is Ollama installed?")
                raise typer.Exit(code=1)
            except subprocess.CalledProcessError as e:
                _warn(f"ollama pull failed (exit {e.returncode}).")
                raise typer.Exit(code=1)
            _ok(f"Pulled {model}")
        else:
            _ok(f"Verified: {model} is available on {target_host}")
    else:
        _warn(f"Ollama unreachable at {target_host} — saving model without verification.")

    config.setdefault("llm", {})["primary"] = cfg.join_provider_model(consts.BACKEND_OLLAMA, model)
    config["llm"]["primary_effort"] = ""
    cfg.save_config(paths, config)
    _ok(f"Model set to [bold]{model}[/bold] in {paths.config_file.relative_to(paths.root)}")
    _hint("Run [bold]wiki add[/bold] to start using the new model.")

