"""Plan G P2 — tests for the single source/asset identity resolution authority.

`asset_identity` is a facade over existing helpers (Reference Mode stub expansion,
Zotero resolution, logical-id derivation, sources-row lookup). It performs NO DB
mutation and does NOT change dedup semantics.
"""
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock
from unittest.mock import patch

from curator import config as cfg
from curator import db, ingest_raw, asset_identity


class FromSourceRowTests(unittest.TestCase):
    def test_none_row_is_untracked(self) -> None:
        ident = asset_identity.from_source_row(None)
        self.assertEqual(ident.resolution_status, "untracked")
        self.assertIsNone(ident.source_id)
        self.assertFalse(ident.is_reference)

    def test_vault_source_has_no_external_abs_path(self) -> None:
        ident = asset_identity.from_source_row(
            {
                "id": 7,
                "relpath": "04_Resources/Imports/a.md",
                "is_reference": 0,
                "external_ref": None,
                "content_hash": "h",
            }
        )
        self.assertEqual(ident.resolution_status, "resolved")
        self.assertEqual(ident.source_id, 7)
        self.assertFalse(ident.is_reference)
        self.assertIsNone(ident.abs_path)
        self.assertEqual(ident.relpath, "04_Resources/Imports/a.md")

    def test_reference_source_keeps_only_portable_identity_without_paths(self) -> None:
        ident = asset_identity.from_source_row(
            {
                "id": 9,
                "relpath": "04_Resources/References/paper.md",
                "is_reference": 1,
                "external_ref": None,
                "logical_source_id": "zotero:ABCD1234",
                "content_hash": "h",
            }
        )
        self.assertEqual(ident.resolution_status, "path_unresolved")
        self.assertTrue(ident.is_reference)
        self.assertIsNone(ident.abs_path)
        self.assertEqual(ident.relpath, "04_Resources/References/paper.md")
        self.assertEqual(ident.zotero_key, "ABCD1234")

    def test_reference_without_runtime_resolver_is_path_unresolved(self) -> None:
        row = {
            "id": 11,
            "relpath": "04_Resources/References/gone.md",
            "is_reference": 1,
            "external_ref": "@library/missing/file.pdf",
            "content_hash": "h",
        }
        cheap = asset_identity.from_source_row(row)
        self.assertEqual(cheap.resolution_status, "path_unresolved")
        self.assertIsNone(cheap.abs_path)

        verified = asset_identity.from_source_row(row, verify_exists=True)
        self.assertEqual(verified.resolution_status, "path_unresolved")
        self.assertIsNone(verified.abs_path)


class ResolveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        for raw_dir in self.paths.raw_dirs:
            raw_dir.mkdir(parents=True, exist_ok=True)
        db.init_db(self.paths.state_db)
        self.config = deepcopy(cfg.DEFAULT_CONFIG)
        self.config["external"]["path_roots"] = {
            "test_library": str(self.root.parent)
        }
        self.config_patcher = patch(
            "curator.config.load_config",
            return_value=self.config,
        )
        self.config_patcher.start()
        
        self.zotero_patcher = patch(
            "curator.zotero_tools.resolve_pdf",
            return_value={"ok": False, "path": None}
        )
        self.zotero_patcher.start()

    def tearDown(self) -> None:
        self.zotero_patcher.stop()
        self.config_patcher.stop()
        self.tmp.cleanup()

    def test_unknown_input_is_untracked(self) -> None:
        ident = asset_identity.resolve(self.paths, abs_path="/nope/missing.pdf")
        self.assertEqual(ident.resolution_status, "untracked")
        self.assertIsNone(ident.source_id)

    def test_zotero_key_derives_logical_id_even_without_path(self) -> None:
        # No Zotero DB configured -> path unresolved, but the logical id is still
        # derived deterministically as zotero:<key>.
        ident = asset_identity.resolve(self.paths, zotero_key="ZKEY99")
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

        ident = asset_identity.resolve(self.paths, abs_path=str(external.resolve()))
        self.assertEqual(ident.resolution_status, "resolved")
        self.assertEqual(ident.source_id, outcome.source_id)
        self.assertTrue(ident.is_reference)
        self.assertEqual(ident.abs_path, str(external.resolve()))
        self.assertEqual(ident.relpath, "04_Resources/References/paper.md")

    def test_resolve_downgrades_tracked_reference_with_deleted_file(self) -> None:
        external_root = self.root.parent / f"{self.root.name}_lib2"
        external_root.mkdir(parents=True, exist_ok=True)
        external = external_root / "paper.md"
        external.write_text(
            "# Ref\n\nExternal reference body with enough words to ingest.",
            encoding="utf-8",
        )
        ingest_raw.import_source_file(self.paths, external, policy="reference")
        abs_path = str(external.resolve())

        # User moves/deletes the external file after it was tracked.
        external.unlink()

        ident = asset_identity.resolve(self.paths, abs_path=abs_path)
        self.assertEqual(ident.resolution_status, "path_unresolved")
        self.assertIsNone(ident.abs_path)
        self.assertTrue(ident.is_reference)

    def test_fresh_resolved_path_overrides_stale_existing_external_path(self) -> None:
        old = self.root.parent / f"{self.root.name}_old" / "paper.pdf"
        new = self.root.parent / f"{self.root.name}_new" / "paper.pdf"
        old.parent.mkdir(parents=True, exist_ok=True)
        new.parent.mkdir(parents=True, exist_ok=True)
        old.write_text("old stale backup", encoding="utf-8")
        new.write_text("new current file", encoding="utf-8")
        now = "2026-06-19T00:00:00Z"
        with db.connect(self.paths.state_db) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, "
                "added_at, logical_source_id, is_reference) "
                "VALUES (?, ?, ?, 0, ?, ?, 1)",
                (
                    "04_Resources/References/paper.md",
                    "h1",
                    "pdf",
                    now,
                    "zotero:MOVE1",
                ),
            )

        with mock.patch("curator.zotero_tools.resolve_pdf", return_value={"ok": True, "path": str(new)}):
            ident = asset_identity.resolve(
                self.paths,
                logical_source_id="zotero:MOVE1",
                abs_path=str(new),
        )
        self.assertEqual(ident.resolution_status, "resolved")
        self.assertEqual(ident.abs_path, str(new))
        self.assertEqual(ident.logical_source_id, "zotero:MOVE1")

    def test_untracked_zotero_logical_id_implies_reference_and_key(self) -> None:
        # logical_source_id="zotero:123" with NO explicit zotero_key must not
        # produce a structurally inconsistent identity (zotero logical but
        # is_reference False / zotero_key None).
        ident = asset_identity.resolve(
            self.paths, logical_source_id="zotero:KEY42"
        )
        self.assertEqual(ident.resolution_status, "untracked")
        self.assertTrue(ident.is_reference)
        self.assertEqual(ident.zotero_key, "KEY42")
        self.assertEqual(ident.logical_source_id, "zotero:KEY42")

    def test_vault_row_does_not_inherit_caller_zotero_identity(self) -> None:
        # State-leakage guard: matching a vault (non-reference) markdown row while
        # the caller also passes a zotero_key must NOT attach Zotero properties to
        # the vault source's identity.
        notes_dir = self.paths.root / "03_Notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        note = notes_dir / "note.md"
        note.write_text(
            "# Note\n\nA plain vault markdown note with enough words to ingest.",
            encoding="utf-8",
        )
        outcome = ingest_raw.import_source_file(
            self.paths, note, policy="into_04_resources"
        )
        row = ingest_raw.get_source(self.paths, outcome.source_id or -1)
        assert row is not None

        ident = asset_identity.resolve(
            self.paths, relpath=row["relpath"], zotero_key="LEAK99"
        )
        self.assertFalse(ident.is_reference)
        self.assertIsNone(ident.zotero_key)
        self.assertIsNone(ident.abs_path)
        self.assertNotEqual(ident.logical_source_id, "zotero:LEAK99")

    def test_logical_source_id_lookup_is_isolated_from_relpath_collision(self) -> None:
        # Two rows where one row's relpath equals the other row's
        # logical_source_id. Resolving by logical id must return the row whose
        # logical_source_id matches, never the relpath-colliding row. (resolve()
        # does an isolated logical-column query, not a relpath OR clause.)
        collide = "ref-COLLIDE"
        now = "2026-06-19T00:00:00Z"
        with db.connect(self.paths.state_db) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, "
                "added_at, logical_source_id, is_reference) "
                "VALUES (?, ?, ?, 0, ?, ?, 1)",
                ("04_Resources/References/real.md", "h1", "pdf", now, collide),
            )
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, "
                "added_at, logical_source_id, is_reference) "
                "VALUES (?, ?, ?, 0, ?, ?, 0)",
                (collide, "h2", "md", now, "ref-other"),
            )
        ident = asset_identity.resolve(self.paths, logical_source_id=collide)
        self.assertEqual(ident.logical_source_id, collide)
        # The logical-matching row is the reference one at References/real.md, not
        # the relpath-colliding markdown row.
        self.assertTrue(ident.is_reference)
        self.assertEqual(ident.relpath, "04_Resources/References/real.md")


if __name__ == "__main__":
    unittest.main()
