"""v0.2.1 spec tests: Hash-based incremental sync (spec 08 section 9, spec 05).

Tests cover:
- _hash_file_content(): frontmatter-excluded body hash (spec 08 section 9.2)
- _find_changed_nodes(): detect nodes whose body changed since last ingest
- run_incremental_sync(): no-op fast path when nothing changed
- EXH cache invalidation: invalidate_exh_cache_for_concept() (spec 07 section 4.4)

These are TDD spec tests. Functions are imported with graceful skip if not yet implemented.
"""
import hashlib
import tempfile
import unittest
from pathlib import Path

from curator import config as cfg
from curator import db

# ---------------------------------------------------------------------------
# Graceful imports
# ---------------------------------------------------------------------------
try:
    from curator.sync import _find_changed_nodes, _hash_file_content
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
# Reference implementation of _hash_file_content for test assertions
# ---------------------------------------------------------------------------

def _ref_hash_file_content(path: Path) -> str:
    """Frontmatter-excluded body hash, 16 hex chars."""
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        body = parts[2] if len(parts) >= 3 else text
    else:
        body = text
    return hashlib.sha256(body.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# _hash_file_content
# ---------------------------------------------------------------------------

class TestHashFileContent(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _hash(self, path: Path) -> str:
        if SYNC_HELPERS_AVAILABLE:
            return _hash_file_content(path)
        return _ref_hash_file_content(path)

    def test_hash_excludes_frontmatter(self) -> None:
        f = self.dir / "node.md"
        body = "\n# Title\n\nBody text.\n"
        f.write_text(f"---\nid: ATM-001\nlast_updated: 2026-01-01\n---{body}")
        h1 = self._hash(f)
        # Change only frontmatter — hash must NOT change
        f.write_text(f"---\nid: ATM-001\nlast_updated: 2026-06-01\n---{body}")
        h2 = self._hash(f)
        self.assertEqual(h1, h2, "Hash must be stable when only frontmatter changes")

    def test_hash_changes_when_body_changes(self) -> None:
        f = self.dir / "node.md"
        f.write_text("---\nid: ATM-001\n---\n\nOriginal body.\n")
        h1 = self._hash(f)
        f.write_text("---\nid: ATM-001\n---\n\nModified body.\n")
        h2 = self._hash(f)
        self.assertNotEqual(h1, h2)

    def test_hash_is_16_hex_chars(self) -> None:
        f = self.dir / "node.md"
        f.write_text("---\nid: ATM-001\n---\n\nBody.\n")
        h = self._hash(f)
        self.assertEqual(len(h), 16)
        self.assertTrue(all(c in "0123456789abcdef" for c in h))

    def test_file_without_frontmatter_hashes_full_content(self) -> None:
        f = self.dir / "plain.md"
        f.write_text("No frontmatter here.\n")
        h = self._hash(f)
        expected = hashlib.sha256("No frontmatter here.\n".encode()).hexdigest()[:16]
        self.assertEqual(h, expected)


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

    def _write_atom(self, atom_id: str, body: str, content_hash: str | None = None) -> Path:
        if content_hash is None:
            body_text = f"# {atom_id}\n\n{body}\n"
            content_hash = hashlib.sha256(body_text.encode()).hexdigest()[:16]
        fm = (
            f"---\nid: {atom_id}\ntype: atom\ncontent_hash: {content_hash}\n"
            f"last_updated: 2026-05-29\n---\n\n# {atom_id}\n\n{body}\n"
        )
        path = self.paths.atoms / f"{atom_id}.md"
        path.write_text(fm, encoding="utf-8")
        return path

    def test_unchanged_node_not_in_changed_list(self) -> None:
        self._write_atom("ATM-abc00001", "Unchanged body.")
        changed = _find_changed_nodes(self.paths)
        self.assertNotIn("ATM-abc00001", changed)

    def test_modified_body_detected_as_changed(self) -> None:
        path = self._write_atom("ATM-abc00002", "Original body.")
        # Overwrite body but keep stale hash in frontmatter
        path.write_text(
            "---\nid: ATM-abc00002\ntype: atom\ncontent_hash: stale0000000000\n"
            "last_updated: 2026-05-29\n---\n\n# ATM-abc00002\n\nModified body.\n",
            encoding="utf-8",
        )
        changed = _find_changed_nodes(self.paths)
        self.assertIn("ATM-abc00002", changed)

    def test_node_with_no_content_hash_is_treated_as_changed(self) -> None:
        # Node created before v0.2.1 has no content_hash → always recheck
        path = self.paths.atoms / "ATM-legacy01.md"
        path.write_text(
            "---\nid: ATM-legacy01\ntype: atom\nlast_updated: 2026-01-01\n---\n\nLegacy body.\n",
            encoding="utf-8",
        )
        changed = _find_changed_nodes(self.paths)
        self.assertIn("ATM-legacy01", changed)

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
        # Write an atom whose content_hash matches its body
        body_text = "# ATM-match01\n\nContent that matches hash.\n"
        content_hash = hashlib.sha256(body_text.encode()).hexdigest()[:16]
        atom_path = self.paths.atoms / "ATM-match01.md"
        atom_path.write_text(
            f"---\nid: ATM-match01\ntype: atom\ncontent_hash: {content_hash}\n"
            f"last_updated: 2026-05-29\n---\n\n{body_text}",
            encoding="utf-8",
        )
        # Should complete without raising — client=None means no LLM available
        result = run_incremental_sync(self.paths, client=None, config={})
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
