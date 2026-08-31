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


def _seed(conn, relpath: str, *, content_hash: str = "h1") -> int:
    cur = conn.execute(
        "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at,"
        " status) VALUES (?,?,?,?,?,?)",
        (relpath, content_hash, "md", 10, "2026-01-01", "curated"),
    )
    return int(cur.lastrowid)


def test_stored_paths_are_rewritten_into_canonical_form(tmp_path) -> None:
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        _seed(conn, NFD)
        rewritten, skipped = si.normalize_stored_relpaths(conn)
        assert (rewritten, skipped) == (1, 0)
        assert conn.execute("SELECT relpath FROM sources").fetchone()[0] == NFC


def test_normalising_twice_changes_nothing_the_second_time(tmp_path) -> None:
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        _seed(conn, NFD)
        si.normalize_stored_relpaths(conn)
        assert si.normalize_stored_relpaths(conn) == (0, 0)


def test_a_collision_is_skipped_not_forced(tmp_path) -> None:
    """Rewriting into a path another row already holds violates UNIQUE.

    More importantly, resolving it means merging the user's data, which is not a
    thing that happens as a side effect of opening the database.
    """
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        _seed(conn, NFC)
        _seed(conn, NFD)
        rewritten, skipped = si.normalize_stored_relpaths(conn)
        assert (rewritten, skipped) == (0, 1)
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 2


def test_a_collision_is_reported(tmp_path) -> None:
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        first = _seed(conn, NFC)
        second = _seed(conn, NFD)
        groups = si.relpath_collisions(conn)
        assert len(groups) == 1
        assert [row["id"] for row in groups[0]] == [first, second]


def test_the_merge_plan_changes_nothing_until_applied(tmp_path) -> None:
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        keep = _seed(conn, NFC)
        drop = _seed(conn, NFD)
        conn.execute(
            "INSERT INTO source_pages (source_id, wiki_path, operation, at)"
            " VALUES (?,?,?,?)",
            (drop, "01_Contexts/CTX-x.md", "created", "2026-01-01"),
        )
        plan = si.merge_relpath_collision(conn, si.relpath_collisions(conn)[0])

        assert plan["keep"] == keep and plan["remove"] == [drop]
        assert plan["rows_moved"].get("source_pages") == 1
        assert plan["applied"] is False
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 2


def test_applying_the_merge_keeps_the_oldest_and_moves_its_children(tmp_path) -> None:
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        keep = _seed(conn, NFC)
        drop = _seed(conn, NFD)
        conn.execute(
            "INSERT INTO source_pages (source_id, wiki_path, operation, at)"
            " VALUES (?,?,?,?)",
            (drop, "01_Contexts/CTX-x.md", "created", "2026-01-01"),
        )
        si.merge_relpath_collision(conn, si.relpath_collisions(conn)[0], apply=True)

        rows = conn.execute("SELECT id, relpath FROM sources").fetchall()
        assert len(rows) == 1
        assert rows[0]["id"] == keep and rows[0]["relpath"] == NFC
        owner = conn.execute("SELECT source_id FROM source_pages").fetchone()[0]
        assert owner == keep, "the surviving source did not inherit the page"


def test_a_merge_is_refused_when_the_bytes_differ(tmp_path) -> None:
    """Two paths that normalise together but hold different content are not one
    file, and merging them would destroy one. This is the plan's stop condition.
    """
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        _seed(conn, NFC, content_hash="aaa")
        _seed(conn, NFD, content_hash="bbb")
        plan = si.merge_relpath_collision(
            conn, si.relpath_collisions(conn)[0], apply=True
        )
        assert plan["refused"] is True
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 2


def test_child_tables_are_read_from_the_schema(tmp_path) -> None:
    """A hardcoded list goes stale, and the table it forgets orphans rows."""
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        tables = si.source_child_tables(conn)
        for expected in ("source_pages", "source_spans", "knowledge_units"):
            assert expected in tables
        assert "sources" not in tables


def test_the_merge_reaches_inside_json_source_id_arrays(tmp_path) -> None:
    """A source id also lives inside JSON arrays, where no column remap reaches.

    `prompt_runs.source_ids` is the known case. PR #190 found the identical blind
    spot on the cross-device import path and built `_SOURCE_ID_ARRAY_REFS` for it;
    the first draft of this merge discovered child tables by looking for a literal
    `source_id` COLUMN, so it could not see that table at all and left rows naming
    a source it had just deleted.

    Caught by review, and confirmed against the live vault after the merge had
    already been applied: two rows still named the removed id.
    """
    import json

    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        keep = _seed(conn, NFC)
        drop = _seed(conn, NFD)
        conn.execute(
            "INSERT INTO prompt_runs (trace_id, prompt_id, prompt_version, family,"
            " role, source_ids, input_hash, output_hash, model_provider,"
            " model_name, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("t1", "p1", "1", "f", "r", json.dumps([drop, 99]), "i", "o", "p", "m", "2026-01-01"),
        )
        # A row already naming the survivor must not end up naming it twice.
        conn.execute(
            "INSERT INTO prompt_runs (trace_id, prompt_id, prompt_version, family,"
            " role, source_ids, input_hash, output_hash, model_provider,"
            " model_name, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("t2", "p1", "1", "f", "r", json.dumps([keep, drop]), "i", "o", "p", "m", "2026-01-01"),
        )

        plan = si.merge_relpath_collision(
            conn, si.relpath_collisions(conn)[0], apply=True
        )
        assert plan["json_arrays_rewritten"] == 2

        rows = [
            json.loads(r[0])
            for r in conn.execute(
                "SELECT source_ids FROM prompt_runs ORDER BY trace_id"
            )
        ]
        assert rows[0] == [keep, 99], "the removed id was not repointed"
        assert rows[1] == [keep], "the survivor was named twice"
        assert not any(drop in ids for ids in rows)
