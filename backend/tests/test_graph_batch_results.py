"""v0.63.0 (ROADMAP 5c, P1): staged per-batch graph extraction results.

Graph extraction holds every batch in memory until the publish gate, so a
capacity deferral discards the whole run. Source 45 needs 72 batches and
completes <=3 per capacity window; it cannot converge. These tests cover the
storage layer that lets a validated batch survive an interruption.

The locked decisions under test are D2 (the write commits in its own
transaction and must survive the compile's rollback) and D5 (the payload
round-trips through the pydantic model exactly).
"""

from __future__ import annotations

import inspect
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from curator import db
from curator.prompting.families.entities import (
    EntityRelationExtractOutput,
    ExtractedEntity,
    ExtractedRelation,
)


@pytest.fixture()
def db_path() -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.sqlite"
        db.init_db(path)
        with db.connect(path) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                ("04_Resources/hartley.md", "hash-1", "md", 10),
            )
        yield path


def _payload(name: str = "Plücker coordinates") -> str:
    """A FULLY populated output -- D5 requires the round-trip test to exercise
    every field, because a dropped optional is exactly what would make a resumed
    run publish a different graph than a clean one."""
    return EntityRelationExtractOutput(
        entities=[
            ExtractedEntity(
                canonical_name=name,
                entity_type="concept",
                description="A 6-vector representation of a line in 3D space.",
                source_span_ids=["SPAN-aaaa1111", "SPAN-bbbb2222"],
            )
        ],
        relations=[
            ExtractedRelation(
                source=name,
                target="Dual Quadric",
                relation_type="constrains",
                description="The algebraic incidence condition L^T M(Q) L = 0.",
                assertion_source="source_states",
                source_span_ids=["SPAN-aaaa1111"],
                confidence=0.87,
            )
        ],
    ).model_dump_json()


def test_put_then_get_returns_the_payload(db_path: Path) -> None:
    db.put_graph_batch_result(
        db_path, source_id=1, input_hash="b0e9892e9d4c30ef",
        payload=_payload(), trace_id="PTR-1234abcd",
    )
    row = db.get_graph_batch_result(db_path, 1, "b0e9892e9d4c30ef")
    assert row is not None
    assert row["trace_id"] == "PTR-1234abcd"
    assert json.loads(row["payload"])["entities"][0]["canonical_name"] == "Plücker coordinates"


def test_a_miss_returns_none(db_path: Path) -> None:
    assert db.get_graph_batch_result(db_path, 1, "never-stored") is None


def test_a_different_source_is_a_miss_for_the_same_hash(db_path: Path) -> None:
    """The key is (source_id, input_hash). Two sources can legitimately produce
    the same batch hash -- an identical units block -- and must not share rows."""
    db.put_graph_batch_result(db_path, source_id=1, input_hash="same", payload=_payload())
    assert db.get_graph_batch_result(db_path, 2, "same") is None


def test_restaging_the_same_key_replaces_rather_than_duplicates(db_path: Path) -> None:
    db.put_graph_batch_result(db_path, source_id=1, input_hash="k", payload=_payload("first"))
    db.put_graph_batch_result(db_path, source_id=1, input_hash="k", payload=_payload("second"))
    row = db.get_graph_batch_result(db_path, 1, "k")
    assert row is not None
    assert json.loads(row["payload"])["entities"][0]["canonical_name"] == "second"
    with db.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM graph_batch_results").fetchone()[0] == 1


# --- D2: the write must not participate in the caller's transaction ----------

def test_the_write_is_committed_immediately(db_path: Path) -> None:
    """D2. A brand-new connection must see the row the instant `put` returns.

    If the write were deferred, or joined a caller's transaction, this read
    misses -- which is precisely the failure that made v0.62.0 worthless: the
    staged rows existed right up until the compile's error handler ran."""
    db.put_graph_batch_result(db_path, source_id=1, input_hash="k", payload=_payload())
    raw = sqlite3.connect(db_path)
    try:
        assert raw.execute("SELECT COUNT(*) FROM graph_batch_results").fetchone()[0] == 1
    finally:
        raw.close()


def test_a_staged_batch_survives_the_compiles_rollback(db_path: Path) -> None:
    """D2, in the real sequence: extraction stages batches, then the compile
    fails and its transaction rolls back. The staged batches are the one thing
    that must NOT roll back -- surviving the failure is their whole purpose.

    A test that only asserts "the row was written" passes against the broken
    implementation. This one rolls the caller back and then looks."""
    db.put_graph_batch_result(db_path, source_id=1, input_hash="k", payload=_payload())

    with pytest.raises(RuntimeError):
        with db.connect(db_path) as conn:
            conn.execute("UPDATE sources SET status = 'staged' WHERE id = 1")
            raise RuntimeError("graph extraction failed after batch 3 of 72")

    assert db.get_graph_batch_result(db_path, 1, "k") is not None
    with db.connect(db_path) as conn:
        # the caller's own work DID roll back -- proving the rollback was real
        assert conn.execute("SELECT status FROM sources WHERE id = 1").fetchone()[0] != "staged"


def test_put_takes_no_caller_connection(db_path: Path) -> None:
    """D2, guarded at the signature. Every other graph writer accepts `conn=` so
    it can join the atomic publish. This one must not: joining a caller's
    transaction is the defect, so the parameter should not exist to be passed."""
    assert "conn" not in inspect.signature(db.put_graph_batch_result).parameters


# --- D5: exact round-trip ----------------------------------------------------

