"""Span-level extraction loss is recorded and stays visible (SYSTEM_BEHAVIOR §26.2b).

Measured on the reporting vault: a 27-page paper whose displayed equations are
rasterized produced 95 spans that are nothing but
`**==> picture [W x H] intentionally omitted <==**`, and its CTX projection —
the text the plugin actually reads — contained the placeholder ZERO times,
because `_section_preview` stripped it to whitespace. The loss was recorded in
the span and erased from the page.
"""

from __future__ import annotations

from curator.ingest_raw import _section_preview
from curator.pipeline.source_spans import classify_span_loss, spans_from_sections

PLACEHOLDER = "**==> picture [221 x 18] intentionally omitted <==**"


class TestClassifySpanLoss:
    def test_picture_placeholder_is_image_only_with_its_geometry(self) -> None:
        loss = classify_span_loss(PLACEHOLDER)
        assert loss is not None
        assert loss["verdict"] == "image_only"
        assert loss["region"] == {"width": 221, "height": 18}
        assert loss["classified_at"]

    def test_ordinary_prose_records_no_loss(self) -> None:
        assert classify_span_loss("This is a quadratic equation in λ1 and λ2.") is None

    def test_empty_text_records_no_loss(self) -> None:
        assert classify_span_loss("") is None
        assert classify_span_loss("   ") is None

    def test_placeholder_inside_a_larger_paragraph_still_counts(self) -> None:
        text = f"and can thus be written as {PLACEHOLDER} where Q is symmetric."
        loss = classify_span_loss(text)
        assert loss is not None and loss["verdict"] == "image_only"

    def test_geometry_is_omitted_rather_than_guessed_when_absent(self) -> None:
        """Absence is recorded as absence — never zeros, never nulls."""
        loss = classify_span_loss("**==> picture intentionally omitted <==**")
        assert loss is not None
        assert loss["verdict"] == "image_only"
        assert "region" not in loss

    def test_region_is_not_a_crop_locator(self) -> None:
        """The placeholder carries no page coordinates, so none may be invented."""
        loss = classify_span_loss(PLACEHOLDER)
        assert loss is not None
        assert set(loss["region"]) == {"width", "height"}


class TestSpansCarryTheLossRecord:
    def test_a_placeholder_span_is_stored_with_its_loss(self) -> None:
        spans = spans_from_sections(
            [
                {
                    "id": "s1",
                    "title": "Triangulation",
                    "page": 11,
                    "text": (
                        "This is a quadratic equation in the endpoint depths,\n"
                        "and can thus be written as\n\n"
                        f"{PLACEHOLDER}\n\n"
                        "Note that there is no constant term."
                    ),
                }
            ]
        )
        lossy = [s for s in spans if s.loss is not None]
        assert len(lossy) == 1, f"expected exactly one lossy span, got {len(lossy)}"
        assert lossy[0].loss["verdict"] == "image_only"
        # The prose spans around it must NOT be marked lossy.
        assert all(s.loss is None for s in spans if s is not lossy[0])

    def test_a_clean_section_marks_nothing(self) -> None:
        spans = spans_from_sections(
            [{"id": "s1", "title": "Intro", "page": 1, "text": "Plain prose only."}]
        )
        assert spans and all(s.loss is None for s in spans)


class TestPreviewKeepsTheGapVisible:
    """§26.2b: a projection must not close the gap silently."""

    def test_preview_renders_a_marker_instead_of_eliding(self) -> None:
        text = f"and can thus be written as {PLACEHOLDER} where Q is symmetric."
        preview = _section_preview(text)
        assert "intentionally omitted" not in preview, "raw parser noise leaked"
        assert "[image" in preview, (
            "the placeholder was stripped to whitespace, so the CTX body — and "
            "therefore the plugin's chat context — shows an unmarked gap"
        )
        assert "quadratic" not in preview or "written as" in preview

    def test_preview_of_clean_prose_is_unchanged(self) -> None:
        assert _section_preview("Plain prose only.") == "Plain prose only."

    def test_preview_of_only_a_placeholder_is_the_marker_alone(self) -> None:
        preview = _section_preview(PLACEHOLDER)
        assert preview.strip() != "", "a placeholder-only section previewed as empty"
        assert "[image" in preview
