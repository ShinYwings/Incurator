"""A source path is judged by `probe`, never by a metadata check.

`Path.exists()`, `Path.is_file()` and `os.access(R_OK)` all answer from metadata,
and under macOS TCC the metadata is readable while the bytes are not. So they
either lie — `os.access` returns True for a file that cannot be opened — or they
raise `PermissionError` from an ancestor folder instead of returning False.

This was fixed once, at `add_file`'s guard, and the identical line was still
sitting in `safe_import_destination` and `import_source_file`. Fixing one call
site and leaving its siblings is the defect shape this repo has paid for in four
separate releases; the point of a guard is that the fifth cannot be silent.

`probe` is the only predicate that agrees with reality, and it distinguishes the
three outcomes that matter: denied (name a folder to grant), not downloaded
(iCloud has the bytes), and genuinely absent.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "curator"

METADATA_CHECK = re.compile(
    r"\bnot\s+(\w+)\.exists\(\)\s+or\s+not\s+\1\.is_file\(\)|os\.access\("
)

#: Files that legitimately test paths this process created or owns — a repo
#: cache dir, a config file, a temp output — where TCC cannot apply.
EXEMPT = {
    SRC / "file_access.py",
    # `wiki init` checks WRITE permission on the vault the user just named. That
    # is a different question with a different remedy — `probe` answers "can I
    # read these bytes", and a vault you cannot write to is not a TCC-denied
    # source. Judged and recorded rather than swept into the guard.
    SRC / "commands" / "core.py",
}


def test_no_source_path_is_judged_by_a_metadata_check() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if path in EXEMPT:
            continue
        text = path.read_text(encoding="utf-8")
        for match in METADATA_CHECK.finditer(text):
            line = text[: match.start()].count("\n") + 1
            # Tight, and only FORWARD. A generous window meant any probe
            # anywhere nearby excused the check — verified by injecting a real
            # violation next to an existing probe and watching the guard stay
            # green. The metadata test is acceptable only as a pre-filter whose
            # verdict a probe immediately overrides, so look at the next two
            # lines and nothing else.
            after = text[match.end() : match.end() + 160]
            if "probe(" in after:
                continue
            offenders.append(f"{path.relative_to(SRC)}:{line}")

    assert not offenders, (
        "these decide whether a source is readable from metadata, which lies "
        "under macOS TCC — a denied file either crashes the caller or is "
        "reported as 'File not found': " + ", ".join(offenders)
    )


def test_the_guard_can_actually_fail() -> None:
    """A guard that cannot fail is decoration.

    v0.79.0 shipped a prompt-budget gate that had been measuring comments for
    releases, and v0.78.0's first guard could not see writes at all.
    """
    sample = "if not source.exists() or not source.is_file():\n    raise"
    assert METADATA_CHECK.search(sample) is not None
    assert "probe" not in sample
