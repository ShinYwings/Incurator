"""XC-1: CLI best-effort failures should warn instead of disappearing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from curator import config as cfg
from curator import db
from curator import cli
from curator.cli import app


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    paths.internal.mkdir(parents=True)
    cfg.save_config(paths, cfg.DEFAULT_CONFIG)
    db.init_db(paths.state_db)
    return vault


def test_sync_mcp_configs_warns_when_target_write_fails(tmp_path, capsys, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    (home / ".gemini").write_text("not a directory", encoding="utf-8")
    vault = _make_vault(tmp_path)
    monkeypatch.setattr(cli.Path, "home", lambda: home)

    updated = cli._sync_mcp_configs(vault)

    out = capsys.readouterr().out
    assert str(vault / ".claude" / "settings.json") in updated
    assert "Skipped MCP config sync" in out
    assert ".gemini" in out


def test_sync_mcp_configs_warns_when_target_has_non_dict_mcp_servers(tmp_path, capsys, monkeypatch):
    home = tmp_path / "home"
    (home / ".gemini").mkdir(parents=True)
    # Hand-edited / foreign-tool config where mcpServers is a list, not an object.
    (home / ".gemini" / "settings.json").write_text('{"mcpServers": []}', encoding="utf-8")
    vault = _make_vault(tmp_path)
    monkeypatch.setattr(cli.Path, "home", lambda: home)

    # Must not raise (a bare `["incurator"] = ...` on a list would TypeError); the
    # malformed target is warned-and-skipped while valid targets still update.
    updated = cli._sync_mcp_configs(vault)

    out = capsys.readouterr().out
    assert str(vault / ".claude" / "settings.json") in updated
    assert str(home / ".gemini" / "settings.json") not in updated
    assert "Skipped MCP config sync" in out
    assert "mcpServers is not an object" in out


def test_config_set_warns_when_runtime_snapshot_refresh_fails(tmp_path):
    runner = CliRunner()
    vault = _make_vault(tmp_path)

    with patch(
        "curator.cli.runtime_state.write_runtime_snapshots",
        side_effect=OSError("readonly"),
    ):
        result = runner.invoke(
            app,
            ["config", "set", "--local", "llm.primary", "ollama::qwen2.5:7b"],
            env={"VAULT_ROOT": str(vault)},
        )

    assert result.exit_code == 0, result.output
    assert "Runtime snapshot refresh skipped" in result.output
    assert "readonly" in result.output


def test_config_set_warns_when_snapshot_refresh_hits_locked_db(tmp_path):
    """A locked state.sqlite raises sqlite3.OperationalError (NOT OSError); the
    best-effort refresh must still warn-and-continue, never crash the already-
    applied config write."""
    import sqlite3

    runner = CliRunner()
    vault = _make_vault(tmp_path)

    with patch(
        "curator.cli.runtime_state.write_runtime_snapshots",
        side_effect=sqlite3.OperationalError("database is locked"),
    ):
        result = runner.invoke(
            app,
            ["config", "set", "--local", "llm.primary", "ollama::qwen2.5:7b"],
            env={"VAULT_ROOT": str(vault)},
        )

    assert result.exit_code == 0, result.output
    assert "Runtime snapshot refresh skipped" in result.output
    assert "database is locked" in result.output


def test_config_set_warns_when_snapshot_refresh_hits_malformed_config(tmp_path):
    """A malformed config reload raises yaml.YAMLError (NOT OSError); the
    best-effort refresh must still warn-and-continue after the config write."""
    import yaml

    runner = CliRunner()
    vault = _make_vault(tmp_path)

    with patch(
        "curator.cli.runtime_state.write_runtime_snapshots",
        side_effect=yaml.YAMLError("bad config"),
    ):
        result = runner.invoke(
            app,
            ["config", "set", "--local", "llm.primary", "ollama::qwen2.5:7b"],
            env={"VAULT_ROOT": str(vault)},
        )

    assert result.exit_code == 0, result.output
    assert "Runtime snapshot refresh skipped" in result.output
    assert "bad config" in result.output


def test_config_provider_warns_when_runtime_snapshot_refresh_fails(tmp_path):
    runner = CliRunner()
    vault = _make_vault(tmp_path)

    with patch("curator.cli._offer_install"), patch(
        "curator.cli.runtime_state.write_runtime_snapshots",
        side_effect=OSError("readonly"),
    ):
        result = runner.invoke(
            app,
            ["config", "provider", "--primary", "ollama", "--model", "qwen2.5:7b"],
            env={"VAULT_ROOT": str(vault)},
            input="",
        )

    assert result.exit_code == 0, result.output
    assert "Runtime snapshot refresh skipped" in result.output
    assert "readonly" in result.output


def test_config_provider_warns_when_snapshot_refresh_hits_locked_db(tmp_path):
    import sqlite3

    runner = CliRunner()
    vault = _make_vault(tmp_path)

    with patch("curator.cli._offer_install"), patch(
        "curator.cli.runtime_state.write_runtime_snapshots",
        side_effect=sqlite3.OperationalError("database is locked"),
    ):
        result = runner.invoke(
            app,
            ["config", "provider", "--primary", "ollama", "--model", "qwen2.5:7b"],
            env={"VAULT_ROOT": str(vault)},
            input="",
        )

    assert result.exit_code == 0, result.output
    assert "Runtime snapshot refresh skipped" in result.output
    assert "database is locked" in result.output


def test_sync_mcp_configs_registers_where_agy_actually_reads(tmp_path):
    """v0.71.0: the registry agy reads was never written, so its tools never existed.

    Measured against agy 1.1.22 on a real machine: with `incurator` present in
    `~/.gemini/settings.json` and `~/.gemini/antigravity/mcp_config.json`, the
    CLI reported "No MCP servers configured" and the model answered that the
    tools were not available. Driving `agy mcp add` and diffing `~/.gemini`
    showed the CLI writes `~/.gemini/config/mcp_config.json`; registering there
    is what made the server appear in `agy mcp list`.

    This is the root cause behind three consecutive permission fixes that
    granted nothing -- the grants were fine, the server was never registered
    anywhere the CLI looked.
    """
    import json

    # `isolate_home_dir` (conftest) already points Path.home() at a temp dir.
    home = Path.home()
    vault = _make_vault(tmp_path)

    updated = cli._sync_mcp_configs(vault)

    agy_registry = home / ".gemini" / "config" / "mcp_config.json"
    assert str(agy_registry) in updated, "the file agy reads was not written"
    servers = json.loads(agy_registry.read_text(encoding="utf-8"))["mcpServers"]
    assert servers["incurator"]["env"]["VAULT_ROOT"] == str(vault)


def test_sync_mcp_configs_keeps_servers_the_user_registered_themselves(tmp_path):
    """`agy mcp add` writes this same file, so a wholesale replace would delete
    whatever the user registered by hand."""
    import json

    home = Path.home()
    (home / ".gemini" / "config").mkdir(parents=True, exist_ok=True)
    (home / ".gemini" / "config" / "mcp_config.json").write_text(
        json.dumps({"mcpServers": {"theirs": {"command": "echo", "args": ["hi"]}}}),
        encoding="utf-8",
    )
    vault = _make_vault(tmp_path)

    cli._sync_mcp_configs(vault)

    servers = json.loads(
        (home / ".gemini" / "config" / "mcp_config.json").read_text(encoding="utf-8")
    )["mcpServers"]
    assert "theirs" in servers, "sync deleted a server the user registered"
    assert "incurator" in servers


def test_sync_mcp_configs_registers_a_command_a_spawned_process_can_find(tmp_path):
    """A bare `wiki` is registered and dead.

    Measured: `command -v wiki` finds nothing in a spawned process's PATH here --
    it is a shell alias to the repo-root venv's console script. agy listed the
    server and then reported that no MCP tools existed, because starting it
    failed. `resolve_wiki_command` already existed for this exact reason on the
    Obsidian install path and simply was not used here.

    This was the third of three independent breakages between the plugin and a
    callable agy tool; the other two are pinned above and in the plugin tests.
    """
    import json

    home = Path.home()
    vault = _make_vault(tmp_path)

    cli._sync_mcp_configs(vault)

    servers = json.loads(
        (home / ".gemini" / "config" / "mcp_config.json").read_text(encoding="utf-8")
    )["mcpServers"]
    command = servers["incurator"]["command"]
    if command != "wiki":
        assert Path(command).is_absolute(), f"not resolvable from a spawn: {command}"
        assert command.endswith("/.venv/bin/wiki"), command
        assert "/backend/" not in command, "venvs live at the repo root"
