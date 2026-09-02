"""`grant_root` must name the folder the user has to grant — including itself.

It walks `path.parents` and never tests `path`. For the shape production hits —
a FILE inside a denied folder — that is correct, and it is the only shape the
July incident produced. But a Dashboard row is a ROOT, and asking which folder to
grant for a denied root returned nothing:

    probe(~/Downloads)                -> denied     grant_root -> None
    probe(~/Library/Mobile Documents) -> denied     grant_root -> None

Both verified live on the machine this was written on. The planned grant button
would have had nothing to open, on precisely the rows it exists for.

`probe` also follows symlinks (`os.open` does) while `Path.parents` does not, so
the two disagreed about what they were looking at.
"""

from __future__ import annotations

import os
import stat

import pytest

from curator import file_access


@pytest.fixture
def denied_dir(tmp_path):
    """A directory this process cannot read.

    POSIX mode, not TCC — they are different mechanisms and `probe` deliberately
    collapses both to DENIED, which is what makes this a usable stand-in for the
    branch under test. It is NOT a stand-in for the TCC propagation question.
    """
    d = tmp_path / "locked"
    d.mkdir()
    (d / "paper.pdf").write_text("x")
    d.chmod(0o000)
    yield d
    d.chmod(stat.S_IRWXU)


def test_a_denied_folder_asked_about_itself_names_itself(denied_dir) -> None:
    """The Dashboard case. Returning None here is what broke the grant button."""
    assert file_access.probe(denied_dir) is file_access.Reachability.DENIED
    assert file_access.grant_root(denied_dir) == denied_dir


def test_a_file_inside_a_denied_folder_still_names_the_folder(denied_dir) -> None:
    """The production case, unchanged. This is the shape the July incident hit."""
    assert file_access.grant_root(denied_dir / "paper.pdf") == denied_dir


def test_a_readable_path_names_nothing(tmp_path) -> None:
    f = tmp_path / "fine.md"
    f.write_text("readable")
    assert file_access.grant_root(f) is None
    assert file_access.grant_root(tmp_path) is None


def test_a_symlink_is_resolved_before_deciding(tmp_path, denied_dir) -> None:
    """`probe` follows symlinks and `Path.parents` does not.

    Without resolving, the two disagree: probe reports the target's denial while
    grant_root walks the LINK's parents, which are readable, and returns None.
    """
    link = tmp_path / "link-to-locked"
    os.symlink(denied_dir, link)

    assert file_access.probe(link) is file_access.Reachability.DENIED
    assert file_access.grant_root(link) == denied_dir


def test_a_missing_path_names_nothing(tmp_path) -> None:
    """Absent is not denied, and offering a folder to grant would be a lie."""
    assert file_access.grant_root(tmp_path / "nope.pdf") is None
