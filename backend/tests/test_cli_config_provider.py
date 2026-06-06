"""`wiki config provider` must persist non-interactively (user report item 13).

The dashboard runs `wiki config provider --primary … --model …` as a subprocess
with no TTY. Two failure modes must be guarded:

1. The provider change must be saved *before* the optional install offer, so a
   failing/skipped offer never loses the change.
2. The install offer must not prompt (and abort on EOF) when stdin is not a TTY.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from curator import config as cfg
from curator.cli import app


def _init_vault(runner: CliRunner, tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    result = runner.invoke(app, ["init", str(vault), "--no-interactive"])
    assert result.exit_code == 0, result.output
    return vault


def _primary(vault: Path) -> str:
    paths = cfg.WikiPaths(vault)
    return str((cfg.load_config(paths).get("llm") or {}).get("primary") or "")


def test_config_provider_saves_ollama_without_prompting(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)

    result = runner.invoke(
        app,
        ["config", "provider", "--primary", "ollama", "--model", "qwen2.5:7b"],
        env={"VAULT_ROOT": str(vault)},
        input="",
    )

    assert result.exit_code == 0, result.output
    assert _primary(vault) == "ollama::qwen2.5:7b"


def test_config_provider_persists_even_if_install_offer_fails(tmp_path: Path) -> None:
    """The change must be saved before the optional install offer runs."""
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)

    with patch("curator.cli._offer_install", side_effect=RuntimeError("boom")):
        runner.invoke(
            app,
            ["config", "provider", "--primary", "ollama", "--model", "qwen2.5:14b"],
            env={"VAULT_ROOT": str(vault)},
            input="",
        )

    # Regardless of how the install offer fared, the provider change persisted.
    assert _primary(vault) == "ollama::qwen2.5:14b"


def test_config_provider_offers_install_only_when_interactive(tmp_path: Path) -> None:
    """The optional install offer must not prompt when stdin is not a TTY."""
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)

    confirm = MagicMock(side_effect=AssertionError("must not prompt non-interactively"))
    # Force the install branch (tool absent, npm available) and a non-TTY stdin.
    with patch("curator.cli._cli_installed", return_value=False), patch(
        "curator.cli._ensure_npm", return_value=True
    ), patch("sys.stdin.isatty", return_value=False), patch(
        "curator.cli.typer.confirm", confirm
    ):
        result = runner.invoke(
            app,
            ["config", "provider", "--primary", "claude-code", "--model", "claude-opus-4-8"],
            env={"VAULT_ROOT": str(vault)},
            input="",
        )

    assert result.exit_code == 0, result.output
    confirm.assert_not_called()
    assert _primary(vault) == "claude-code::claude-opus-4-8"
