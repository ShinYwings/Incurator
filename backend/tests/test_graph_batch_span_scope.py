"""v0.63.0 (ROADMAP 5d): a graph batch is sent only the span ids it can cite.

`client_optimal_chunk_chars` bounds the units block. It does not bound the
rendered prompt, which also carried `valid_span_ids_block` — EVERY span id of the
source — on every batch. Measured on the reference vault's largest source: a
15,981-char units block against a **124,669-char span block**, 87% of a
143,582-char prompt, where the batch cites a median of 67 of those 8,905 ids.
A 139x waste, re-sent 24 times: 3.45 MB against the 476 KB actually needed.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from curator import db
from curator.llm import ChatMessage
from curator.pipeline import graph_index


class CapturingClient:
    """Records the rendered prompt of every call so the test can measure it."""

    def __init__(self, responses: list[str], model: str = "fake") -> None:
        self._responses = list(responses)
        self.model = model
        self.prompts: list[str] = []

    @property
    def optimal_chunk_chars(self) -> int:
        return 400  # force the fixture units into separate batches

    def chat(self, messages: list[ChatMessage], *, json_mode=False, temperature=0.3) -> str:
        self.prompts.append("\n".join(m.content for m in messages))
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


ALL_SPANS = [f"SPAN-{i:08x}" for i in range(60)]


def _units() -> list[dict]:
    return [
        {"id": "KNU-aaaa1111", "source_id": 1, "unit_type": "claim",
         "statement": "A" * 200, "source_span_ids": ["SPAN-00000000", "SPAN-00000001"]},
        {"id": "KNU-bbbb2222", "source_id": 1, "unit_type": "claim",
         "statement": "B" * 200, "source_span_ids": ["SPAN-0000002a"]},
    ]


def _graph_json(span: str) -> str:
    return json.dumps({
        "entities": [{"canonical_name": f"E{span}", "entity_type": "method",
                      "source_span_ids": [span]}],
        "relations": [],
    })


def test_a_batch_is_sent_only_the_spans_its_units_cite(dbp: Path) -> None:
    client = CapturingClient([_graph_json("SPAN-00000000"), _graph_json("SPAN-0000002a")])
    data = graph_index.extract_graph_data(
        dbp, client, units=_units(), valid_span_ids=ALL_SPANS
    )
    assert data.ok
    assert len(client.prompts) == 2, "the fixture must split into two batches"

    first, second = client.prompts
    assert "SPAN-00000000" in first and "SPAN-00000001" in first
    assert "SPAN-0000002a" not in first, "batch 1 was sent a span it cannot cite"
    assert "SPAN-0000002a" in second
    assert "SPAN-00000000" not in second


def test_the_span_block_no_longer_dominates_the_prompt(dbp: Path) -> None:
    """The regression this exists to prevent, stated as a ratio rather than a
    byte count so it survives template edits."""
    client = CapturingClient([_graph_json("SPAN-00000000"), _graph_json("SPAN-0000002a")])
    graph_index.extract_graph_data(dbp, client, units=_units(), valid_span_ids=ALL_SPANS)

    for prompt in client.prompts:
        sent = sum(1 for s in ALL_SPANS if s in prompt)
        assert sent <= 2, f"batch was sent {sent} of {len(ALL_SPANS)} span ids"


def test_a_citation_outside_the_batch_is_rejected(dbp: Path) -> None:
    """The narrowed list is the CONTRACT, not just a size trim: validation has to
    agree with what the prompt allowed, or the model is told one thing and judged
    by another."""
    stray = _graph_json("SPAN-0000002a")  # belongs to batch 2, cited from batch 1
    client = CapturingClient([stray] * 40 + [_graph_json("SPAN-0000002a")])
    data = graph_index.extract_graph_data(
        dbp, client, units=_units(), valid_span_ids=ALL_SPANS
    )
    assert not data.ok
    assert any("SPAN-0000002a" in e or "span" in e.lower() for e in data.errors)


def test_a_batch_citing_nothing_still_gets_the_source_list(dbp: Path) -> None:
    """Defensive: a unit with no spans must not produce an EMPTY allowed list,
    which would forbid every citation the model could make."""
    units = [{"id": "KNU-cccc3333", "source_id": 1, "unit_type": "claim",
              "statement": "C" * 200, "source_span_ids": []}]
    client = CapturingClient([_graph_json("SPAN-00000005")])
    data = graph_index.extract_graph_data(
        dbp, client, units=units, valid_span_ids=ALL_SPANS
    )
    assert data.ok
    assert "SPAN-00000005" in client.prompts[0]
