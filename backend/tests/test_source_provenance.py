import tempfile
import unittest
from pathlib import Path

from curator import config as cfg
from curator import db, ingest_raw


class SourceProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        for raw_dir in self.paths.raw_dirs:
            raw_dir.mkdir(parents=True, exist_ok=True)
        db.init_db(self.paths.state_db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_import_mirrors_03_notes_to_04_resources(self) -> None:
        note = self.root / "03_Notes" / "Papers" / "note.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text("# Note\n\nA useful source with enough words to ingest safely.", encoding="utf-8")

        outcome = ingest_raw.import_source_file(self.paths, note)

        self.assertEqual(outcome.result, ingest_raw.AddResult.ADDED)
        self.assertTrue(outcome.relpath.startswith("04_Resources/Papers/"))
        self.assertTrue((self.root / outcome.relpath).exists())
        self.assertNotEqual(note, self.root / outcome.relpath)

        row = ingest_raw.get_source(self.paths, outcome.source_id or -1)
        self.assertIsNotNone(row)
        self.assertEqual(row["import_origin"], str(note.resolve()))
        self.assertEqual(row["import_policy"], "mirror_03_to_04")

    def test_pdf_page_metadata_is_recorded_even_for_empty_pdf(self) -> None:
        try:
            from pypdf import PdfWriter
        except ImportError:
            self.skipTest("pypdf not installed")

        pdf_path = self.root / "04_Resources" / "blank.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.add_blank_page(width=72, height=72)
        with pdf_path.open("wb") as fh:
            writer.write(fh)

        outcome = ingest_raw.add_file(self.paths, pdf_path)

        print("OUTCOME ERROR:", outcome.message)
        self.assertEqual(outcome.result, ingest_raw.AddResult.SKIPPED_EMPTY)
        self.assertIsNotNone(outcome.source_id)
        pages = db.list_source_pdf_pages(self.paths.state_db, outcome.source_id or -1)
        self.assertEqual([p["page_number"] for p in pages], [1, 2])
        self.assertEqual([p["word_count"] for p in pages], [0, 0])


if __name__ == "__main__":
    unittest.main()