def test_the_payload_round_trips_through_the_model_exactly(db_path: Path) -> None:
    """D5. A resumed run replaces the model's own parsed output with this
    payload. If a field is dropped -- an empty description, a float's precision,
    an empty span list -- the resumed run publishes a DIFFERENT graph than a
    clean run, and nothing would flag it."""
    original = EntityRelationExtractOutput.model_validate_json(_payload())
    db.put_graph_batch_result(
        db_path, source_id=1, input_hash="k", payload=original.model_dump_json()
    )
    row = db.get_graph_batch_result(db_path, 1, "k")
    assert row is not None
    restored = EntityRelationExtractOutput.model_validate_json(row["payload"])
    assert restored == original
    assert restored.relations[0].confidence == 0.87
    assert restored.entities[0].source_span_ids == ["SPAN-aaaa1111", "SPAN-bbbb2222"]


def test_an_empty_extraction_round_trips_as_empty_not_missing(db_path: Path) -> None:
    """A batch can legitimately yield nothing. That is a CACHEABLE result -- it
    cost a provider round-trip -- and must come back as empty lists rather than
    as a miss that re-pays for it."""
    db.put_graph_batch_result(
        db_path, source_id=1, input_hash="k",
        payload=EntityRelationExtractOutput().model_dump_json(),
    )
    row = db.get_graph_batch_result(db_path, 1, "k")
    assert row is not None
    restored = EntityRelationExtractOutput.model_validate_json(row["payload"])
    assert restored.entities == [] and restored.relations == []


# --- lifecycle ---------------------------------------------------------------

def test_delete_clears_one_source_and_leaves_others(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("03_Notes/other.md", "hash-2", "md", 10),
        )
    db.put_graph_batch_result(db_path, source_id=1, input_hash="a", payload=_payload())
    db.put_graph_batch_result(db_path, source_id=1, input_hash="b", payload=_payload())
    db.put_graph_batch_result(db_path, source_id=2, input_hash="a", payload=_payload())

    assert db.delete_graph_batch_results(db_path, 1) == 2
    assert db.get_graph_batch_result(db_path, 1, "a") is None
    assert db.get_graph_batch_result(db_path, 2, "a") is not None


def test_removing_the_source_cascades(db_path: Path) -> None:
    """D6. An abandoned source must not leave payloads behind."""
    db.put_graph_batch_result(db_path, source_id=1, input_hash="a", payload=_payload())
    with db.connect(db_path) as conn:
        conn.execute("DELETE FROM sources WHERE id = 1")
    assert db.get_graph_batch_result(db_path, 1, "a") is None


def test_the_table_appears_on_a_database_that_predates_it() -> None:
    """The migration is additive: SCHEMA_SQL is re-executed on connect, so an
    existing vault gains the table without losing anything."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.sqlite"
        db.init_db(path)
        with db.connect(path) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                ("03_Notes/pre-existing.md", "hash-old", "md", 10),
            )
        # simulate a database from before this release
        raw = sqlite3.connect(path)
        try:
            raw.execute("DROP TABLE graph_batch_results")
            raw.commit()
        finally:
            raw.close()

        with db.connect(path) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
            assert "graph_batch_results" in tables
            assert conn.execute(
                "SELECT relpath FROM sources WHERE id = 1").fetchone()[0] \
                == "03_Notes/pre-existing.md"


def test_generation_units_have_a_deterministic_order(db_path: Path) -> None:
    """The resume key depends on this, so it must not rest on SQLite's sorter.

    `list_generation_units` ordered by `created_at` alone. `created_at` has
    one-second granularity and L2 inserts a whole batch inside one second —
    measured on the reference vault, **all 5,358 units of source 45 sit in tie
    groups**, 279 distinct timestamps with the largest group at 57. Tie order was
    therefore decided by the sorter rather than the query.

    It measured stable across a `generation_id` re-stamp and a `VACUUM`, but
    SQLite does not document its sorter as stable. If the plan ever changes, the
    units block reorders, batch boundaries move, and every graph batch hash from
    the first divergence onward misses — a silent full re-pay of the whole
    source.
    """
    same_instant = "2026-08-22T08:04:18Z"
    ids = ["KNU-cccc3333", "KNU-aaaa1111", "KNU-bbbb2222"]
    with db.connect(db_path) as conn:
        for unit_id in ids:
            conn.execute(
                "INSERT INTO knowledge_units "
                "(id, source_id, unit_type, canonical_name, statement, "
                " source_span_ids, generation_id, support_status, "
                " created_at, updated_at) "
                "VALUES (?, 1, 'claim', ?, ?, '[]', 'GEN-tie', 'verified', ?, ?)",
                (unit_id, unit_id, f"statement for {unit_id}",
                 same_instant, same_instant),
            )

    ordered = [str(u["id"]) for u in db.list_generation_units(db_path, "GEN-tie")]
    assert ordered == sorted(ids), "tied timestamps must fall back to a stable id order"


def test_delete_joins_the_callers_transaction(db_path: Path) -> None:
    """Deletion is the one operation that MUST join the publish transaction.

    Staged rows have to disappear exactly when the generation they fed becomes
    authoritative. If the delete committed on its own, a publish that then rolled
    back would have destroyed the resume its own failure still needs.
    """
    db.put_graph_batch_result(db_path, source_id=1, input_hash="k", payload=_payload())

    with pytest.raises(RuntimeError):
        with db.connect(db_path) as conn:
            db.delete_graph_batch_results(db_path, 1, conn=conn)
            raise RuntimeError("publish failed after the delete")

    assert db.get_graph_batch_result(db_path, 1, "k") is not None
