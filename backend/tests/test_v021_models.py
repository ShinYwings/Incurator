"""v0.2.1 tests for shared cloud model catalogue and config."""

import tempfile
import unittest
from pathlib import Path

import yaml

from curator import config as cfg
from curator import models
from curator.llm import AntigravityCliClient, make_client_by_key


class TestSharedModelsCatalogue(unittest.TestCase):
    def test_available_models_exposes_antigravity_and_claude(self) -> None:
        available = models.get_available_models()
        self.assertIn("antigravity", available)
        self.assertIn("claude", available)
        self.assertIn("openai", available)
        self.assertTrue(len(available["antigravity"]) > 0)

    def test_default_antigravity_model_from_catalogue(self) -> None:
        self.assertEqual(
            models.get_default_model("antigravity"),
            "gemini-3.5-flash",
        )

    def test_models_json_is_single_source_and_well_formed(self) -> None:
        """data/models.json is the single source of truth — guard its shape.

        Every provider must expose at least one model with
        a non-empty id, so get_default_model resolves (llm.py
        only carries last-resort fallbacks, not the full catalogue).
        """
        catalogue = models.load_models_catalogue()
        providers = catalogue.get("providers", {})
        self.assertTrue(providers, "models.json must define providers")
        for name in ("antigravity", "claude", "openai"):
            self.assertIn(name, providers)
            self.assertTrue(providers[name].get("models", []), f"{name} missing models")
            self.assertNotEqual(
                models.get_default_model(name), "",
                f"{name} default did not resolve from models.json",
            )

    def test_empty_catalogue_degrades_gracefully(self) -> None:
        """If the data file is unavailable, callers must not crash."""
        from unittest.mock import patch

        with patch.object(models, "load_models_catalogue", return_value=models._EMPTY_CATALOGUE):
            self.assertEqual(models.get_available_models(), {})
            self.assertEqual(models.get_default_model("antigravity"), "")


class TestAntigravityConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        self.paths.internal.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_antigravity_client_factory_keeps_selected_model(self) -> None:
        client = make_client_by_key(
            "antigravity-cli",
            {"llm": {"primary": "antigravity-cli::gemini-2.5-flash"}},
        )
        self.assertIsInstance(client, AntigravityCliClient)
        self.assertEqual(client.model, "gemini-2.5-flash")


if __name__ == "__main__":
    unittest.main()
