"""D1c: two devices asserting the same relation keep two rows for it.

`graph_entities` and `source_spans` converge because each carries a natural-key
UNIQUE index, so the second device's row collides on content and is recognised as
one it already has. `graph_relations` has no such index. Two devices that
independently extract "A works_at B" mint two `REL-` ids, and after v0.72.0 both
rows point at the same converged entity pair — correct, but doubled.

Doubling a relation is not cosmetic. `graph_relations` is what traversal walks
and what community construction counts, so a duplicated edge is weighted twice
in every query that follows it.

The natural key is `(source_entity_id, target_entity_id, relation_type)`. That
was a modelling question the roadmap flagged, and the data answered it: on the
reference vault all 2,787 relations are already unique under it, while
`(source, target)` alone collides in 125 groups. Adding `assertion_source` or
`description` changes nothing, so neither belongs in the key.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from curator import db
from curator.db_sync import export_knowledge, import_knowledge


@pytest.fixture()
def device(tmp_path: Path):
    def _make(name: str) -> Path:
        p = tmp_path / name / "state.sqlite"
        p.parent.mkdir(parents=True, exist_ok=True)
        db.init_db(p)
        with db.connect(p) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes,"
                " added_at, last_ingested) VALUES (?, ?, 'md', 1, ?, ?)",
                ("03_Notes/paper.md", "abc123", "2026-01-01T00:00:00Z",
                 "2026-01-01T00:00:00Z"),
            )
        return p

    return _make


def _seed(path: Path, prefix: str) -> None:
    """The same two entities and the same assertion, under device-local ids."""
    with db.connect(path) as conn:
        for suffix, name, etype in (("1", "Alan Turing", "person"),
                                    ("2", "Bletchley Park", "organization")):
            conn.execute(
                "INSERT INTO graph_entities (id, canonical_name, entity_type,"
                " description, source_span_ids, knowledge_unit_ids, created_at,"
                " updated_at) VALUES (?, ?, ?, '', '[]', '[]', ?, ?)",
                (f"ENT-{prefix}{suffix}", name, etype,
                 "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
            )
        conn.execute(
            "INSERT INTO graph_relations (id, source_entity_id, target_entity_id,"
            " relation_type, description, source_span_ids, created_at, updated_at)"
            " VALUES (?, ?, ?, 'works_at', ?, '[]', ?, ?)",
            (f"REL-{prefix}0001", f"ENT-{prefix}1", f"ENT-{prefix}2",
             f"asserted by {prefix}", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )


def test_the_same_assertion_from_two_devices_is_one_edge(device, tmp_path: Path) -> None:
    """After the sync the graph must hold one `works_at` edge between those two
    entities, not two — a doubled edge is weighted twice by every traversal."""
    a, b = device("a"), device("b")
    _seed(a, "aaaaaaa")
    _seed(b, "bbbbbbb")

    export_path = tmp_path / "b.json"
    export_knowledge(b, export_path)
    import_knowledge(a, export_path)

    with db.connect(a) as conn:
        rows = conn.execute(
            "SELECT source_entity_id, target_entity_id, relation_type"
            " FROM graph_relations"
        ).fetchall()
    keys = [(r["source_entity_id"], r["target_entity_id"], r["relation_type"]) for r in rows]
    assert len(keys) == len(set(keys)), f"the same edge is stored twice: {keys}"
    assert len(keys) == 1, f"expected exactly one edge, got {len(keys)}: {keys}"


def test_a_different_relation_type_is_a_different_edge(device, tmp_path: Path) -> None:
    """`relation_type` is IN the key. Two assertions about the same pair that say
    different things must both survive — collapsing them would lose an edge."""
    a, b = device("a"), device("b")
    _seed(a, "aaaaaaa")
    _seed(b, "bbbbbbb")
    with db.connect(b) as conn:
        conn.execute(
            "INSERT INTO graph_relations (id, source_entity_id, target_entity_id,"
            " relation_type, description, source_span_ids, created_at, updated_at)"
            " VALUES ('REL-bbbbbbb2', 'ENT-bbbbbbb1', 'ENT-bbbbbbb2', 'founded',"
            " 'a different claim', '[]', ?, ?)",
            ("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )

    export_path = tmp_path / "b.json"
    export_knowledge(b, export_path)
    import_knowledge(a, export_path)

    with db.connect(a) as conn:
        types = sorted(
            r["relation_type"] for r in conn.execute(
                "SELECT relation_type FROM graph_relations")
        )
    assert types == ["founded", "works_at"], f"expected both edges, got {types}"


def test_converging_merges_the_newer_row_rather_than_dropping_it(
    device, tmp_path: Path
) -> None:
    """Converging must not mean "whoever inserted first wins".

    The first version of this fix skipped the peer's row outright once it
    recognised the edge as one we already had. Measured: a peer row eight months
    newer, with a better description and 0.95 confidence against our 0.2,
    vanished silently. Rewriting the id and letting `_lw_upsert` run means the
    same last-write-wins rule decides this that decides every other table.
    """
    a, b = device("a"), device("b")
    _seed(a, "aaaaaaa")
    _seed(b, "bbbbbbb")
    with db.connect(a) as conn:
        conn.execute(
            "UPDATE graph_relations SET description = 'stale', confidence = 0.2,"
            " updated_at = '2026-01-01T00:00:00Z'"
        )
    with db.connect(b) as conn:
        conn.execute(
            "UPDATE graph_relations SET description = 'newer and precise',"
            " confidence = 0.95, updated_at = '2026-09-01T00:00:00Z'"
        )

    export_path = tmp_path / "b.json"
    export_knowledge(b, export_path)
    import_knowledge(a, export_path)

    with db.connect(a) as conn:
        rows = conn.execute(
            "SELECT description, confidence FROM graph_relations"
        ).fetchall()
    assert len(rows) == 1, f"expected one edge, got {len(rows)}"
    assert rows[0]["description"] == "newer and precise", (
        "the peer's newer row was dropped instead of merged"
    )
    assert rows[0]["confidence"] == 0.95


def test_our_newer_row_is_not_overwritten_by_an_older_peer(device, tmp_path: Path) -> None:
    """The other half of last-write-wins: merging must not mean the peer always
    wins either."""
    a, b = device("a"), device("b")
    _seed(a, "aaaaaaa")
    _seed(b, "bbbbbbb")
    with db.connect(a) as conn:
        conn.execute(
            "UPDATE graph_relations SET description = 'ours, newer',"
            " updated_at = '2026-09-01T00:00:00Z'"
        )
    with db.connect(b) as conn:
        conn.execute(
            "UPDATE graph_relations SET description = 'theirs, older',"
            " updated_at = '2026-01-01T00:00:00Z'"
        )

    export_path = tmp_path / "b.json"
    export_knowledge(b, export_path)
    import_knowledge(a, export_path)

    with db.connect(a) as conn:
        rows = conn.execute("SELECT description FROM graph_relations").fetchall()
    assert len(rows) == 1
    assert rows[0]["description"] == "ours, newer"
