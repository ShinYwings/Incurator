"""Phase 4 (v0.3.1): LLM knowledge-unit extraction into the DB."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from curator import db
from curator.llm import ChatMessage
from curator.pipeline import knowledge_units as ku
from curator.pipeline import source_spans as ss


class FakeClient:
    def __init__(
        self,
        responses: list[str | Exception],
        model: str = "fake",
        optimal_chars: int = 60000,
    ) -> None:
        self._responses = list(responses)
        self._optimal_chars = optimal_chars
        self.model = model
        self.calls = 0

    def optimal_chunk_chars(self) -> int:
        return self._optimal_chars

    def chat(self, messages: list[ChatMessage], *, json_mode=False, temperature=0.3) -> str:
        self.calls += 1
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture()
def vault():
    with tempfile.TemporaryDirectory() as t:
        dbp = Path(t) / "state.sqlite"
        db.init_db(dbp)
        with db.connect(dbp) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                ("04_Resources/resnet.md", "h", "md", 1),
            )
        spans = ss.spans_from_sections(
            [{
                "id": "s1",
                "title": "Intro",
                "page": 1,
                "text": "Residual connections ease optimization and enable very deep nets.",
            }]
        )
        ids = ss.store_source_spans(dbp, 1, "04_Resources/resnet.md", spans)
        # Pair stored ids with full text for the extractor.
        span_inputs = [
            {"id": ids[i], "text": spans[i].text, "section_title": spans[i].section_title}
            for i in range(len(ids))
        ]
        yield dbp, span_inputs


def _units_json(span_id: str) -> str:
    return json.dumps(
        {
            "units": [
                {
                    "canonical_name": "Residual learning eases optimization",
                    "unit_type": "claim",
                    "statement": "Residual connections make deep nets easier to optimize.",
                    "source_span_ids": [span_id],
                    "confidence": 0.9,
                    "truth_status": "source_supported",
                }
            ]
        }
    )


def _add_span(dbp: Path, text: str, title: str) -> dict:
    spans = ss.spans_from_sections(
        [{"id": title.lower(), "title": title, "page": 1, "text": text}]
    )
    ids = ss.store_source_spans(dbp, 1, "04_Resources/resnet.md", spans)
    return {"id": ids[0], "text": spans[0].text, "section_title": spans[0].section_title}


def test_extract_persists_units(vault) -> None:
    dbp, spans = vault
    client = FakeClient([_units_json(spans[0]["id"])])
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=spans
    )
    assert result.ok
    assert len(result.unit_ids) == 1
    units = db.list_knowledge_units_for_source(dbp, 1)
    assert len(units) == 1
    assert units[0]["truth_status"] == "source_supported"
    assert units[0]["source_span_ids"] == [spans[0]["id"]]
    assert units[0]["prompt_run_id"] == result.trace_id
    supports = db.list_claim_supports(dbp, units[0]["id"])
    assert len(supports) == 1
    assert supports[0]["source_span_id"] == spans[0]["id"]
    assert supports[0]["support_role"] == "primary"
    assert supports[0]["support_status"] == "unchecked"


def test_invented_span_rejected_and_not_persisted(vault) -> None:
    dbp, spans = vault
    bad = _units_json("SPAN-invented")
    client = FakeClient([bad, bad])  # repair also bad
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=spans
    )
    assert not result.ok
    assert result.errors
    # No partial artifact written.
    assert db.list_knowledge_units_for_source(dbp, 1) == []


def test_failed_late_batch_leaves_no_partial_units(vault) -> None:
    dbp, spans = vault
    spans.append(_add_span(dbp, "Batch two content is intentionally unrecoverable.", "Second"))
    client = FakeClient(
        [_units_json(spans[0]["id"]), "not json", "still not json"],
        optimal_chars=160,
    )
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=spans
    )
    assert not result.ok
    assert result.errors
    assert db.list_knowledge_units_for_source(dbp, 1) == []


def test_provider_exception_leaves_no_partial_units(vault) -> None:
    dbp, spans = vault
    spans.append(_add_span(dbp, "The provider fails on the second batch.", "Second"))
    client = FakeClient(
        [_units_json(spans[0]["id"]), RuntimeError("capacity exhausted")],
        optimal_chars=160,
    )
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=spans
    )
    assert not result.ok
    assert "capacity exhausted" in result.errors[0]
    assert db.list_knowledge_units_for_source(dbp, 1) == []


def test_extraction_discards_previous_unpublished_units(vault) -> None:
    dbp, spans = vault
    stale_id = db.upsert_knowledge_unit(
        dbp,
        unit_type="claim",
        canonical_name="Stale failed-run unit",
        statement="A failed extraction previously wrote this unpublished unit.",
        source_span_ids=[spans[0]["id"]],
        source_id=1,
        confidence=0.1,
        truth_status="source_supported",
    )
    assert db.list_knowledge_units_for_source(dbp, 1)[0]["id"] == stale_id

    client = FakeClient([_units_json(spans[0]["id"])])
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=spans
    )
    assert result.ok
    units = db.list_knowledge_units_for_source(dbp, 1)
    assert [unit["id"] for unit in units] == result.unit_ids
    assert stale_id not in result.unit_ids


def test_failed_combined_batch_retries_smaller_batches(vault) -> None:
    dbp, spans = vault
    spans.append(_add_span(dbp, "Residual blocks can be stacked deeply.", "Depth"))
    client = FakeClient(
        [
            "not json",
            "still not json",
            _units_json(spans[0]["id"]),
            _units_json(spans[1]["id"]),
        ],
        optimal_chars=60000,
    )
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=spans
    )
    assert result.ok, result.errors
    assert client.calls == 4
    units = db.list_knowledge_units_for_source(dbp, 1)
    assert len(units) == 2
    assert {tuple(unit["source_span_ids"]) for unit in units} == {
        (spans[0]["id"],),
        (spans[1]["id"],),
    }


def test_empty_spans_is_noop(vault) -> None:
    dbp, _ = vault
    client = FakeClient([])
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=[]
    )
    assert result.ok
    assert result.unit_ids == []


def test_chunking_large_span_is_split(vault) -> None:
    dbp, spans = vault
    huge_text = "A" * 60000
    spans[0]["text"] = huge_text
    span_id = spans[0]["id"]

    class SmallChunkClient:
        def optimal_chunk_chars(self) -> int:
            return 20000

        def chat(self, messages, **kwargs):
            return _units_json(span_id)

    client = SmallChunkClient()
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=spans
    )
    assert result.ok, result.errors

    units = db.list_knowledge_units_for_source(dbp, 1)
    assert len(units) > 1
    for u in units:
        assert u["source_span_ids"] == [span_id]
