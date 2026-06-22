"""Tests for the L1-ingest / L2-L3-build separation (v0.2.x refactor).

Covers the split of curator_ingest_source into:
  - curator_register_source  → instant L1, NO LLM client, optional background queue
  - curator_build_source     → L2/L3 (enqueue by default, wait=True runs sync)
  - curator_ingest_source    → deprecated alias

The register/enqueue paths must work with no LLM backend available, so these
tests patch llm.build_client to raise and assert L1 still succeeds.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class RegisterBuildSplitTests(unittest.TestCase):
    def setUp(self) -> None:
        from curator import config as cfg, db, ingest_raw

        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        from curator import constants as consts
        curator_dir = self.root / consts.INTERNAL_DIR
        curator_dir.mkdir(parents=True, exist_ok=True)
        (curator_dir / consts.SETTINGS_FILE).write_text("llm:\n  provider: ollama\n", encoding="utf-8")
        self.paths = cfg.WikiPaths(self.root)
        for d in self.paths.raw_dirs:
            d.mkdir(parents=True, exist_ok=True)
        db.init_db(self.paths.state_db)

        # Register a real source so the tools can resolve it.
        note = self.root / "04_Resources" / "doc.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text(
            "# Title\n\n## Section A\n\nEnough words here to register a usable source file.\n",
            encoding="utf-8",
        )
        outcome = ingest_raw.add_file(self.paths, note)
        self.source_id = int(outcome.source_id)
        self.note = note

        os.environ["VAULT_ROOT"] = str(self.root)

    def tearDown(self) -> None:
        os.environ.pop("VAULT_ROOT", None)
        self.tmp.cleanup()

    def _tools(self):
        from curator import mcp_server

        with patch("curator.ingest_worker.IngestWorker", autospec=True):
            server = mcp_server.build_server()
        return getattr(server._tool_manager, "_tools", {})

    def _queued_job_count(self) -> int:
        from curator import db

        with db.connect(self.paths.state_db) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM ingest_jobs WHERE state = 'queued'"
            ).fetchone()[0]

    # ── register: instant L1, no LLM ──────────────────────────────────────

    def test_register_generates_l1_without_llm(self) -> None:
        """curator_register_source must succeed even when no LLM can be built."""
        tools = self._tools()
        register = tools["curator_register_source"].fn
        with patch("curator.llm.build_client", side_effect=RuntimeError("no LLM")):
            result = register(source_id=self.source_id, build=False, workspace_path=str(self.root))
        self.assertTrue(result["ok"], result)
        self.assertTrue(str(result["context_id"]).startswith("CTX-"))
        # L1 context file actually written
        self.assertTrue((self.paths.contexts / f"{result['context_id']}.md").exists())
        # build=False ⇒ nothing queued
        self.assertFalse(result["l2_l3_queued"])
        self.assertEqual(self._queued_job_count(), 0)

    def test_register_with_build_enqueues_l2_l3(self) -> None:
        tools = self._tools()
        register = tools["curator_register_source"].fn
        with patch("curator.llm.build_client", side_effect=RuntimeError("no LLM")):
            result = register(source_id=self.source_id, build=True, workspace_path=str(self.root))
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["l2_l3_queued"])
        self.assertEqual(len(result["job_ids"]), 1)
        self.assertEqual(self._queued_job_count(), 1)

    # ── build: enqueue vs sync ────────────────────────────────────────────

    def test_build_enqueues_when_not_wait(self) -> None:
        tools = self._tools()
        register = tools["curator_register_source"].fn
        build = tools["curator_build_source"].fn
        register(source_id=self.source_id, build=False, workspace_path=str(self.root))
        result = build(source_id=self.source_id, wait=False, workspace_path=str(self.root))
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["queued"])
        self.assertEqual(self._queued_job_count(), 1)

    def test_build_requires_l1_first(self) -> None:
        tools = self._tools()
        build = tools["curator_build_source"].fn
        # No register call → no L1 context → build should refuse.
        result = build(source_id=self.source_id, wait=False, workspace_path=str(self.root))
        self.assertFalse(result["ok"])
        self.assertIn("L1", result["error"])

    # ── deprecated alias ──────────────────────────────────────────────────

    def test_ingest_alias_register_only(self) -> None:
        """curator_ingest_source(run_l2_l3=False) delegates to register, no LLM needed."""
        tools = self._tools()
        ingest = tools["curator_ingest_source"].fn
        with patch("curator.llm.build_client", side_effect=RuntimeError("no LLM")):
            result = ingest(source_id=self.source_id, run_l2_l3=False, workspace_path=str(self.root))
        self.assertTrue(result["ok"], result)
        self.assertTrue(str(result["context_id"]).startswith("CTX-"))


if __name__ == "__main__":
    unittest.main()
