"""`wiki plugin access` says which folders Incurator can read, and which it cannot.

The backend has known the answer since `file_access` existed — `probe` classifies
a path and `grant_root` names the folder to grant — and `grep plugin/src` for any
of it returned nothing. So a user whose PDF store moved into a cloud folder saw
sources fail with no way to learn why, which is the incident that produced this
release.

This is the one place that logic lives. The plugin renders rows; it does not
decide what a root is or whether it is readable, because a second implementation
in TypeScript is a second thing to drift.

The trap this test pins: `probe` opens a path as a FILE, so a perfectly readable
DIRECTORY comes back MISSING. A report built on the raw verdict would call every
healthy root missing.
"""

from __future__ import annotations

import stat

import pytest

from curator import config as cfg
from curator.plugin_api import access as access_api


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    (root / "04_Resources").mkdir(parents=True)
    (root / ".curator").mkdir()
    return root


def test_a_readable_directory_is_reported_readable_not_missing(vault) -> None:
    """The trap. `probe` on a directory returns MISSING; the report must not."""
    rows = access_api.access_report(cfg.WikiPaths(vault))
    vault_row = next(r for r in rows if r["path"] == str(vault.resolve()))
    assert vault_row["state"] == "ok"
    assert vault_row["grant_folder"] == ""


def test_a_denied_root_names_the_folder_to_grant(vault, tmp_path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o000)
    try:
        rows = access_api.access_report(
            cfg.WikiPaths(vault), extra_roots={"zotero_attachments": locked}
        )
        row = next(r for r in rows if r["path"] == str(locked.resolve()))
        assert row["state"] == "denied"
        assert row["grant_folder"] == str(locked.resolve()), (
            "a denied ROOT must name itself — returning nothing is what left the "
            "grant button with nothing to open"
        )
    finally:
        locked.chmod(stat.S_IRWXU)


def test_every_row_says_what_it_is(vault) -> None:
    """A path alone is not actionable; the user needs to know why it matters."""
    rows = access_api.access_report(cfg.WikiPaths(vault))
    assert rows, "the vault root alone should produce a row"
    for row in rows:
        assert row["label"], row
        assert row["path"], row
        assert row["state"] in {"ok", "denied", "missing", "not_downloaded"}


def test_a_root_that_is_not_there_is_omitted(vault, tmp_path) -> None:
    """A folder that does not exist is not a permission problem.

    A row saying "missing" about a folder the user never set up is noise, and
    noise is what stops someone reading the one row that matters.
    """
    absent = tmp_path / "never-created"
    rows = access_api.access_report(
        cfg.WikiPaths(vault), extra_roots={"Ghost": absent}
    )
    assert not any(r["path"] == str(absent) for r in rows)


def test_a_missing_vault_is_still_reported(tmp_path) -> None:
    """The one exception: if the vault itself is gone, say so."""
    gone = tmp_path / "no-such-vault"
    rows = access_api.access_report(cfg.WikiPaths(gone))
    assert any(r["path"] == str(gone) for r in rows)


def test_the_report_is_deduplicated(vault) -> None:
    """The same folder configured twice is one row, not two."""
    rows = access_api.access_report(
        cfg.WikiPaths(vault),
        extra_roots={"a": vault, "b": vault},
    )
    paths = [r["path"] for r in rows]
    assert len(paths) == len(set(paths))
