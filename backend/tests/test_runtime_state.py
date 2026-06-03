import json
import tempfile
import unittest
from pathlib import Path

from curator import config as cfg
from curator import __version__
from curator import db
from curator import runtime_state


class TestRuntimeStateSnapshots(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = cfg.WikiPaths(Path(self.tmp.name))
        db.init_db(self.paths.state_db)
        self.paths.contexts.mkdir(parents=True, exist_ok=True)
        self.paths.atoms.mkdir(parents=True, exist_ok=True)
        (self.paths.contexts / "CTX-test.md").write_text("# Context\n", encoding="utf-8")
        with db.connect(self.paths.state_db) as conn:
            conn.execute(
                """
                INSERT INTO sources
                (relpath, content_hash, file_type, bytes, added_at, status,
                 context_id, l1_status, l2_status, l3_status, l4_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "04_Resources/paper.pdf",
                    "abc",
                    "pdf",
                    123,
                    "2026-06-02T00:00:00Z",
                    "curated",
                    "CTX-test",
                    "done",
                    "done",
                    "pending",
                    "pending",
                ),
            )
            source_id = conn.execute("SELECT id FROM sources").fetchone()["id"]
            conn.execute(
                """
                INSERT INTO ingest_jobs
                (source_id, job_type, trigger, state, phase, progress,
                 progress_current, progress_total, source_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    "l2_atoms",
                    "wiki_add",
                    "queued",
                    "queued",
                    0.0,
                    0,
                    10,
                    "paper.pdf",
                    "2026-06-02T00:00:00Z",
                ),
            )
            conn.execute(
                """
                INSERT INTO ingest_jobs
                (source_id, job_type, trigger, state, phase, progress,
                 progress_current, progress_total, source_name, created_at, finished_at, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    "l2_atoms",
                    "wiki_add",
                    "failed",
                    "failed",
                    0.0,
                    0,
                    10,
                    "failed.pdf",
                    "2026-06-02T00:00:00Z",
                    "2026-06-02T00:01:00Z",
                    "boom",
                ),
            )
            conn.execute(
                """
                INSERT INTO ingest_jobs
                (source_id, job_type, trigger, state, phase, progress,
                 progress_current, progress_total, source_name, created_at, finished_at, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    "l3_concepts",
                    "wiki_add",
                    "cancelled",
                    "cancelled",
                    0.0,
                    0,
                    10,
                    "cancelled.pdf",
                    "2026-06-02T00:00:00Z",
                    "2026-06-02T00:01:00Z",
                    "Cancelled by user",
                ),
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_write_runtime_snapshots(self) -> None:
        status = runtime_state.write_runtime_snapshots(self.paths, {"llm": {"primary": "codex-cli::gpt-5.5"}})

        runtime_dir = self.paths.internal / "runtime"
        self.assertEqual(status["layer_counts"]["contexts"], 1)
        self.assertEqual(status["sources"]["total"], 1)
        self.assertEqual(status["jobs"]["queued"], 1)
        self.assertEqual(status["sources"]["l1_done"], 1)
        self.assertEqual(status["sources"]["l2_done"], 1)
        self.assertEqual(status["sources"]["l3_done"], 0)
        self.assertEqual(status["backend_version"], __version__)

        for name in ("status", "sources", "jobs"):
            path = runtime_dir / f"{name}.json"
            self.assertTrue(path.exists(), f"{name}.json was not written")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(payload["ok"])

        sources = json.loads((runtime_dir / "sources.json").read_text(encoding="utf-8"))
        self.assertEqual(sources["sources"][0]["relpath"], "04_Resources/paper.pdf")

        jobs = json.loads((runtime_dir / "jobs.json").read_text(encoding="utf-8"))
        self.assertEqual(jobs["queued"][0]["source_name"], "paper.pdf")
        self.assertEqual(jobs["failed"][0]["source_name"], "failed.pdf")
        self.assertEqual(jobs["cancelled"][0]["source_name"], "cancelled.pdf")
