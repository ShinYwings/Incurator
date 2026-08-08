"""Archiving a merged conflict file must survive a cross-filesystem move.

B2 / CAND-03. `_archive_conflict` moves the file OUT of the synced vault
(`<vault>/.curator/sync/`) INTO the repo-local cache
(`<repo>/.cache/vaults/<hash>/runtime/sync_conflicts/`). Those are two different
trees by design — the vault lives on synced storage (iCloud, Syncthing, a
network mount), the cache is local — so they are frequently on different
filesystems, where `Path.rename` raises `OSError(EXDEV)`.

That failure is not cosmetic: `autosync` turns it into an `AutosyncError`, the
conflict file stays in the sync dir, and every later run re-imports the same
file and fails again. One un-archivable file wedges sync for that vault
permanently — the "per-file error that wedges every retry" B2 exists to remove.
"""

from __future__ import annotations

import errno
from pathlib import Path

import pytest

from curator import db_sync


def _conflict(tmp_path: Path) -> tuple[Path, Path]:
    internal = tmp_path / "vault" / ".curator"
    (internal / "sync").mkdir(parents=True)
    cf = internal / "sync" / "dev-abc.sync-conflict-20260808.jsonl"
    cf.write_text('{"table":"sources"}\n', encoding="utf-8")
    return cf, internal


def test_archive_survives_a_cross_device_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cf, internal = _conflict(tmp_path)
    payload = cf.read_text(encoding="utf-8")

    # Simulate a filesystem boundary. `shutil.move` calls `os.rename` (NOT
    # `Path.rename`), so patching the wrong one makes this test pass whether or
    # not the fallback exists.
    import os as _os

    def _exdev(src, dst, *args, **kwargs) -> None:
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(_os, "rename", _exdev)
    monkeypatch.setattr(Path, "rename", lambda self, t: _exdev(self, t))

    db_sync._archive_conflict(cf, internal)

    assert not cf.exists(), "the conflict file was left in the synced dir"
    archived = list(
        (tmp_path / "vault").parent.rglob("sync_conflicts/*.jsonl")
    ) or list(Path(tmp_path).rglob("sync_conflicts/*.jsonl"))
    assert archived, "the conflict file was not archived anywhere"
    assert archived[0].read_text(encoding="utf-8") == payload, "content changed"


def test_archive_still_works_on_one_filesystem(tmp_path: Path) -> None:
    """The ordinary case must be unchanged."""
    cf, internal = _conflict(tmp_path)
    payload = cf.read_text(encoding="utf-8")

    db_sync._archive_conflict(cf, internal)

    assert not cf.exists()
    archived = list(Path(tmp_path).rglob("sync_conflicts/*.jsonl"))
    assert archived and archived[0].read_text(encoding="utf-8") == payload


def test_archive_does_not_clobber_an_earlier_file_of_the_same_name(
    tmp_path: Path,
) -> None:
    """Two conflicts with one name must not silently collapse to one."""
    cf, internal = _conflict(tmp_path)
    db_sync._archive_conflict(cf, internal)

    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text('{"table":"atoms"}\n', encoding="utf-8")
    db_sync._archive_conflict(cf, internal)

    archived = sorted(Path(tmp_path).rglob("sync_conflicts/*.jsonl"))
    assert len(archived) == 2, (
        f"expected both conflict files to survive, found {len(archived)}: "
        f"{[p.name for p in archived]}"
    )
