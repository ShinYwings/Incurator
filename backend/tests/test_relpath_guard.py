"""Every comparison against `sources.relpath` goes through the normaliser.

Not a style rule. `sources.relpath` is the UNIQUE key AND the column `db_sync`
reconciles peers through, so a lookup that binds a raw path is a lookup that
misses an existing row and creates a duplicate. One such site is enough: the
measured damage was the same file registered twice, both rows `curated`, its
knowledge split across two source ids.

v0.77.0 shipped four separate cases of a fix applied at one call site and
silently missing its sibling. This release has eight sites. A test is cheaper
than remembering.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "curator"

# The module that DEFINES the boundary is allowed to touch the column raw.
# The module that DEFINES the boundary. It lives outside `db/` because that
# whole package is pinned by content hash in the D2 holdout record, which freezes
# a retrieval evaluation against specific code — adding a helper there, or even a
# re-export, silently invalidates a result that has nothing to do with paths.
EXEMPT = {
    # The module that DEFINES the boundary. It lives outside `db/` because that
    # whole package is pinned by content hash in the D2 holdout record, which
    # freezes a retrieval evaluation against specific code — adding a helper
    # there, or even a re-export, silently invalidates a result that has nothing
    # to do with paths.
    SRC / "source_identity.py",
    # `db/sources.py` is itself frozen by that record, so its one unnormalised
    # comparison cannot be edited here. Judged and recorded rather than waved
    # through: it is a READ-ONLY lookup that already falls back to content_hash
    # on a miss, so a path in the other form degrades to the hash path instead of
    # registering a duplicate. No write site depends on it.
    #
    # Close it when the freeze next lifts. Until then this exemption is the
    # honest statement of a known gap, not a hole in the guard.
    SRC / "db" / "sources.py",
}

RELPATH_SQL = re.compile(r"WHERE\s+relpath\s*=", re.I)


def _statement_window(text: str, at: int) -> str:
    """The SQL line plus the parameter binding that follows it.

    The normalisation lives in the bound value, one or more lines below the SQL
    string, so a line-scoped check would report every site as unguarded.
    """
    start = text.rfind("\n", 0, max(0, at - 400))
    end = text.find(").fetchone()", at)
    if end == -1:
        end = text.find(")", text.find("(", at))
    return text[max(0, start) : end + 40 if end != -1 else at + 600]


def test_every_relpath_comparison_normalises_its_argument() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if path in EXEMPT:
            continue
        text = path.read_text(encoding="utf-8")
        for match in RELPATH_SQL.finditer(text):
            window = _statement_window(text, match.start())
            if "normalize_relpath" in window:
                continue
            line = text[: match.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(SRC)}:{line}")

    assert not offenders, (
        "these compare against sources.relpath without normalising the bound "
        "value, so a path in the other Unicode form will miss the existing row "
        "and register a duplicate: " + ", ".join(offenders)
    )


def test_the_insert_stores_the_canonical_form() -> None:
    text = (SRC / "ingest_raw.py").read_text(encoding="utf-8")
    insert_at = text.find("INSERT INTO sources (relpath")
    assert insert_at != -1, "the source insert moved; this guard needs updating"
    assert "normalize_relpath(relpath)" in text[insert_at : insert_at + 900], (
        "the registration insert stores the path as given, so the macOS form "
        "and the typed form become two rows"
    )


def test_the_guard_can_actually_fail() -> None:
    """A guard that cannot fail is decoration.

    v0.77.0 found a prompt-budget gate that had been measuring comments for
    releases while reporting a number nobody could act on.
    """
    sample = 'conn.execute("SELECT id FROM sources WHERE relpath = ?", (raw,))'
    assert RELPATH_SQL.search(sample) is not None
    assert "normalize_relpath" not in sample


INIT_DB = re.compile(r"^(\s*)db\.init_db\(", re.M)


def test_every_init_db_is_followed_by_canonicalisation() -> None:
    """Opening the database must leave its paths in the form lookups use.

    Lookups normalise as of v0.78.0, so a row still stored in the macOS form is
    unreachable by its own path — and the next ingest of that file would not find
    it and would register a SECOND row. Normalising the reads without normalising
    what is already stored manufactures the very duplicates this release removes.

    The pairing cannot live inside `db.init_db` itself: `db/schema.py` is pinned
    by content hash in the D2 holdout record. So it is enforced here instead, and
    the four call sites cannot quietly become three.
    """
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in INIT_DB.finditer(text):
            following = text[match.end() : match.end() + 400]
            if "ensure_canonical_relpaths" in following:
                continue
            line = text[: match.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(SRC)}:{line}")

    assert not offenders, (
        "these open the state database without canonicalising its stored paths, "
        "so a pre-existing row in the other Unicode form stays unreachable by "
        "path and the next ingest registers a duplicate: " + ", ".join(offenders)
    )


def test_the_cli_gate_canonicalises_before_any_command_touches_sources() -> None:
    """`_resolve_root_or_die` is the one gate every vault-opening command passes.

    Pairing canonicalisation with `db.init_db` alone was not enough, and that was
    found by applying the migration to a real vault and then checking: `wiki add`
    — the command that actually registers sources — never calls `init_db`. So the
    ingest path kept reading stale forms, a lookup normalised past the stored NFD
    row, and the next add would have written a SECOND row. The change would have
    manufactured the duplicates it exists to remove.
    """
    text = (SRC / "commands" / "common.py").read_text(encoding="utf-8")
    gate = text.find("def _resolve_root_or_die(")
    assert gate != -1, "the CLI root gate moved; this guard needs updating"
    body = text[gate : gate + 700]
    assert "_canonicalise_once" in body, (
        "the CLI root gate no longer canonicalises stored source paths, so a "
        "vault holding pre-v0.78.0 NFD paths will register duplicates on its "
        "next ingest"
    )
