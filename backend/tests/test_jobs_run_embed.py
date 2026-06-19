"""`wiki jobs run` must always refresh the vector index, even on an empty queue.

Regression guard for the v0.3.2 workflow gap where a vault whose L2/L3 finished
but whose embeddings never completed (interrupted daemon, FTS-only `wiki add`)
had no automatic path to vectors and stayed FTS5-only until a manual
`wiki reindex --embed`. `jobs run` (which `wiki build` spawns in the background)
now embeds unconditionally; `update_index` is fingerprinted/idempotent.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from curator.cli import app


def _init_vault(runner: CliRunner, tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    result = runner.invoke(app, ["init", str(vault), "--no-interactive"])
    assert result.exit_code == 0, result.output
    return vault


def test_jobs_run_embeds_even_with_empty_queue(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)

    with patch("curator.ingest_worker.run_queued_jobs", return_value=[]) as run_jobs, patch(
        "curator.cli._refresh_search_index"
    ) as refresh:
        result = runner.invoke(app, ["jobs", "run"], env={"VAULT_ROOT": str(vault)})

    assert result.exit_code == 0, result.output
    run_jobs.assert_called_once()
    # The embed refresh must still run despite the empty queue.
    refresh.assert_called_once()
    assert refresh.call_args.kwargs.get("embed") is True


def test_jobs_run_embeds_after_processing_jobs(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)

    fake_results = [{"ok": True, "job": {"id": 1}}]
    with patch("curator.ingest_worker.run_queued_jobs", return_value=fake_results), patch(
        "curator.cli._refresh_search_index"
    ) as refresh:
        result = runner.invoke(app, ["jobs", "run"], env={"VAULT_ROOT": str(vault)})

    assert result.exit_code == 0, result.output
    refresh.assert_called_once()
    assert refresh.call_args.kwargs.get("embed") is True
