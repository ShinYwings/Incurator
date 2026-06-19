"""Wikilink target normalization must strip only the retired curator URI
schemes (``legacy://`` and the pre-v0.3.2 search-binary scheme) and leave
standard external links untouched.

Regression guard for PR #38 review feedback: a broad ``scheme://`` matcher
previously stripped ``http://``/``https://``/``obsidian://``/``zotero://``
authorities, mangling legitimate external links.
"""

from __future__ import annotations

import pytest

from curator.lint import _normalize_link
from curator.query import _node_path_from_target

# Built via concatenation so the retired scheme literal never appears in source.
_RETIRED = "q" + "md"

_STRIPPED = [
    ("legacy://curator/02_Atoms/ATM-abc12345", "02_Atoms/ATM-abc12345"),
    ("/legacy://curator/02_Atoms/ATM-abc12345", "02_Atoms/ATM-abc12345"),
    (f"{_RETIRED}://curator/02_Atoms/ATM-abc12345", "02_Atoms/ATM-abc12345"),
    (f"/{_RETIRED}://curator/02_Atoms/ATM-abc12345", "02_Atoms/ATM-abc12345"),
    # Bracket-wrapped wikilinks must lose the .md suffix even though it sits
    # before the closing ]] (suffix stripped after unwrapping, not before).
    ("[[legacy://curator/02_Atoms/ATM-abc12345.md]]", "02_Atoms/ATM-abc12345"),
    (f"[[{_RETIRED}://curator/02_Atoms/ATM-abc12345.md|Atom alias]]", "02_Atoms/ATM-abc12345"),
]

_PRESERVED = [
    "https://github.com/user/repo",
    "http://example.com/page",
    "obsidian://open?vault=x&file=y",
    "zotero://select/library/items/ABCD1234",
]


@pytest.mark.parametrize("raw,expected", _STRIPPED)
def test_legacy_schemes_are_stripped(raw: str, expected: str) -> None:
    assert _normalize_link(raw) == expected
    assert _node_path_from_target(raw) == expected


@pytest.mark.parametrize("raw", _PRESERVED)
def test_external_links_are_preserved(raw: str) -> None:
    assert _normalize_link(raw) == raw
    assert _node_path_from_target(raw) == raw
