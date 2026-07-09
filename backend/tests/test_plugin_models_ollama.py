"""`wiki plugin models ollama|pull` JSON commands (user report item 13).

The dashboard needs machine-readable Ollama recommendations (from models.json)
annotated with local install status + hardware fit, plus a way to pull a model.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from curator.cli import app


def _init_vault(runner: CliRunner, tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    result = runner.invoke(app, ["init", str(vault), "--no-interactive"])
    assert result.exit_code == 0, result.output
    return vault


def _json(output: str) -> dict:
    start = output.index("{")
    end = output.rindex("}")
    return json.loads(output[start : end + 1])


def test_plugin_models_ollama_lists_with_install_and_ram_flags(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)

    with patch("curator.commands.common._list_models_on_host_impl", return_value=[]), patch(
        "curator.cli.list_models_on_host", return_value=["qwen2.5:7b"]
    ), patch("curator.llm.detect_ram_gb", return_value=8.0):
        result = runner.invoke(
            app,
            ["plugin", "models", "ollama", "--json"],
            env={"VAULT_ROOT": str(vault)},
        )

    assert result.exit_code == 0, result.output
    payload = _json(result.output)
    assert payload["ram_gb"] == 8.0
    assert isinstance(payload["models"], list) and payload["models"]
    by_id = {m["id"]: m for m in payload["models"]}
    # Curated catalogue from models.json is present, annotated per model.
    assert "qwen2.5:7b" in by_id
    assert by_id["qwen2.5:7b"]["installed"] is True
    assert by_id["qwen2.5:7b"]["fits_ram"] is True   # 5 GB <= 8 GB
    # A large model is not installed and does not fit 8 GB of RAM.
    assert by_id["qwen2.5:32b"]["installed"] is False
    assert by_id["qwen2.5:32b"]["fits_ram"] is False  # 20 GB > 8 GB


def test_plugin_models_pull_invokes_ollama_pull(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)

    class _Result:
        returncode = 0

    with patch("subprocess.run", return_value=_Result()) as run:
        result = runner.invoke(
            app,
            ["plugin", "models", "pull", "--model", "qwen2.5:7b", "--json"],
            env={"VAULT_ROOT": str(vault)},
        )

    assert result.exit_code == 0, result.output
    payload = _json(result.output)
    assert payload["ok"] is True
    assert payload["model"] == "qwen2.5:7b"
    # The actual `ollama pull qwen2.5:7b` was invoked.
    called = run.call_args[0][0]
    assert "pull" in called and "qwen2.5:7b" in called


def test_plugin_models_pull_reports_failure(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)

    class _Result:
        returncode = 1

    with patch("subprocess.run", return_value=_Result()):
        result = runner.invoke(
            app,
            ["plugin", "models", "pull", "--model", "nope:1b", "--json"],
            env={"VAULT_ROOT": str(vault)},
        )

    assert result.exit_code == 0, result.output  # JSON error, not a crash
    payload = _json(result.output)
    assert payload["ok"] is False
    assert payload["model"] == "nope:1b"
