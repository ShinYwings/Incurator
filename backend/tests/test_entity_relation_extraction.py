"""Phase 5 (v0.3.1): entity/relation graph extraction into the DB."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from curator import db
from curator.llm import ChatMessage
from curator.pipeline import graph_index


class FakeClient:
    def __init__(self, responses: list[str], model: str = "fake") -> None:
        self._responses = list(responses)
        self.model = model
        self.calls = 0

    def chat(self, messages: list[ChatMessage], *, json_mode=False, temperature=0.3) -> str:
        self.calls += 1
        return self._responses.pop(0)


@pytest.fixture()
def dbp():
    with tempfile.TemporaryDirectory() as t:
        path = Path(t) / "state.sqlite"
        db.init_db(path)
        yield path


UNITS = [
    {"id": "KNU-1", "unit_type": "claim", "statement": "ResNet addresses degradation.",
     "source_span_ids": ["SPAN-1"]},
]


def _graph_json() -> str:
    return json.dumps(
        {
            "entities": [
                {"canonical_name": "ResNet", "entity_type": "method",
                 "description": "Residual network", "source_span_ids": ["SPAN-1"]},
                {"canonical_name": "degradation problem", "entity_type": "concept",
                 "source_span_ids": ["SPAN-1"]},
            ],
            "relations": [
                {"source": "ResNet", "target": "degradation problem",
                 "relation_type": "addresses", "assertion_source": "source_states",
                 "source_span_ids": ["SPAN-1"], "confidence": 0.9},
            ],
        }
    )


def test_extract_persists_entities_and_relations(dbp: Path) -> None:
    client = FakeClient([_graph_json()])
    result = graph_index.extract_entities_and_relations(
        dbp, client, units=UNITS, valid_span_ids=["SPAN-1"]
    )
    assert result.ok
    assert set(result.entity_ids) == {"ResNet", "degradation problem"}
    assert len(result.relation_ids) == 1

    resnet_id = result.entity_ids["ResNet"]
    ent = db.get_graph_entity(dbp, resnet_id)
    assert ent["entity_type"] == "method"
    neigh = db.relation_neighborhood(dbp, [resnet_id])
    assert len(neigh) == 1
    assert neigh[0]["relation_type"] == "addresses"
    assert neigh[0]["confidence"] == 0.9


def test_invented_relation_endpoint_rejected(dbp: Path) -> None:
    bad = json.dumps(
        {
            "entities": [
                {"canonical_name": "ResNet", "entity_type": "method",
                 "source_span_ids": ["SPAN-1"]}
            ],
            "relations": [
                {"source": "ResNet", "target": "Undeclared Thing",
                 "relation_type": "x", "source_span_ids": ["SPAN-1"], "confidence": 0.5}
            ],
        }
    )
    client = FakeClient([bad, bad])
    result = graph_index.extract_entities_and_relations(
        dbp, client, units=UNITS, valid_span_ids=["SPAN-1"]
    )
    assert not result.ok
    # No entities/relations persisted on a failed run.
    with db.connect(dbp) as conn:
        assert conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM graph_relations").fetchone()[0] == 0


def test_empty_units_is_noop(dbp: Path) -> None:
    result = graph_index.extract_entities_and_relations(
        dbp, FakeClient([]), units=[], valid_span_ids=[]
    )
    assert result.ok
    assert result.entity_ids == {}


def test_property_chunk_budget_is_respected(dbp: Path) -> None:
    units = [
        {
            "id": "KNU-1",
            "unit_type": "claim",
            "statement": "A" * 480,
            "source_span_ids": ["SPAN-1"],
        },
        {
            "id": "KNU-2",
            "unit_type": "claim",
            "statement": "B" * 480,
            "source_span_ids": ["SPAN-1"],
        },
    ]

    class PropertyChunkClient(FakeClient):
        @property
        def optimal_chunk_chars(self) -> int:
            return 1000

    client = PropertyChunkClient([_graph_json(), _graph_json()])
    result = graph_index.extract_graph_data(
        dbp, client, units=units, valid_span_ids=["SPAN-1"]
    )

    assert result.ok
    assert client.calls == 2


def test_chunking_large_unit_is_truncated(dbp: Path) -> None:
    from copy import deepcopy
    units = deepcopy(UNITS)
    # Make statement huge
    units[0]["statement"] = "A" * 60000
    
    class SmallChunkClient:
        def optimal_chunk_chars(self) -> int:
            return 20000
            
        def chat(self, messages, **kwargs):
            # Verify truncation in the prompt string
            assert len(messages[-1].content) < 30000
            return _graph_json()

    client = SmallChunkClient()
    result = graph_index.extract_entities_and_relations(
        dbp, client, units=units, valid_span_ids=["SPAN-1"]
    )
    assert result.ok


def test_tiny_reported_chunk_budget_keeps_the_head_of_a_statement(dbp: Path) -> None:
    """`statement[:max_chars - 500]` is the same unchecked subtraction (v0.58.1).

    As a slice bound rather than a size, a negative value does not explode — it
    silently amputates the TAIL of every long statement and then labels the
    result `... [TRUNCATED]`, which reads as a deliberate head-truncation and is
    not one. With `optimal_chunk_chars = 200` the bound was -300, so a
    3,000-character statement became its first 2,700 characters' opposite: the
    last 300 removed and the beginning kept only by accident of the value's
    magnitude. A statement shorter than 300 characters would vanish entirely.

    Truncation must keep a positive-length HEAD regardless of the reported
    budget.
    """
    from copy import deepcopy

    units = deepcopy(UNITS)
    units[0]["statement"] = "HEADMARKER " + ("A" * 200)

    seen: list[str] = []

    class TinyBudgetClient:
        def optimal_chunk_chars(self) -> int:
            return 200

        def chat(self, messages, **kwargs):
            seen.append(messages[-1].content)
            return _graph_json()

    result = graph_index.extract_graph_data(
        dbp, TinyBudgetClient(), units=units, valid_span_ids=["SPAN-1"]
    )

    assert result.ok, result.errors
    assert seen, "no prompt was ever built"
    assert "HEADMARKER" in seen[0]


def test_chunking_never_truncates_formula_bearing_unit(dbp: Path) -> None:
    formula = "$" + ("x" * 25000) + "$"
    units = [
        {
            "id": "KNU-formula",
            "unit_type": "equation",
            "statement": "Central equation: " + formula,
            "source_span_ids": ["SPAN-1"],
        }
    ]

    class SmallChunkClient:
        def optimal_chunk_chars(self) -> int:
            return 20000

        def chat(self, messages, **kwargs):
            assert formula in messages[-1].content
            assert "[TRUNCATED]" not in messages[-1].content
            return _graph_json()

    result = graph_index.extract_entities_and_relations(
        dbp, SmallChunkClient(), units=units, valid_span_ids=["SPAN-1"]
    )
    assert result.ok
