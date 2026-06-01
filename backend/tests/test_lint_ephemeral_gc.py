import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from curator import config as cfg
from curator import lint


class EphemeralGarbageCollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.paths = cfg.paths_from_config(self.root)
        self.paths.exhibitions.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_exhibition(self, name: str, *, ephemeral: bool) -> Path:
        path = self.paths.exhibitions / name
        path.write_text(
            "\n".join(
                [
                    "---",
                    f"ephemeral: {str(ephemeral).lower()}",
                    "---",
                    "",
                    "# Session Answer",
                    "",
                    "Body.",
                ]
            ),
            encoding="utf-8",
        )
        return path

    def test_gc_deletes_only_stale_ephemeral_exhibitions(self) -> None:
        old_ephemeral = self._write_exhibition("EXH-old.md", ephemeral=True)
        recent_ephemeral = self._write_exhibition("EXH-recent.md", ephemeral=True)
        old_persistent = self._write_exhibition("EXH-persistent.md", ephemeral=False)

        old_time = time.time() - (25 * 3600)
        os.utime(old_ephemeral, (old_time, old_time))
        os.utime(old_persistent, (old_time, old_time))

        deleted = lint.gc_ephemeral_exhibitions(self.paths, max_age_hours=24)

        self.assertEqual(deleted, [str(old_ephemeral)])
        self.assertFalse(old_ephemeral.exists())
        self.assertTrue(recent_ephemeral.exists())
        self.assertTrue(old_persistent.exists())


if __name__ == "__main__":
    unittest.main()
