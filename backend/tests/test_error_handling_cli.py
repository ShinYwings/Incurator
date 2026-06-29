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
    home.mkdir()
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
