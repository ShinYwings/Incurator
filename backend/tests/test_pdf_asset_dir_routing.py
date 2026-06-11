"""v0.5.6 tests: PDF add-source asset routing via --asset-dir (PLUGIN_SCHEMA §1.1).

Covers:
  - _safe_vault_subdir: vault-relative validation (no abs paths, no `..` escape,
    path-resolution errors fall back without failing ingest)
  - _save_pdf_images(asset_dir=...): routed write, obsidian_path == write root,
    unsafe/empty values fall back to the legacy 05_Assets/<slug>/ location
  - plugin_api.register_source(asset_dir=...) → generate_l1_structural_context
  - wiki plugin source register --asset-dir CLI plumbing
"""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from curator import config as cfg
from curator import db
from curator.ingest_raw import _safe_vault_subdir, _save_pdf_images


def _make_paths(root: Path) -> cfg.WikiPaths:
    paths = cfg.WikiPaths(root)
    db.init_db(paths.state_db)
    return paths


def _fake_parsed(images: list | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        file_type="pdf",
        title="Test Doc",
        text="body text",
        metadata={
            "pdf_images": images if images is not None else [],
            "pdf_pages": [],
        },
    )


IMG = {"page": 1, "data": b"x" * 2000, "ext": "png"}


class TestSafeVaultSubdir(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = _make_paths(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_valid_relative_dir_is_accepted(self) -> None:
        result = _safe_vault_subdir(self.paths, "05_Assets/Zotero Assets/kim2024")
        self.assertEqual(result, "05_Assets/Zotero Assets/kim2024")

    def test_empty_is_rejected(self) -> None:
        self.assertIsNone(_safe_vault_subdir(self.paths, ""))
        self.assertIsNone(_safe_vault_subdir(self.paths, "   "))

    def test_absolute_path_is_rejected(self) -> None:
        self.assertIsNone(_safe_vault_subdir(self.paths, "/etc/evil"))
        self.assertIsNone(_safe_vault_subdir(self.paths, str(self.root / "05_Assets")))

    def test_parent_traversal_is_rejected(self) -> None:
        self.assertIsNone(_safe_vault_subdir(self.paths, "../outside"))
        self.assertIsNone(_safe_vault_subdir(self.paths, "05_Assets/../../outside"))

    def test_inner_dot_segments_are_normalized(self) -> None:
        result = _safe_vault_subdir(self.paths, "05_Assets/./sub")
        self.assertEqual(result, "05_Assets/sub")

    def test_trailing_and_duplicate_slashes_are_normalized(self) -> None:
        result = _safe_vault_subdir(self.paths, "05_Assets//sub/")
        self.assertEqual(result, "05_Assets/sub")

    def test_resolution_error_is_rejected(self) -> None:
        with patch("curator.ingest_raw.Path.resolve", side_effect=OSError("invalid path")):
            self.assertIsNone(_safe_vault_subdir(self.paths, "05_Assets/sub"))


class TestSavePdfImagesAssetDir(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = _make_paths(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_asset_dir_routes_write_and_obsidian_path(self) -> None:
        parsed = _fake_parsed(images=[dict(IMG)])
        result = _save_pdf_images(
            parsed, "04_Resources/paper.pdf", self.paths,
            asset_dir="05_Assets/Zotero Assets/kim2024",
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0]["obsidian_path"],
            "05_Assets/Zotero Assets/kim2024/p01_img01.png",
        )
        # obsidian_path must match the actual write root
        self.assertTrue((self.root / result[0]["obsidian_path"]).exists())

    def test_unsafe_asset_dir_falls_back_to_legacy(self) -> None:
        for bad in ("../../outside", "/abs/outside", "05_Assets/../../x"):
            parsed = _fake_parsed(images=[dict(IMG)])
            result = _save_pdf_images(
                parsed, "04_Resources/paper.pdf", self.paths, asset_dir=bad
            )
            self.assertEqual(len(result), 1, bad)
            self.assertEqual(
                result[0]["obsidian_path"], "05_Assets/paper/p01_img01.png", bad
            )
            self.assertTrue((self.root / result[0]["obsidian_path"]).exists(), bad)
        # nothing escaped the vault root
        self.assertFalse((self.root.parent / "outside").exists())

    def test_no_asset_dir_keeps_legacy_behavior(self) -> None:
        parsed = _fake_parsed(images=[dict(IMG)])
        result = _save_pdf_images(parsed, "04_Resources/paper.pdf", self.paths)
        self.assertEqual(result[0]["obsidian_path"], "05_Assets/paper/p01_img01.png")

    def test_empty_asset_dir_keeps_legacy_behavior(self) -> None:
        parsed = _fake_parsed(images=[dict(IMG)])
        result = _save_pdf_images(
            parsed, "04_Resources/paper.pdf", self.paths, asset_dir=""
        )
        self.assertEqual(result[0]["obsidian_path"], "05_Assets/paper/p01_img01.png")


class TestRegisterSourceAssetDirPlumbing(unittest.TestCase):
    def setUp(self) -> None:
        from curator import ingest_raw

        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = _make_paths(self.root)
        for d in self.paths.raw_dirs:
            d.mkdir(parents=True, exist_ok=True)

        note = self.root / "04_Resources" / "doc.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text(
            "# Title\n\n## Section A\n\nEnough words here to register a usable source file.\n",
            encoding="utf-8",
        )
        outcome = ingest_raw.add_file(self.paths, note)
        self.source_id = int(outcome.source_id)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_register_source_forwards_asset_dir(self) -> None:
        from curator import plugin_api

        with patch(
            "curator.ingest_raw.generate_l1_structural_context",
            return_value="CTX-test0001",
        ) as gen:
            result = plugin_api.register_source(
                self.paths,
                source_id=self.source_id,
                force=True,
                build=False,
                asset_dir="05_Assets/Routed",
            )
        self.assertTrue(result["ok"])
        self.assertEqual(gen.call_args.kwargs.get("asset_dir"), "05_Assets/Routed")

    def test_register_source_defaults_to_no_asset_dir(self) -> None:
        from curator import plugin_api

        with patch(
            "curator.ingest_raw.generate_l1_structural_context",
            return_value="CTX-test0002",
        ) as gen:
            result = plugin_api.register_source(
                self.paths,
                source_id=self.source_id,
                force=True,
                build=False,
            )
        self.assertTrue(result["ok"])
        self.assertFalse(gen.call_args.kwargs.get("asset_dir"))


class TestPluginCliAssetDirArg(unittest.TestCase):
    def test_register_cli_passes_asset_dir(self) -> None:
        from curator.cli import app

        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            cfg.save_config(cfg.WikiPaths(vault), {"llm": {"provider": "ollama"}})
            with patch(
                "curator.plugin_api.register_source",
                return_value={"ok": True, "state": "l1_ready"},
            ) as reg:
                result = runner.invoke(
                    app,
                    [
                        "plugin", "source", "register",
                        "--source-id", "1",
                        "--asset-dir", "05_Assets/Routed",
                        "--no-build",
                        "--workspace-path", str(vault),
                    ],
                )
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output[result.output.find("{"):result.output.rfind("}") + 1])
        self.assertTrue(payload["ok"])
        self.assertEqual(reg.call_args.kwargs.get("asset_dir"), "05_Assets/Routed")


if __name__ == "__main__":
    unittest.main()
