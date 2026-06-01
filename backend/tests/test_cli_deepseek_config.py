from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

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
