"""One file is one source, whichever Unicode form its path arrives in.

Measured on the live vault 2026-08-31: 18 of 50 stored relpaths (36%) are in NFD,
the form macOS `readdir` returns, while nearly all tooling and all typed text
produce NFC. One pair already collides — the same file registered twice, both
rows `curated`, both carrying the same `content_hash`, its knowledge split across
two source ids.

`sources.relpath` is the UNIQUE key and registration looks up `WHERE relpath = ?`,
so two byte-different strings naming one file are two sources and nothing in the
schema says otherwise. `db_sync` then uses that same column to reconcile peers
(`db_sync.py:1686`), so two devices in different forms do not collide at all —
the peer's child rows attach to a fresh duplicate. That makes this a duplication
mechanism, not a local annoyance.
"""

from __future__ import annotations

import unicodedata

from curator import db
from curator import source_identity as si

# "Plücker" and "Přibyl" — the real path from the user's vault, which is exactly
# where this was found.
NFC = "04_Resources/References/Plücker Přibyl.md"
NFD = unicodedata.normalize("NFD", NFC)


def test_the_two_forms_really_are_different_strings() -> None:
    """Guard the premise. If these ever compare equal the rest proves nothing."""
    assert NFC != NFD
    assert unicodedata.normalize("NFC", NFD) == NFC


def test_normalisation_folds_the_macos_form_onto_the_typed_one() -> None:
    assert si.normalize_relpath(NFD) == NFC
    assert si.normalize_relpath(NFC) == NFC


def test_normalisation_leaves_ascii_and_empty_alone() -> None:
    for value in ("03_Notes/plain.md", "", "a/b/c.pdf"):
        assert si.normalize_relpath(value) == value


def test_normalisation_is_idempotent() -> None:
    once = si.normalize_relpath(NFD)
    assert si.normalize_relpath(once) == once


def test_the_same_file_in_two_forms_registers_once(tmp_path) -> None:
    """The whole point, at the database boundary."""
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        for form in (NFD, NFC):
            if si.find_source_by_relpath(conn, form) is None:
                conn.execute(
                    "INSERT INTO sources (relpath, content_hash, file_type, bytes,"
                    " added_at, status) VALUES (?,?,?,?,?,?)",
                    (si.normalize_relpath(form), "h1", "md", 10, "2026-01-01", "pending"),
                )

        rows = conn.execute("SELECT relpath FROM sources").fetchall()
        assert len(rows) == 1, "the same file registered twice"
        assert rows[0][0] == NFC


def test_a_lookup_in_either_form_finds_the_one_row(tmp_path) -> None:
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes,"
            " added_at, status) VALUES (?,?,?,?,?,?)",
            (NFC, "h1", "md", 10, "2026-01-01", "pending"),
        )

        assert si.find_source_by_relpath(conn, NFD) is not None
        assert si.find_source_by_relpath(conn, NFC) is not None
