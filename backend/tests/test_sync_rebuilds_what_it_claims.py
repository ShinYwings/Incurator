"""ROADMAP B1: `wiki sync` said it rebuilds four files and rebuilt two.

`sync.finalize_routing_tables` is documented — in its own docstring, in
`sync.py`'s module docstring, in the `wiki sync` CLI help, and in the CLI table
in `CLAUDE.md` ("Verify DAG integrity, rebuild index/ledger") — as rebuilding
`index.md`, `ledger.md`, `log.md` and `overview.md`.

It called `rebuild_index` and `append_log_entry`. `ledger.md` and `overview.md`
were never touched by `wiki sync` at any point in its life; only `wiki build`
wrote them, from its own Phase D.

So a user who ran `wiki sync` after a manual correction got an `index.md` that
matched the vault and a `ledger.md` still reporting the counts from the last
build. Both files claim "Auto-maintained by the Curator engine" in their own
header, which is exactly the kind of stale-but-authoritative artefact this
project keeps losing time to.
"""

from __future__ import annotations

from pathlib import Path

from curator import config as cfg
from curator import db, sync


def _vault(tmp_path: Path) -> cfg.WikiPaths:
    paths = cfg.WikiPaths(tmp_path / "vault")
    paths.internal.mkdir(parents=True, exist_ok=True)
    cfg.save_config(paths, cfg.DEFAULT_CONFIG)
    db.init_db(paths.state_db)
    return paths


def test_finalize_writes_every_file_its_docstring_names(tmp_path: Path) -> None:
    paths = _vault(tmp_path)
    for f in (paths.index, paths.ledger, paths.log, paths.overview):
        assert not f.exists()

    sync.finalize_routing_tables(paths)

    missing = [
        f.name
        for f in (paths.index, paths.ledger, paths.log, paths.overview)
        if not f.exists()
    ]
    assert not missing, f"finalize_routing_tables claims to rebuild {missing} and does not"


def test_the_ledger_reflects_the_state_at_sync_time_not_at_last_build(
    tmp_path: Path,
) -> None:
    """The failure a user actually sees: correct a source, run `wiki sync`, and
    read counts from whenever `wiki build` last ran."""
    paths = _vault(tmp_path)
    sync.finalize_routing_tables(paths)
    assert "| Sources curated | 0 |" in paths.ledger.read_text(encoding="utf-8")

    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at, status) "
            "VALUES ('04_Resources/a.md', 'h', 'md', 1, datetime('now'), 'curated')"
        )
    sync.finalize_routing_tables(paths)
    assert "| Sources curated | 1 |" in paths.ledger.read_text(encoding="utf-8")
