"""The search index holds a span's full text, not its first 200 characters.

`source_spans` has no full-text column. It stores `content_hash`, computed over
the whole span, and `text_preview` — `" ".join(text.split())[:_PREVIEW_CHARS]`
(`pipeline/source_spans.py:159-163`). The materializer indexed that preview as
the span's searchable body, so the searchable body of a span WAS 200 characters.

Measured on a real vault before this changed: 4,865 of 11,774 spans (41.3%) sat
exactly at the cap, with a true median length of 418 and a p90 of 1,426.

It was not only a recall problem. The primary hybrid-search path reads this body
back out (`engine.py::_hydrate`) and hands it to the model, so a sentence cut
mid-word reached the answer. Only the entity/source-section route re-hydrated.

These tests drive the REAL `materialize_search_documents`. The first version of
this file monkeypatched the helper and then asserted on the monkeypatched value,
which proves the fixture and not the code — review caught it, and a revert of the
fix would have passed every test in it.
"""

from __future__ import annotations

from pathlib import Path

from curator import db
from curator.pipeline.source_spans import _PREVIEW_CHARS
from curator.retrieval import materializer

LONG_BODY = (
    "Rasterisation proceeds tile by tile. " * 8
    + "The distinctive marker STOPTHEPOP appears only near the end."
)


def _seed_span(db_path: Path, *, full_text: str) -> str:
    """Register one source and one span whose preview is capped like a real one."""
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        source_id = conn.execute(
            """
            INSERT INTO sources
                (relpath, content_hash, file_type, bytes, added_at, status)
            VALUES ('04_Resources/paper.md', 'h1', 'md', 128,
                    '2026-09-01T00:00:00Z', 'curated')
            """
        ).lastrowid
    preview = " ".join(full_text.split())[:_PREVIEW_CHARS]
    return db.upsert_source_span(
        db_path,
        source_id=int(source_id),
        relpath="04_Resources/paper.md",
        span_type="paragraph",
        section_title="Method",
        content_hash="span-hash",
        text_preview=preview,
    )


def test_the_preview_really_is_capped() -> None:
    """Guard the premise. If the cap moves, the rest of this file is moot."""
    assert _PREVIEW_CHARS == 200
    assert len(" ".join(LONG_BODY.split())[:_PREVIEW_CHARS]) == 200


def test_a_term_past_the_cap_is_absent_when_the_source_cannot_be_read(
    tmp_path: Path,
) -> None:
    """The defect, and the honest limit of the fix.

    The seeded source file does not exist on disk, so hydration cannot recover
    anything and the body falls back to the preview — which is exactly what
    happens on a vault whose PDFs live behind a permission the process lacks. The
    marker past character 200 is unfindable, and the run SAYS so.
    """
    db_path = tmp_path / "state.sqlite"
    span_id = _seed_span(db_path, full_text=LONG_BODY)

    result = materializer.materialize_search_documents(db_path)

    assert result.preview_fallbacks == 1, "a silent fallback is the failure mode"
    doc = db.get_search_document(db_path, f"DOC-source_span-{span_id}")
    assert len(doc["body"]) == _PREVIEW_CHARS
    assert "STOPTHEPOP" not in doc["body"]


def test_a_term_past_the_cap_reaches_the_index_when_the_source_is_readable(
    tmp_path: Path, monkeypatch
) -> None:
    """The fix, through the real materializer.

    Hydration is stubbed at the pipeline boundary rather than at the helper, so
    the materializer's own decision — use hydrated text, else the preview, and
    count it — is the thing under test.
    """
    db_path = tmp_path / "state.sqlite"
    span_id = _seed_span(db_path, full_text=LONG_BODY)

    monkeypatch.setattr(
        "curator.pipeline.compile.hydrate_spans",
        lambda _p, ids: {sid: LONG_BODY for sid in ids},
    )
    result = materializer.materialize_search_documents(db_path)

    assert result.preview_fallbacks == 0
    doc = db.get_search_document(db_path, f"DOC-source_span-{span_id}")
    assert "STOPTHEPOP" in doc["body"], "the term past the cap never reached the index"
    assert len(doc["body"]) > _PREVIEW_CHARS


def test_an_untruncated_span_is_not_hydrated_at_all(
    tmp_path: Path, monkeypatch
) -> None:
    """Hydration costs a source re-parse, so it must buy something.

    A preview shorter than the cap already holds the whole span. Hydrating it
    would re-parse the file for nothing AND change its body for whitespace alone
    — `text_preview` collapses internal whitespace and hydration does not —
    re-embedding 53% of untruncated spans for no gain. Measured; review caught it.
    """
    db_path = tmp_path / "state.sqlite"
    _seed_span(db_path, full_text="Short and complete.")

    asked: list[list[str]] = []

    def _spy(_p, ids):
        asked.append(list(ids))
        return {}

    monkeypatch.setattr("curator.pipeline.compile.hydrate_spans", _spy)
    result = materializer.materialize_search_documents(db_path)

    assert all(not ids for ids in asked), f"re-parsed for nothing: {asked}"
    assert result.preview_fallbacks == 0
