"""D1: two devices extracting the same entity orphan each other's relations.

`graph_entities` and `source_spans` are transported on their surrogate `id`, but
both carry a natural identity — `UNIQUE(canonical_name, entity_type)` and
`UNIQUE(source_id, content_hash)`. Two devices that independently extract the
same thing mint different ids, so the peer's row looks new by key and collides on
content. `db_sync._do_insert`'s own docstring names this exactly:

    "Two devices that independently extract the same entity mint different ids,
     so the peer's row looks new by key and collides on content. The data is
     already here; the ids simply never converge."

The content converging is not the problem. The problem is the second half: the
peer's CHILDREN still reference the peer's id, which does not exist locally, and
nothing remaps them. `sources` solved this — on a duplicate it looks up the local
id "so the peer's child rows attach to it instead of being orphaned"
(`db_sync.py`, `_lw_upsert_source`). Neither of these two tables does.

These tests reproduce the damage. They are written against the OBSERVABLE
consequence — a relation whose endpoint names an entity that does not exist —
rather than against any particular fix, so they stay honest whichever design
lands.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from curator import db
from curator.db_sync import export_knowledge, import_knowledge


@pytest.fixture()
def device(tmp_path: Path):
    """Two independent devices, each with the same source registered."""

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


def _add_entity(path: Path, entity_id: str, name: str, etype: str = "person") -> None:
    with db.connect(path) as conn:
        conn.execute(
            "INSERT INTO graph_entities (id, canonical_name, entity_type, description,"
            " source_span_ids, knowledge_unit_ids, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, '[]', '[]', ?, ?)",
            (entity_id, name, etype, "", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )


def _add_relation(path: Path, rel_id: str, src: str, dst: str) -> None:
    with db.connect(path) as conn:
        conn.execute(
            "INSERT INTO graph_relations (id, source_entity_id, target_entity_id,"
            " relation_type, description, source_span_ids, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, '[]', ?, ?)",
            (rel_id, src, dst, "works_at", "knows",
             "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )


def _dangling_endpoints(path: Path) -> list[tuple[str, str]]:
    with db.connect(path) as conn:
        rows = conn.execute(
            "SELECT r.id, r.source_entity_id, r.target_entity_id FROM graph_relations r"
            " WHERE NOT EXISTS (SELECT 1 FROM graph_entities e WHERE e.id = r.source_entity_id)"
            "    OR NOT EXISTS (SELECT 1 FROM graph_entities e WHERE e.id = r.target_entity_id)"
        ).fetchall()
    return [(str(r["id"]), f"{r['source_entity_id']}->{r['target_entity_id']}") for r in rows]


def test_a_relation_from_a_peer_must_not_point_at_an_entity_that_does_not_exist(
    device, tmp_path: Path
) -> None:
    """The core D1 damage, stated as the user would see it.

    Device A and device B both extract "Alan Turing"/person from the same source,
    minting different ids. B also extracts a relation involving it. After A
    imports B's export, A's graph holds a relation whose endpoint names an id A
    has never had — a broken edge in a graph whose whole purpose is traversal.
    """
    a, b = device("a"), device("b")

    _add_entity(a, "ENT-aaaaaaaa", "Alan Turing")
    _add_entity(b, "ENT-bbbbbbbb", "Alan Turing")
    _add_entity(b, "ENT-cccccccc", "Bletchley Park", etype="place")
    _add_relation(b, "REL-11111111", "ENT-bbbbbbbb", "ENT-cccccccc")

    export_path = tmp_path / "b.json"
    export_knowledge(b, export_path)
    import_knowledge(a, export_path)

    assert _dangling_endpoints(a) == [], (
        "a relation arrived pointing at an entity id this device does not have; "
        "the entity converged by content but its id never did"
    )


def test_the_converged_entity_is_not_duplicated(device, tmp_path: Path) -> None:
    """The content half already works — pin it so a fix cannot regress it into
    duplicate rows while chasing the id half."""
    a, b = device("a"), device("b")
    _add_entity(a, "ENT-aaaaaaaa", "Alan Turing")
    _add_entity(b, "ENT-bbbbbbbb", "Alan Turing")

    export_path = tmp_path / "b.json"
    export_knowledge(b, export_path)
    import_knowledge(a, export_path)

    with db.connect(a) as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM graph_entities WHERE canonical_name = ? AND entity_type = ?",
            ("Alan Turing", "person"),
        ).fetchone()[0]
    assert n == 1, f"the same entity exists {n} times"


def test_a_knowledge_unit_must_not_cite_a_span_this_device_does_not_have(
    device, tmp_path: Path
) -> None:
    """The same failure for `source_spans`, through the citation path.

    Spans are cited from JSON arrays (`knowledge_units.source_span_ids`), so a
    span id that never converges becomes a citation pointing at nothing — which
    the claim-grounding rules (SYSTEM_BEHAVIOR §27.5) treat as unsupported.
    """
    a, b = device("a"), device("b")

    for path, span_id in ((a, "SPAN-aaaaaaaa"), (b, "SPAN-bbbbbbbb")):
        with db.connect(path) as conn:
            conn.execute(
                "INSERT INTO source_spans (id, source_id, relpath, span_type,"
                " content_hash, text_preview, start_char, end_char, created_at)"
                " VALUES (?, 1, ?, 'paragraph', ?, ?, 0, 10, ?)",
                (span_id, "03_Notes/paper.md", "hash-identical",
                 "the same sentence", "2026-01-01T00:00:00Z"),
            )
    with db.connect(b) as conn:
        conn.execute(
            "INSERT INTO knowledge_units (id, unit_type, canonical_name, statement,"
            " source_span_ids, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("KNU-11111111", "claim", "A claim", "A claim.",
             json.dumps(["SPAN-bbbbbbbb"]),
             "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )

    export_path = tmp_path / "b.json"
    export_knowledge(b, export_path)
    import_knowledge(a, export_path)

    with db.connect(a) as conn:
        row = conn.execute(
            "SELECT source_span_ids FROM knowledge_units WHERE id = ?", ("KNU-11111111",)
        ).fetchone()
        assert row is not None, "the knowledge unit did not arrive at all"
        cited = json.loads(row["source_span_ids"])
        present = {
            r["id"] for r in conn.execute("SELECT id FROM source_spans").fetchall()
        }
    missing = [s for s in cited if s not in present]
    assert missing == [], f"claim cites spans this device does not have: {missing}"
