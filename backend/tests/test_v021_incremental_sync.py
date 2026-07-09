"""v0.2.1 spec tests: Hash-based incremental sync (spec 08 section 9, spec 05).

Tests cover:
- _find_changed_nodes(): detect nodes whose file hash changed since last DB stamp
- run_incremental_sync(): no-op fast path when nothing changed

These are TDD spec tests. Functions are imported with graceful skip if not yet implemented.
"""
import tempfile
import unittest
from pathlib import Path

from curator import config as cfg
from curator import db

# ---------------------------------------------------------------------------
# Graceful imports
# ---------------------------------------------------------------------------
try:
    from curator.sync import _find_changed_nodes, scan_for_changes, update_all_page_hashes
    SYNC_HELPERS_AVAILABLE = True
except ImportError:
    SYNC_HELPERS_AVAILABLE = False

try:
    from curator.sync import run_incremental_sync
    INCREMENTAL_SYNC_AVAILABLE = True
except ImportError:
    INCREMENTAL_SYNC_AVAILABLE = False

try:
    pass
    EXH_CACHE_AVAILABLE = True
except ImportError:
    EXH_CACHE_AVAILABLE = False


# ---------------------------------------------------------------------------
# _find_changed_nodes
# ---------------------------------------------------------------------------

@unittest.skipUnless(SYNC_HELPERS_AVAILABLE, "sync._find_changed_nodes not yet implemented")
class TestFindChangedNodes(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        db.init_db(self.paths.state_db)
        self.paths.atoms.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_atom(self, atom_id: str, body: str) -> Path:
        fm = (
            f"---\nid: {atom_id}\ntype: atom\n"
            f"last_updated: 2026-05-29\n---\n\n# {atom_id}\n\n{body}\n"
        )
        path = self.paths.atoms / f"{atom_id}.md"
        path.write_text(fm, encoding="utf-8")
        return path

    def test_unchanged_node_not_in_changed_list(self) -> None:
        # G04-1 fix: changed detection uses DB page hashes, not frontmatter content_hash.
        # Must stamp the DB hash first; a file with no DB hash is always "changed".
        self._write_atom("ATM-abc00001", "Unchanged body.")
        update_all_page_hashes(self.paths)  # stamp current file hashes into DB
        changed = _find_changed_nodes(self.paths)
        self.assertNotIn("ATM-abc00001", changed)

    def test_modified_body_detected_as_changed(self) -> None:
        path = self._write_atom("ATM-abc00002", "Original body.")
        update_all_page_hashes(self.paths)  # stamp original hash into DB
        # Now overwrite the body — DB hash is now stale
        path.write_text(
            "---\nid: ATM-abc00002\ntype: atom\nlast_updated: 2026-05-29\n---\n\n"
            "# ATM-abc00002\n\nModified body.\n",
            encoding="utf-8",
        )
        changed = _find_changed_nodes(self.paths)
        self.assertIn("ATM-abc00002", changed)

    def test_node_with_no_db_hash_is_treated_as_changed(self) -> None:
        # A new file with no DB hash entry is always reported as changed.
        path = self.paths.atoms / "ATM-legacy01.md"
        path.write_text(
            "---\nid: ATM-legacy01\ntype: atom\nlast_updated: 2026-01-01\n---\n\nLegacy body.\n",
            encoding="utf-8",
        )
        changed = _find_changed_nodes(self.paths)
        self.assertIn("ATM-legacy01", changed)

    def test_deleted_page_hashes_are_pruned_after_update(self) -> None:
        path = self._write_atom("ATM-delete01", "Temporary body.")
        update_all_page_hashes(self.paths)
        path.unlink()
        self.assertIn("02_Atoms/ATM-delete01.md", scan_for_changes(self.paths).deleted)
        update_all_page_hashes(self.paths)
        self.assertNotIn("02_Atoms/ATM-delete01.md", scan_for_changes(self.paths).deleted)

    def test_empty_collections_returns_empty_list(self) -> None:
        changed = _find_changed_nodes(self.paths)
        self.assertEqual(changed, [])


# ---------------------------------------------------------------------------
# run_incremental_sync — no-op fast path
# ---------------------------------------------------------------------------

@unittest.skipUnless(INCREMENTAL_SYNC_AVAILABLE, "sync.run_incremental_sync not yet implemented")
class TestRunIncrementalSyncFastPath(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        db.init_db(self.paths.state_db)
        for layer in (self.paths.contexts, self.paths.atoms,
                      self.paths.concepts, self.paths.synthesis):
            layer.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_empty_vault_completes_without_error(self) -> None:
        result = run_incremental_sync(self.paths, client=None, config={})
        self.assertIsNotNone(result)

    def test_all_hashes_match_no_llm_call_needed(self) -> None:
        atom_path = self.paths.atoms / "ATM-match01.md"
        atom_path.write_text(
            "---\nid: ATM-match01\ntype: atom\nlast_updated: 2026-05-29\n---\n\n"
            "# ATM-match01\n\nContent that matches hash.\n",
            encoding="utf-8",
        )
        # Should complete without raising — client=None means no LLM available
        result = run_incremental_sync(self.paths, client=None, config={})
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
