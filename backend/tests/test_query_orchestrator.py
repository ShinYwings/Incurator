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
from curator.retrieval import QueryOrchestrator, QueryRequest, QueryResultV031
from curator.retrieval.orchestrator import _context_evidence_block


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


class InvalidCitationClient:
    model = "fake"

    def chat(self, messages: list[ChatMessage], *, json_mode=False, temperature=0.3) -> str:
        return json.dumps({
            "answer": "Unsupported answer.",
            "source_span_ids": ["SPAN-deadbeef"],
            "used_report_ids": ["REP-deadbeef"],
            "confidence": 0.8,
        })


class LastCitationClient:
    model = "fake"

    def __init__(self) -> None:
        self.cited_spans: list[str] = []

    def chat(self, messages: list[ChatMessage], *, json_mode=False, temperature=0.3) -> str:
        text = "\n".join(m.content for m in messages)
        spans = re.findall(r"SPAN-[0-9a-f]{8}", text)
        cited = spans[-1:] if spans else []
        self.cited_spans = cited
        return json.dumps({
            "answer": "Only the last provided span was needed.",
            "source_span_ids": cited,
            "used_report_ids": [],
            "confidence": 0.8,
        })


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
    context_trace = trace["retrieval_trace"]["context_service"]
    assert context_trace["pack_id"].startswith("PACK-")
    assert context_trace["snapshot"]["snapshot_id"].startswith("SNAP-")
    assert any(
        action["action_type"] == "synthesis"
        and action["child_id"] in res.prompt_trace_ids
        for action in context_trace["actions"]
    )
    assert len(db.list_query_traces(paths.state_db)) == 1


def test_context_evidence_block_joins_all_budgeted_items_without_truncation() -> None:
    items = [
        {
            "kind": "source_span",
            "record_id": "SPAN-a",
            "summary": "first",
            "detail": "A" * 12_000,
        },
        {
            "kind": "source_span",
            "record_id": "SPAN-b",
            "summary": "second",
            "detail": "B" * 12_000,
        },
    ]

    block = _context_evidence_block(items)

    assert "SPAN-a" in block
    assert "SPAN-b" in block
    assert "A" * 12_000 in block
    assert "B" * 12_000 in block


def test_context_evidence_block_does_not_render_none_values() -> None:
    block = _context_evidence_block([
        {
            "kind": None,
            "record_id": None,
            "item_id": "ITEM-1",
            "summary": None,
            "detail": None,
        }
    ])

    assert "None" not in block
    assert "ITEM-1" in block


def test_successful_answer_records_only_parsed_cited_spans(vault) -> None:
    paths, first_span = vault
    second_span = "SPAN-1234abcd"
    context_pack = {
        "route": "local",
        "source_span_ids": [first_span, second_span],
        "items": [
            {
                "kind": "source_span",
                "record_id": first_span,
                "summary": "First support.",
                "detail": "First detail.",
            },
            {
                "kind": "source_span",
                "record_id": second_span,
                "summary": "Second support.",
                "detail": "Second detail.",
            },
        ],
    }
    result = QueryResultV031(
        question="What does residual learning do?",
        route="local",
        trace_id="QTR-cited",
        source_span_ids=list(context_pack["source_span_ids"]),
    )
    client = LastCitationClient()

    QueryOrchestrator(paths, client)._run_answer_from_context(
        QueryRequest(question="What does residual learning do?", mode="local"),
        context_pack,
        "",
        result,
    )

    assert result.ok
    assert client.cited_spans
    assert result.source_span_ids == client.cited_spans
    assert result.source_span_ids != context_pack["source_span_ids"]


def test_failed_answer_validation_clears_answer_provenance(vault) -> None:
    paths, span = vault
    db.upsert_synthesis_node(
        paths.state_db,
        title="Cross-cutting insight",
        statement="Residual learning ~ discretized dynamics.",
        dependency_hash="d1",
        source_span_ids=[span],
        confidence=0.6,
    )

    res = QueryOrchestrator(paths, InvalidCitationClient()).run(
        QueryRequest(question="overall summary of themes", mode="global")
    )

    assert not res.ok
    assert res.error == "answer synthesis failed validation"
    assert res.source_span_ids == []
    assert res.community_report_ids == []
    assert res.synthesis_node_ids == []
    assert res.memory_path_ids == []
    assert res.insight_candidate_ids == []
    assert any("unknown source span ids" in warning for warning in res.warnings)

    trace = db.get_query_trace(paths.state_db, res.trace_id)
    assert trace is not None
    assert trace["source_span_ids"] == []
    assert trace["community_report_ids"] == []
    assert trace["synthesis_node_ids"] == []
    context_trace = trace["retrieval_trace"]["context_service"]
    selected_items = context_trace["selected_items"]
    assert span in [
        source_span_id
        for item in selected_items
        for source_span_id in item.get("source_span_ids", [])
    ]
    assert any(item.get("kind") == "community_report" for item in selected_items)
    assert any(item.get("kind") == "synthesis" for item in selected_items)
    assert trace["insight_candidate_ids"] == []
    actions = context_trace["actions"]
    synthesis_action = actions[-1]
    assert synthesis_action["action_type"] == "synthesis"
    assert synthesis_action["payload"]["synthesis_status"] == "failed"
    assert synthesis_action["payload"]["cited_source_span_ids"] == []


def test_synthesis_trace_update_tolerates_null_retrieval_trace(vault) -> None:
    paths, span = vault
    trace_id = db.insert_query_trace(
        paths.state_db,
        trace_id="QTR-nullrt",
        route="local",
        question_hash="q",
        source_span_ids=[span],
        retrieval_trace={},
    )
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE query_traces SET retrieval_trace_json = 'null' WHERE trace_id = ?",
            (trace_id,),
        )

    result = QueryResultV031(
        question="q",
        route="local",
        trace_id=trace_id,
        answer="a",
        prompt_trace_ids=["PTR-1"],
        source_span_ids=[span],
    )

    QueryOrchestrator(paths, DynamicFakeClient())._update_context_trace_after_synthesis(
        result,
        latency_ms=1,
    )

    trace = db.get_query_trace(paths.state_db, trace_id)
    assert trace is not None
    assert trace["retrieval_trace"]["context_service"]["actions"][0]["child_id"] == "PTR-1"


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
