"""Phase 7 (v0.3.1): backprop classification + insight lifecycle + source-truth safety."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db, insight_lifecycle
from curator.backprop_classifier import BackpropClassification, BackpropEvent, classify_feedback
from curator.llm import ChatMessage


class FakeClient:
    model = "fake"

    def __init__(self, payload: str) -> None:
        self._payload = payload

    def chat(self, messages: list[ChatMessage], *, json_mode=False, temperature=0.3) -> str:
        return self._payload


@pytest.fixture()
def vault():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        paths = cfg.WikiPaths(root)
        db.init_db(paths.state_db)
        yield paths


def _classify_json(cls: str, action: str, impact="none") -> str:
    return json.dumps({
        "classification": cls, "confidence": 0.8, "affected_nodes": ["ATM-1", "CON-2"],
        "source_truth_impact": impact, "recommended_action": action, "reason": "r",
    })


def test_classify_correction(vault) -> None:
    paths = vault
    client = FakeClient(_classify_json("correction", "patch_generated", "source_misread"))
    result = classify_feedback(paths.state_db, BackpropEvent("old", "new"), client)
    assert result.ok
    assert result.classification == "correction"
    assert result.affected_nodes == ["ATM-1", "CON-2"]
    # prompt run was traced
    assert db.get_prompt_run(paths.state_db, result.trace_id)


def test_classify_invalid_json_is_ambiguous(vault) -> None:
    paths = vault
    result = classify_feedback(paths.state_db, BackpropEvent("a", "b"), FakeClient("garbage"))
    assert not result.ok
    assert result.classification == "ambiguous"
    assert result.recommended_action == "flag_review"


def test_plan_action_never_writes_source_truth() -> None:
    for cls in ("correction", "contradiction", "derived_insight", "style_only",
                "promotion_request", "ambiguous"):
        plan = insight_lifecycle.plan_action(
            BackpropClassification(classification=cls, affected_nodes=["ATM-1"])
        )
        assert plan.writes_source_truth is False


def test_correction_only_targets_generated_nodes() -> None:
    plan = insight_lifecycle.plan_action(
        BackpropClassification(classification="correction",
                               affected_nodes=["ATM-1", "03_Notes/x.md", "CON-2"])
    )
    assert plan.action == "patch_generated"
    assert set(plan.patch_node_ids) == {"ATM-1", "CON-2"}  # source path excluded


def test_derived_insight_creates_candidate(vault) -> None:
    paths = vault
    cls = BackpropClassification(classification="derived_insight", confidence=0.6,
                                 affected_nodes=["CON-2"], trace_id="PTR-x")
    plan = insight_lifecycle.plan_action(cls)
    assert plan.action == "create_insight_candidate"
    ins_id = insight_lifecycle.create_insight_from_classification(
        paths.state_db, cls, statement="ResNet ~ Euler step.", workspace_id="lab",
    )
    pending = db.list_insight_candidates(paths.state_db, workspace_id="lab", status="pending")
    assert len(pending) == 1
    assert pending[0]["id"] == ins_id
    assert pending[0]["classification"] == "derived_insight"


def test_contradiction_candidate_needs_review(vault) -> None:
    paths = vault
    cls = BackpropClassification(classification="contradiction", affected_nodes=["ATM-1"])
    ins_id = insight_lifecycle.create_insight_from_classification(
        paths.state_db, cls, statement="A conflicts with B", workspace_id="lab",
    )
    needs = db.list_insight_candidates(paths.state_db, workspace_id="lab", status="needs_review")
    assert any(c["id"] == ins_id for c in needs)


def test_promotion_writes_only_to_wiki(vault) -> None:
    paths = vault
    cls = BackpropClassification(classification="derived_insight", trace_id="PTR-x")
    ins_id = insight_lifecycle.create_insight_from_classification(
        paths.state_db, cls, statement="Promote me please", workspace_id="lab",
    )
    rel = insight_lifecycle.promote_insight(paths, ins_id)
    assert rel.startswith("02_Wiki/")
    assert (paths.root / rel).exists()
    assert "03_Notes" not in rel and "04_Resources" not in rel
    # candidate marked promoted
    cand = db.get_insight_candidate(paths.state_db, ins_id)
    assert cand["status"] == "promoted"
    # source folders untouched
    assert not (paths.root / "03_Notes").exists()
    assert not (paths.root / "04_Resources").exists()
