"""Phase 5 (v0.3.1): community detection + report generation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from curator import db
from curator.llm import ChatMessage
from curator.pipeline import community_reports as cr


class FakeClient:
    def __init__(self, responses: list[str], model: str = "fake") -> None:
        self._responses = list(responses)
        self.model = model

    def chat(self, messages: list[ChatMessage], *, json_mode=False, temperature=0.3) -> str:
        return self._responses.pop(0)


@pytest.fixture()
def graph_db():
    with tempfile.TemporaryDirectory() as t:
        path = Path(t) / "state.sqlite"
        db.init_db(path)
        # Two connected entities + one isolated entity in a separate component.
        a = db.upsert_graph_entity(path, canonical_name="ResNet", entity_type="method",
                                   source_span_ids=["SPAN-1"])
        b = db.upsert_graph_entity(path, canonical_name="degradation", entity_type="concept",
                                   source_span_ids=["SPAN-1"])
        c = db.upsert_graph_entity(path, canonical_name="Neural ODE", entity_type="method")
        d = db.upsert_graph_entity(path, canonical_name="Euler", entity_type="concept")
        db.upsert_graph_relation(path, source_entity_id=a, target_entity_id=b,
                                 relation_type="addresses", confidence=0.9,
                                 source_span_ids=["SPAN-1"])
        db.upsert_graph_relation(path, source_entity_id=c, target_entity_id=d,
                                 relation_type="discretizes", confidence=0.7)
        yield path, {"a": a, "b": b, "c": c, "d": d}


def test_detect_communities_groups_connected_components(graph_db) -> None:
    path, ids = graph_db
    plans = cr.detect_communities(path)
    assert len(plans) == 2
    members = [set(p.entity_ids) for p in plans]
    assert {ids["a"], ids["b"]} in members
    assert {ids["c"], ids["d"]} in members
    # Each plan has a stable key and its relations.
    for p in plans:
        assert p.community_key.startswith("comm-")
        assert len(p.relation_ids) == 1


def _report_json() -> str:
    return json.dumps(
        {
            "title": "Residual learning community",
            "summary": "ResNet addresses the degradation problem.",
            "full_content": "Longer report ...",
            "findings": [
                {"summary": "ResNet addresses degradation", "explanation": "",
                 "source_span_ids": ["SPAN-1"], "rank": 0.8}
            ],
            "contradictions": [],
            "source_span_ids": ["SPAN-1"],
            "rank": 0.7,
        }
    )


def test_generate_community_report_persists(graph_db) -> None:
    path, ids = graph_db
    plans = cr.detect_communities(path)
    target = next(p for p in plans if ids["a"] in p.entity_ids)
    client = FakeClient([_report_json()])
    rep_id = cr.generate_community_report(path, client, target)
    assert rep_id and rep_id.startswith("REP-")
    report = db.get_community_report(path, rep_id)
    assert report["title"] == "Residual learning community"
    assert report["dependency_hash"]
    assert report["source_span_ids"] == ["SPAN-1"]
    assert report["findings"][0]["rank"] == 0.8


def test_report_dependency_hash_changes_when_graph_changes(graph_db) -> None:
    path, ids = graph_db
    plans = cr.detect_communities(path)
    target = next(p for p in plans if ids["a"] in p.entity_ids)
    rep1 = cr.generate_community_report(path, FakeClient([_report_json()]), target)
    h1 = db.get_community_report(path, rep1)["dependency_hash"]
    # Mutate an entity in the community -> its updated_at changes -> dep hash differs.
    db.upsert_graph_entity(path, canonical_name="ResNet", entity_type="method",
                           description="updated desc")
    rep2 = cr.generate_community_report(path, FakeClient([_report_json()]), target)
    h2 = db.get_community_report(path, rep2)["dependency_hash"]
    assert h1 != h2
