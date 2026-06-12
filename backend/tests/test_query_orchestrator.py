"""Phase 6 (v0.3.1): end-to-end query orchestration (local/global/explore)."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db
from curator.llm import ChatMessage
from curator.retrieval import QueryOrchestrator, QueryRequest


class DynamicFakeClient:
    """Branches on the rendered prompt; cites span ids it sees."""

    model = "fake"

    def chat(self, messages: list[ChatMessage], *, json_mode=False, temperature=0.3) -> str:
        text = "\n".join(m.content for m in messages)
        spans = re.findall(r"SPAN-[0-9a-f]{8}", text)
        first = spans[0] if spans else "SPAN-00000000"
        if "Query Router" in text:
            return json.dumps({"route": "local", "reason": "x", "confidence": 0.9})
        if "explore mode" in text:  # check before global (explore primer mentions reports)
            return json.dumps({
                "followup_questions": ["How does residual learning relate to ODEs?"],
                "insight_candidates": [
                    {"statement": "Residual blocks ~ Euler steps.", "rationale": "r",
                     "source_span_ids": [first], "confidence": 0.5, "needs_human_review": True}
                ],
            })
        if "global answer by reducing" in text:
            return json.dumps({"answer": "Global synthesis.", "source_span_ids": [first],
                               "used_report_ids": [], "confidence": 0.7})
        # local answer
        return json.dumps({"answer": "Residual connections ease optimization.",
                           "source_span_ids": [first], "used_report_ids": [], "confidence": 0.8})


@pytest.fixture()
def vault():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        paths = cfg.WikiPaths(root)
        db.init_db(paths.state_db)
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES ('04_Resources/r.md', 'h', 'md', 1, datetime('now'))"
            )
        span = db.upsert_source_span(
            paths.state_db, source_id=1, relpath="04_Resources/r.md",
            span_type="paragraph", content_hash="c1", section_title="Intro",
            text_preview="Residual connections ease optimization.",
        )
        a = db.upsert_graph_entity(paths.state_db, canonical_name="residual learning",
                                   entity_type="concept", source_span_ids=[span])
        b = db.upsert_graph_entity(paths.state_db, canonical_name="Euler discretization",
                                   entity_type="concept", source_span_ids=[span])
        db.upsert_graph_relation(paths.state_db, source_entity_id=a, target_entity_id=b,
                                 relation_type="reinterpreted_as", confidence=0.8,
                                 source_span_ids=[span], assertion_source="system_infers")
        db.upsert_community_report(
            paths.state_db, community_key="comm-1", title="Residual community",
            summary="ResNet eases optimization.", full_content="...",
            dependency_hash="d1", entity_ids=[a, b], source_span_ids=[span], rank=0.7,
        )
        yield paths, span


def test_local_route_answers_with_spans(vault) -> None:
    paths, span = vault
    res = QueryOrchestrator(paths, DynamicFakeClient()).run(
        QueryRequest(question="What does residual learning do?", mode="local")
    )
    assert res.ok
    assert res.route == "local"
    assert res.answer
    assert res.trace_id.startswith("QTR-")
    assert res.prompt_trace_ids
    # prompt run is linked to the query trace
    runs = db.list_prompt_runs_for_query(paths.state_db, res.trace_id)
    assert runs and runs[0]["query_trace_id"] == res.trace_id
    trace = db.get_query_trace(paths.state_db, res.trace_id)
    assert trace is not None
    assert trace["route"] == "local"
    assert trace["source_span_ids"] == [span]
    assert trace["prompt_trace_ids"] == res.prompt_trace_ids
    assert trace["retrieval_trace"]["mode"] == "hybrid"
    assert len(db.list_query_traces(paths.state_db)) == 1


def test_global_route_uses_reports(vault) -> None:
    paths, span = vault
    res = QueryOrchestrator(paths, DynamicFakeClient()).run(
        QueryRequest(question="overall summary of themes", mode="global")
    )
    assert res.ok
    assert res.route == "global"
    assert res.community_report_ids  # report evidence surfaced


def test_global_route_surfaces_synthesis_layer(vault) -> None:
    paths, span = vault
    db.upsert_synthesis_node(
        paths.state_db, title="Cross-cutting insight",
        statement="Residual learning ~ discretized dynamics.",
        dependency_hash="d1", source_span_ids=[span], confidence=0.6,
    )
    res = QueryOrchestrator(paths, DynamicFakeClient()).run(
        QueryRequest(question="overall summary of themes", mode="global")
    )
    assert res.ok
    assert res.route == "global"
    assert res.synthesis_node_ids  # shared L4 synthesis surfaced as global evidence


def test_fetch_context_includes_synthesis_in_global(vault) -> None:
    paths, span = vault
    db.upsert_synthesis_node(
        paths.state_db, title="Cross-cutting insight",
        statement="Residual learning ~ discretized dynamics.",
        dependency_hash="d1", source_span_ids=[span], confidence=0.6,
    )

    class NoChatClient:
        model = "fake"
        def chat(self, *a, **k):  # pragma: no cover - must not be called
            raise AssertionError("fetch_context must not synthesize")

    out = QueryOrchestrator(paths, NoChatClient()).fetch_context(
        QueryRequest(question="overall summary", mode="global")
    )
    assert out["ok"]
    assert out["synthesis_node_ids"]
    assert any(it["kind"] == "synthesis" for it in out["evidence"])


def test_explore_route_creates_insight_candidates(vault) -> None:
    paths, span = vault
    res = QueryOrchestrator(paths, DynamicFakeClient()).run(
        QueryRequest(question="what else connects residual learning?", mode="explore")
    )
    assert res.route == "explore"
    assert res.insight_candidate_ids
    assert res.memory_path_ids  # associative paths recorded
    pending = db.list_insight_candidates(paths.state_db, status="pending")
    assert len(pending) == len(res.insight_candidate_ids)
    assert "Insight candidates" in res.answer


def test_fetch_context_returns_evidence_without_synthesis(vault) -> None:
    paths, span = vault
    # No LLM synthesis should run; a client that errors on chat proves it.
    class NoChatClient:
        model = "fake"
        def chat(self, *a, **k):  # pragma: no cover - must not be called
            raise AssertionError("fetch_context must not synthesize")
    out = QueryOrchestrator(paths, NoChatClient()).fetch_context(
        QueryRequest(question="residual learning", mode="local")
    )
    assert out["ok"]
    assert out["route"] == "local"
    assert out["trace_id"].startswith("QTR-")
    assert "answer" not in out  # evidence pack only, no synthesized answer
    assert any(it["kind"] == "entity" for it in out["evidence"])
    assert span in out["source_span_ids"]


def test_source_section_route(vault) -> None:
    paths, span = vault
    res = QueryOrchestrator(paths, DynamicFakeClient()).run(
        QueryRequest(question="summarize this source", mode="source-section", source_key="1")
    )
    assert res.route == "source-section"
    assert span in res.source_span_ids
    assert len(db.list_query_traces(paths.state_db)) == 1
