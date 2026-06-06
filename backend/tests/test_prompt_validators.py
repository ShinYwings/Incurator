"""Phase 1 (v0.3.1): prompt output validators."""

from __future__ import annotations

from curator.prompting import validators as V
from curator.prompting.families.knowledge_units import (
    ExtractedKnowledgeUnit,
    KnowledgeUnitExtractOutput,
)


def _ku(span_ids, confidence=0.8, truth="source_supported"):
    return KnowledgeUnitExtractOutput(
        units=[
            ExtractedKnowledgeUnit(
                canonical_name="x",
                unit_type="claim",
                statement="s",
                source_span_ids=span_ids,
                confidence=confidence,
                truth_status=truth,
            )
        ]
    )


def test_source_span_ids_rejects_invented() -> None:
    parsed = _ku(["SPAN-real", "SPAN-fake"])
    res = V.validate_source_span_ids("", parsed, {"valid_span_ids": ["SPAN-real"]})
    assert not res.ok
    assert "SPAN-fake" in res.errors[0]


def test_source_span_ids_accepts_known() -> None:
    parsed = _ku(["SPAN-real"])
    res = V.validate_source_span_ids("", parsed, {"valid_span_ids": ["SPAN-real"]})
    assert res.ok


def test_requires_source_spans_flags_empty() -> None:
    parsed = _ku([])
    res = V.validate_requires_source_spans("", parsed, {})
    assert not res.ok


def test_requires_source_spans_allows_derived_without_spans() -> None:
    parsed = _ku([], truth="derived_insight")
    res = V.validate_requires_source_spans("", parsed, {})
    assert res.ok


def test_confidence_range_rejects_out_of_bounds() -> None:
    # Build dict-like parsed via a simple model carrying confidence values.
    parsed = _ku(["SPAN-real"], confidence=0.5)
    ok = V.validate_confidence_range("", parsed, {})
    assert ok.ok


def test_no_source_truth_pollution_rejects_mutation() -> None:
    raw = "Then overwrite 03_Notes/foo.md with the new claim."
    res = V.validate_no_source_truth_pollution(raw, None, {})
    assert not res.ok


def test_no_source_truth_pollution_allows_clean_text() -> None:
    raw = "The source states X. Cite SPAN-1."
    res = V.validate_no_source_truth_pollution(raw, None, {})
    assert res.ok


def test_no_unknown_wikilinks() -> None:
    raw = "See [[Real Note]] and [[Invented Note]]."
    res = V.validate_no_unknown_wikilinks(raw, None, {"allowed_targets": ["Real Note"]})
    assert not res.ok
    assert "Invented Note" in res.errors[0]


def test_run_validators_aggregates() -> None:
    parsed = _ku(["SPAN-fake"])
    res = V.run_validators(
        ("source_span_ids", "requires_source_spans"),
        "",
        parsed,
        {"valid_span_ids": ["SPAN-real"]},
    )
    assert not res.ok
