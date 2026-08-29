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
from curator.db_sync import (
    _canonical_composite_key,
    export_knowledge,
    import_knowledge,
    record_row_tombstone_on_connection,
    record_tombstone_on_connection,
)


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


def test_an_unmapped_id_passes_through_while_others_are_translated(
    device, tmp_path: Path
) -> None:
    """Translation must not invent matches — tested with a NON-EMPTY map.

    The first version of this test gave the sync no converging ids at all, so
    `_translate_tombstone_token` short-circuited on `if not any(maps[kind] ...)`
    and never reached the per-field pass-through it claimed to exercise. It
    passed against code with no translation logic whatsoever, which makes it
    evidence of nothing.

    So: one span genuinely converges (filling the map), and a SECOND tombstone
    names a span that does not. The first must apply; the second must not touch
    the unrelated row that happens to sit beside it.
    """
    a, b = device("a"), device("b")
    _seed_span_and_support(a, "SPAN-aaaaaaaa")
    _seed_span_and_support(b, "SPAN-bbbbbbbb")

    # An unrelated support row on B, keyed on a span A has never seen.
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
    assert _support_count(b) == 2

    # A deletes its own support (its span DOES converge onto B's), and also
    # tombstones one naming a span nobody has.
    with db.connect(a) as conn:
        row = conn.execute("SELECT * FROM claim_supports").fetchone()
        record_row_tombstone_on_connection(conn, "claim_supports", dict(row))
        conn.execute("DELETE FROM claim_supports")
        record_tombstone_on_connection(
            conn, "claim_supports",
            _canonical_composite_key("claim_supports", {
                "knowledge_unit_id": "KNU-99999999",
                "source_span_id": "SPAN-nosuchid",
                "support_role": "primary",
            }),
        )

    export_path = tmp_path / "a.json"
    export_knowledge(a, export_path)
    import_knowledge(b, export_path)

    with db.connect(b) as conn:
        remaining = [
            r["source_span_id"]
            for r in conn.execute("SELECT source_span_id FROM claim_supports")
        ]
    assert remaining == ["SPAN-unrelated"], (
        f"expected only the unrelated row to survive, got {remaining}"
    )


def test_an_entity_lineage_delete_also_crosses_devices(device, tmp_path: Path) -> None:
    """`entity_resolution_lineage` is the other table the fix names, and it had
    no test at all — every case above only seeded `claim_supports`."""
    a, b = device("a"), device("b")
    for path, entity_id in ((a, "ENT-aaaaaaaa"), (b, "ENT-bbbbbbbb")):
        with db.connect(path) as conn:
            conn.execute(
                "INSERT INTO graph_entities (id, canonical_name, entity_type,"
                " description, source_span_ids, knowledge_unit_ids, created_at,"
                " updated_at) VALUES (?, 'Alan Turing', 'person', '', '[]', '[]', ?, ?)",
                (entity_id, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
            )
            conn.execute(
                "INSERT INTO entity_resolution_lineage (decision_id,"
                " origin_entity_id, canonical_entity_id, rewrite_json)"
                " VALUES ('DEC-1', ?, 'ENT-survivor', '{}')",
                (entity_id,),
            )

    with db.connect(a) as conn:
        row = conn.execute("SELECT * FROM entity_resolution_lineage").fetchone()
        record_row_tombstone_on_connection(conn, "entity_resolution_lineage", dict(row))
        conn.execute("DELETE FROM entity_resolution_lineage")

    export_path = tmp_path / "a.json"
    export_knowledge(a, export_path)
    import_knowledge(b, export_path)

    with db.connect(b) as conn:
        n = conn.execute("SELECT COUNT(*) FROM entity_resolution_lineage").fetchone()[0]
    assert n == 0, "the lineage tombstone named the peer's entity id and matched nothing"


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


def test_a_polymorphic_dependency_this_device_deleted_does_not_walk_back_in(
    device, tmp_path: Path
) -> None:
    """The mirror direction for `artifact_dependencies`, which the outbound fix
    did not close.

    The pre-upsert translation walks `_SCALAR_ID_REFS`, keyed on column NAME.
    `artifact_dependencies` is polymorphic — the kind lives in a sibling `*_type`
    column — so it is invisible to that registry, exactly as it was invisible to
    the reference-column registry in v0.72.0. The tombstone-token path got a
    kind-free escape hatch; this path did not, so a row deleted here walks back
    in past its own tombstone.
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

    with db.connect(b) as conn:
        row = conn.execute("SELECT * FROM artifact_dependencies").fetchone()
        record_row_tombstone_on_connection(conn, "artifact_dependencies", dict(row))
        conn.execute("DELETE FROM artifact_dependencies")

    export_path = tmp_path / "a.json"
    export_knowledge(a, export_path)
    import_knowledge(b, export_path)

    with db.connect(b) as conn:
        n = conn.execute("SELECT COUNT(*) FROM artifact_dependencies").fetchone()[0]
    assert n == 0, "a dependency this device deleted came back past its own tombstone"


def test_translation_does_not_launder_a_token_the_gate_would_refuse(
    device, tmp_path: Path
) -> None:
    """The translation must not sit in front of the fail-closed decoder.

    `_decode_composite_key` refuses an unsupported token version, extra top-level
    fields, duplicate JSON keys, and non-canonical encoding — `SCHEMA.md` §11.17
    calls this out by name. A permissive `json.loads` in the translation step
    would parse such a token, rewrite one field, and re-canonicalize it into a
    valid `v:1` token, which then passes validation downstream and DELETES a row
    the gate existed to protect. Measured: it did exactly that.
    """
    import json as _json

    a, b = device("a"), device("b")
    _seed_span_and_support(a, "SPAN-aaaaaaaa")
    _seed_span_and_support(b, "SPAN-bbbbbbbb")
    assert _support_count(b) == 1

    export_path = tmp_path / "a.json"
    export_knowledge(a, export_path)

    # A tombstone whose key is legitimate and whose SPAN genuinely converges —
    # only the version is unsupported. Nothing else about it is wrong.
    poisoned = _json.dumps(
        {"key": {"knowledge_unit_id": "KNU-11111111",
                 "source_span_id": "SPAN-aaaaaaaa",
                 "support_role": "primary"}, "v": 2},
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    )
    with export_path.open("a", encoding="utf-8") as f:
        f.write(_json.dumps({"type": "row", "table": "deleted_records", "row": {
            "table_name": "claim_supports", "record_id": poisoned,
            "deleted_at": "2026-06-01T00:00:00Z"}}) + "\n")

    with pytest.raises(ValueError):
        import_knowledge(b, export_path)

    assert _support_count(b) == 1, (
        "an unsupported token version was re-canonicalized into a valid one and applied"
    )
