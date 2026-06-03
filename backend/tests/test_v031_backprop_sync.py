"""Phase 8c (v0.3.1): Exhibition reverse-parse backprop sync."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from curator import backprop_sync, config as cfg, db
from curator.llm import ChatMessage


class FakeClient:
    model = "fake"

    def __init__(self, *payloads: str) -> None:
        self._payloads = list(payloads)

    def chat(self, messages: list[ChatMessage], *, json_mode=False, temperature=0.3) -> str:
        return self._payloads.pop(0) if self._payloads else "{}"

    def close(self) -> None:
        ...


@pytest.fixture()
def vault():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        paths = cfg.WikiPaths(root)
        db.init_db(paths.state_db)
        paths.exhibitions.mkdir(parents=True, exist_ok=True)
        exh = paths.exhibitions / "EXH-abcd1234.md"
        exh.write_text(
            "---\nid: EXH-abcd1234\ntype: exhibition\nworkspace_id: Lab\n"
            "core_concepts:\n  - 03_Concepts/CON-1111\nsource_span_ids:\n  - SPAN-aaaa1111\n---\n\n"
            "# ResNet as Euler discretization\n\nResidual blocks resemble one Euler step.\n",
            encoding="utf-8",
        )
        yield paths


def _classify(cls: str, action: str) -> str:
    return json.dumps({
        "classification": cls, "confidence": 0.8, "affected_nodes": ["CON-1111"],
        "source_truth_impact": "none", "recommended_action": action, "reason": "r",
    })


def test_derived_insight_creates_candidate(vault) -> None:
    paths = vault
    client = FakeClient(_classify("derived_insight", "create_insight_candidate"))
    res = backprop_sync.backprop_from_exhibition(paths, client, "EXH-abcd1234")
    assert res.ok
    assert res.classification.classification == "derived_insight"
    assert res.plan.action == "create_insight_candidate"
    assert res.insight_candidate_id
    cands = db.list_insight_candidates(paths.state_db, workspace_id="Lab", status="pending")
    assert len(cands) == 1
    # source truth untouched
    assert not (paths.root / "03_Notes").exists()


def test_correction_builds_patch_plan_targeting_generated_only(vault) -> None:
    paths = vault
    patch = json.dumps({
        "nodes_to_patch": ["CON-1111"], "nodes_to_invalidate": [],
        "reports_to_refresh": [], "exhibitions_to_refresh": ["EXH-abcd1234"],
        "preserve_human_verified": [], "sources_unchanged": ["03_Notes/x.md"], "notes": "",
    })
    client = FakeClient(_classify("correction", "patch_generated"), patch)
    res = backprop_sync.backprop_from_exhibition(paths, client, "EXH-abcd1234")
    assert res.ok
    assert res.plan.action == "patch_generated"
    assert res.patch_plan is not None
    assert res.patch_plan["nodes_to_patch"] == ["CON-1111"]
    # no insight candidate for a correction
    assert res.insight_candidate_id == ""


def test_dry_run_creates_no_candidate(vault) -> None:
    paths = vault
    client = FakeClient(_classify("derived_insight", "create_insight_candidate"))
    res = backprop_sync.backprop_from_exhibition(paths, client, "EXH-abcd1234", dry_run=True)
    assert res.dry_run
    assert res.insight_candidate_id == ""
    assert db.list_insight_candidates(paths.state_db, status="pending") == []


def test_missing_exhibition_errors(vault) -> None:
    paths = vault
    res = backprop_sync.backprop_from_exhibition(paths, FakeClient(), "EXH-nope")
    assert not res.ok
    assert "not found" in res.error
