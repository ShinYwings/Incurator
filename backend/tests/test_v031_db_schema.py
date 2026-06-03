"""Phase 2 (v0.3.1): SQLite schema v4 tables and accessors.

Covers the new curation-native records defined in
docs/specs/curator_schema/SCHEMA_v0.3.1.md §11: source_spans, knowledge_units,
graph_entities, graph_relations, community_reports, memory_paths, prompt_runs,
curation_plans, insight_candidates, and artifact_dependencies.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from curator import db


@pytest.fixture()
def db_path() -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.sqlite"
        db.init_db(path)
        # A source row (id=1) so the source_spans foreign key resolves.
        with db.connect(path) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                ("04_Resources/paper.md", "hash-1", "md", 10),
            )
        yield path


def test_schema_version_is_4() -> None:
    assert db.SCHEMA_VERSION == 4


def test_v031_tables_exist(db_path: Path) -> None:
    expected = {
        "source_spans",
        "knowledge_units",
        "graph_entities",
        "graph_relations",
        "community_reports",
        "memory_paths",
        "prompt_runs",
        "curation_plans",
        "insight_candidates",
        "artifact_dependencies",
    }
    with db.connect(db_path) as conn:
        tables = {
            str(r[0])
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert expected <= tables


def test_source_span_roundtrip(db_path: Path) -> None:
    span_id = db.upsert_source_span(
        db_path,
        source_id=1,
        relpath="04_Resources/paper.md",
        span_type="paragraph",
        content_hash="span-hash-1",
        page_number=1,
        section_title="Introduction",
        toc_id="s1",
        start_char=0,
        end_char=120,
        text_preview="Residual learning ...",
    )
    assert span_id.startswith("SPAN-")
    spans = db.list_source_spans(db_path, source_id=1)
    assert len(spans) == 1
    assert spans[0]["id"] == span_id
    assert spans[0]["section_title"] == "Introduction"

    # Re-upserting the same (source_id, content_hash) is stable, not duplicated.
    again = db.upsert_source_span(
        db_path,
        source_id=1,
        relpath="04_Resources/paper.md",
        span_type="paragraph",
        content_hash="span-hash-1",
        text_preview="Residual learning ...",
    )
    assert again == span_id
    assert len(db.list_source_spans(db_path, source_id=1)) == 1


def test_knowledge_unit_roundtrip(db_path: Path) -> None:
    span_id = db.upsert_source_span(
        db_path,
        source_id=1,
        relpath="04_Resources/paper.md",
        span_type="paragraph",
        content_hash="span-hash-2",
    )
    ku_id = db.upsert_knowledge_unit(
        db_path,
        unit_type="claim",
        canonical_name="Residual learning eases optimization",
        statement="Residual connections make deep nets easier to optimize.",
        source_span_ids=[span_id],
        source_id=1,
        confidence=0.9,
        prompt_run_id="PTR-abc",
    )
    assert ku_id.startswith("KNU-")
    units = db.list_knowledge_units_for_source(db_path, source_id=1)
    assert len(units) == 1
    assert units[0]["truth_status"] == "source_supported"
    assert units[0]["source_span_ids"] == [span_id]


def test_graph_entity_dedup_and_relation(db_path: Path) -> None:
    e1 = db.upsert_graph_entity(
        db_path, canonical_name="ResNet", entity_type="method", description="d1"
    )
    e1_again = db.upsert_graph_entity(
        db_path, canonical_name="ResNet", entity_type="method", description="d2"
    )
    assert e1 == e1_again  # dedup by (canonical_name, entity_type)
    e2 = db.upsert_graph_entity(
        db_path, canonical_name="Neural ODE", entity_type="method"
    )
    rel_id = db.upsert_graph_relation(
        db_path,
        source_entity_id=e1,
        target_entity_id=e2,
        relation_type="reinterpreted_as",
        confidence=0.7,
        assertion_source="system_infers",
    )
    assert rel_id.startswith("REL-")
    neighborhood = db.relation_neighborhood(db_path, entity_ids=[e1])
    assert any(r["id"] == rel_id for r in neighborhood)


def test_prompt_run_lifecycle(db_path: Path) -> None:
    trace_id = db.record_prompt_run(
        db_path,
        prompt_id="curator.knowledge_unit_extract",
        prompt_version="v1",
        family="knowledge_units",
        role="extractor",
        model_provider="ollama",
        model_name="qwen",
        input_hash="in-1",
        source_ids=[1],
    )
    assert trace_id.startswith("PTR-")
    run = db.get_prompt_run(db_path, trace_id)
    assert run is not None
    assert run["validator_status"] == "pending"

    db.finish_prompt_run(
        db_path,
        trace_id,
        output_hash="out-1",
        validator_status="ok",
        validator_errors=[],
        latency_ms=42,
    )
    run2 = db.get_prompt_run(db_path, trace_id)
    assert run2["validator_status"] == "ok"
    assert run2["output_hash"] == "out-1"
    assert run2["finished_at"]


def test_curation_plan_roundtrip(db_path: Path) -> None:
    plan_id = db.record_curation_plan(
        db_path,
        workspace_id="resnet-lab",
        workspace_path="/v/01_Workspaces/resnet-lab",
        project="resnet",
        curate_spec_hash="spec-1",
        route="exhibition",
        source_policy={"include": ["03_Notes/**"], "exclude": []},
        retrieval_policy={"allowed_modes": ["local", "global"]},
        prompt_profile="technical-research",
    )
    assert plan_id.startswith("PLAN-")
    plan = db.get_curation_plan(db_path, workspace_id="resnet-lab")
    assert plan is not None
    assert plan["route"] == "exhibition"
    assert plan["source_policy"]["include"] == ["03_Notes/**"]


def test_insight_candidate_lifecycle(db_path: Path) -> None:
    ins_id = db.create_insight_candidate(
        db_path,
        workspace_id="resnet-lab",
        classification="derived_insight",
        statement="ResNet residual blocks ~ Euler discretization of an ODE.",
        evidence=[{"span": "SPAN-x"}],
        affected_node_ids=["CON-1"],
        confidence=0.6,
    )
    assert ins_id.startswith("INS-")
    pending = db.list_insight_candidates(db_path, workspace_id="resnet-lab")
    assert len(pending) == 1
    assert pending[0]["status"] == "pending"

    db.update_insight_candidate_status(db_path, ins_id, status="promoted")
    promoted = db.list_insight_candidates(
        db_path, workspace_id="resnet-lab", status="promoted"
    )
    assert len(promoted) == 1


def test_artifact_dependency_invalidation(db_path: Path) -> None:
    db.record_artifact_dependency(
        db_path,
        artifact_id="REP-1",
        artifact_type="community_report",
        depends_on_id="SPAN-1",
        depends_on_type="source_span",
        dependency_hash="h1",
    )
    db.record_artifact_dependency(
        db_path,
        artifact_id="EXH-1",
        artifact_type="exhibition",
        depends_on_id="SPAN-1",
        depends_on_type="source_span",
        dependency_hash="h1",
    )
    stale = db.dependents_of(db_path, depends_on_id="SPAN-1")
    stale_ids = {d["artifact_id"] for d in stale}
    assert stale_ids == {"REP-1", "EXH-1"}
