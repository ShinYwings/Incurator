"""Tests for db.get_source_row and db.source_path_to_relpath."""

import tempfile
import unittest
from pathlib import Path

from curator import config as cfg
from curator import db


class SourcePathToRelpathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(db.source_path_to_relpath(self.root, ""), "")

    def test_relative_passes_through(self) -> None:
        self.assertEqual(
            db.source_path_to_relpath(self.root, "04_Resources/paper.pdf"),
            "04_Resources/paper.pdf",
        )

    def test_absolute_inside_vault(self) -> None:
        abs_path = str(self.root / "04_Resources" / "paper.pdf")
        self.assertEqual(
            db.source_path_to_relpath(self.root, abs_path),
            "04_Resources/paper.pdf",
        )

    def test_absolute_outside_vault(self) -> None:
        result = db.source_path_to_relpath(self.root, "/some/other/path.pdf")
        self.assertEqual(result, "/some/other/path.pdf")


class GetSourceRowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        db.init_db(self.paths.state_db)
        # Seed a source row
        with db.connect(self.paths.state_db) as conn:
            conn.execute(
                """
                INSERT INTO sources (relpath, content_hash, file_type, bytes,
                    added_at, status, external_path, logical_source_id, import_origin)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "04_Resources/paper.pdf",
                    "abc123",
                    "pdf",
                    1024,
                    "2025-01-01T00:00:00Z",
                    "pending",
                    "/ext/Zotero/paper.pdf",
                    "lsid-001",
                    "/original/paper.pdf",
                ),
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_lookup_by_id(self) -> None:
        row = db.get_source_row(self.paths.state_db, self.root, source_id=1)
        self.assertIsNotNone(row)
        self.assertEqual(row["relpath"], "04_Resources/paper.pdf")

    def test_lookup_by_relpath(self) -> None:
        row = db.get_source_row(
            self.paths.state_db, self.root, relpath="04_Resources/paper.pdf"
        )
        self.assertIsNotNone(row)
        self.assertEqual(int(row["id"]), 1)

    def test_lookup_by_external_path(self) -> None:
        row = db.get_source_row(
            self.paths.state_db, self.root, relpath="/ext/Zotero/paper.pdf"
        )
        self.assertIsNotNone(row)
        self.assertEqual(int(row["id"]), 1)

    def test_lookup_by_external_path_resolves_symlink_alias(self) -> None:
        real_dir = self.root / "real_external"
        real_dir.mkdir()
        real_file = real_dir / "paper.pdf"
        real_file.write_text("pdf placeholder", encoding="utf-8")
        alias_dir = self.root / "alias_external"
        alias_dir.symlink_to(real_dir, target_is_directory=True)
        alias_file = alias_dir / "paper.pdf"
        with db.connect(self.paths.state_db) as conn:
            conn.execute(
                "UPDATE sources SET external_path = ? WHERE id = 1",
                (str(real_file.resolve()),),
            )

        row = db.get_source_row(
            self.paths.state_db, self.root, source_path=str(alias_file)
        )

        self.assertIsNotNone(row)
        self.assertEqual(int(row["id"]), 1)

    def test_lookup_by_logical_source_id(self) -> None:
        row = db.get_source_row(
            self.paths.state_db, self.root, relpath="lsid-001"
        )
        self.assertIsNotNone(row)

    def test_lookup_by_import_origin(self) -> None:
        row = db.get_source_row(
            self.paths.state_db, self.root, relpath="/original/paper.pdf"
        )
        self.assertIsNotNone(row)

    def test_lookup_by_source_path_absolute(self) -> None:
        abs_path = str(self.root / "04_Resources" / "paper.pdf")
        row = db.get_source_row(
            self.paths.state_db, self.root, source_path=abs_path
        )
        self.assertIsNotNone(row)
        self.assertEqual(int(row["id"]), 1)

    def test_lookup_not_found(self) -> None:
        row = db.get_source_row(
            self.paths.state_db, self.root, relpath="nonexistent.pdf"
        )
        self.assertIsNone(row)

    def test_lookup_empty_args(self) -> None:
        row = db.get_source_row(self.paths.state_db, self.root)
        self.assertIsNone(row)


if __name__ == "__main__":
    unittest.main()
