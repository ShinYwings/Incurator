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


# --- v0.62.1: one provider refusal must not kill an 87-batch compile ---------


class RefusingOnceClient(FakeClient):
    """Raises on the first call of each batch, succeeds on the retry.

    Models the measured agy behaviour: `-p` mode has nobody to approve a tool
    request, so agy exits 1 with `permission check failed`. It is nondeterministic
    — 57% of calls succeeded across the 2026-08-21 attempts — so the same batch
    re-run usually goes through.
    """

    def __init__(self, responses: list[str], *, fail_first_n: int = 1) -> None:
        super().__init__(responses)
        self._left = fail_first_n
        self.refusals = 0

    def chat(self, messages, *, json_mode=False, temperature=0.3) -> str:
        if self._left > 0:
            self._left -= 1
            self.refusals += 1
            raise RuntimeError(
                'Antigravity CLI exited 1: permission check failed for command '
                '"python3 -c \'...\'": user denied permission to run command'
            )
        return super().chat(messages, json_mode=json_mode, temperature=temperature)


def test_a_provider_refusal_retries_the_batch_instead_of_killing_the_compile(
    dbp: Path,
) -> None:
    """`extract_graph_data` guarded validation failures with `continue` but had no
    `try` around `run_prompt`, and `run_prompt` closes the trace and re-raises. So
    one refusal propagated out of `compile_source_l2` and killed the whole compile.

    Measured on the live vault: source 45 needs ~87 graph batches and every one
    must succeed. At the observed 43% refusal rate the expected number of batches
    completed before the first abort is 1/0.43 ≈ 2.3 — the live run aborted after
    exactly 2, and P(87 clean) was about 7e-22.
    """
    client = RefusingOnceClient([_graph_json()], fail_first_n=1)
    result = graph_index.extract_graph_data(
        dbp, client, units=UNITS, valid_span_ids=["SPAN-1"]
    )
    assert client.refusals == 1, "the fixture did not actually refuse"
    assert result.ok, f"a single refusal still failed the run: {result.errors}"
    assert result.entities, "the retried batch produced nothing"


def test_a_batch_that_refuses_every_attempt_fails_without_raising(dbp: Path) -> None:
    """Exhausting the retries must surface as `ok=False` with the reason, the same
    shape a validation failure already produces — not an exception that unwinds the
    caller's staging block.
    """
    client = RefusingOnceClient([_graph_json()], fail_first_n=99)
    result = graph_index.extract_graph_data(
        dbp, client, units=UNITS, valid_span_ids=["SPAN-1"]
    )
    assert result.ok is False
    assert any("permission check failed" in e for e in result.errors), result.errors
    assert client.refusals == graph_index._MAX_BATCH_ATTEMPTS


def test_a_capacity_refusal_is_not_retried_here(dbp: Path) -> None:
    """429 is the one refusal this loop must NOT absorb.

    Retrying a rate limit in a tight loop spends the budget against the wall and
    undoes v0.61.1, whose whole point is that a refused job stays queued and the
    worker reports how long to wait. Measured on the live run: of 11 graph
    failures, 5 were capacity and 6 were permission denials — retrying all 11
    alike was the first draft's mistake.

    Detection asks the client, not the message. Substring matching on error text
    is what misclassified a permanent failure as transient in `_is_transient`.
    """
    from curator import llm

    class CapacityBlockedClient(FakeClient):
        CAPACITY_KEY = "test-capacity-probe"

        def capacity_blocked_for(self) -> float:
            return llm.capacity_blocked_for(self.CAPACITY_KEY)

        def chat(self, messages, *, json_mode=False, temperature=0.3) -> str:
            llm.block_capacity(self.CAPACITY_KEY)
            raise llm.LLMError("capacity exhausted (429)")

    llm.clear_capacity_block(CapacityBlockedClient.CAPACITY_KEY)
    try:
        client = CapacityBlockedClient([_graph_json()])
        with pytest.raises(llm.LLMError):
            graph_index.extract_graph_data(
                dbp, client, units=UNITS, valid_span_ids=["SPAN-1"]
            )
        assert client.calls == 0, "chat is counted only on success; sanity"
    finally:
        llm.clear_capacity_block(CapacityBlockedClient.CAPACITY_KEY)
