"""XC-1 slice 1: error-handling for ingest_raw.py best-effort resolvers.

Key guarantee (review-flagged): the external-source-path resolver must degrade
to the original source on any failure — including a transient DB lock — and the
failure must be logged instead of swallowed.

**One carve-out, added in v0.61.0**: a `ParserAccessDenied` propagates instead of
degrading. The guarantee exists because a resolver failure means "no external
file here, use the note", and degrading is then correct. A denial means the
opposite — the file IS there and we were refused — so degrading would ingest the
stub's frontmatter and report SUCCESS, turning a 673-page book into four lines of
metadata without telling anyone. That is worse than the crash the rule prevents,
and it is not hypothetical: it happened while implementing v0.61.0 and was caught
by running the code, not by a test.

The "never crash the caller" half still holds in practice. All four call sites
handle it: `ingest_raw.py:1437` and `:2053` sit inside broader `except`s, and
`ParserAccessDenied` subclasses `ParserError` so existing handlers catch it;
`pipeline/compile.py` and `mcp/server.py` each wrap their call. See
SYSTEM_BEHAVIOR §12.3.
"""

import logging
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from curator import ingest_raw


def test_resolve_reference_source_falls_back_and_logs_on_db_error(tmp_path, monkeypatch, caplog):
    src = tmp_path / "ref.md"
    src.write_text("---\ntype: reference\nzotero_key: ABC\n---\nbody\n", encoding="utf-8")
    paths = SimpleNamespace(root=tmp_path, state_db=tmp_path / "state.sqlite")

    monkeypatch.delenv("ZOTERO_BASE_PATH", raising=False)
    monkeypatch.setattr(ingest_raw.cfg, "load_config", lambda p: {})

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(ingest_raw.db, "get_source_row", boom)

    with caplog.at_level(logging.WARNING, logger="curator.ingest_raw"):
        result = ingest_raw._resolve_reference_source(paths, src)

    # Reviewer's scenario: a transient DB lock must NOT crash; fall back to source.
    assert result == src
    assert any("resolution failed" in r.message for r in caplog.records)


def test_safe_vault_subdir_returns_none_and_logs_on_error(tmp_path, monkeypatch, caplog):
    paths = SimpleNamespace(root=tmp_path)
    orig_resolve = Path.resolve

    def boom(self, *args, **kwargs):
        raise OSError("resolve failed")

    monkeypatch.setattr(Path, "resolve", boom)

    with caplog.at_level(logging.DEBUG, logger="curator.ingest_raw"):
        assert ingest_raw._safe_vault_subdir(paths, "sub/dir") is None

    # restore so caplog teardown / other paths aren't affected
    monkeypatch.setattr(Path, "resolve", orig_resolve)
    assert any("subdir validation failed" in r.message for r in caplog.records)
