from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from curator import config as cfg
from curator.cli import app


def test_wiki_init_then_config_provider_deepseek(tmp_path: Path):
    runner = CliRunner()
    vault = tmp_path / "vault"

    init_result = runner.invoke(app, ["init", str(vault), "--no-interactive"])
    assert init_result.exit_code == 0, init_result.output

    config_result = runner.invoke(
        app,
        [
            "config",
            "provider",
            "--primary",
            "deepseek-api",
            "--model",
            "deepseek-v4-pro",
            "--api-key-env",
            "DEEPSEEK_TEST_KEY",
            "--base-url",
            "https://api.deepseek.com",
        ],
        env={"VAULT_ROOT": str(vault)},
    )
    assert config_result.exit_code == 0, config_result.output

    primary = runner.invoke(
        app,
        ["config", "get", "llm.primary"],
        env={"VAULT_ROOT": str(vault)},
    )
    assert primary.exit_code == 0, primary.output
    assert primary.output.strip() == "deepseek-api::deepseek-v4-pro"

    key_env = runner.invoke(
        app,
        ["config", "get", "llm.deepseek-api.api_key_env"],
        env={"VAULT_ROOT": str(vault)},
    )
    assert key_env.exit_code == 0, key_env.output
    assert key_env.output.strip() == "DEEPSEEK_TEST_KEY"


def test_config_provider_deepseek_api_key_uses_local_secret(tmp_path: Path, monkeypatch):
    global_dir = tmp_path / "cache_config"
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: global_dir)
    runner = CliRunner()
    vault = tmp_path / "vault"

    init_result = runner.invoke(app, ["init", str(vault), "--no-interactive"])
    assert init_result.exit_code == 0, init_result.output

    config_result = runner.invoke(
        app,
        [
            "config",
            "provider",
            "--primary",
            "deepseek-api",
            "--model",
            "deepseek-v4-flash",
            "--api-key",
            "sk-test-secret",
        ],
        env={"VAULT_ROOT": str(vault)},
    )
    assert config_result.exit_code == 0, config_result.output

    # Raw key must NOT appear anywhere in the synced vault config
    vault_text = (vault / ".curator" / "config.yml").read_text(encoding="utf-8")
    assert "sk-test-secret" not in vault_text
    # llm is machine-local → key reference goes to global cache, not vault
    assert "api_key_secret" not in vault_text
    global_text = (global_dir / "config.yml").read_text(encoding="utf-8")
    assert "api_key_secret: secret:deepseek-api-key" in global_text
