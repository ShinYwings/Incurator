"""v0.2.1 tests for shared cloud model catalogue and config migration."""

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
            "gemini-3.1-flash-lite-preview",
        )


class TestAntigravityConfigMigration(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        self.paths.internal.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_legacy_gemini_keys_migrate_in_memory(self) -> None:
        self.paths.config_file.write_text(
            yaml.safe_dump(
                {
                    "llm": {
                        "primary": "gemini-cli",
                        "fallback": "gemini-cli",
                        "gemini_flash_model": "gemini-2.5-flash",
                        "gemini_think_model": "gemini-2.5-pro",
                    }
                }
            ),
            encoding="utf-8",
        )
        loaded = cfg.load_config(self.paths)
        llm_cfg = loaded["llm"]
        self.assertEqual(llm_cfg["primary"], "antigravity-cli")
        self.assertEqual(llm_cfg["fallback"], "antigravity-cli")
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
