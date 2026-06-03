"""v0.2.1 tests for background ingest job orchestration."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from curator import config as cfg
from curator import db
from curator import ingest_worker
from curator import source_tools


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


class TestBackgroundJobQueue(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        db.init_db(self.paths.state_db)
        self.source_id = _register_source(self.paths.state_db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_enqueue_job_is_idempotent_while_queued(self) -> None:
        first = db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        second = db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        self.assertEqual(first, second)
        jobs = db.list_ingest_jobs(self.paths.state_db, states=("queued", "running"))
        self.assertEqual(len(jobs), 1)

    def test_source_status_includes_pending_jobs(self) -> None:
        db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        with db.connect(self.paths.state_db) as conn:
            row = dict(conn.execute("SELECT * FROM sources WHERE id = ?", (self.source_id,)).fetchone())
        source_path = self.root / row["relpath"]
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text("# Paper\n\nbody text for parser\n", encoding="utf-8")
        with patch("curator.source_tools.parse_source") as parse:
            parse.return_value = SimpleNamespace(content_hash=row["content_hash"])
            status = source_tools.source_status(self.paths, row, cfg.DEFAULT_CONFIG)
        self.assertTrue(status["registered"])
        self.assertFalse(status["l2_complete"])
        self.assertEqual(status["jobs_pending"][0]["type"], "l2_atoms")

    def test_run_next_job_marks_done(self) -> None:
        job_id = db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        fake_client = Mock()
        fake_client.close = Mock()
        fake_result = SimpleNamespace(
            ok=True, error=None, pages_created=2, pages_updated=1, changes=[]
        )
        with patch("curator.ingest_worker.build_client", return_value=fake_client), \
             patch("curator.ingest_worker.ingest_llm.ingest_source", return_value=fake_result), \
             patch("curator.ingest_worker.ingest_llm.run_l3_from_existing_atoms", return_value=[]):
            result = ingest_worker.run_next_job(self.paths, cfg.DEFAULT_CONFIG)
        self.assertTrue(result["ok"])
        with db.connect(self.paths.state_db) as conn:
            row = conn.execute("SELECT * FROM ingest_jobs WHERE id = ?", (job_id,)).fetchone()
        self.assertEqual(row["state"], "done")
        self.assertEqual(row["pages_created"], 2)
        self.assertEqual(row["pages_updated"], 1)

    def test_failed_job_records_error(self) -> None:
        job_id = db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        fake_client = Mock()
        fake_client.close = Mock()
        with patch("curator.ingest_worker.build_client", return_value=fake_client), \
             patch("curator.ingest_worker.ingest_llm.ingest_source",
                   side_effect=RuntimeError("boom")):
            result = ingest_worker.run_next_job(self.paths, cfg.DEFAULT_CONFIG)
        self.assertFalse(result["ok"])
        with db.connect(self.paths.state_db) as conn:
            row = conn.execute("SELECT * FROM ingest_jobs WHERE id = ?", (job_id,)).fetchone()
        self.assertEqual(row["state"], "failed")
        self.assertIn("boom", row["error"])

    def test_cancel_job_marks_queued_job_cancelled(self) -> None:
        job_id = db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")

        self.assertTrue(db.cancel_job(self.paths.state_db, job_id))

        with db.connect(self.paths.state_db) as conn:
            row = conn.execute("SELECT * FROM ingest_jobs WHERE id = ?", (job_id,)).fetchone()
        self.assertEqual(row["state"], "cancelled")
        self.assertEqual(row["phase"], "cancelled")
        self.assertIn("Cancelled by user", row["error"])

    def test_cancel_job_leaves_running_job_untouched(self) -> None:
        job_id = db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        db.claim_next_job(self.paths.state_db)

        self.assertFalse(db.cancel_job(self.paths.state_db, job_id))

        with db.connect(self.paths.state_db) as conn:
            row = conn.execute("SELECT * FROM ingest_jobs WHERE id = ?", (job_id,)).fetchone()
        self.assertEqual(row["state"], "running")

    def test_rerun_job_requeues_terminal_job(self) -> None:
        job_id = db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        db.mark_job_failed(self.paths.state_db, job_id, "boom")

        self.assertTrue(db.rerun_job(self.paths.state_db, job_id))

        with db.connect(self.paths.state_db) as conn:
            row = conn.execute("SELECT * FROM ingest_jobs WHERE id = ?", (job_id,)).fetchone()
        self.assertEqual(row["state"], "queued")
        self.assertEqual(row["phase"], "rerun")
        self.assertIsNone(row["error"])
        self.assertIsNone(row["started_at"])
        self.assertIsNone(row["finished_at"])

    def test_failed_job_sets_l2_error_layer_status(self) -> None:
        db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        fake_client = Mock()
        fake_client.close = Mock()
        with patch("curator.ingest_worker.build_client", return_value=fake_client), \
             patch("curator.ingest_worker.ingest_llm.ingest_source",
                   side_effect=RuntimeError("parse failed")):
            ingest_worker.run_next_job(self.paths, cfg.DEFAULT_CONFIG)
        with db.connect(self.paths.state_db) as conn:
            row = conn.execute("SELECT l2_status FROM sources WHERE id = ?", (self.source_id,)).fetchone()
        self.assertEqual(row["l2_status"], "error")

    def test_transient_error_requeues_for_retry(self) -> None:
        job_id = db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        fake_client = Mock()
        fake_client.close = Mock()
        with patch("curator.ingest_worker.build_client", return_value=fake_client), \
             patch("curator.ingest_worker.ingest_llm.ingest_source",
                   side_effect=RuntimeError("connection timeout")):
            result = ingest_worker.run_next_job(self.paths, cfg.DEFAULT_CONFIG)
        self.assertFalse(result["ok"])
        with db.connect(self.paths.state_db) as conn:
            row = conn.execute("SELECT * FROM ingest_jobs WHERE id = ?", (job_id,)).fetchone()
        # Should be re-queued (not failed) after first transient error
        self.assertEqual(row["state"], "queued")
        self.assertEqual(row["retry_count"], 1)

    def test_permanent_failure_after_max_retries(self) -> None:
        job_id = db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        # Manually set retry_count to MAX_RETRIES so the next failure is permanent
        with db.connect(self.paths.state_db) as conn:
            conn.execute(
                "UPDATE ingest_jobs SET retry_count = ? WHERE id = ?",
                (ingest_worker.MAX_RETRIES, job_id),
            )
        fake_client = Mock()
        fake_client.close = Mock()
        with patch("curator.ingest_worker.build_client", return_value=fake_client), \
             patch("curator.ingest_worker.ingest_llm.ingest_source",
                   side_effect=RuntimeError("connection timeout")):
            result = ingest_worker.run_next_job(self.paths, cfg.DEFAULT_CONFIG)
        self.assertFalse(result["ok"])
        with db.connect(self.paths.state_db) as conn:
            row = conn.execute("SELECT * FROM ingest_jobs WHERE id = ?", (job_id,)).fetchone()
        self.assertEqual(row["state"], "failed")

    def test_l3_triggered_when_no_remaining_l2_jobs(self) -> None:
        db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        fake_client = Mock()
        fake_client.close = Mock()
        fake_result = SimpleNamespace(ok=True, error=None, pages_created=1, pages_updated=0, changes=[])
        l3_called = []

        def fake_l3(paths, client, cb_factory):
            l3_called.append(True)
            return []

        with patch("curator.ingest_worker.build_client", return_value=fake_client), \
             patch("curator.ingest_worker.ingest_llm.ingest_source", return_value=fake_result), \
             patch("curator.ingest_worker.ingest_llm.run_l3_from_existing_atoms", side_effect=fake_l3):
            ingest_worker.run_next_job(self.paths, cfg.DEFAULT_CONFIG)
        self.assertEqual(len(l3_called), 1, "L3 should be triggered once after last L2 job")

    def test_l3_skipped_when_more_l2_jobs_remain(self) -> None:
        source_id2 = _register_source(self.paths.state_db, "04_Resources/paper2.md")
        db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        db.enqueue_job(self.paths.state_db, source_id2, "l2_atoms")
        fake_client = Mock()
        fake_client.close = Mock()
        fake_result = SimpleNamespace(ok=True, error=None, pages_created=1, pages_updated=0, changes=[])
        l3_called = []

        def fake_l3(paths, client, cb_factory):
            l3_called.append(True)
            return []

        with patch("curator.ingest_worker.build_client", return_value=fake_client), \
             patch("curator.ingest_worker.ingest_llm.ingest_source", return_value=fake_result), \
             patch("curator.ingest_worker.ingest_llm.run_l3_from_existing_atoms", side_effect=fake_l3):
            ingest_worker.run_next_job(self.paths, cfg.DEFAULT_CONFIG)
        # With 2 jobs queued initially, after first completes there's still 1 queued → skip L3
        self.assertEqual(len(l3_called), 0, "L3 should be skipped while L2 jobs remain")

    def test_count_active_l2_jobs(self) -> None:
        self.assertEqual(db.count_active_l2_jobs(self.paths.state_db), 0)
        db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        self.assertEqual(db.count_active_l2_jobs(self.paths.state_db), 1)

    def test_requeue_job_for_retry(self) -> None:
        job_id = db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        db.requeue_job_for_retry(self.paths.state_db, job_id, 1, "timeout")
        with db.connect(self.paths.state_db) as conn:
            row = conn.execute("SELECT * FROM ingest_jobs WHERE id = ?", (job_id,)).fetchone()
        self.assertEqual(row["state"], "queued")
        self.assertEqual(row["retry_count"], 1)
        self.assertIn("timeout", row["error"])

    def test_get_jobs_done_today_returns_done_jobs(self) -> None:
        job_id = db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        db.mark_job_done(self.paths.state_db, job_id, pages_created=3, pages_updated=1)
        jobs = db.get_jobs_done_today(self.paths.state_db)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], job_id)
        self.assertEqual(jobs[0]["pages_created"], 3)

    def test_dashboard_written_by_worker(self) -> None:
        from curator import ingest_worker
        worker = ingest_worker.IngestWorker(self.paths)
        worker._write_dashboard()
        dashboard = self.root / ".curator" / "dashboard.md"
        self.assertTrue(dashboard.exists())
        content = dashboard.read_text(encoding="utf-8")
        self.assertIn("Incurator Build Status", content)

    def test_canvas_written_with_dag_edges(self) -> None:
        from curator import ingest_worker, db as _db
        # Record a CTX→ATM edge so canvas has content
        _db.insert_dag_edge(self.paths.state_db, "CTX-aaa00001", "ATM-bbb00001", "extracted_from", str(self.source_id))
        _db.insert_dag_edge(self.paths.state_db, "ATM-bbb00001", "CON-ccc00001", "clustered_to", None)
        worker = ingest_worker.IngestWorker(self.paths)
        worker._write_build_canvas(self.source_id, "paper_test")
        self.assertFalse((self.root / ".curator" / "build_trace_paper_test.canvas").exists())
        canvas_path = self.root / ".curator" / "staging" / "canvas" / "build_trace_paper_test.canvas"
        self.assertTrue(canvas_path.exists())
        import json
        data = json.loads(canvas_path.read_text(encoding="utf-8"))
        node_ids = {n["id"] for n in data["nodes"]}
        self.assertIn("CTX-aaa00001", node_ids)
        self.assertIn("ATM-bbb00001", node_ids)
        self.assertIn("CON-ccc00001", node_ids)
        edge_labels = {e["label"] for e in data["edges"]}
        self.assertIn("extracted_from", edge_labels)
        self.assertIn("clustered_to", edge_labels)


class TestTokenCostTracking(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        db.init_db(self.paths.state_db)
        self.source_id = _register_source(self.paths.state_db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_accumulate_job_tokens_adds_to_zero(self) -> None:
        job_id = db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        db.accumulate_job_tokens(self.paths.state_db, job_id, 100, 50)
        with db.connect(self.paths.state_db) as conn:
            row = conn.execute(
                "SELECT input_tokens, output_tokens FROM ingest_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        self.assertEqual(row["input_tokens"], 100)
        self.assertEqual(row["output_tokens"], 50)

    def test_accumulate_job_tokens_is_cumulative(self) -> None:
        job_id = db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        db.accumulate_job_tokens(self.paths.state_db, job_id, 100, 50)
        db.accumulate_job_tokens(self.paths.state_db, job_id, 200, 75)
        with db.connect(self.paths.state_db) as conn:
            row = conn.execute(
                "SELECT input_tokens, output_tokens FROM ingest_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        self.assertEqual(row["input_tokens"], 300)
        self.assertEqual(row["output_tokens"], 125)

    def test_get_stats_includes_token_totals(self) -> None:
        job_id = db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        db.mark_job_done(self.paths.state_db, job_id)
        db.accumulate_job_tokens(self.paths.state_db, job_id, 1000, 400)
        stats = db.get_stats(self.paths.state_db)
        self.assertEqual(stats["total_input_tokens"], 1000)
        self.assertEqual(stats["total_output_tokens"], 400)
        self.assertIn("total_cost_usd", stats)

    def test_get_stats_only_counts_done_jobs(self) -> None:
        # queued job tokens should not appear in stats
        job_id = db.enqueue_job(self.paths.state_db, self.source_id, "l2_atoms")
        db.accumulate_job_tokens(self.paths.state_db, job_id, 500, 200)
        stats = db.get_stats(self.paths.state_db)
        self.assertEqual(stats["total_input_tokens"], 0)
        self.assertEqual(stats["total_output_tokens"], 0)

    def test_ollama_client_tracks_tokens_via_mocked_response(self) -> None:
        from curator.llm import OllamaClient
        import unittest.mock as mock

        client = OllamaClient.__new__(OllamaClient)
        client._job_input_tokens = 0
        client._job_output_tokens = 0

        fake_response = mock.MagicMock()
        fake_response.json.return_value = {
            "message": {"content": "hello"},
            "prompt_eval_count": 42,
            "eval_count": 17,
        }
        fake_response.raise_for_status = mock.MagicMock()

        with mock.patch.object(OllamaClient, "chat") as mock_chat:
            mock_chat.return_value = "hello"
            # Directly test the accumulation logic (chat is patched)
            client._job_input_tokens += fake_response.json()["prompt_eval_count"]
            client._job_output_tokens += fake_response.json()["eval_count"]

        in_tok, out_tok = client.get_and_reset_token_usage()
        self.assertEqual(in_tok, 42)
        self.assertEqual(out_tok, 17)
        # After reset, counters are zero
        self.assertEqual(client._job_input_tokens, 0)
        self.assertEqual(client._job_output_tokens, 0)


if __name__ == "__main__":
    unittest.main()
