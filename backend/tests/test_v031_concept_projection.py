"""Phase 5 (v0.3.1): CON markdown projection from a community report."""

from __future__ import annotations

import yaml

from curator.pipeline import projection


def _frontmatter(md: str) -> dict:
    return yaml.safe_load(md.split("---\n", 2)[1])


def test_concept_markdown_carries_graph_provenance() -> None:
    report = {
        "id": "REP-aaaa1111",
        "community_key": "comm-abc123",
        "title": "Residual learning community",
        "summary": "ResNet addresses degradation.",
        "full_content": "Longer report body.",
        "findings": [{"summary": "ResNet addresses degradation", "rank": 0.8}],
        "entity_ids": ["ENT-1", "ENT-2"],
        "relation_ids": ["REL-1"],
        "source_span_ids": ["SPAN-1"],
        "rank": 0.7,
        "prompt_run_id": "PTR-deadbeef",
    }
    cid = projection.new_concept_id()
    md = projection.emit_concept_markdown(report, cid)
    fm = _frontmatter(md)
    assert fm["id"] == cid
    assert fm["type"] == "concept"
    assert fm["community_report_id"] == "REP-aaaa1111"
    assert fm["entity_ids"] == ["ENT-1", "ENT-2"]
    assert fm["source_span_ids"] == ["SPAN-1"]
    assert fm["prompt_trace_ids"] == ["PTR-deadbeef"]
    assert "Residual learning community" in md
    assert "ResNet addresses degradation" in md


def test_new_concept_id_format() -> None:
    cid = projection.new_concept_id()
    assert cid.startswith("CON-") and len(cid) == 12
