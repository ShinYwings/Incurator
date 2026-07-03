"""`wiki update` consolidation + always-on auto-embedding (user report item 14).

- `wiki update` is the one-shot pipeline (add -> build -> embed -> sync).
- The `jobs` group is hidden from `wiki --help` but stays functional.
- Synchronous `build` refreshes the vector index unconditionally, even when no
  atoms changed, so an already-built vault never silently stays FTS5-only.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
from typer.testing import CliRunner

from curator.cli import app


def _init_vault(runner: CliRunner, tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    result = runner.invoke(app, ["init", str(vault), "--no-interactive"])
    assert result.exit_code == 0, result.output
    return vault

def test_update_command_is_registered() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["update", "--help"])
    assert result.exit_code == 0, result.output
    clean_output = click.unstyle(result.output)
    assert "--force" in clean_output
    assert "--no-sync" in clean_output


def test_jobs_group_is_hidden_but_functional() -> None:
    runner = CliRunner()
    top = runner.invoke(app, ["--help"])
    assert top.exit_code == 0, top.output
    # Hidden from the advertised command list...
    assert "jobs" not in top.output
    # ...but still fully functional for the worker / dashboard.
    jobs = runner.invoke(app, ["jobs", "--help"])
    assert jobs.exit_code == 0, jobs.output
    assert "run" in jobs.output


def test_paths_migration_group_is_removed() -> None:
    runner = CliRunner()

    top = runner.invoke(app, ["--help"])
    assert top.exit_code == 0, top.output
    assert re.search(r"│\s+paths\s+", click.unstyle(top.output)) is None

    removed = runner.invoke(app, ["paths", "--help"])
    assert removed.exit_code != 0


def test_build_wait_always_embeds_even_with_no_atom_changes(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)

    # A real Markdown source so build sees an L1-ready source needing L2/L3
    # (no LLM/pymupdf needed for L1 on Markdown).
    note = vault / "03_Notes" / "note.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "# Heading\n\nThis note has enough words to register as a source.",
        encoding="utf-8",
    )
    added = runner.invoke(app, ["add", "--no-sync"], env={"VAULT_ROOT": str(vault)})
    assert added.exit_code == 0, added.output

    # Build produces zero atom changes; the embed refresh must still run.
    with patch("curator.cli._start_client", return_value=MagicMock()), patch(
        "curator.ingest_llm.run_l1_to_l3", return_value=[]
    ), patch("curator.cli._refresh_search_index") as refresh:
        result = runner.invoke(
            app, ["build", "--wait", "--no-sync"], env={"VAULT_ROOT": str(vault)}
        )

    assert result.exit_code == 0, result.output
    refresh.assert_called_once()
    assert refresh.call_args.kwargs.get("embed") is True


def test_build_wait_with_no_pending_sources_runs_global_l3_and_embeds(
    tmp_path: Path,
) -> None:
    """The `build --wait` no-pending branch must use the real client constructor
    and still refresh embeddings (regression: it called a nonexistent
    `ingest_llm.get_client`, which `wiki update` surfaced on a built vault)."""
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)  # empty vault: no L1-ready sources

    client = MagicMock()
    with patch("curator.cli._start_client", return_value=client) as start, patch(
        "curator.ingest_llm.run_l3_from_existing_atoms"
    ) as run_l3, patch("curator.cli._refresh_search_index") as refresh:
        result = runner.invoke(
            app, ["build", "--wait", "--no-sync"], env={"VAULT_ROOT": str(vault)}
        )

    assert result.exit_code == 0, result.output
    start.assert_called_once()
    run_l3.assert_called_once()
    client.close.assert_called_once()
    refresh.assert_called_once()
    assert refresh.call_args.kwargs.get("embed") is True


def test_update_orchestrates_add_build_sync_in_order(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)

    manager = MagicMock()
    with patch("curator.cli.add", manager.add), patch(
        "curator.cli.build", manager.build
    ), patch("curator.cli.sync", manager.sync), patch(
        "curator.cli._maybe_auto_export"
    ) as auto_export:
        result = runner.invoke(app, ["update"], env={"VAULT_ROOT": str(vault)})

    assert result.exit_code == 0, result.output
    # add -> build -> sync, in that order.
    order = [c[0] for c in manager.mock_calls]
    assert order == ["add", "build", "sync"]
    # add/build run with verification deferred to the single final sync.
    assert manager.add.call_args.kwargs.get("no_sync") is True
    assert manager.build.call_args.kwargs.get("no_sync") is True
    assert manager.build.call_args.kwargs.get("wait") is True
    auto_export.assert_called_once()


def test_update_skips_sync_with_no_sync_flag(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = _init_vault(runner, tmp_path)

    manager = MagicMock()
    with patch("curator.cli.add", manager.add), patch(
        "curator.cli.build", manager.build
    ), patch("curator.cli.sync", manager.sync):
        result = runner.invoke(
            app, ["update", "--no-sync"], env={"VAULT_ROOT": str(vault)}
        )

    assert result.exit_code == 0, result.output
    manager.sync.assert_not_called()
