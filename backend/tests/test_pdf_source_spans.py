"""Phase 4 (v0.3.1): PDF source spans carry page provenance."""

from __future__ import annotations

import tempfile
from pathlib import Path

from curator import db
from curator.pipeline import source_spans as ss


def _pdf_sections():
    # Shape produced by ingest_raw._extract_pdf_sections: page-numbered sections.
    return [
        {"id": "s1", "title": "Introduction", "page": 1, "text": "Intro on page one.\n\nMore intro."},
        {"id": "s2", "title": "Method", "page": 4, "text": "The method is described here."},
    ]


def test_pdf_spans_carry_page_numbers() -> None:
    spans = ss.spans_from_sections(_pdf_sections())
    by_section = {}
    for s in spans:
        by_section.setdefault(s.toc_id, []).append(s)
    assert all(s.page_number == 1 for s in by_section["s1"])
    assert all(s.page_number == 4 for s in by_section["s2"])
    assert by_section["s2"][0].section_title == "Method"


def test_pdf_spans_persist_page_number() -> None:
    with tempfile.TemporaryDirectory() as t:
        dbp = Path(t) / "state.sqlite"
        db.init_db(dbp)
        with db.connect(dbp) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                ("04_Resources/p.pdf", "h", "pdf", 1),
            )
        spans = ss.spans_from_sections(_pdf_sections())
        ss.store_source_spans(dbp, 1, "04_Resources/p.pdf", spans)
        rows = db.list_source_spans(dbp, 1)
        pages = {r["section_title"]: r["page_number"] for r in rows}
        assert pages["Method"] == 4
        # ordered by page_number then start
        assert [r["page_number"] for r in rows] == sorted(r["page_number"] for r in rows)
