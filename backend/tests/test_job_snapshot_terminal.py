"""v0.52.1: a job's terminal transition must re-derive `runtime/jobs.json`.

The plugin's chat status bar polls that snapshot and nothing else. Before this
fix `run_next_job` wrote the snapshot only mid-run (after L2, before L3), so the
last file on disk kept the job in `running` forever while the DB said `done` —
the spinner span forever, `wiki jobs list` (which queries the DB) showed nothing.
"""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from curator import config as cfg
from curator import db
from curator import ingest_worker
from curator import runtime_state


def _register_source(db_path: Path, relpath: str = "04_Resources/paper.md") -> int:
    with db.connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO sources
                (relpath, content_hash, file_type, bytes, added_at,
                 l1_status, l2_status, l3_status)
            VALUES (?, ?, 'md', 12, datetime('now'), 'done', 'pending', 'pending')
            """,
            (relpath, "abc123abc123abc1"),
        )
        return int(cur.lastrowid)


def _snapshot(paths: cfg.WikiPaths) -> dict:
    path = runtime_state.snapshot_path(paths, "jobs")
    if not path.exists():
        raise AssertionError("runtime/jobs.json was never written")
    return json.loads(path.read_text(encoding="utf-8"))


class TestJobSnapshotOnTerminalTransition(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        db.init_db(self.paths.state_db)
        self.source_id = _register_source(self.paths.state_db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _fake_client(self) -> Mock:
        client = Mock()
        client.close = Mock()
        return client

    def test_completed_job_clears_running_from_the_snapshot(self) -> None:
        db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        result = SimpleNamespace(ok=True, error=None, atom_ids=["ATM-1"])
        with patch("curator.ingest_worker.build_client", return_value=self._fake_client()), \
             patch("curator.pipeline.compile.compile_source_l2", return_value=result), \
             patch("curator.ingest_worker.ingest_llm.run_l3_from_existing_atoms", return_value=[]):
            ingest_worker.run_next_job(self.paths, cfg.DEFAULT_CONFIG)

        snap = _snapshot(self.paths)
        self.assertEqual(snap["running"], [], "spinner would keep spinning on a stale `running`")
        self.assertEqual(snap["queued"], [])
        self.assertTrue(snap["idle"])

    def test_failed_job_clears_running_from_the_snapshot(self) -> None:
        db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        with patch("curator.ingest_worker.build_client", return_value=self._fake_client()), \
             patch("curator.pipeline.compile.compile_source_l2",
                   side_effect=RuntimeError("permanent boom")):
            ingest_worker.run_next_job(self.paths, cfg.DEFAULT_CONFIG)

        snap = _snapshot(self.paths)
        self.assertEqual(snap["running"], [])
        self.assertTrue(snap["idle"])
        self.assertEqual(len(snap["failed"]), 1)

    def test_snapshot_agrees_with_what_wiki_jobs_list_queries(self) -> None:
        """The reported symptom is exactly a disagreement between these two."""
        db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        result = SimpleNamespace(ok=True, error=None, atom_ids=["ATM-1"])
        with patch("curator.ingest_worker.build_client", return_value=self._fake_client()), \
             patch("curator.pipeline.compile.compile_source_l2", return_value=result), \
             patch("curator.ingest_worker.ingest_llm.run_l3_from_existing_atoms", return_value=[]):
            ingest_worker.run_next_job(self.paths, cfg.DEFAULT_CONFIG)

        snap = _snapshot(self.paths)
        from_db = db.list_ingest_jobs(self.paths.state_db, states=("queued", "running"))
        self.assertEqual(
            len(snap["running"]) + len(snap["queued"]),
            len(from_db),
            "the snapshot the plugin polls disagrees with the DB `wiki jobs list` reads",
        )

    def test_snapshot_write_failure_never_fails_the_job(self) -> None:
        db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        result = SimpleNamespace(ok=True, error=None, atom_ids=["ATM-1"])
        with patch("curator.ingest_worker.build_client", return_value=self._fake_client()), \
             patch("curator.pipeline.compile.compile_source_l2", return_value=result), \
             patch("curator.ingest_worker.ingest_llm.run_l3_from_existing_atoms", return_value=[]), \
             patch("curator.runtime_state.write_runtime_snapshots",
                   side_effect=OSError("disk full")):
            outcome = ingest_worker.run_next_job(self.paths, cfg.DEFAULT_CONFIG)

        self.assertTrue(outcome["ok"], "observability must never fail a committed job")


if __name__ == "__main__":
    unittest.main()
