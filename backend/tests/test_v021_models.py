"""v0.2.1 tests for shared cloud model catalogue and config."""

import tempfile
import unittest
from pathlib import Path


from unittest.mock import patch

from curator import config as cfg
from curator import constants as consts
from curator import models
from curator.llm import (
    AntigravityCliClient,
    AntigravityCliError,
    ClaudeCodeClient,
    CodexCliClient,
    build_client,
    make_client_by_key,
)


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
            provider_models = providers[name]["models"]
            ids = [model["id"] for model in provider_models]
            self.assertEqual(len(ids), len(set(ids)), f"{name} has duplicate model ids")
            for model in provider_models:
                default_effort = model.get("default_effort", "")
                if default_effort:
                    self.assertIn(default_effort, model.get("efforts", []))

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
            {"llm": {"primary": "antigravity-cli::gemini-3.5-flash"}},
        )
        self.assertIsInstance(client, AntigravityCliClient)
        self.assertEqual(client.model, "gemini-3.5-flash")

    def test_antigravity_empty_stdout_with_quota_log_raises_capacity_error(self) -> None:
        client = AntigravityCliClient(model="gemini-3.5-flash")
        captured: dict = {}

        def fake_run(cmd, **kwargs):  # noqa: ARG001
            captured["cmd"] = cmd
            log_path = Path(cmd[cmd.index("--log-file") + 1])
            log_path.write_text(
                "agent executor error: RESOURCE_EXHAUSTED (code 429): Individual quota reached.",
                encoding="utf-8",
            )

            class _R:
                returncode = 0
                stdout = ""
                stderr = ""

            return _R()

        with patch("curator.llm.subprocess.run", fake_run):
            with self.assertRaises(AntigravityCliError) as ctx:
                client._run("hi")

        self.assertIn("capacity exhausted", str(ctx.exception))
        self.assertIn("--log-file", captured["cmd"])
        self.assertFalse(client.ping())

    def test_antigravity_run_passes_full_prompt_model_and_catalogue_default_effort(
        self,
    ) -> None:
        client = AntigravityCliClient(model="gemini-3.6-flash")
        prompt = (
            "Return exactly one <transcription> block. "
            "The reconstruction loss is L = sum_i (x_i - y_i)^2."
        )
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs

            class _R:
                returncode = 0
                stdout = "<transcription>Clean $L = \\\\sum_i (x_i-y_i)^2$.</transcription>"
                stderr = ""

            return _R()

        with patch("curator.llm.subprocess.run", fake_run):
            result = client._run(prompt)

        cmd = captured["cmd"]
        self.assertEqual(cmd[cmd.index("--print") + 1], prompt)
        self.assertEqual(cmd[cmd.index("--model") + 1], "gemini-3.6-flash")
        self.assertEqual(cmd[cmd.index("--effort") + 1], "medium")
        self.assertNotIn("input", captured["kwargs"])
        self.assertIn("<transcription>", result)

    def test_antigravity_run_preserves_explicit_effort(self) -> None:
        client = AntigravityCliClient(model="gemini-3.6-flash", effort="high")
        captured: dict = {}

        def fake_run(cmd, **kwargs):  # noqa: ARG001
            captured["cmd"] = cmd

            class _R:
                returncode = 0
                stdout = "ok"
                stderr = ""

            return _R()

        with patch("curator.llm.subprocess.run", fake_run):
            client._run("Return OK")

        cmd = captured["cmd"]
        self.assertEqual(cmd[cmd.index("--effort") + 1], "high")

    def test_antigravity_run_omits_effort_for_model_without_effort_dimension(
        self,
    ) -> None:
        client = AntigravityCliClient(model="custom-model-without-catalogue-effort")
        captured: dict = {}

        def fake_run(cmd, **kwargs):  # noqa: ARG001
            captured["cmd"] = cmd

            class _R:
                returncode = 0
                stdout = "ok"
                stderr = ""

            return _R()

        with patch("curator.llm.subprocess.run", fake_run):
            client._run("Return OK")

        self.assertNotIn("--effort", captured["cmd"])

    def test_start_client_primary_without_fallback_returns_primary(self) -> None:
        from curator import cli

        class ReadyClient:
            def __init__(self) -> None:
                self.ready = False

            def ensure_ready(self) -> None:
                self.ready = True

        ready_client = ReadyClient()
        config = {"llm": {"primary": "antigravity-cli::gemini-3.5-flash", "fallback": ""}}

        with patch("curator.cli.make_client_by_key", return_value=ready_client), patch(
            "curator.cli.build_client"
        ) as build_client_mock:
            result = cli._start_client_inner(config)

        self.assertIs(result, ready_client)
        self.assertTrue(ready_client.ready)
        build_client_mock.assert_not_called()


