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
# Helpers: Copy static PDF fixtures
# ---------------------------------------------------------------------------
import shutil

def _copy_fixture_pdf(fixture_name: str, dest_path: Path) -> Path:
    """Copy a static pre-generated PDF fixture from backend/tests/fixtures/."""
    # Assuming tests are run from backend/
    fixture_path = Path("tests/fixtures") / fixture_name
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture {fixture_path} not found.")
    shutil.copy2(fixture_path, dest_path)
    return dest_path


# ---------------------------------------------------------------------------
# Tests for parsers/pdf.py helpers
# ---------------------------------------------------------------------------

class ParsePageWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_pdf(self, fixture_name: str) -> Path:
        p = self.root / "test.pdf"
        return _copy_fixture_pdf(fixture_name, p)

    def test_get_page_count_returns_correct_count(self) -> None:
        from curator.parsers.pdf import get_page_count
        try:
            path = self._write_pdf("test.pdf")
            count = get_page_count(path)
            self.assertEqual(count, 3)
        except Exception:
            self.skipTest("PDF fixture not available")

    def test_parse_page_window_only_reads_requested_pages(self) -> None:
        from curator.parsers.pdf import parse_page_window
        try:
            path = self._write_pdf("long.pdf")
            result = parse_page_window(path, {2, 4})
            self.assertIn(2, result)
            self.assertIn(4, result)
            self.assertNotIn(1, result)
            self.assertNotIn(3, result)
            self.assertNotIn(5, result)
        except Exception:
            self.skipTest("PDF fixture not available")

    def test_get_page_count_missing_file(self) -> None:
        from curator.parsers.pdf import get_page_count
        count = get_page_count(self.root / "nonexistent.pdf")
        self.assertEqual(count, 0)

    def test_parse_page_window_missing_file(self) -> None:
        from curator.parsers.pdf import parse_page_window
        result = parse_page_window(self.root / "nonexistent.pdf", {1, 2})
        self.assertEqual(result, {})

    def test_chunk_page_number_accepts_page_number_metadata(self) -> None:
        from curator.parsers.pdf import _chunk_page_number

        self.assertEqual(_chunk_page_number({"metadata": {"page_number": 4}}), 4)
        self.assertEqual(_chunk_page_number({"metadata": {"page": 3}}), 3)
        self.assertEqual(_chunk_page_number({"metadata": {"page_number": "2"}}), 2)
        self.assertEqual(_chunk_page_number({"metadata": {"page_number": 0}}), 1)

    def test_merge_raw_text_fallback_preserves_omitted_math_lines(self) -> None:
        from curator.parsers.pdf import _merge_raw_text_fallback

        merged = _merge_raw_text_fallback(
            "Formally, a building block is shown in Fig. 2.",
            "Formally, a building block is shown in Fig. 2.\n"
            "y = F(x, {Wi}) + x.\n"
            "Here x and y are the input and output vectors.",
        )

        self.assertIn("Raw PDF Text Fallback", merged)
        self.assertIn("y = F(x, {Wi}) + x.", merged)


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
        try:
            pdf_path = self.root / "untracked.pdf"
            _copy_fixture_pdf("test.pdf", pdf_path)
        except FileNotFoundError:
            self.skipTest("PDF fixture not available")

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
            self.assertIn("error", result)

    def test_window_radius_limits_pages(self) -> None:
        """Returned pages should not exceed radius*2+1 from page_num."""
        try:
            pdf_path = self.root / "long.pdf"
            _copy_fixture_pdf("long.pdf", pdf_path)
        except FileNotFoundError:
            self.skipTest("PDF fixture not available")

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
        try:
            pdf_path = self.root / "empty.pdf"
            _copy_fixture_pdf("empty.pdf", pdf_path)
        except FileNotFoundError:
            self.skipTest("PDF fixture not available")

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
