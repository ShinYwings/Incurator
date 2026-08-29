"""D1b: a delete on one device silently fails to apply on another.

`claim_supports` and `entity_resolution_lineage` put a raw, DEVICE-LOCAL id into
their composite tombstone token — `source_span_id` and `origin_entity_id`. The
token is computed at deletion time, on the deleting device, from that device's
own surrogate ids.

`source_pages`/`source_pdf_pages` do not have this problem: their specs transport
`source_sync_key`, a value both devices agree on, instead of the local
`source_id`.

So when device A deletes a `claim_supports` row, the tombstone names A's span id.
Device B holds the same span — same source, same content hash — under its own id.
`_apply_tombstone` builds a WHERE clause from the token, matches zero rows, and
reports the tombstone as applied. B's copy survives. Nothing says so.

v0.72.0's remap does NOT reach this. That pass repairs references BETWEEN rows
after an import; a tombstone token is minted before any import exists.

These tests assert the observable consequence — the row is still there after the
delete was synced — rather than any particular fix.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from curator import db
from curator.db_sync import export_knowledge, import_knowledge, record_row_tombstone_on_connection


@pytest.fixture()
def device(tmp_path: Path):
    def _make(name: str) -> Path:
        p = tmp_path / name / "state.sqlite"
        p.parent.mkdir(parents=True, exist_ok=True)
        db.init_db(p)
        with db.connect(p) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes,"
                " added_at, last_ingested) VALUES (?, ?, ?, ?, ?, ?)",
                ("03_Notes/paper.md", "abc123", "md", 100,
                 "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
            )
        return p

    return _make


def _seed_span_and_support(path: Path, span_id: str) -> None:
    """The same span (same source, same content hash) under a device-local id,
    plus a claim_supports row citing it."""
    with db.connect(path) as conn:
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type,"
            " content_hash, text_preview, start_char, end_char, created_at)"
            " VALUES (?, 1, ?, 'paragraph', ?, ?, 0, 10, ?)",
            (span_id, "03_Notes/paper.md", "hash-identical", "same text",
             "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO knowledge_units (id, unit_type, canonical_name, statement,"
            " source_span_ids, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("KNU-11111111", "claim", "A claim", "A claim.", "[]",
             "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO claim_supports (knowledge_unit_id, source_span_id,"
            " support_role, support_status, evidence_hash, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("KNU-11111111", span_id, "primary", "unchecked", "hash-identical",
             "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )


def _support_count(path: Path) -> int:
    with db.connect(path) as conn:
        return conn.execute("SELECT COUNT(*) FROM claim_supports").fetchone()[0]


def test_deleting_a_support_on_one_device_deletes_it_on_the_other(
    device, tmp_path: Path
) -> None:
    """The core D1b damage, stated as the user would see it.

    Both devices independently extracted the same span, so each holds it under
    its own id. A deletes the support row and syncs. B must not still have it.
    """
    a, b = device("a"), device("b")
    _seed_span_and_support(a, "SPAN-aaaaaaaa")
    _seed_span_and_support(b, "SPAN-bbbbbbbb")
    assert _support_count(b) == 1

    with db.connect(a) as conn:
        row = conn.execute("SELECT * FROM claim_supports").fetchone()
        record_row_tombstone_on_connection(conn, "claim_supports", dict(row))
        conn.execute("DELETE FROM claim_supports")

    export_path = tmp_path / "a.json"
    export_knowledge(a, export_path)
    import_knowledge(b, export_path)

    assert _support_count(b) == 0, (
        "the delete synced but did not apply — the tombstone named the deleting "
        "device's own span id, which this device has never had"
    )


def test_the_same_delete_works_when_both_devices_share_the_id(
    device, tmp_path: Path
) -> None:
    """Control. With identical ids the delete already propagates, so a failure
    here would mean the harness is wrong rather than the transport."""
    a, b = device("a"), device("b")
    _seed_span_and_support(a, "SPAN-shared01")
    _seed_span_and_support(b, "SPAN-shared01")

    with db.connect(a) as conn:
        row = conn.execute("SELECT * FROM claim_supports").fetchone()
        record_row_tombstone_on_connection(conn, "claim_supports", dict(row))
        conn.execute("DELETE FROM claim_supports")

    export_path = tmp_path / "a.json"
    export_knowledge(a, export_path)
    import_knowledge(b, export_path)

    assert _support_count(b) == 0


def test_a_row_this_device_deleted_does_not_walk_back_in(device, tmp_path: Path) -> None:
    """The mirror failure, and the worse one: deleted data returning.

    `_row_is_blocked_by_tombstone` computes an incoming row's token from that
    row's OWN ids — the peer's. This device's tombstone names its own span id.
    The two never match, so a row deliberately deleted here is re-inserted by the
    next sync, silently, with the tombstone sitting right beside it.
    """
    a, b = device("a"), device("b")
    _seed_span_and_support(a, "SPAN-aaaaaaaa")
    _seed_span_and_support(b, "SPAN-bbbbbbbb")

    # B deletes its own copy and records the tombstone under B's span id.
    with db.connect(b) as conn:
        row = conn.execute("SELECT * FROM claim_supports").fetchone()
        record_row_tombstone_on_connection(conn, "claim_supports", dict(row))
        conn.execute("DELETE FROM claim_supports")
    assert _support_count(b) == 0

    # A, which never deleted anything, syncs its copy over.
    export_path = tmp_path / "a.json"
    export_knowledge(a, export_path)
    import_knowledge(b, export_path)

    assert _support_count(b) == 0, (
        "a row this device deleted came back: the incoming row's token was built "
        "from the peer's span id, so the local tombstone never matched it"
    )


def test_a_tombstone_for_a_row_this_device_never_had_still_matches_nothing(
    device, tmp_path: Path
) -> None:
    """Translation must not invent matches. An unknown id passes through
    unchanged, so the delete correctly affects nothing rather than guessing."""
    a, b = device("a"), device("b")
    _seed_span_and_support(a, "SPAN-aaaaaaaa")
    # B has a support row for a DIFFERENT span entirely.
    with db.connect(b) as conn:
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type,"
            " content_hash, text_preview, start_char, end_char, created_at)"
            " VALUES ('SPAN-unrelated', 1, ?, 'paragraph', 'other-hash', 'x', 0, 5, ?)",
            ("03_Notes/paper.md", "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO knowledge_units (id, unit_type, canonical_name, statement,"
            " source_span_ids, created_at, updated_at)"
            " VALUES ('KNU-22222222', 'claim', 'Other', 'Other.', '[]', ?, ?)",
            ("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO claim_supports (knowledge_unit_id, source_span_id,"
            " support_role, support_status, evidence_hash, created_at, updated_at)"
            " VALUES ('KNU-22222222', 'SPAN-unrelated', 'primary', 'unchecked',"
            " 'other-hash', ?, ?)",
            ("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )

    with db.connect(a) as conn:
        row = conn.execute("SELECT * FROM claim_supports").fetchone()
        record_row_tombstone_on_connection(conn, "claim_supports", dict(row))
        conn.execute("DELETE FROM claim_supports")

    export_path = tmp_path / "a.json"
    export_knowledge(a, export_path)
    import_knowledge(b, export_path)

    assert _support_count(b) == 1, "the delete removed an unrelated row"


def test_a_polymorphic_dependency_tombstone_is_translated(device, tmp_path: Path) -> None:
    """`artifact_dependencies` hides a span id in a generically-named column.

    Its token is `(artifact_id, depends_on_id, depends_on_type)` — and
    `artifact_type` is NOT a transport field, so `artifact_id` has to be
    dispatched by prefix rather than by a declared kind. This is the same table
    whose reference columns a name-keyed registry could not see in v0.72.0; here
    it hides in a tombstone instead.
    """
    a, b = device("a"), device("b")

    def seed(path: Path, span_id: str) -> None:
        with db.connect(path) as conn:
            conn.execute(
                "INSERT INTO source_spans (id, source_id, relpath, span_type,"
                " content_hash, text_preview, start_char, end_char, created_at)"
                " VALUES (?, 1, ?, 'paragraph', 'hash-identical', 'same', 0, 10, ?)",
                (span_id, "03_Notes/paper.md", "2026-01-01T00:00:00Z"),
            )
            conn.execute(
                "INSERT INTO artifact_dependencies (artifact_id, artifact_type,"
                " depends_on_id, depends_on_type, dependency_hash, created_at)"
                " VALUES ('KNU-11111111', 'knowledge_unit', ?, 'source_span', 'h', ?)",
                (span_id, "2026-01-01T00:00:00Z"),
            )

    seed(a, "SPAN-aaaaaaaa")
    seed(b, "SPAN-bbbbbbbb")

    with db.connect(a) as conn:
        row = conn.execute("SELECT * FROM artifact_dependencies").fetchone()
        record_row_tombstone_on_connection(conn, "artifact_dependencies", dict(row))
        conn.execute("DELETE FROM artifact_dependencies")

    export_path = tmp_path / "a.json"
    export_knowledge(a, export_path)
    import_knowledge(b, export_path)

    with db.connect(b) as conn:
        n = conn.execute("SELECT COUNT(*) FROM artifact_dependencies").fetchone()[0]
    assert n == 0, "the dependency tombstone named the peer's span id and matched nothing"
