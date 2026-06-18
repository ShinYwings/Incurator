"""Plan G P2 — tests for the single PDF-identity resolution authority.

`pdf_identity` is a facade over existing helpers (Reference Mode stub expansion,
Zotero resolution, logical-id derivation, sources-row lookup). It performs NO DB
mutation and does NOT change dedup semantics.
"""
import tempfile
import unittest
from pathlib import Path

from curator import config as cfg
from curator import db, ingest_raw, pdf_identity


class FromSourceRowTests(unittest.TestCase):
    def test_none_row_is_untracked(self) -> None:
        ident = pdf_identity.from_source_row(None)
        self.assertEqual(ident.resolution_status, "untracked")
        self.assertIsNone(ident.source_id)
        self.assertFalse(ident.is_reference)

    def test_vault_source_has_no_external_abs_path(self) -> None:
        ident = pdf_identity.from_source_row(
            {
                "id": 7,
                "relpath": "04_Resources/Imports/a.md",
                "is_reference": 0,
                "external_path": None,
                "content_hash": "h",
            }
        )
        self.assertEqual(ident.resolution_status, "resolved")
        self.assertEqual(ident.source_id, 7)
        self.assertFalse(ident.is_reference)
        self.assertIsNone(ident.abs_path)
        self.assertEqual(ident.relpath, "04_Resources/Imports/a.md")

    def test_reference_source_exposes_external_file_as_abs_path(self) -> None:
        ident = pdf_identity.from_source_row(
            {
                "id": 9,
                "relpath": "04_Resources/References/paper.md",
                "is_reference": 1,
                "external_path": "/ext/lib/paper.pdf",
                "logical_source_id": "zotero:ABCD1234",
                "content_hash": "h",
            }
        )
        self.assertEqual(ident.resolution_status, "resolved")
        self.assertTrue(ident.is_reference)
        self.assertEqual(ident.abs_path, "/ext/lib/paper.pdf")
        self.assertEqual(ident.relpath, "04_Resources/References/paper.md")
        self.assertEqual(ident.zotero_key, "ABCD1234")


class ResolveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        for raw_dir in self.paths.raw_dirs:
            raw_dir.mkdir(parents=True, exist_ok=True)
        db.init_db(self.paths.state_db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_unknown_input_is_untracked(self) -> None:
        ident = pdf_identity.resolve(self.paths, abs_path="/nope/missing.pdf")
        self.assertEqual(ident.resolution_status, "untracked")
        self.assertIsNone(ident.source_id)

    def test_zotero_key_derives_logical_id_even_without_path(self) -> None:
        # No Zotero DB configured -> path unresolved, but the logical id is still
        # derived deterministically as zotero:<key>.
        ident = pdf_identity.resolve(self.paths, zotero_key="ZKEY99")
        self.assertEqual(ident.logical_source_id, "zotero:ZKEY99")
        self.assertEqual(ident.zotero_key, "ZKEY99")
        self.assertIsNone(ident.abs_path)

    def test_resolves_existing_reference_row_by_external_path(self) -> None:
        external_root = self.root.parent / f"{self.root.name}_lib"
        external_root.mkdir(parents=True, exist_ok=True)
        external = external_root / "paper.md"
        external.write_text(
            "# Ref\n\nExternal reference body with enough words to ingest.",
            encoding="utf-8",
        )
        outcome = ingest_raw.import_source_file(self.paths, external, policy="reference")

        ident = pdf_identity.resolve(self.paths, abs_path=str(external.resolve()))
        self.assertEqual(ident.resolution_status, "resolved")
        self.assertEqual(ident.source_id, outcome.source_id)
        self.assertTrue(ident.is_reference)
        self.assertEqual(ident.abs_path, str(external.resolve()))
        self.assertEqual(ident.relpath, "04_Resources/References/paper.md")


if __name__ == "__main__":
    unittest.main()
