from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from curator import config as cfg
from curator import db, lint
from curator.cli import _filter_sync_structural_issues


class SyncReportFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        self.paths.internal.mkdir(parents=True, exist_ok=True)
        db.init_db(self.paths.state_db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_l1_orphan_is_not_actionable_while_l2_is_pending(self) -> None:
        with db.connect(self.paths.state_db) as conn:
            conn.execute(
                """INSERT INTO sources
                   (relpath, content_hash, file_type, bytes, added_at, status,
                    context_id, l1_status, l2_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "03_Notes/source.md",
                    "hash",
                    "md",
                    10,
                    "2026-06-01T00:00:00Z",
                    "pending",
                    "CTX-abc12345",
                    "done",
                    "pending",
                ),
            )

        issue = lint.LintIssue(
            check=lint.CheckId.ORPHAN_PAGE,
            severity=lint.Severity.WARNING,
            page="01_Contexts/CTX-abc12345.md",
            message="No incoming wikilinks.",
        )

        self.assertEqual(_filter_sync_structural_issues(self.paths, [issue]), [])


if __name__ == "__main__":
    unittest.main()
