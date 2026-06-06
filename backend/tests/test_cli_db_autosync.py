"""`wiki db autosync` CLI + the auto_sync export hook on `wiki update`."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from curator import config as cfg
from curator import db_sync
from curator.cli import app


def _init_vault(runner: CliRunner, tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    result = runner.invoke(app, ["init", str(vault), "--no-interactive"])
    assert result.exit_code == 0, result.output
    return vault


def test_autosync_command_registered() -> None:
    result = CliRunner().invoke(app, ["db", "autosync", "--help"])
    assert result.exit_code == 0, result.output
    assert "--dry-run" in result.output


def test_autosync_json_runs_on_empty_vault(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)
    result = runner.invoke(
        app, ["db", "autosync", "--json"], env={"VAULT_ROOT": str(vault)}
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["imported_files"] == 0
    assert payload["inserted"] == 0


def test_update_hook_exports_only_when_auto_sync_enabled(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)
    paths = cfg.paths_from_config(vault)

    # Disabled by default → no device file written by the hook.
    from curator.cli import _maybe_auto_export

    _maybe_auto_export(paths)
    sync_dir = paths.internal / "sync"
    assert not sync_dir.exists() or not list(sync_dir.glob("dev-*.jsonl"))

    # Enable in vault config → hook writes this device's snapshot.
    config = cfg.load_config(paths)
    config["auto_sync"]["enabled"] = True
    cfg.save_config(paths, config)

    _maybe_auto_export(paths)
    did = db_sync.get_device_id(paths.internal)
    assert (paths.internal / "sync" / f"dev-{did}.jsonl").exists()
