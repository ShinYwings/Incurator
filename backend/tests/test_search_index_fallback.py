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
        unit_id = db.upsert_knowledge_unit(
            self.paths.state_db, unit_type="fact",
            canonical_name="Residual learning",
            statement="residual connections ease optimization",
            source_span_ids=[],
        )
        db.set_unit_support_status(self.paths.state_db, unit_id, "verified")

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

    def test_embed_unloads_configured_ollama_before_llama_cpp(self) -> None:
        config = cfg.DEFAULT_CONFIG.copy()
        config["llm"] = {
            **cfg.DEFAULT_CONFIG["llm"],
            "primary": "ollama::qwen2.5:7b",
        }
        config["search"] = {
            **cfg.DEFAULT_CONFIG["search"],
            "embedding": "llama-cpp::qwen3-embedding-0.6b",
        }
        with (
            patch.object(cfg, "load_config", return_value=config),
            patch("curator.model_setup.unload_configured_ollama_models") as unload,
            patch.object(providers, "build_embedder", return_value=None),
        ):
            search.update_index(self.paths, embed=True)

        unload.assert_called_once_with(config)


if __name__ == "__main__":
    unittest.main()
