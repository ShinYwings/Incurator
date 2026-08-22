"""v0.63.0 (ROADMAP 5c, P2): graph extraction resumes instead of re-paying.

Every graph batch must succeed for a generation to publish, and results were held
in memory, so one capacity deferral discarded the whole run. The reference
vault's largest source needs dozens of batches and completes at most ~3 per
capacity window; it could never converge.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import pytest

from curator import db
from curator.llm import ChatMessage
from curator.pipeline import graph_index


class FakeClient:
    """Serves canned responses and counts provider round-trips.

    The count is the measurement that matters: resume is worth having only if a
    batch already paid for is not paid for twice.
    """

    def __init__(self, responses: list[str], model: str = "fake") -> None:
        self._responses = list(responses)
        self.model = model
        self.calls = 0

    @property
    def optimal_chunk_chars(self) -> int:
        return 1000  # small, so the fixture units split into 2 batches

    def chat(self, messages: list[ChatMessage], *, json_mode=False, temperature=0.3) -> str:
        self.calls += 1
        if not self._responses:
            raise AssertionError("provider called for a batch that should have been reused")
        return self._responses.pop(0)


@pytest.fixture()
def dbp():
    with tempfile.TemporaryDirectory() as t:
        path = Path(t) / "state.sqlite"
        db.init_db(path)
        with db.connect(path) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES ('04_Resources/book.md', 'h', 'md', 10, datetime('now'))"
            )
        yield path


def _units() -> list[dict]:
    """Two units large enough to land in separate batches at 1000 chars."""
    return [
        {"id": "KNU-aaaa1111", "source_id": 1, "unit_type": "claim",
         "statement": "A" * 480, "source_span_ids": ["SPAN-1"]},
        {"id": "KNU-bbbb2222", "source_id": 1, "unit_type": "claim",
         "statement": "B" * 480, "source_span_ids": ["SPAN-1"]},
    ]


def _graph_json(name: str) -> str:
    return json.dumps({
        "entities": [
            {"canonical_name": name, "entity_type": "method",
             "description": f"about {name}", "source_span_ids": ["SPAN-1"]},
        ],
        "relations": [],
    })


def _names(data) -> list[str]:
    return sorted(e.canonical_name for e, _ in data.entities)


def test_two_batches_are_staged_as_they_complete(dbp: Path) -> None:
    client = FakeClient([_graph_json("First"), _graph_json("Second")])
    data = graph_index.extract_graph_data(
        dbp, client, units=_units(), valid_span_ids=["SPAN-1"]
    )
    assert data.ok and client.calls == 2
    assert db.count_graph_batch_results(dbp, 1) == 2


def test_a_second_run_pays_nothing(dbp: Path) -> None:
    """The whole point. A run whose batches all validated earlier makes ZERO
    provider calls and returns the same graph."""
    first = FakeClient([_graph_json("First"), _graph_json("Second")])
    original = graph_index.extract_graph_data(
        dbp, first, units=_units(), valid_span_ids=["SPAN-1"]
    )

    second = FakeClient([])  # raises if the provider is called at all
    resumed = graph_index.extract_graph_data(
        dbp, second, units=_units(), valid_span_ids=["SPAN-1"]
    )

    assert second.calls == 0
    assert resumed.ok
    assert _names(resumed) == _names(original) == ["First", "Second"]


def test_an_interrupted_run_re_pays_only_the_missing_batch(dbp: Path) -> None:
    """Batch 1 validates, batch 2 fails. The resumed run issues exactly ONE
    provider call and completes."""
    bad = json.dumps({"entities": [], "relations": [
        {"source": "Nope", "target": "Also Nope", "relation_type": "x",
         "source_span_ids": ["SPAN-1"], "confidence": 0.5}]})
    first = FakeClient([_graph_json("First")] + [bad] * 40)
    failed = graph_index.extract_graph_data(
        dbp, first, units=_units(), valid_span_ids=["SPAN-1"]
    )
    assert not failed.ok
    assert db.count_graph_batch_results(dbp, 1) == 1, "only the validated batch stages"

    second = FakeClient([_graph_json("Second")])
    resumed = graph_index.extract_graph_data(
        dbp, second, units=_units(), valid_span_ids=["SPAN-1"]
    )
    assert second.calls == 1
    assert resumed.ok
    assert _names(resumed) == ["First", "Second"]


def test_a_refused_batch_is_never_staged(dbp: Path) -> None:
    """D6: only a validated result is cacheable. Caching a refusal would replay
    it forever."""
    class RefusingClient(FakeClient):
        def chat(self, messages, *, json_mode=False, temperature=0.3):
            self.calls += 1
            raise RuntimeError("permission check failed for command python3")

    data = graph_index.extract_graph_data(
        dbp, RefusingClient([]), units=_units(), valid_span_ids=["SPAN-1"]
    )
    assert not data.ok
    assert db.count_graph_batch_results(dbp, 1) == 0


def test_the_reused_count_is_logged(dbp: Path, caplog) -> None:
    """D4: a cache miss is correct, a SILENT one is the defect."""
    first = FakeClient([_graph_json("First"), _graph_json("Second")])
    graph_index.extract_graph_data(dbp, first, units=_units(), valid_span_ids=["SPAN-1"])

    with caplog.at_level(logging.INFO, logger="curator.pipeline.graph_index"):
        graph_index.extract_graph_data(
            dbp, FakeClient([]), units=_units(), valid_span_ids=["SPAN-1"]
        )
    assert "reused 2/2" in caplog.text


def test_a_total_miss_against_staged_rows_is_loud(dbp: Path, caplog) -> None:
    """The realistic silent failure: a provider failover resizes every batch, so
    every hash misses and the source re-pays in full while looking exactly like a
    run that had no cache. Say so."""
    first = FakeClient([_graph_json("First"), _graph_json("Second")])
    graph_index.extract_graph_data(dbp, first, units=_units(), valid_span_ids=["SPAN-1"])

    changed = [dict(u, statement=u["statement"].replace("A", "C").replace("B", "D"))
               for u in _units()]
    with caplog.at_level(logging.WARNING, logger="curator.pipeline.graph_index"):
        graph_index.extract_graph_data(
            dbp, FakeClient([_graph_json("X"), _graph_json("Y")]),
            units=changed, valid_span_ids=["SPAN-1"],
        )
    assert "matched NOTHING" in caplog.text


def test_units_without_a_source_id_simply_do_not_stage(dbp: Path) -> None:
    """The back-compat wrapper and older callers pass units with no `source_id`.
    They must keep working, just without resume."""
    units = [{"id": "KNU-cccc3333", "unit_type": "claim",
              "statement": "C" * 480, "source_span_ids": ["SPAN-1"]}]
    data = graph_index.extract_graph_data(
        dbp, FakeClient([_graph_json("Loner")]), units=units, valid_span_ids=["SPAN-1"]
    )
    assert data.ok
    with db.connect(dbp) as conn:
        assert conn.execute("SELECT COUNT(*) FROM graph_batch_results").fetchone()[0] == 0
