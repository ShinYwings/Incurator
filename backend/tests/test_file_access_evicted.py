"""A file iCloud has not downloaded is not a file you lack permission to read.

`probe` reached DENIED only through `except PermissionError`. Everything else —
including a dataless placeholder that macOS's File Provider has evicted to
iCloud-only — fell to MISSING and surfaced as "File not found".

That matters because the folder-permission work is gated on telling the user
which folder to grant. For an evicted file there is no folder to grant: access
was never revoked, the bytes are simply not on this machine. Sending someone to
System Settings for that is the exact failure `grant_root`'s own docstring was
written about — it once named `~/Library/CloudStorage`, which was readable, and
the setting was never the problem.

Found by the Arena's red team, which was asked to look for the case this feature
would misdiagnose.
"""

from __future__ import annotations

import errno
import os

from curator import file_access


def test_a_normal_missing_file_is_still_missing(tmp_path) -> None:
    assert file_access.probe(tmp_path / "nope.pdf") is file_access.Reachability.MISSING


def test_a_readable_file_is_ok(tmp_path) -> None:
    f = tmp_path / "here.md"
    f.write_text("bytes")
    assert file_access.probe(f) is file_access.Reachability.OK


def test_an_evicted_placeholder_is_not_reported_as_missing(tmp_path, monkeypatch) -> None:
    """ENODATA/EDEADLK is how a dataless file fails when it cannot materialise.

    It exists, its metadata is there, and the read is what fails — which is why
    `stat`-based checks call it present and the read calls it gone.
    """
    f = tmp_path / "evicted.pdf"
    f.write_text("placeholder")

    real_read = os.read

    def _no_data(fd, n):  # type: ignore[no-untyped-def]
        raise OSError(errno.ENODATA, "attribute not found")

    monkeypatch.setattr(os, "read", _no_data)
    try:
        verdict = file_access.probe(f)
    finally:
        monkeypatch.setattr(os, "read", real_read)

    assert verdict is file_access.Reachability.NOT_DOWNLOADED


def test_an_evicted_file_offers_no_folder_to_grant(tmp_path, monkeypatch) -> None:
    """The point of separating it: a picker would be a no-op here."""
    f = tmp_path / "evicted.pdf"
    f.write_text("placeholder")

    def _no_data(fd, n):  # type: ignore[no-untyped-def]
        raise OSError(errno.ENODATA, "attribute not found")

    monkeypatch.setattr(os, "read", _no_data)
    assert file_access.grant_root(f) is None


def test_the_reason_a_user_is_shown_says_download_not_permission(tmp_path, monkeypatch) -> None:
    f = tmp_path / "evicted.pdf"
    f.write_text("placeholder")

    def _no_data(fd, n):  # type: ignore[no-untyped-def]
        raise OSError(errno.ENODATA, "attribute not found")

    monkeypatch.setattr(os, "read", _no_data)
    reason = file_access.describe(f)

    assert "download" in reason.lower()
    assert "permission" not in reason.lower()


def test_the_parser_refuses_an_evicted_file_with_the_right_reason(
    tmp_path, monkeypatch
) -> None:
    """It used to fall through the dispatch guard entirely.

    `NOT_DOWNLOADED` matched neither case, so the file reached a parser that
    failed on empty content and blamed the format. Saying "File not found" would
    be worse still: the file IS there, and the user would go looking for a
    deletion that never happened.
    """
    import pytest

    from curator import parsers

    f = tmp_path / "evicted.pdf"
    f.write_text("placeholder")

    def _no_data(fd, n):  # type: ignore[no-untyped-def]
        raise OSError(errno.ENODATA, "attribute not found")

    monkeypatch.setattr(os, "read", _no_data)

    with pytest.raises(parsers.ParserError) as caught:
        parsers.parse(f)

    message = str(caught.value).lower()
    assert "not downloaded" in message
    assert "not found" not in message
    assert not isinstance(caught.value, parsers.ParserAccessDenied)
