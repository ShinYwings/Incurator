"""Phase 4 (v0.3.1): ATM markdown projection carries span/unit/trace provenance."""

from __future__ import annotations

import yaml

from curator.pipeline import projection


def _frontmatter(md: str) -> dict:
    assert md.startswith("---\n")
    fm = md.split("---\n", 2)[1]
    return yaml.safe_load(fm)


def test_atom_frontmatter_has_provenance() -> None:
    unit = {
        "id": "KNU-abc12345",
        "unit_type": "claim",
        "canonical_name": "Residual learning eases optimization",
        "statement": "Residual connections make deep nets easier to optimize.",
        "source_span_ids": ["SPAN-aaaa1111", "SPAN-bbbb2222"],
        "truth_status": "source_supported",
        "confidence": 0.9,
        "prompt_run_id": "PTR-deadbeef",
    }
    atom_id = projection.new_atom_id()
    md = projection.emit_atom_markdown(unit, atom_id, source_path="04_Resources/resnet.md")
    fm = _frontmatter(md)
    assert fm["id"] == atom_id
    assert fm["type"] == "atom"
    assert fm["unit_type"] == "claim"
    assert fm["knowledge_unit_ids"] == ["KNU-abc12345"]
    assert fm["source_span_ids"] == ["SPAN-aaaa1111", "SPAN-bbbb2222"]
    assert fm["prompt_trace_ids"] == ["PTR-deadbeef"]
    assert fm["truth_status"] == "source_supported"
    assert fm["source_path"] == "04_Resources/resnet.md"
    # Body contains the statement.
    assert "easier to optimize" in md


def test_new_atom_id_format() -> None:
    aid = projection.new_atom_id()
    assert aid.startswith("ATM-") and len(aid) == 12
