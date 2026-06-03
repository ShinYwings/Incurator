"""Phase 8b (v0.3.1): run_query delegates to the QueryOrchestrator for routes."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db, query
from curator.llm import ChatMessage


class DynamicFakeClient:
    model = "fake"

    def chat(self, messages: list[ChatMessage], *, json_mode=False, temperature=0.3) -> str:
        text = "\n".join(m.content for m in messages)
        spans = re.findall(r"SPAN-[0-9a-f]{8}", text)
        first = spans[0] if spans else "SPAN-0"
        if "explore mode" in text:
            return json.dumps({
                "followup_questions": ["How does it relate to ODEs?"],
                "insight_candidates": [{"statement": "Residual ~ Euler step.",
                                        "rationale": "r", "source_span_ids": [first],
                                        "confidence": 0.5, "needs_human_review": True}],
            })
        return json.dumps({"answer": "Residual learning eases optimization.",
                           "source_span_ids": [first], "used_report_ids": [], "confidence": 0.8})

    def close(self) -> None:
        ...


@pytest.fixture()
def vault():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        paths = cfg.WikiPaths(root)
        db.init_db(paths.state_db)
        with db.connect(paths.state_db) as c:
            c.execute("INSERT INTO sources (relpath,content_hash,file_type,bytes,added_at) "
                      "VALUES ('04_Resources/r.md','h','md',1,datetime('now'))")
        sp = db.upsert_source_span(paths.state_db, source_id=1, relpath="04_Resources/r.md",
                                   span_type="paragraph", content_hash="c1",
                                   section_title="Intro",
                                   text_preview="Residual learning eases optimization.")
        a = db.upsert_graph_entity(paths.state_db, canonical_name="residual learning",
                                   entity_type="concept", source_span_ids=[sp])
        b = db.upsert_graph_entity(paths.state_db, canonical_name="Euler discretization",
                                   entity_type="concept", source_span_ids=[sp])
        db.upsert_graph_relation(paths.state_db, source_entity_id=a, target_entity_id=b,
                                 relation_type="reinterpreted_as", confidence=0.8,
                                 source_span_ids=[sp], assertion_source="system_infers")
        yield paths, sp


def test_route_local_delegates_to_orchestrator(vault) -> None:
    paths, sp = vault
    res = query.run_query(paths, DynamicFakeClient(), "What does residual learning do?",
                          query.QueryCallbacks(), route="local")
    assert res.ok
    assert res.route == "local"
    assert res.trace_id.startswith("QTR-")
    assert res.prompt_trace_ids
    assert sp in res.source_span_ids


def test_route_explore_records_insight_candidates(vault) -> None:
    paths, sp = vault
    res = query.run_query(paths, DynamicFakeClient(), "what else connects residual learning?",
                          query.QueryCallbacks(), route="explore")
    assert res.route == "explore"
    assert res.insight_candidate_ids
    assert res.memory_path_ids


def test_empty_route_uses_legacy_path_fields(vault) -> None:
    # With no route, the v0.3.1 trace fields stay empty (legacy qmd path).
    # qmd is unavailable in tests, so this returns an error result — but crucially
    # it does NOT carry a QTR route/trace (i.e. the orchestrator was not used).
    paths, sp = vault
    res = query.run_query(paths, DynamicFakeClient(), "hello?",
                          query.QueryCallbacks(), route="")
    assert res.route == ""
    assert res.trace_id == ""
