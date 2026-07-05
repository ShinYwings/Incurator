from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from curator import config as cfg
from curator.cli import app


def test_wiki_reset_removes_generated_state_and_keeps_config(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = tmp_path / "vault"

    init_result = runner.invoke(app, ["init", str(vault), "--no-interactive"])
    assert init_result.exit_code == 0, init_result.output

    curator = vault / ".curator"
    paths = cfg.paths_from_config(vault)
    sessions = curator / "sessions.json"
    sessions.write_text("shared-session", encoding="utf-8")
    generated_files = [
        paths.dashboard,
        paths.sync_report,
        paths.event_log,
        paths.staging / "canvas" / "build_trace_new.canvas",
    ]
    for path in generated_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("generated", encoding="utf-8")

    reset_result = runner.invoke(
        app,
        ["reset", "--force"],
        env={"VAULT_ROOT": str(vault)},
    )

    assert reset_result.exit_code == 0, reset_result.output
    assert (curator / "settings.yml").exists()
    assert sessions.read_text(encoding="utf-8") == "shared-session"
    for path in generated_files:
        assert not path.exists(), f"{path} should be removed by reset"
    assert not (curator / "Collections").exists()
