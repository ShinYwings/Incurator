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
    def __init__(self, responses: list[str], model: str = "fake") -> None:
        self._responses = list(responses)
        self.model = model

    def chat(self, messages: list[ChatMessage], *, json_mode=False, temperature=0.3) -> str:
        return self._responses.pop(0)


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
            [{"id": "s1", "title": "Intro", "page": 1, "text": "Residual connections ease optimization.\n\nThey enable very deep nets."}]
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
            from .test_knowledge_unit_extraction import _units_json
            return _units_json(span_id)

    from curator.pipeline import knowledge_units as ku
    from curator import db
    client = SmallChunkClient()
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=spans
    )
    assert result.ok, result.errors
    
    units = db.list_knowledge_units_for_source(dbp, 1)
    assert len(units) > 1
    for u in units:
        assert u["source_span_ids"] == [span_id]
