import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from curator import config as cfg
from curator import search


class SearchIndexFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        self.paths.collections.mkdir(parents=True, exist_ok=True)
        self.paths.qmd_dir.mkdir(parents=True, exist_ok=True)
        self.paths.qmd_config_file.write_text("collections: []\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_embed_failure_degrades_after_successful_bm25_update(self) -> None:
        calls: list[list[str]] = []

        def fake_run_qmd(args, **kwargs):  # noqa: ANN001, ANN003
            calls.append(list(args))
            if args == ["update"]:
                return subprocess.CompletedProcess(args, 0, stdout="updated", stderr="")
            if args == ["embed"]:
                return subprocess.CompletedProcess(
                    args,
                    1,
                    stdout="",
                    stderr="Failed to create any embedding context",
                )
            raise AssertionError(args)

        with patch.object(search, "_run_qmd", side_effect=fake_run_qmd):
            result = search.update_index(self.paths, embed=True)

        self.assertEqual(calls, [["update"], ["embed"]])
        self.assertTrue(result.updated)
        self.assertFalse(result.embedded)
        self.assertTrue(result.degraded)
        self.assertIn("qmd embed failed", result.warning)

    def test_update_failure_still_raises(self) -> None:
        def fake_run_qmd(args, **kwargs):  # noqa: ANN001, ANN003
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="update failed")

        with patch.object(search, "_run_qmd", side_effect=fake_run_qmd):
            with self.assertRaises(search.SearchBackendError):
                search.update_index(self.paths, embed=True)


if __name__ == "__main__":
    unittest.main()
