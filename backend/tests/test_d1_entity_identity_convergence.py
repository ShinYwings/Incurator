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


def _add_span(path: Path, span_id: str, content_hash: str = "hash-identical") -> None:
    with db.connect(path) as conn:
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type,"
            " content_hash, text_preview, start_char, end_char, created_at)"
            " VALUES (?, 1, ?, 'paragraph', ?, ?, 0, 10, ?)",
            (span_id, "03_Notes/paper.md", content_hash, "same text",
             "2026-01-01T00:00:00Z"),
        )


def test_a_polymorphic_dependency_column_is_remapped_too(device, tmp_path: Path) -> None:
    """`artifact_dependencies` names the id's KIND in a sibling column.

    A registry keyed on column name cannot see these — the same blind spot that
    hid `graph_batch_results.trace_id` from v0.71.0's prompt-run scan. It is not
    a dormant branch either: 6,241 rows on the reference vault carry a `SPAN-`
    id this way, written by three call sites in the compile and synthesis paths.
    """
    a, b = device("a"), device("b")
    _add_span(a, "SPAN-aaaaaaaa")
    _add_span(b, "SPAN-bbbbbbbb")
    with db.connect(b) as conn:
        conn.execute(
            "INSERT INTO artifact_dependencies (artifact_id, artifact_type,"
            " depends_on_id, depends_on_type, dependency_hash, created_at)"
            " VALUES ('KNU-11111111', 'knowledge_unit', 'SPAN-bbbbbbbb',"
            " 'source_span', 'h', '2026-01-01T00:00:00Z')",
        )

    export_path = tmp_path / "b.json"
    export_knowledge(b, export_path)
    import_knowledge(a, export_path)

    with db.connect(a) as conn:
        rows = conn.execute(
            "SELECT depends_on_id FROM artifact_dependencies WHERE depends_on_type='source_span'"
        ).fetchall()
    ids = {r["depends_on_id"] for r in rows}
    assert "SPAN-bbbbbbbb" not in ids, "a dependency still names the peer's span id"
    assert "SPAN-aaaaaaaa" in ids


def test_a_merge_reversal_payload_is_remapped(device, tmp_path: Path) -> None:
    """`entity_resolution_lineage.rewrite_json` is replayed verbatim.

    `reverse_entity_merge` reads it back to restore relation endpoints. If it
    still names the peer's id, reversing that merge later re-points a relation at
    an entity this device never had — the same dangling reference, arriving
    through a path nothing else watches. It is nested, so neither the flat-array
    nor the hop-object handler reaches it.
    """
    a, b = device("a"), device("b")
    _add_entity(a, "ENT-aaaaaaaa", "Alan Turing")
    _add_entity(b, "ENT-bbbbbbbb", "Alan Turing")
    payload = {
        "origin_entity": {"id": "ENT-bbbbbbbb", "canonical_name": "Alan Turing"},
        "relation_rewrites": [
            {"relation_id": "REL-11111111", "field": "source_entity_id",
             "from": "ENT-bbbbbbbb", "to": "ENT-cccccccc"}
        ],
    }
    with db.connect(b) as conn:
        conn.execute(
            "INSERT INTO entity_resolution_lineage (decision_id, origin_entity_id,"
            " canonical_entity_id, rewrite_json)"
            " VALUES ('DEC-1', 'ENT-bbbbbbbb', 'ENT-cccccccc', ?)",
            (json.dumps(payload, sort_keys=True),),
        )

    export_path = tmp_path / "b.json"
    export_knowledge(b, export_path)
    import_knowledge(a, export_path)

    with db.connect(a) as conn:
        row = conn.execute(
            "SELECT origin_entity_id, rewrite_json FROM entity_resolution_lineage"
            " WHERE decision_id = 'DEC-1'"
        ).fetchone()
    assert row is not None, "the lineage row did not arrive"
    assert row["origin_entity_id"] == "ENT-aaaaaaaa", "the scalar column was not remapped"
    replayed = json.loads(row["rewrite_json"])
    assert replayed["origin_entity"]["id"] == "ENT-aaaaaaaa"
    assert replayed["relation_rewrites"][0]["from"] == "ENT-aaaaaaaa", (
        "reversing this merge would re-point a relation at the peer's id"
    )


def test_the_candidate_scan_is_chunked_rather_than_one_giant_or_chain(
    device, tmp_path: Path
) -> None:
    """One `LIKE ?` per converged id in a single statement eventually raises
    "Expression tree is too large", and the transaction it raises inside commits
    only on a clean exit — so it would discard the ENTIRE import, not just the
    repair.

    The threshold is a build-time property, not a constant: `SQLITE_MAX_EXPR_DEPTH`
    defaults to 1000 and this build reports 10000. Asserting on a crash would
    therefore pass or fail by machine. Assert the chunking itself instead, which
    is what actually removes the dependence.
    """
    from curator import db_sync

    id_map = {f"ENT-r{i:07d}": f"ENT-l{i:07d}" for i in range(2500)}
    widths: list[int] = []

    class _EmptyCursor:
        def fetchall(self):  # noqa: ANN201
            return []

    class _RecordingConn:
        def execute(self, sql: str, params=None):  # noqa: ANN001
            widths.append(sql.count("LIKE ?"))
            return _EmptyCursor()

    db_sync._candidate_rows(_RecordingConn(), "community_reports", "entity_ids", id_map)

    assert widths, "the scan issued no query at all"
    assert len(widths) > 1, (
        f"2,500 converged ids went out as {len(widths)} query — unchunked, so the "
        f"width is bounded only by whatever this build happens to allow"
    )
    assert max(widths) <= 1000, (
        f"widest chunk was {max(widths)} clauses; must stay under the 1000 that "
        f"a default-configured SQLite allows"
    )
    assert sum(widths) == len(id_map), "chunking dropped or duplicated ids"
