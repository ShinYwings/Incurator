"""v0.3.2: native `update_index` rebuild + embedding degradation (qmd retired)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from curator import config as cfg
from curator import db
from curator import search
from curator.retrieval import providers


class SearchIndexFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        self.paths.internal.mkdir(parents=True, exist_ok=True)
        db.init_db(self.paths.state_db)
        # Authoritative row the materializer projects into the search corpus.
        db.upsert_knowledge_unit(
            self.paths.state_db, unit_type="fact",
            canonical_name="Residual learning",
            statement="residual connections ease optimization",
            source_span_ids=[],
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_rebuild_without_embed_succeeds_and_is_fts_only(self) -> None:
        result = search.update_index(self.paths, embed=False)
        self.assertTrue(result.updated)
        self.assertFalse(result.embedded)
        # FTS5 lexical search works with no embedder
        hits = db.fts_search(self.paths.state_db, "residual")
        self.assertTrue(hits)

    def test_embed_degrades_when_embedder_unavailable(self) -> None:
        # When no embedder is configured, embedding must degrade to FTS5-only
        # rather than raise — search still works lexically.
        with patch.object(providers, "build_embedder", return_value=None):
            result = search.update_index(self.paths, embed=True)

        self.assertTrue(result.updated)
        self.assertFalse(result.embedded)
        self.assertTrue(result.degraded)
        self.assertIn("FTS5-only", result.warning)


if __name__ == "__main__":
    unittest.main()
