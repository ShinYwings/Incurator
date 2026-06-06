"""Phase 4 (v0.3.1): deterministic markdown source-span extraction."""

from __future__ import annotations

import tempfile
from pathlib import Path

from curator import db
from curator.pipeline import source_spans as ss


def _sections_from_markdown(text: str):
    # Mirror ingest_raw._extract_markdown_sections shape without importing the
    # heavy module: one section here, exercising the within-section splitter.
    return [{"id": "s1", "title": "Body", "page": 1, "text": text}]


def test_paragraphs_become_separate_spans() -> None:
    text = "First paragraph.\n\nSecond paragraph."
    spans = ss.spans_from_sections(_sections_from_markdown(text))
    types = [s.span_type for s in spans]
    assert types == ["paragraph", "paragraph"]
    assert spans[0].text == "First paragraph."
    assert spans[1].text == "Second paragraph."


def test_equation_block_is_its_own_span() -> None:
    text = "Intro text.\n\n$$E = mc^2$$\n\nAfter."
    spans = ss.spans_from_sections(_sections_from_markdown(text))
    kinds = [s.span_type for s in spans]
    assert "equation" in kinds
    eq = next(s for s in spans if s.span_type == "equation")
    assert eq.text == "$$E = mc^2$$"  # delimiters preserved exactly


def test_code_block_is_its_own_span() -> None:
    text = "Use this:\n\n```python\nprint('hi')\n```\n\nDone."
    spans = ss.spans_from_sections(_sections_from_markdown(text))
    code = [s for s in spans if s.span_type == "code"]
    assert len(code) == 1
    assert "print('hi')" in code[0].text


def test_single_chunk_section_is_heading_section() -> None:
    spans = ss.spans_from_sections([{"id": "s1", "title": "T", "page": 1, "text": "Just one line."}])
    assert len(spans) == 1
    assert spans[0].span_type == "heading_section"
    assert spans[0].toc_id == "s1"
    assert spans[0].section_title == "T"


def test_empty_section_skipped() -> None:
    spans = ss.spans_from_sections([{"id": "s1", "title": "T", "page": 1, "text": "   "}])
    assert spans == []


def test_content_hash_is_stable_and_text_sensitive() -> None:
    a = ss.spans_from_sections(_sections_from_markdown("X.\n\nY."))
    b = ss.spans_from_sections(_sections_from_markdown("X.\n\nY."))
    assert [s.content_hash for s in a] == [s.content_hash for s in b]
    assert a[0].content_hash != a[1].content_hash


def test_store_source_spans_roundtrip_and_idempotent() -> None:
    with tempfile.TemporaryDirectory() as t:
        dbp = Path(t) / "state.sqlite"
        db.init_db(dbp)
        with db.connect(dbp) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                ("03_Notes/x.md", "h", "md", 1),
            )
        spans = ss.spans_from_sections(_sections_from_markdown("A.\n\nB."))
        ids = ss.store_source_spans(dbp, 1, "03_Notes/x.md", spans)
        assert len(ids) == 2 and all(i.startswith("SPAN-") for i in ids)
        # Idempotent: same content reuses ids.
        ids2 = ss.store_source_spans(dbp, 1, "03_Notes/x.md", spans)
        assert ids2 == ids
        rows = db.list_source_spans(dbp, 1)
        assert {r["span_type"] for r in rows} == {"paragraph"}
        assert all(r["text_preview"] for r in rows)
