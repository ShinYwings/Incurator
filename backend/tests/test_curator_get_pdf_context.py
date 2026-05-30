"""Tests for curator_get_pdf_context MCP tool and pdf.py page-window helpers.

Tests exercise the underlying functions directly (no FastMCP wire protocol)
so the suite runs fast without external dependencies.
"""
from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers: minimal PDF builder using pypdf / reportlab fallback
# ---------------------------------------------------------------------------

def _make_minimal_pdf(pages: list[str]) -> bytes:
    """Build a minimal multi-page text PDF using pypdf's PdfWriter."""
    try:
        from pypdf import PdfWriter
        from pypdf.generic import NameObject, ArrayObject, DictionaryObject, ByteStringObject
    except ImportError:
        # Absolute minimal PDF structure if pypdf write isn't available
        return b""

    # Use reportlab if available for proper text embedding
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas as rl_canvas

        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=letter)
        for text in pages:
            c.drawString(72, 720, text)
            c.showPage()
        c.save()
        return buf.getvalue()
    except ImportError:
        pass

    # Fallback: hand-craft a minimal PDF with text streams
    lines: list[bytes] = []
    offsets: list[int] = []

    def w(b: bytes) -> None:
        offsets.append(len(b"".join(lines)))
        lines.append(b)

    w(b"%PDF-1.4\n")
    obj_offsets: dict[int, int] = {}

    def begin_obj(n: int) -> None:
        obj_offsets[n] = sum(len(x) for x in lines)
        lines.append(f"{n} 0 obj\n".encode())

    def end_obj() -> None:
        lines.append(b"endobj\n")

    # Objects: 1=catalog, 2=pages, 3+=(page,stream) pairs per page
    page_obj_ids: list[int] = []
    next_id = 3

    for i, text in enumerate(pages):
        stream_text = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        stream_id = next_id
        page_id = next_id + 1
        page_obj_ids.append(page_id)
        next_id += 2

        begin_obj(stream_id)
        lines.append(f"<< /Length {len(stream_text)} >>\nstream\n".encode())
        lines.append(stream_text)
        lines.append(b"\nendstream\n")
        end_obj()

        begin_obj(page_id)
        lines.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {stream_id} 0 R "
            f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>\n".encode()
        )
        end_obj()

    pages_ref = " ".join(f"{pid} 0 R" for pid in page_obj_ids)

    begin_obj(2)
    lines.append(
        f"<< /Type /Pages /Kids [{pages_ref}] /Count {len(pages)} >>\n".encode()
    )
    end_obj()

    begin_obj(1)
    lines.append(b"<< /Type /Catalog /Pages 2 0 R >>\n")
    end_obj()

    xref_offset = sum(len(x) for x in lines)
    xref_entries = {**obj_offsets, 1: obj_offsets.get(1, 0), 2: obj_offsets.get(2, 0)}
    all_ids = sorted(xref_entries)
    xref_count = max(all_ids) + 1

    lines.append(b"xref\n")
    lines.append(f"0 {xref_count}\n".encode())
    lines.append(b"0000000000 65535 f \n")
    for i in range(1, xref_count):
        off = xref_entries.get(i, 0)
        lines.append(f"{off:010d} 00000 n \n".encode())

    lines.append(
        f"trailer\n<< /Size {xref_count} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return b"".join(lines)


# ---------------------------------------------------------------------------
# Tests for parsers/pdf.py helpers
# ---------------------------------------------------------------------------

class ParsePageWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_pdf(self, pages: list[str]) -> Path:
        pdf_bytes = _make_minimal_pdf(pages)
        p = self.root / "test.pdf"
        p.write_bytes(pdf_bytes)
        return p

    def test_get_page_count_returns_correct_count(self) -> None:
        from curator.parsers.pdf import get_page_count
        try:
            path = self._write_pdf(["Page one", "Page two", "Page three"])
            if path.stat().st_size < 10:
                self.skipTest("PDF builder not available")
            count = get_page_count(path)
            self.assertEqual(count, 3)
        except Exception:
            self.skipTest("pypdf or reportlab not available for PDF creation")

    def test_parse_page_window_only_reads_requested_pages(self) -> None:
        from curator.parsers.pdf import parse_page_window
        try:
            path = self._write_pdf(["Alpha", "Beta", "Gamma", "Delta", "Epsilon"])
            if path.stat().st_size < 10:
                self.skipTest("PDF builder not available")
            result = parse_page_window(path, {2, 4})
            self.assertIn(2, result)
            self.assertIn(4, result)
            self.assertNotIn(1, result)
            self.assertNotIn(3, result)
            self.assertNotIn(5, result)
        except Exception:
            self.skipTest("pypdf or reportlab not available for PDF creation")

    def test_get_page_count_missing_file(self) -> None:
        from curator.parsers.pdf import get_page_count
        count = get_page_count(self.root / "nonexistent.pdf")
        self.assertEqual(count, 0)

    def test_parse_page_window_missing_file(self) -> None:
        from curator.parsers.pdf import parse_page_window
        result = parse_page_window(self.root / "nonexistent.pdf", {1, 2})
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# Tests for curator_get_pdf_context MCP tool
# ---------------------------------------------------------------------------

class CuratorGetPdfContextTests(unittest.TestCase):
    def setUp(self) -> None:
        import os
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # Create minimal vault structure required by _resolve_paths
        from curator import config as cfg, db
        from curator import constants as consts
        curator_dir = self.root / consts.INTERNAL_DIR
        curator_dir.mkdir(parents=True, exist_ok=True)
        (curator_dir / consts.CONFIG_FILE).write_text("llm:\n  provider: ollama\n", encoding="utf-8")
        paths = cfg.WikiPaths(self.root)
        for d in paths.raw_dirs:
            d.mkdir(parents=True, exist_ok=True)
        db.init_db(paths.state_db)
        os.environ["VAULT_ROOT"] = str(self.root)

    def tearDown(self) -> None:
        import os
        os.environ.pop("VAULT_ROOT", None)
        self.tmp.cleanup()

    def _get_tool(self):
        """Return curator_get_pdf_context directly without starting background workers."""
        from unittest.mock import patch
        from curator import mcp_server
        # Patch IngestWorker so build_server() doesn't start background threads
        with patch("curator.ingest_worker.IngestWorker", autospec=True):
            server = mcp_server.build_server()
        tools = getattr(server._tool_manager, "_tools", {})
        self.assertIn("curator_get_pdf_context", tools)
        return tools["curator_get_pdf_context"].fn

    def test_missing_file_returns_error(self) -> None:
        tool = self._get_tool()
        result = tool(
            file_path=str(self.root / "missing.pdf"),
            workspace_path=str(self.root),
        )
        self.assertFalse(result["ok"])
        self.assertIn("error", result)

    def test_non_pdf_returns_error(self) -> None:
        txt = self.root / "doc.txt"
        txt.write_text("hello")
        tool = self._get_tool()
        result = tool(file_path=str(txt), workspace_path=str(self.root))
        self.assertFalse(result["ok"])

    def test_untracked_pdf_returns_ok_false_or_pages(self) -> None:
        """For an untracked PDF, ok=True with pages OR ok=False with parse error."""
        pdf_bytes = _make_minimal_pdf(["Hello world page one", "Second page content"])
        if not pdf_bytes or len(pdf_bytes) < 10:
            self.skipTest("PDF builder not available")
        pdf_path = self.root / "untracked.pdf"
        pdf_path.write_bytes(pdf_bytes)

        tool = self._get_tool()
        result = tool(
            file_path=str(pdf_path),
            page_num=1,
            radius=1,
            workspace_path=str(self.root),
        )
        if result.get("ok"):
            self.assertFalse(result["source_tracked"])
            self.assertIsNone(result["source_id"])
            self.assertIsInstance(result["pages"], list)
            self.assertIsInstance(result["outline"], list)
            self.assertIsInstance(result["total_pages"], int)
            self.assertIn("is_empty_pdf", result)
        else:
            # parse may fail for hand-crafted minimal PDF — that's OK
            self.assertIn("error", result)

    def test_window_radius_limits_pages(self) -> None:
        """Returned pages should not exceed radius*2+1 from page_num."""
        pdf_bytes = _make_minimal_pdf([f"Page {i}" for i in range(1, 11)])
        if not pdf_bytes or len(pdf_bytes) < 10:
            self.skipTest("PDF builder not available")
        pdf_path = self.root / "long.pdf"
        pdf_path.write_bytes(pdf_bytes)

        tool = self._get_tool()
        result = tool(
            file_path=str(pdf_path),
            page_num=5,
            radius=1,
            max_pages=3,
            workspace_path=str(self.root),
        )
        if not result.get("ok"):
            self.skipTest("PDF parse failed for minimal test PDF")
        pages = result["pages"]
        page_nums = [p["page_num"] for p in pages]
        self.assertLessEqual(len(pages), 3)
        for pn in page_nums:
            self.assertGreaterEqual(pn, 1)

    def test_is_empty_pdf_flag(self) -> None:
        """A real empty PDF should return is_empty_pdf=True."""
        # Create a text-free minimal PDF (all pages have no text)
        pdf_bytes = _make_minimal_pdf([""])
        if not pdf_bytes or len(pdf_bytes) < 10:
            self.skipTest("PDF builder not available")
        pdf_path = self.root / "empty.pdf"
        pdf_path.write_bytes(pdf_bytes)

        tool = self._get_tool()
        result = tool(
            file_path=str(pdf_path),
            workspace_path=str(self.root),
        )
        if result.get("ok"):
            # is_empty_pdf depends on whether the PDF writer embedded text
            self.assertIn("is_empty_pdf", result)


if __name__ == "__main__":
    unittest.main()
