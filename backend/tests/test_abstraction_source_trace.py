"""Forward provenance: high-level abstraction records trace back to their sources.

RAG stabilization materializes source provenance up the DAG (atoms, entities,
relations, community reports, synthesis nodes all carry aggregated
``source_span_ids``), but the abstraction -> source trace was never asserted, and
``materializer._first_source_id`` keeps only ONE source per record. These tests
pin the forward resolver ``db.sources_for_spans`` and prove that a multi-source
abstraction record traces to ALL of its origin documents.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from typing import Any, Iterator

from curator import db


def _insert_source(db_path: Path, relpath: str) -> int:
    with db.connect(db_path) as conn:
        rowid = conn.execute(
            """
            INSERT INTO sources
                (relpath, content_hash, file_type, bytes, added_at, context_id,
                 l1_status, l2_status, l3_status)
            VALUES (?, ?, 'md', 128, '2026-06-04T00:00:00Z', ?, 'done', 'done', 'done')
            """,
            (relpath, f"h-{relpath}", f"CTX-{relpath}"),
        ).lastrowid
        assert rowid is not None
        return rowid


def _span(db_path: Path, source_id: int, relpath: str, content_hash: str) -> str:
    return db.upsert_source_span(
        db_path,
        source_id=source_id,
        relpath=relpath,
        span_type="paragraph",
        section_title="s",
        start_char=0,
        end_char=10,
        content_hash=content_hash,
        text_preview="evidence text",
    )


def test_sources_for_spans_single_source(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    sid = _insert_source(db_path, "04_Resources/a.md")
    span = _span(db_path, sid, "04_Resources/a.md", "ha")

    assert db.sources_for_spans(db_path, [span]) == [
        {"source_id": sid, "relpath": "04_Resources/a.md"}
    ]


def test_sources_for_spans_dedups_and_preserves_order(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    sid_a = _insert_source(db_path, "04_Resources/a.md")
    sid_b = _insert_source(db_path, "04_Resources/b.md")
    a1 = _span(db_path, sid_a, "04_Resources/a.md", "a1")
    a2 = _span(db_path, sid_a, "04_Resources/a.md", "a2")
    b1 = _span(db_path, sid_b, "04_Resources/b.md", "b1")

    # b1 first, then two spans from source a → b then a, each source once.
    assert db.sources_for_spans(db_path, [b1, a1, a2]) == [
        {"source_id": sid_b, "relpath": "04_Resources/b.md"},
        {"source_id": sid_a, "relpath": "04_Resources/a.md"},
    ]


def test_sources_for_spans_batches_source_relpath_lookup(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    sid_a = _insert_source(db_path, "04_Resources/a.md")
    sid_b = _insert_source(db_path, "04_Resources/b.md")
    a1 = _span(db_path, sid_a, "04_Resources/a.md", "a1")
    a2 = _span(db_path, sid_a, "04_Resources/a.md", "a2")
    b1 = _span(db_path, sid_b, "04_Resources/b.md", "b1")

    source_relpath_selects: list[str] = []
    original_connect = db.connect

    class CountingConnection:
        def __init__(self, conn: Any) -> None:
            self._conn = conn

        def __getattr__(self, name: str) -> Any:
            return getattr(self._conn, name)

        def execute(self, sql: str, *args: Any, **kwargs: Any) -> Any:
            normalized = f" {sql.lower()} "
            if " from sources " in normalized:
                source_relpath_selects.append(sql)
            return self._conn.execute(sql, *args, **kwargs)

    @contextmanager
    def counting_connect(path: Path) -> Iterator[CountingConnection]:
        with original_connect(path) as conn:
            yield CountingConnection(conn)

    monkeypatch.setattr(db, "connect", counting_connect)

    assert db.sources_for_spans(db_path, [a1, a2, b1]) == [
        {"source_id": sid_a, "relpath": "04_Resources/a.md"},
        {"source_id": sid_b, "relpath": "04_Resources/b.md"},
    ]
    assert len(source_relpath_selects) == 1
    assert " IN " in source_relpath_selects[0]


def test_multi_source_synthesis_node_traces_to_all_origins(tmp_path: Path) -> None:
    """A synthesis node aggregating spans from two sources must trace to BOTH —
    the exact case `_first_source_id` (single source) silently drops."""
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    sid_a = _insert_source(db_path, "04_Resources/a.md")
    sid_b = _insert_source(db_path, "04_Resources/b.md")
    span_a = _span(db_path, sid_a, "04_Resources/a.md", "ha")
    span_b = _span(db_path, sid_b, "04_Resources/b.md", "hb")

    syn_id = db.upsert_synthesis_node(
        db_path,
        title="Cross-source synthesis",
        statement="A recurring pattern observed across two papers.",
        full_content="Synthesis across sources.",
        dependency_hash="syn-deps",
        community_report_ids=[],
        source_span_ids=[span_a, span_b],
        confidence=0.9,
    )

    # Read the abstraction record's stored spans exactly as a search hit carries
    # them, then resolve the full forward trace.
    with db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT source_span_ids FROM synthesis_nodes WHERE id = ?", (syn_id,)
        ).fetchone()
    stored_spans = [str(s) for s in json.loads(row["source_span_ids"])]
    assert set(stored_spans) == {span_a, span_b}

    assert db.sources_for_spans(db_path, stored_spans) == [
        {"source_id": sid_a, "relpath": "04_Resources/a.md"},
        {"source_id": sid_b, "relpath": "04_Resources/b.md"},
    ]


def test_sources_for_spans_ignores_unknown_and_empty(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    assert db.sources_for_spans(db_path, []) == []
    assert db.sources_for_spans(db_path, ["SPAN-does-not-exist"]) == []
