"""Synthesis audit reports for proving L4 -> L1 grounding."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db
from curator.inspection import synthesis_audit


@pytest.fixture()
def seeded_vault():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        paths = cfg.WikiPaths(root)
        db.init_db(paths.state_db)
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES ('04_Resources/resnet.md', 'source-hash', 'md', 128, datetime('now'))"
            )
        ptr_unit = db.record_prompt_run(
            paths.state_db,
            prompt_id="curator.knowledge_unit_extract",
            prompt_version="v1",
            family="knowledge_units",
            role="extractor",
            input_hash="unit-input",
        )
        db.finish_prompt_run(paths.state_db, ptr_unit, output_hash="unit-output")
        span = db.upsert_source_span(
            paths.state_db,
            source_id=1,
            relpath="04_Resources/resnet.md",
            span_type="paragraph",
            page_number=12,
            section_title="Residual Learning",
            toc_id="s2",
            content_hash="span-hash",
            text_preview="Residual connections ease optimization.",
            metadata={"paragraph": 3},
        )
        unit = db.upsert_knowledge_unit(
            paths.state_db,
            unit_type="claim",
            canonical_name="Residual learning",
            statement="Residual connections ease optimization.",
            source_span_ids=[span],
            source_id=1,
            confidence=0.9,
            prompt_run_id=ptr_unit,
        )
        ent_a = db.upsert_graph_entity(
            paths.state_db,
            canonical_name="Residual learning",
            entity_type="concept",
            source_span_ids=[span],
            knowledge_unit_ids=[unit],
        )
        ent_b = db.upsert_graph_entity(
            paths.state_db,
            canonical_name="Euler discretization",
            entity_type="concept",
            source_span_ids=[span],
            knowledge_unit_ids=[unit],
        )
        rel = db.upsert_graph_relation(
            paths.state_db,
            source_entity_id=ent_a,
            target_entity_id=ent_b,
            relation_type="analogous_to",
            source_span_ids=[span],
            confidence=0.7,
        )
        ptr_report = db.record_prompt_run(
            paths.state_db,
            prompt_id="curator.community_report_write",
            prompt_version="v1",
            family="community_reports",
            role="synthesizer",
            input_hash="report-input",
        )
        db.finish_prompt_run(paths.state_db, ptr_report, output_hash="report-output")
        report = db.upsert_community_report(
            paths.state_db,
            community_key="comm-residual",
            title="Residual methods",
            summary="Residual methods connect optimization and discretization.",
            full_content="Full report.",
            dependency_hash="report-dep",
            findings=[{"summary": "Residual blocks resemble Euler steps.", "rating": 0.7}],
            entity_ids=[ent_a, ent_b],
            relation_ids=[rel],
            source_span_ids=[span],
            rank=0.8,
            prompt_run_id=ptr_report,
        )
        ptr_syn = db.record_prompt_run(
            paths.state_db,
            prompt_id="curator.synthesis_write",
            prompt_version="v1",
            family="synthesis",
            role="synthesizer",
            input_hash="syn-input",
        )
        db.finish_prompt_run(paths.state_db, ptr_syn, output_hash="syn-output")
        syn = db.upsert_synthesis_node(
            paths.state_db,
            title="Residual learning as dynamics",
            statement="Residual learning and Euler discretization share an update view.",
            full_content="Grounded explanation.",
            dependency_hash="syn-dep",
            community_report_ids=[report],
            source_span_ids=[span],
            confidence=0.82,
            prompt_run_id=ptr_syn,
        )
        db.record_artifact_dependency(
            paths.state_db,
            artifact_id=syn,
            artifact_type="synthesis_node",
            depends_on_id=span,
            depends_on_type="source_span",
            dependency_hash="span-hash",
        )
        yield paths, {
            "span": span,
            "unit": unit,
            "entities": [ent_a, ent_b],
            "relation": rel,
            "report": report,
            "synthesis": syn,
            "prompts": [ptr_unit, ptr_report, ptr_syn],
        }


def test_build_synthesis_audit_hydrates_l4_to_l1_chain(seeded_vault) -> None:
    paths, ids = seeded_vault

    audit = synthesis_audit.build_synthesis_audit(paths.state_db, ids["synthesis"])

    assert audit["ok"] is True
    assert audit["kind"] == "synthesis"
    assert audit["synthesis"]["id"] == ids["synthesis"]
    assert [r["id"] for r in audit["community_reports"]] == [ids["report"]]
    assert {e["id"] for e in audit["entities"]} == set(ids["entities"])
    assert [r["id"] for r in audit["relations"]] == [ids["relation"]]
    assert [u["id"] for u in audit["knowledge_units"]] == [ids["unit"]]
    assert [s["id"] for s in audit["source_spans"]] == [ids["span"]]
    assert audit["source_spans"][0]["metadata"] == {"paragraph": 3}
    assert {p["traceId"] for p in audit["prompt_runs"]} == set(ids["prompts"])
    assert audit["warnings"] == []
    assert audit["dependency_warnings"] == []


def test_synthesis_audit_warns_on_missing_prompt_and_stale_dependency(seeded_vault) -> None:
    paths, ids = seeded_vault
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE synthesis_nodes SET prompt_run_id = 'PTR-missing' WHERE id = ?",
            (ids["synthesis"],),
        )
    db.record_artifact_dependency(
        paths.state_db,
        artifact_id=ids["synthesis"],
        artifact_type="synthesis_node",
        depends_on_id=ids["span"],
        depends_on_type="source_span",
        dependency_hash="old-span-hash",
    )

    audit = synthesis_audit.build_synthesis_audit(paths.state_db, ids["synthesis"])

    assert audit["ok"] is True
    assert any("missing prompt trace: PTR-missing" in w for w in audit["warnings"])
    assert any("stale dependency" in w for w in audit["dependency_warnings"])


def test_build_answer_audit_hydrates_query_trace_evidence(seeded_vault) -> None:
    paths, ids = seeded_vault
    trace_id = db.insert_query_trace(
        paths.state_db,
        trace_id="QTR-answer01",
        route="global",
        question_hash="question-hash",
        workspace_id="default",
        route_reason="broad synthesis",
        synthesis_node_ids=[ids["synthesis"]],
        community_report_ids=[ids["report"]],
        source_span_ids=[ids["span"]],
        prompt_trace_ids=[ids["prompts"][2]],
        warnings=["reranker_unavailable"],
        latency_ms=17,
    )

    audit = synthesis_audit.build_answer_audit(paths.state_db, trace_id)

    assert audit["ok"] is True
    assert audit["kind"] == "answer"
    assert audit["query_trace"]["traceId"] == trace_id
    assert audit["query_trace"]["route"] == "global"
    assert audit["synthesis"]["id"] == ids["synthesis"]
    assert [r["id"] for r in audit["community_reports"]] == [ids["report"]]
    assert audit["warnings"] == ["reranker_unavailable"]
