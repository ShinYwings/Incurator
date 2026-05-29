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
        self.assertTrue(any(m["tier"] == "flash" for m in available["antigravity"]))

    def test_default_antigravity_model_from_catalogue(self) -> None:
        self.assertEqual(
            models.get_default_model("antigravity", "flash"),
            "gemini-3.5-flash",
        )

    def test_models_json_is_single_source_and_well_formed(self) -> None:
        """data/models.json is the single source of truth — guard its shape.

        Every provider must expose at least one flash and one think model with
        a non-empty id, so get_default_model resolves for both tiers (llm.py
        only carries last-resort fallbacks, not the full catalogue).
        """
        catalogue = models.load_models_catalogue()
        providers = catalogue.get("providers", {})
        self.assertTrue(providers, "models.json must define providers")
        for name in ("antigravity", "claude", "openai"):
            self.assertIn(name, providers)
            tiers = {m.get("tier") for m in providers[name].get("models", [])}
            self.assertIn("flash", tiers, f"{name} missing a flash model")
            self.assertIn("think", tiers, f"{name} missing a think model")
            for tier in ("flash", "think"):
                self.assertNotEqual(
                    models.get_default_model(name, tier), "",
                    f"{name}/{tier} default did not resolve from models.json",
                )

    def test_empty_catalogue_degrades_gracefully(self) -> None:
        """If the data file is unavailable, callers must not crash."""
        from unittest.mock import patch

        with patch.object(models, "load_models_catalogue", return_value=models._EMPTY_CATALOGUE):
            self.assertEqual(models.get_available_models(), {})
            self.assertEqual(models.get_default_model("antigravity", "flash"), "")


class TestAntigravityConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        self.paths.internal.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_legacy_gemini_model_keys_rename(self) -> None:
        """gemini_flash_model / gemini_think_model keys are renamed to antigravity_*."""
        self.paths.config_file.write_text(
            yaml.safe_dump(
                {
                    "llm": {
                        "primary": "antigravity-cli",
                        "gemini_flash_model": "gemini-2.5-flash",
                        "gemini_think_model": "gemini-2.5-pro",
                    }
                }
            ),
            encoding="utf-8",
        )
        loaded = cfg.load_config(self.paths)
        llm_cfg = loaded["llm"]
        self.assertEqual(llm_cfg["antigravity_flash_model"], "gemini-2.5-flash")
        self.assertEqual(llm_cfg["antigravity_think_model"], "gemini-2.5-pro")

    def test_antigravity_client_factory_keeps_selected_model(self) -> None:
        client = make_client_by_key(
            "antigravity-cli",
            {"llm": {"antigravity_flash_model": "gemini-2.5-flash"}},
        )
        self.assertIsInstance(client, AntigravityCliClient)
        self.assertEqual(client.model, "gemini-2.5-flash")


if __name__ == "__main__":
    unittest.main()
