"""`wiki db autosync` CLI + the auto_sync export hook on `wiki update`."""

from __future__ import annotations

import json
from pathlib import Path

import click
import pytest
from typer.testing import CliRunner

from curator import config as cfg
from curator import db_sync
from curator.cli import app


@pytest.fixture(autouse=True)
def isolated_sync_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cfg,
        "get_global_config_dir",
        lambda: tmp_path / "backend-cache",
    )


def _init_vault(runner: CliRunner, tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    result = runner.invoke(app, ["init", str(vault), "--no-interactive"])
    assert result.exit_code == 0, result.output
    return vault


def test_autosync_command_registered() -> None:
    result = CliRunner().invoke(app, ["db", "autosync", "--help"])
    assert result.exit_code == 0, result.output
    assert "--dry-run" in click.unstyle(result.output)


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


def test_autosync_json_reports_corrupt_state_without_overwriting(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)
    paths = cfg.paths_from_config(vault)
    state_path = db_sync._sync_state_path(paths.internal)
    state_path.parent.mkdir(parents=True)
    payload = b"{broken"
    state_path.write_bytes(payload)

    result = runner.invoke(
        app, ["db", "autosync", "--json"], env={"VAULT_ROOT": str(vault)}
    )

    assert result.exit_code == 1
    response = json.loads(result.output)
    assert response["ok"] is False
    assert "sync state" in response["error"]
    assert state_path.read_bytes() == payload


def test_autosync_human_error_is_visible_and_nonzero(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)
    paths = cfg.paths_from_config(vault)
    state_path = db_sync._sync_state_path(paths.internal)
    state_path.parent.mkdir(parents=True)
    state_path.write_text("{broken", encoding="utf-8")

    result = runner.invoke(app, ["db", "autosync"], env={"VAULT_ROOT": str(vault)})

    assert result.exit_code == 1
    assert "Auto-sync failed" in click.unstyle(result.output)


def test_export_hook_default_on_and_opt_out(tmp_path: Path) -> None:
    """v0.30.0: `auto_sync.enabled` defaults to true (opt-out).

    The v0.30.0 incident: every export trigger was opt-in, so a CLI-primary
    device silently never exported and peers converged on a stale snapshot.
    """
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)
    paths = cfg.paths_from_config(vault)

    from curator.cli import _maybe_auto_export

    # Default (no explicit setting) → the hook exports this device's snapshot.
    _maybe_auto_export(paths)
    did = db_sync.get_device_id(paths.internal)
    assert (paths.internal / "sync" / f"dev-{did}.jsonl").exists()

    # Explicit opt-out → the hook does nothing.
    config = cfg.load_config(paths)
    config["auto_sync"]["enabled"] = False
    cfg.save_config(paths, config)
    (paths.internal / "sync" / f"dev-{did}.jsonl").unlink()

    _maybe_auto_export(paths)
    assert not (paths.internal / "sync" / f"dev-{did}.jsonl").exists()


def test_export_hook_skips_when_nothing_unexported(tmp_path: Path) -> None:
    """The hook is LWW-gated: with no rows newer than `last_export_ts` it does
    not rewrite the snapshot (changes that don't bump an LWW column cannot
    propagate anyway, so re-exporting would be pure churn)."""
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)
    paths = cfg.paths_from_config(vault)

    from curator.cli import _maybe_auto_export

    _maybe_auto_export(paths)
    did = db_sync.get_device_id(paths.internal)
    out = paths.internal / "sync" / f"dev-{did}.jsonl"
    assert out.exists()

    # Nothing changed since the export above → a second call must not rewrite.
    out.unlink()
    _maybe_auto_export(paths)
    assert not out.exists()


def _register_markdown_source(vault: Path) -> None:
    note = vault / "03_Notes" / "note.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "# Heading\n\nThis note has enough words to register as a source.",
        encoding="utf-8",
    )


def test_add_exports_snapshot_by_default(tmp_path: Path) -> None:
    """`wiki add` must publish this device's snapshot when it registers sources
    (the '5 vs 31' trigger hole: only `wiki update` used to export)."""
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)
    paths = cfg.paths_from_config(vault)
    _register_markdown_source(vault)

    result = runner.invoke(app, ["add", "--no-sync"], env={"VAULT_ROOT": str(vault)})
    assert result.exit_code == 0, result.output

    did = db_sync.get_device_id(paths.internal)
    out = paths.internal / "sync" / f"dev-{did}.jsonl"
    assert out.exists(), "wiki add finished without exporting the device snapshot"
    assert '"table": "sources"' in out.read_text() or '"table":"sources"' in out.read_text()


