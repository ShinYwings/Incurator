"""Phase 8 (v0.3.1): MCP curation-native tools."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from curator import config as cfg
from curator import db, mcp_server
from curator.llm import ChatMessage

CURATE_YML = """\
project: "resnet-lab"
goal:
  primary: "Study residual learning."
  audience: "researcher"
reasoning:
  default_mode: "local"
  allowed_modes: ["local", "global", "explore"]
verification:
  min_confidence: 0.7
"""


class _FakeClient:
    model = "fake"

    def __init__(self, payload: str) -> None:
        self._payload = payload

    def chat(self, messages: list[ChatMessage], *, json_mode=False, temperature=0.3) -> str:
        return self._payload

    def close(self) -> None:
        ...


class V031McpToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        self.paths.internal.mkdir(parents=True, exist_ok=True)
        cfg.save_config(self.paths, cfg.DEFAULT_CONFIG)
        db.init_db(self.paths.state_db)
        self.ws = self.root / "01_Workspaces" / "Lab"
        self.ws.mkdir(parents=True, exist_ok=True)
        (self.ws / "curate.yml").write_text(CURATE_YML, encoding="utf-8")
        os.environ["VAULT_ROOT"] = str(self.root)
        os.environ["CURATOR_DISABLE_INGEST_WORKER"] = "1"

    def tearDown(self) -> None:
        os.environ.pop("VAULT_ROOT", None)
        os.environ.pop("CURATOR_DISABLE_INGEST_WORKER", None)
        self.tmp.cleanup()

    def _tool(self, name: str):
        server = mcp_server.build_server()
        return server._tool_manager._tools[name].fn

    def test_validate_curate_spec(self) -> None:
        out = self._tool("curator_validate_curate_spec")(workspace_path=str(self.ws))
        self.assertTrue(out["ok"])
        self.assertEqual(out["errors"], [])
        self.assertEqual(out["policy"]["default_route"], "local")
        self.assertIn("explore", out["policy"]["allowed_routes"])
        self.assertTrue(out["spec_hash"])

    def test_plan_workspace_records_plan(self) -> None:
        out = self._tool("curator_plan_workspace")(workspace_path=str(self.ws))
        self.assertTrue(out["ok"])
        self.assertEqual(out["workspace_id"], "Lab")
        plan = db.get_curation_plan(self.paths.state_db, "Lab")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["id"], out["plan_id"])

    def test_insight_list_and_promote(self) -> None:
        ins_id = db.create_insight_candidate(
            self.paths.state_db, classification="derived_insight",
            statement="Residual blocks resemble Euler steps.", workspace_id="Lab",
        )
        listed = self._tool("curator_list_insight_candidates")(workspace_path=str(self.ws))
        self.assertTrue(listed["ok"])
        self.assertEqual(len(listed["candidates"]), 1)

        promoted = self._tool("curator_promote_insight")(
            insight_id=ins_id, workspace_path=str(self.ws)
        )
        self.assertTrue(promoted["ok"])
        self.assertTrue(promoted["promoted_to"].startswith("02_Wiki/"))
        self.assertEqual(
            db.get_insight_candidate(self.paths.state_db, ins_id)["status"], "promoted"
        )

    def test_fetch_context_evidence_only(self) -> None:
        # Seed minimal graph so the evidence pack has content.
        with db.connect(self.paths.state_db) as conn:
            conn.execute("INSERT INTO sources (relpath,content_hash,file_type,bytes,added_at) "
                         "VALUES ('x.md','c1','md',1,datetime('now'))")
        sp = db.upsert_source_span(self.paths.state_db, source_id=1,
                                   relpath="x.md", span_type="paragraph",
                                   content_hash="c1", text_preview="residual learning")
        db.upsert_graph_entity(self.paths.state_db, canonical_name="residual learning",
                               entity_type="concept", source_span_ids=[sp])

        class NoChatClient:
            model = "fake"
            def chat(self, *a, **k):
                raise AssertionError("fetch_context must not synthesize")

        with patch("curator.llm.build_client", return_value=NoChatClient()):
            out = self._tool("curator_fetch_context")(query="residual learning", workspace_path=str(self.ws))
        self.assertTrue(out["ok"])
        self.assertNotIn("answer", out)
        self.assertTrue(out["trace_id"].startswith("QTR-"))

    def test_get_prompt_trace(self) -> None:
        trace_id = db.record_prompt_run(
            self.paths.state_db, prompt_id="curator.x", prompt_version="v1",
            family="f", input_hash="h",
        )
        out = self._tool("curator_get_prompt_trace")(trace_id=trace_id)
        self.assertTrue(out["ok"])
        self.assertEqual(out["trace"]["prompt_id"], "curator.x")

    def test_propose_correction_classifies_and_records(self) -> None:
        payload = json.dumps({
            "classification": "derived_insight", "confidence": 0.7,
            "affected_nodes": ["CON-1"], "source_truth_impact": "none",
            "recommended_action": "create_insight_candidate", "reason": "later interpretation",
        })
        with patch("curator.llm.build_client", return_value=_FakeClient(payload)):
            out = self._tool("curator_propose_correction")(
                node_id="CON-1", correction="ResNet ~ Euler discretization.",
                workspace_path=str(self.ws),
            )
        self.assertTrue(out["ok"])
        self.assertEqual(out["classification"], "derived_insight")
        self.assertEqual(out["recommended_action"], "create_insight_candidate")
        self.assertTrue(out["insight_candidate_id"])
        # candidate persisted; source truth untouched
        cands = db.list_insight_candidates(self.paths.state_db, status="pending")
        self.assertEqual(len(cands), 1)


if __name__ == "__main__":
    unittest.main()
