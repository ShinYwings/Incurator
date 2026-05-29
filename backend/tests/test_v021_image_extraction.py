"""v0.2.1 tests for L1 PDF image extraction and 05_Assets persistence."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from curator import config as cfg
from curator import db
from curator.ingest_raw import _save_pdf_images


def _make_paths(root: Path) -> cfg.WikiPaths:
    paths = cfg.WikiPaths(root)
    db.init_db(paths.state_db)
    return paths


def _fake_parsed(file_type: str = "pdf", images: list | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        file_type=file_type,
        title="Test Doc",
        text="body text",
        metadata={
            "pdf_images": images if images is not None else [],
            "pdf_pages": [],
        },
    )


class TestSavePdfImages(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = _make_paths(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_no_images_returns_empty(self) -> None:
        parsed = _fake_parsed(file_type="pdf", images=[])
        result = _save_pdf_images(parsed, "04_Resources/paper.pdf", self.paths)
        self.assertEqual(result, [])

    def test_non_pdf_returns_empty(self) -> None:
        parsed = _fake_parsed(file_type="md", images=[{"page": 1, "data": b"x" * 2000, "ext": "png"}])
        result = _save_pdf_images(parsed, "03_Notes/note.md", self.paths)
        self.assertEqual(result, [])

    def test_images_are_saved_to_assets(self) -> None:
        img_data = b"\x89PNG\r\n" + b"x" * 2000
        parsed = _fake_parsed(images=[
            {"page": 3, "data": img_data, "ext": "png"},
            {"page": 7, "data": img_data, "ext": "jpeg"},
        ])
        result = _save_pdf_images(parsed, "04_Resources/mypaper.pdf", self.paths)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["page"], 3)
        self.assertIn("05_Assets/mypaper/p03_img01.png", result[0]["obsidian_path"])
        self.assertEqual(result[1]["page"], 7)
        self.assertIn("05_Assets/mypaper/p07_img01.jpeg", result[1]["obsidian_path"])

        # Files actually exist on disk
        for img in result:
            self.assertTrue((self.root / img["obsidian_path"]).exists())

    def test_multiple_images_same_page_get_sequential_index(self) -> None:
        img_data = b"x" * 2000
        parsed = _fake_parsed(images=[
            {"page": 5, "data": img_data, "ext": "png"},
            {"page": 5, "data": img_data, "ext": "png"},
        ])
        result = _save_pdf_images(parsed, "04_Resources/doc.pdf", self.paths)
        paths_saved = [r["obsidian_path"] for r in result]
        self.assertIn("05_Assets/doc/p05_img01.png", paths_saved)
        self.assertIn("05_Assets/doc/p05_img02.png", paths_saved)

    def test_slug_sanitizes_special_chars(self) -> None:
        img_data = b"x" * 2000
        parsed = _fake_parsed(images=[{"page": 1, "data": img_data, "ext": "png"}])
        result = _save_pdf_images(parsed, "04_Resources/my paper (2024).pdf", self.paths)
        self.assertEqual(len(result), 1)
        # obsidian_path should not contain spaces or parens
        self.assertNotIn(" ", result[0]["obsidian_path"])
        self.assertNotIn("(", result[0]["obsidian_path"])


class TestStructuralContextWithImages(unittest.TestCase):
    """Verify generate_l1_structural_context embeds images in CTX frontmatter."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = _make_paths(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_embedded_images_in_frontmatter_and_body(self) -> None:
        from curator.ingest_raw import _build_structural_context_page
        from types import SimpleNamespace

        parsed = _fake_parsed(images=[])
        saved = [{"obsidian_path": "05_Assets/paper/p03_img01.png", "page": 3}]

        # Minimal parsed object that _build_structural_context_page can handle
        parsed_full = SimpleNamespace(
            file_type="pdf",
            title="Test Paper",
            text="section content",
            metadata={"pdf_pages": [], "pdf_toc": []},
        )

        with patch("curator.ingest_raw._extract_structural_sections", return_value=[]):
            with patch("curator.ingest_raw._structural_atom_candidates", return_value=[]):
                content = _build_structural_context_page(
                    context_id="CTX-test0001",
                    parsed=parsed_full,
                    relpath="04_Resources/paper.pdf",
                    content_hash="abc123",
                    today="2026-05-29",
                    saved_images=saved,
                )

        self.assertIn("embedded_images", content)
        self.assertIn("05_Assets/paper/p03_img01.png", content)
        self.assertIn("## Embedded Figures", content)
        self.assertIn("![[05_Assets/paper/p03_img01.png]]", content)


if __name__ == "__main__":
    unittest.main()
