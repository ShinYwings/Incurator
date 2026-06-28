"""XC-1 slice 1: error-handling logging for parsers/pdf.py.

The PyMuPDF/pymupdf4llm failure surface is opaque and version-dependent, so these
best-effort extractors keep a broad ``except`` (R2) but must now LOG instead of
swallowing silently while preserving graceful degradation.
"""

import logging
from pathlib import Path

from curator.parsers import pdf


def _missing_pdf(tmp_path: Path) -> Path:
    return tmp_path / "does_not_exist.pdf"


def test_get_page_count_returns_zero_and_logs(tmp_path, caplog):
    with caplog.at_level(logging.DEBUG, logger="curator.parsers.pdf"):
        assert pdf.get_page_count(_missing_pdf(tmp_path)) == 0
    assert any("page-count probe failed" in r.message for r in caplog.records)


def test_extract_pdf_toc_returns_empty_and_logs(tmp_path, caplog):
    with caplog.at_level(logging.DEBUG, logger="curator.parsers.pdf"):
        assert pdf._extract_pdf_toc(_missing_pdf(tmp_path)) == []
    assert any("outline extraction failed" in r.message for r in caplog.records)


def test_extract_pdf_images_returns_empty_and_logs(tmp_path, caplog):
    with caplog.at_level(logging.DEBUG, logger="curator.parsers.pdf"):
        assert pdf._extract_pdf_images(_missing_pdf(tmp_path)) == []
    assert any("image extraction failed" in r.message for r in caplog.records)


def test_parse_page_window_degrades_and_warns(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="curator.parsers.pdf"):
        assert pdf.parse_page_window(_missing_pdf(tmp_path), {1, 2}) == {}
    assert any("Windowed PDF parse failed" in r.message for r in caplog.records)
