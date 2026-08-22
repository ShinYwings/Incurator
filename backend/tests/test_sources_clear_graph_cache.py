"""v0.63.0 (ROADMAP 5c, P3): the escape hatch for a poisoned resume cache.

A graph batch that VALIDATES but extracts nonsense is cached and replayed on
every subsequent run. Re-ingesting does not clear it: `wiki add --force` releases
and re-adopts the same unit rows, so the unit ids — and therefore the batch
hashes — are unchanged. Without a way to clear, the only recovery is editing
SQLite by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from curator import config as cfg
from curator import db
from curator.cli import app


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    paths.internal.mkdir(parents=True)
    cfg.save_config(paths, cfg.DEFAULT_CONFIG)
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        for relpath in ("04_Resources/a.md", "04_Resources/b.md"):
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES (?, ?, 'md', 10, datetime('now'))",
                (relpath, relpath),
            )
    payload = json.dumps({"entities": [], "relations": []})
    for src, h in ((1, "aaa"), (1, "bbb"), (2, "ccc")):
        db.put_graph_batch_result(
            paths.state_db, source_id=src, input_hash=h, payload=payload
        )
    return vault


def test_clear_graph_cache_drops_one_sources_batches(tmp_path, monkeypatch) -> None:
    vault = _vault(tmp_path)
    monkeypatch.setenv("VAULT_ROOT", str(vault))
    paths = cfg.WikiPaths(vault)

    result = CliRunner().invoke(app, ["source", "clear-graph-cache", "1"])

    assert result.exit_code == 0, result.output
    assert "2" in result.output
    assert db.count_graph_batch_results(paths.state_db, 1) == 0
    assert db.count_graph_batch_results(paths.state_db, 2) == 1, "other sources untouched"


def test_clear_graph_cache_on_an_unknown_source_fails_loudly(tmp_path, monkeypatch) -> None:
    vault = _vault(tmp_path)
    monkeypatch.setenv("VAULT_ROOT", str(vault))

    result = CliRunner().invoke(app, ["source", "clear-graph-cache", "99"])

    assert result.exit_code == 1
    assert "99" in result.output


def test_clear_graph_cache_with_nothing_staged_is_not_an_error(tmp_path, monkeypatch) -> None:
    """A source that never staged anything is the normal case, not a failure."""
    vault = _vault(tmp_path)
    monkeypatch.setenv("VAULT_ROOT", str(vault))
    paths = cfg.WikiPaths(vault)
    db.delete_graph_batch_results(paths.state_db, 2)

    result = CliRunner().invoke(app, ["source", "clear-graph-cache", "2"])

    assert result.exit_code == 0, result.output