def test_build_exports_snapshot_by_default(tmp_path: Path) -> None:
    """`wiki build --wait` must publish the snapshot after the L2/L3 pass."""
    from unittest.mock import MagicMock, patch

    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)
    paths = cfg.paths_from_config(vault)
    _register_markdown_source(vault)
    added = runner.invoke(app, ["add", "--no-sync"], env={"VAULT_ROOT": str(vault)})
    assert added.exit_code == 0, added.output

    # `add` already exported; only a post-build export can recreate the file.
    did = db_sync.get_device_id(paths.internal)
    out = paths.internal / "sync" / f"dev-{did}.jsonl"
    if out.exists():
        out.unlink()

    with patch("curator.cli._start_client", return_value=MagicMock()), patch(
        "curator.ingest_llm.run_l1_to_l3", return_value=[]
    ), patch("curator.cli._refresh_search_index"), patch(
        # Force the LWW gate open so the assert isolates the *wiring*:
        # a mocked no-change build may not bump any LWW column.
        "curator.db_sync.local_has_unexported_changes", return_value=True
    ):
        result = runner.invoke(
            app, ["build", "--wait", "--no-sync"], env={"VAULT_ROOT": str(vault)}
        )

    assert result.exit_code == 0, result.output
    assert out.exists(), "wiki build finished without exporting the device snapshot"


def test_sync_incremental_exports_snapshot_by_default(tmp_path: Path) -> None:
    """Bare `wiki sync` — the DEFAULT incremental path — must publish the
    snapshot when done (PR #78 review: the incremental branch returned before
    the hook, so the normal sync flow silently never exported; the earlier test
    passed --no-interactive, which accidentally selected the LLM-dependent full
    path and broke CI when no provider was available)."""
    from unittest.mock import patch

    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)
    paths = cfg.paths_from_config(vault)

    did = db_sync.get_device_id(paths.internal)
    out = paths.internal / "sync" / f"dev-{did}.jsonl"
    if out.exists():
        out.unlink()

    with patch("curator.db_sync.local_has_unexported_changes", return_value=True):
        # No flags → incremental path (client=None, LLM-free).
        result = runner.invoke(app, ["sync"], env={"VAULT_ROOT": str(vault)})

    assert result.exit_code == 0, result.output
    assert out.exists(), "incremental wiki sync finished without exporting the device snapshot"


def test_lww_gate_catches_same_second_mutation(tmp_path: Path) -> None:
    """PR #78 review: timestamps have second precision, so a mutation stamped in
    the SAME second as `last_export_ts` must still count as unexported (>=, not
    strict >) — otherwise it never ships until an unrelated later mutation."""
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)
    paths = cfg.paths_from_config(vault)

    from curator import db

    ts = "2026-07-02T10:00:00Z"
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("03_Notes/n.md", "h1", "md", 1, ts),
        )
    db_sync.write_sync_state(
        paths.internal, {"device_id": "test-device", "last_export_ts": ts}
    )

    assert db_sync.local_has_unexported_changes(paths.internal, paths.state_db) is True


def test_lww_gate_counts_tombstones(tmp_path: Path) -> None:
    """PR #78 review: deleted_records was excluded from the max-timestamp scan,
    so a delete-only change never triggered an export and peers never saw the
    deletion."""
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)
    paths = cfg.paths_from_config(vault)

    # Baseline: nothing unexported after an export "now".
    db_sync.write_sync_state(
        paths.internal,
        {"device_id": "test-device", "last_export_ts": "2026-07-02T10:00:00Z"},
    )
    assert db_sync.local_has_unexported_changes(paths.internal, paths.state_db) is False

    # A tombstone newer than last_export_ts must flip the gate.
    from curator import db

    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO deleted_records (table_name, record_id, deleted_at) "
            "VALUES (?, ?, ?)",
            ("atoms", "ATM-dead", "2026-07-02T10:00:01Z"),
        )
    assert db_sync.local_has_unexported_changes(paths.internal, paths.state_db) is True


def test_autosync_dry_run_reports_would_export(tmp_path: Path) -> None:
    """`wiki db autosync --dry-run --json` exposes `would_export` so a stale
    snapshot is visible without mutating anything."""
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)

    # Fresh vault, never exported → an export is pending.
    result = runner.invoke(
        app, ["db", "autosync", "--dry-run", "--json"], env={"VAULT_ROOT": str(vault)}
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["would_export"] is True

    # A real pass exports; immediately after, nothing is pending.
    real = runner.invoke(app, ["db", "autosync"], env={"VAULT_ROOT": str(vault)})
    assert real.exit_code == 0, real.output
    again = runner.invoke(
        app, ["db", "autosync", "--dry-run", "--json"], env={"VAULT_ROOT": str(vault)}
    )
    assert again.exit_code == 0, again.output
    assert json.loads(again.output)["would_export"] is False
