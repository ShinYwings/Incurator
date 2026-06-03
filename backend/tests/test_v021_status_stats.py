import tempfile
import unittest
from pathlib import Path

from curator import config as cfg
from curator import db


class StatusStatsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        db.init_db(self.paths.state_db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_get_stats_counts_l1_done_separately_from_curated_status(self) -> None:
        with db.connect(self.paths.state_db) as conn:
            conn.execute(
                """INSERT INTO sources
                   (relpath, content_hash, file_type, bytes, added_at, status, l1_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("02_Wiki/l1-only.md", "hash-a", "md", 10,
                 "2026-05-29T00:00:00Z", "pending", "done"),
            )
            conn.execute(
                """INSERT INTO sources
                   (relpath, content_hash, file_type, bytes, added_at, status, l1_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("02_Wiki/curated.md", "hash-b", "md", 10,
                 "2026-05-29T00:00:00Z", "curated", "done"),
            )

        stats = db.get_stats(self.paths.state_db)

        self.assertEqual(stats["sources_total"], 2)
        self.assertEqual(stats["sources_l1_done"], 2)
        self.assertEqual(stats["sources_curated"], 1)

    def test_get_stats_bootstraps_when_db_file_exists_without_sources_table(self) -> None:
        # Simulate an existing DB file that has no Curator tables.
        self.paths.state_db.parent.mkdir(parents=True, exist_ok=True)
        self.paths.state_db.write_bytes(b"")

        stats = db.get_stats(self.paths.state_db)

        self.assertEqual(stats["sources_total"], 0)
        self.assertEqual(stats["sources_l1_done"], 0)
        self.assertEqual(stats["sources_curated"], 0)


if __name__ == "__main__":
    unittest.main()
