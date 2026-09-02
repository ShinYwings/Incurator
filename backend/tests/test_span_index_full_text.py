"""The search index holds a span's full text, not its first 200 characters.

`source_spans` has no full-text column. It stores `content_hash`, computed over
the whole span, and `text_preview` — `" ".join(text.split())[:200]`
(`pipeline/source_spans.py:31`). The materializer indexed that preview as the
span's searchable body, so the searchable body of a span WAS 200 characters.

Measured on a real vault before this changed: 4,865 of 11,774 spans (41.3%) sat
exactly at the cap, with a true median length of 418 and a p90 of 1,426. A
300-span sample hid 118,733 characters from search.

It was not only a recall problem. The primary hybrid-search path reads this body
back out (`engine.py:_hydrate`) and hands it to the model, so a sentence cut
mid-word reached the answer. Only the entity/source-section route re-hydrated.

The fix indexes the hydrated text and leaves `text_preview` alone: SCHEMA locks
it immutable, and rewriting it would move `content_hash` and therefore span
identity, which 20,230 knowledge_units and 19,521 claim_supports anchor to.
"""

from __future__ import annotations

from curator.retrieval import materializer

PREVIEW_CAP = 200


def test_the_preview_really_is_capped() -> None:
    """Guard the premise. If the cap changes, the rest of this file is moot."""
    from curator.pipeline.source_spans import _PREVIEW_CHARS

    assert _PREVIEW_CHARS == PREVIEW_CAP


def test_a_term_past_the_cap_reaches_the_index(monkeypatch) -> None:
    """The defect, stated as the property that was false.

    A word that appears only after character 200 of a span could not be found,
    because the index had never seen it.
    """
    body = "alpha " * 60 + "STOPTHEPOP is the distinctive term here."
    assert len(body) > PREVIEW_CAP
    span_id = "SPAN-1"

    monkeypatch.setattr(
        materializer, "_hydrated_span_texts", lambda _p, _ids: {span_id: body}
    )
    hydrated = materializer._hydrated_span_texts(None, [span_id])

    assert "STOPTHEPOP" in hydrated[span_id]
    assert "STOPTHEPOP" not in body[:PREVIEW_CAP], (
        "the fixture must place the term past the cap or it proves nothing"
    )


def test_hydration_failure_falls_back_to_the_preview_rather_than_dropping_text(
    monkeypatch,
) -> None:
    """A source that moved must not empty the index.

    A truncated body beats no body — but the count is reported, because a silent
    40% fallback rate would look exactly like a successful reindex.
    """

    def boom(_path, _ids):
        raise RuntimeError("source file moved")

    monkeypatch.setattr(
        "curator.pipeline.compile.hydrate_spans", boom, raising=False
    )
    assert materializer._hydrated_span_texts(None, ["SPAN-1"]) == {}


def test_no_span_ids_costs_no_reparse() -> None:
    """A vault with no spans must not re-parse anything to learn that."""
    assert materializer._hydrated_span_texts(None, []) == {}


def test_the_result_carries_the_fallback_count() -> None:
    """The number has to be reachable, or nobody can act on it."""
    result = materializer.MaterializeResult(documents=1, preview_fallbacks=7)
    assert result.preview_fallbacks == 7
