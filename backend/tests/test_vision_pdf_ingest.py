"""P4: VLM-PDF ingest pipeline (v0.22.0, SYSTEM_BEHAVIOR §26.2a).

Uses a fake vision client (no real model). Covers: VLM text becomes L1 with
parser_used=vlm, per-page parser_text retention, per-page fallback on failure,
the vision_max_pages_per_run rail, and the model-keyed cache (R12).
"""

from pathlib import Path

import fitz

from curator import db, ingest_raw
from curator.parsers.base import ParsedDocument


def _make_pdf(path: Path, pages: int = 2) -> None:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=300, height=200)
        page.insert_text((40, 80), f"parser text page {i + 1}", fontsize=18)
    doc.save(str(path))
    doc.close()


def _parsed(pdf: Path, pages: int = 2) -> ParsedDocument:
    pdf_pages = [{"page": i + 1, "text": f"parser text {i + 1}"} for i in range(pages)]
    return ParsedDocument(
        source_path=pdf,
        file_type="pdf",
        title="t",
        text="\n\n".join(p["text"] for p in pdf_pages),
        content_hash="h",
        bytes=pdf.stat().st_size,
        metadata={"pdf_pages": pdf_pages, "parser_used": "pymupdf4llm"},
    )


class _FakeVision:
    supports_vision = True

    def __init__(self, model: str = "ollama::test-vl", fail: bool = False) -> None:
        self.model = model
        self.fail = fail
        self.calls = 0

    def describe_image(self, _png: bytes, prompt: str = "") -> str:
        self.calls += 1
        if self.fail:
            raise RuntimeError("vision boom")
        return "$$VLMLATEX$$"


def _cfg(**overrides) -> dict:
    llm = {"vision_render_dpi": 80, "vision_max_image_px": 1600,
           "vision_max_pages_per_run": 300}
    llm.update(overrides)
    return {"llm": llm}


def test_vlm_text_becomes_l1_with_parser_used_vlm(tmp_path) -> None:
    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, 2)
    parsed = _parsed(pdf, 2)
    vc = _FakeVision()
    ingest_raw._apply_vlm_pdf_extraction(parsed, pdf, vc, _cfg(), tmp_path / "s.sqlite")

    assert parsed.metadata["parser_used"] == "vlm"
    assert "VLMLATEX" in parsed.text
    # parser_text retained for every page; page text is the VLM transcription.
    for page in parsed.metadata["pdf_pages"]:
        assert page["parser_text"].startswith("parser text")
        assert "VLMLATEX" in page["text"]


def test_per_page_failure_falls_back_to_parser_text(tmp_path) -> None:
    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, 2)
    parsed = _parsed(pdf, 2)
    vc = _FakeVision(fail=True)  # every page raises
    ingest_raw._apply_vlm_pdf_extraction(parsed, pdf, vc, _cfg(), tmp_path / "s.sqlite")

    assert parsed.metadata["parser_used"] == "vlm"
    # Fallback: pages keep pymupdf4llm text; ingest does not abort.
    for page in parsed.metadata["pdf_pages"]:
        assert page["text"].startswith("parser text")


def test_max_pages_rail_skips_excess_pages(tmp_path) -> None:
    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, 3)
    parsed = _parsed(pdf, 3)
    vc = _FakeVision()
    ingest_raw._apply_vlm_pdf_extraction(
        parsed, pdf, vc, _cfg(vision_max_pages_per_run=1), tmp_path / "s.sqlite"
    )
    pages = parsed.metadata["pdf_pages"]
    assert "VLMLATEX" in pages[0]["text"]          # first page transcribed
    assert pages[1]["text"].startswith("parser text")  # skipped → parser text
    assert pages[2]["text"].startswith("parser text")


def test_cache_is_model_keyed(tmp_path) -> None:
    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, 2)
    dbp = tmp_path / "s.sqlite"

    vc1 = _FakeVision(model="ollama::model-A")
    ingest_raw._apply_vlm_pdf_extraction(_parsed(pdf, 2), pdf, vc1, _cfg(), dbp)
    assert vc1.calls == 2  # both pages transcribed (cold cache)

    # Same model again → cache hit, no new vision calls.
    vc1b = _FakeVision(model="ollama::model-A")
    ingest_raw._apply_vlm_pdf_extraction(_parsed(pdf, 2), pdf, vc1b, _cfg(), dbp)
    assert vc1b.calls == 0

    # Different model → cache miss (R12: model switch invalidates), re-transcribes.
    vc2 = _FakeVision(model="ollama::model-B")
    ingest_raw._apply_vlm_pdf_extraction(_parsed(pdf, 2), pdf, vc2, _cfg(), dbp)
    assert vc2.calls == 2


def test_cache_get_put_roundtrip(tmp_path) -> None:
    dbp = tmp_path / "s.sqlite"
    assert db.vision_cache_get(dbp, "hash1", "m") is None
    db.vision_cache_put(dbp, "hash1", "m", "$$x$$")
    assert db.vision_cache_get(dbp, "hash1", "m") == "$$x$$"
    # Different model is a separate key.
    assert db.vision_cache_get(dbp, "hash1", "other") is None