class TestModelEfforts(unittest.TestCase):
    """Reasoning/effort dimension added to the catalogue and CLI clients."""

    def test_catalogue_exposes_efforts(self) -> None:
        available = models.get_available_models()
        sonnet = next(m for m in available["claude"] if m["id"] == "claude-sonnet-4-6")
        self.assertEqual(sonnet["efforts"], ["low", "medium", "high", "max"])
        self.assertEqual(sonnet["default_effort"], "high")
        sol = next(m for m in available["openai"] if m["id"] == "gpt-5.6-sol")
        self.assertEqual(sol["efforts"], ["low", "medium", "high", "xhigh", "max", "ultra"])
        self.assertEqual(sol["default_effort"], "low")

    def test_cli_catalogue_ids_order_context_and_defaults_are_exact(self) -> None:
        available = models.get_available_models()
        self.assertEqual(
            [model["id"] for model in available["claude"]],
            ["claude-sonnet-4-6", "claude-fable-5", "claude-opus-4-8", "claude-haiku-4-5"],
        )
        self.assertEqual(
            [model["id"] for model in available["openai"]],
            ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5"],
        )
        self.assertEqual([model["context_window"] for model in available["openai"]], [272000] * 4)
        self.assertEqual(consts.DEFAULT_CLAUDE_MODEL, available["claude"][0]["id"])
        self.assertEqual(consts.DEFAULT_CODEX_MODEL, available["openai"][0]["id"])
        self.assertEqual(consts.DEFAULT_CLAUDE_EFFORT, "high")
        self.assertEqual(consts.DEFAULT_CODEX_EFFORT, "low")

    def test_effort_helpers(self) -> None:
        self.assertEqual(
            models.get_model_efforts("openai", "gpt-5.6-terra"),
            ["low", "medium", "high", "xhigh", "max", "ultra"],
        )
        self.assertEqual(models.get_default_effort("claude", "claude-sonnet-4-6"), "high")
        self.assertEqual(models.get_model_efforts("claude", "claude-haiku-4-5"), [])
        # Ollama models have no effort dimension.
        self.assertEqual(models.get_model_efforts("ollama", "qwen2.5:7b"), [])

    def test_no_phantom_models(self) -> None:
        """Models that the live CLIs do not expose must not be in the catalogue."""
        catalogue = models.load_models_catalogue()
        agy_ids = {m["id"] for m in catalogue["providers"]["antigravity"]["models"]}
        self.assertNotIn("gemini-3.5-pro", agy_ids)
        self.assertIn("gemini-3.5-flash", agy_ids)
        self.assertIn("gpt-oss-120b", agy_ids)

    def test_codex_client_injects_reasoning_effort(self) -> None:
        client = CodexCliClient(model="gpt-5.6-sol", effort="ultra")
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            out_idx = cmd.index("--output-last-message") + 1
            Path(cmd[out_idx]).write_text("ok", encoding="utf-8")

            class _R:
                returncode = 0
                stdout = ""
                stderr = ""

            return _R()

        with patch("curator.llm.subprocess.run", fake_run):
            client._run("hi")
        self.assertIn("-c", captured["cmd"])
        self.assertIn("model_reasoning_effort=ultra", captured["cmd"])

    def test_codex_client_clone_preserves_model_and_effort(self) -> None:
        client = CodexCliClient(model="gpt-5.6-luna", effort="medium")
        clone = client.clone()

        self.assertIsInstance(clone, CodexCliClient)
        self.assertIsNot(clone, client)
        self.assertEqual(clone.model, "gpt-5.6-luna")
        self.assertEqual(clone.effort, "medium")
        self.assertLessEqual(clone.optimal_chunk_chars, 12000)

    def test_claude_client_passes_effort_flag(self) -> None:
        client = ClaudeCodeClient(model="claude-sonnet-4-6", effort="max")
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd

            class _R:
                returncode = 0
                stdout = "ok"
                stderr = ""

            return _R()

        with patch("curator.llm.subprocess.run", fake_run):
            client._run("hi")
        self.assertIn("--effort", captured["cmd"])
        self.assertIn("max", captured["cmd"])

    def test_claude_image_path_preserves_effort_flag(self) -> None:
        client = ClaudeCodeClient(model="claude-fable-5", effort="high")
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd

            class _R:
                returncode = 0
                stdout = "ok"
                stderr = ""

            return _R()

        with patch("curator.llm.subprocess.run", fake_run):
            client._run_with_image_path("Read image", "/tmp/image.png")
        self.assertIn("--effort", captured["cmd"])
        self.assertIn("high", captured["cmd"])

    def test_claude_no_effort_omits_flag(self) -> None:
        client = ClaudeCodeClient(model="claude-haiku-4-5", effort="")
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd

            class _R:
                returncode = 0
                stdout = "ok"
                stderr = ""

            return _R()

        with patch("curator.llm.subprocess.run", fake_run):
            client._run("hi")
        self.assertNotIn("--effort", captured["cmd"])

    def test_build_client_threads_per_slot_effort(self) -> None:
        config = {"llm": {"primary": "codex-cli::gpt-5.6-sol", "primary_effort": "ultra", "fallback": ""}}
        client = build_client(config)
        inner = client.providers[0] if hasattr(client, "providers") else client
        self.assertIsInstance(inner, CodexCliClient)
        self.assertEqual(inner.effort, "ultra")

    def test_default_config_has_effort_keys(self) -> None:
        self.assertIn("primary_effort", cfg.DEFAULT_CONFIG["llm"])
        self.assertIn("fallback_effort", cfg.DEFAULT_CONFIG["llm"])


if __name__ == "__main__":
    unittest.main()
