"""ROADMAP B1: an empty database is not the same fact as an empty vault.

`state.sqlite` is machine-local, keyed by `sha256(resolved_vault_root)[:16]`, so
TWO ordinary events produce a brand-new empty database:

1. the repo's `.cache/` is deleted, moved, or not carried to a new machine;
2. the vault is renamed or moved — the key changes, so a different cache
   directory is minted.

In both cases `connect()` self-heals a fresh schema and `get_stats` returns
zeros, with nothing distinguishing that from a vault nobody has ingested yet.
Measured on the reference vault: the database is 287 MB and the vault carries
**89 MB of sync journal** — so the knowledge is *right there* and recoverable,
while `wiki status` would report an empty vault and invite a full re-ingest.

The signature is the same for both causes — empty DB, journals present — so one
check covers both, which is why they are fixed together.
"""

from __future__ import annotations

from pathlib import Path

from curator import config as cfg
from curator import db
from curator.db_sync import describe_recoverable_state


def _vault(tmp_path: Path) -> cfg.WikiPaths:
    paths = cfg.WikiPaths(tmp_path / "vault")
    paths.internal.mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    return paths


def _journal(paths: cfg.WikiPaths, name: str = "dev-abc123.jsonl", size: int = 4096) -> Path:
    sync_dir = paths.internal / "sync"
    sync_dir.mkdir(parents=True, exist_ok=True)
    path = sync_dir / name
    path.write_text('{"table":"sources"}\n' * max(1, size // 20), encoding="utf-8")
    return path


def test_empty_db_with_a_journal_is_reported_as_recoverable(tmp_path: Path) -> None:
    paths = _vault(tmp_path)
    journal = _journal(paths)

    message = describe_recoverable_state(paths)

    assert message is not None, "an empty DB beside a sync journal reported nothing"
    assert journal.name in message
    assert "wiki db import" in message, "the message must name the recovery command"


def test_a_genuinely_new_vault_is_not_warned_about(tmp_path: Path) -> None:
    """No journal means nothing was ever ingested here. Warning would train the
    user to ignore the message that matters."""
    assert describe_recoverable_state(_vault(tmp_path)) is None


def test_a_populated_db_is_not_warned_about(tmp_path: Path) -> None:
    """The mutation this test exists for: "journals exist -> warn" fires on EVERY
    healthy vault, because a healthy vault writes a journal on every auto-sync.
    Emptiness of the database is the load-bearing half of the condition."""
    paths = _vault(tmp_path)
    _journal(paths)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES ('04_Resources/a.md', 'h', 'md', 1, datetime('now'))"
        )

    assert describe_recoverable_state(paths) is None


def test_an_empty_journal_file_is_not_treated_as_recoverable(tmp_path: Path) -> None:
    """A zero-byte journal recovers nothing; promising otherwise sends the user
    to a command that will report 0 changes and look broken."""
    paths = _vault(tmp_path)
    (paths.internal / "sync").mkdir(parents=True, exist_ok=True)
    (paths.internal / "sync" / "dev-empty.jsonl").write_text("", encoding="utf-8")

    assert describe_recoverable_state(paths) is None


def test_wiki_status_surfaces_it(tmp_path: Path, monkeypatch) -> None:
    """Detection that nothing prints is not a fix. `wiki status` is where a user
    goes precisely when the numbers look wrong."""
    from typer.testing import CliRunner

    from curator.cli import app

    paths = _vault(tmp_path)
    cfg.save_config(paths, cfg.DEFAULT_CONFIG)
    _journal(paths)
    monkeypatch.setenv("VAULT_ROOT", str(paths.root))

    result = CliRunner().invoke(app, ["status"])
    assert result.exit_code == 0, result.stdout
    assert "wiki db import" in result.stdout, result.stdout


def test_wiki_status_json_carries_it_too(tmp_path: Path, monkeypatch) -> None:
    """The plugin dashboard reads --json; a warning only humans can see would
    leave the dashboard reporting a healthy empty vault."""
    import json as _json

    from typer.testing import CliRunner

    from curator.cli import app

    paths = _vault(tmp_path)
    cfg.save_config(paths, cfg.DEFAULT_CONFIG)
    _journal(paths)
    monkeypatch.setenv("VAULT_ROOT", str(paths.root))

    result = CliRunner().invoke(app, ["status", "--json"])
    assert result.exit_code == 0, result.stdout
    assert "wiki db import" in _json.loads(result.stdout)["recoverable_state"]
