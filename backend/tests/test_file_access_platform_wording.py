"""A denial says the same thing everywhere; the FIX does not.

macOS denials are usually TCC, granted through a system dialog. On Linux the
identical verdict is filesystem permissions — there is no grant dialog, opening
the folder grants nothing, and telling someone to allow it "when macOS asks"
sends them waiting for a prompt that will never come.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from curator import file_access


@pytest.fixture
def denied_dir(tmp_path: Path) -> Path:
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "paper.pdf").write_text("x")
    os.chmod(locked, 0o000)
    yield locked / "paper.pdf"
    os.chmod(locked, 0o755)


def test_macos_denial_names_the_grant(monkeypatch: pytest.MonkeyPatch, denied_dir: Path) -> None:
    monkeypatch.setattr(file_access.sys, "platform", "darwin")
    said = file_access.describe(denied_dir)
    assert "Grant access to" in said


def test_linux_denial_does_not_invent_a_grant_dialog(
    monkeypatch: pytest.MonkeyPatch, denied_dir: Path
) -> None:
    monkeypatch.setattr(file_access.sys, "platform", "linux")
    said = file_access.describe(denied_dir)
    assert "Grant access to" not in said
    assert "readable by the user running" in said
    # It must still name the folder — that is the whole point of grant_root.
    assert str(denied_dir.parent) in said


def test_linux_eviction_does_not_send_the_user_to_finder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(file_access.sys, "platform", "linux")
    monkeypatch.setattr(
        file_access, "probe", lambda _p: file_access.Reachability.NOT_DOWNLOADED
    )
    said = file_access.describe(tmp_path / "online_only.pdf")
    assert "Finder" not in said
    assert "iCloud" not in said
    assert "cloud client" in said
