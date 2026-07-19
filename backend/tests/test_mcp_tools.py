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

    def test_invalid_plan_workspace_does_not_persist(self) -> None:
        (self.ws / "curate.yml").write_text(
            'project: "bad"\nreasoning:\n  allowed_modes: [bogus]\n',
            encoding="utf-8",
        )
        with db.connect(self.paths.state_db) as conn:
            before = conn.execute("SELECT COUNT(*) FROM curation_plans").fetchone()[0]

        out = self._tool("curator_plan_workspace")(workspace_path=str(self.ws))

        self.assertFalse(out["ok"])
        self.assertIn("allowed_modes", out["error"])
        with db.connect(self.paths.state_db) as conn:
            after = conn.execute("SELECT COUNT(*) FROM curation_plans").fetchone()[0]
        self.assertEqual(after, before)

    def test_validation_only_never_persists_invalid_plan(self) -> None:
        (self.ws / "curate.yml").write_text(
            'project: "bad"\nreasoning:\n  allowed_modes: [bogus]\n',
            encoding="utf-8",
        )

        out = self._tool("curator_validate_curate_spec")(
            workspace_path=str(self.ws)
        )

        self.assertFalse(out["ok"])
        with db.connect(self.paths.state_db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM curation_plans").fetchone()[0]
        self.assertEqual(count, 0)

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
        self.assertEqual(out["operation"], "context_fetch")
        self.assertEqual(out["contract_version"], "1")
        self.assertTrue(out["pack_id"].startswith("PACK-"))
        self.assertTrue(out["trace_id"].startswith("QTR-"))
        self.assertTrue(out["retrieval_execution_id"].startswith("RTR-"))
        self.assertTrue(out["snapshot"]["snapshot_id"].startswith("SNAP-"))
        self.assertLessEqual(out["budget"]["used_tokens"], out["budget"]["limit_tokens"])
        self.assertTrue(out["items"])
        self.assertTrue(out["items"][0]["expansion_handle"].startswith("EXP-"))
        self.assertTrue(out["items"][0]["verification_handle"].startswith("VER-"))

        trace = db.get_query_trace(self.paths.state_db, out["trace_id"])
        self.assertIsNotNone(trace)
        context_trace = trace["retrieval_trace"]["context_service"]
        self.assertEqual(context_trace["pack_id"], out["pack_id"])
        self.assertEqual(
            context_trace["snapshot"]["snapshot_id"],
            out["snapshot"]["snapshot_id"],
        )

    def test_curator_query_uses_context_service_trace_additively(self) -> None:
        with db.connect(self.paths.state_db) as conn:
            conn.execute(
                "INSERT INTO sources (relpath,content_hash,file_type,bytes,added_at) "
                "VALUES ('x.md','c1','md',1,datetime('now'))"
            )
        sp = db.upsert_source_span(
            self.paths.state_db,
            source_id=1,
            relpath="x.md",
            span_type="paragraph",
            content_hash="c1",
            section_title="Context",
            text_preview="residual learning",
        )
        db.upsert_graph_entity(
            self.paths.state_db,
            canonical_name="residual learning",
            entity_type="concept",
            source_span_ids=[sp],
        )
        con_dir = self.paths.collections / "03_Concepts"
        con_dir.mkdir(parents=True, exist_ok=True)
        (con_dir / "CON-test.md").write_text("---\nname: residual learning\n---\n", encoding="utf-8")

        class AnswerClient:
            model = "fake"

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def chat(self, *args, **kwargs):
                return json.dumps({
                    "answer": "Residual learning eases optimization.",
                    "source_span_ids": [sp],
                    "used_report_ids": [],
                    "confidence": 0.8,
                })

        with patch("curator.llm.build_client", return_value=AnswerClient()):
            out = self._tool("curator_query")(
                question="What does residual learning do?",
                workspace_path=str(self.ws),
            )

        self.assertTrue(out["ok"])
        self.assertEqual(out["answer"], "Residual learning eases optimization.")
        self.assertTrue(out["trace"]["trace_id"].startswith("QTR-"))
        self.assertTrue(out["trace"]["pack_id"].startswith("PACK-"))
        self.assertTrue(out["trace"]["snapshot"]["snapshot_id"].startswith("SNAP-"))
        self.assertLessEqual(out["trace"]["budget"]["used_tokens"], out["trace"]["budget"]["limit_tokens"])
        self.assertEqual(out["trace"]["source_span_ids"], [sp])
        trace = db.get_query_trace(self.paths.state_db, out["trace"]["trace_id"])
        self.assertIsNotNone(trace)
        context_trace = trace["retrieval_trace"]["context_service"]
        self.assertEqual(context_trace["pack_id"], out["trace"]["pack_id"])
        self.assertTrue(any(
            action["action_type"] == "synthesis"
            and action["child_id"] in trace["prompt_trace_ids"]
            for action in context_trace["actions"]
        ))

    def test_curator_query_explore_grounds_on_unified_context_pack(self) -> None:
        with db.connect(self.paths.state_db) as conn:
            conn.execute(
                "INSERT INTO sources (relpath,content_hash,file_type,bytes,added_at) "
                "VALUES ('x.md','c1','md',1,datetime('now'))"
            )
        sp = db.upsert_source_span(
            self.paths.state_db,
            source_id=1,
            relpath="x.md",
            span_type="paragraph",
            content_hash="c1",
            section_title="Context",
            text_preview="residual learning",
        )
        left = db.upsert_graph_entity(
            self.paths.state_db,
            canonical_name="residual learning",
            entity_type="concept",
            source_span_ids=[sp],
        )
        right = db.upsert_graph_entity(
            self.paths.state_db,
            canonical_name="Euler discretization",
            entity_type="concept",
            source_span_ids=[sp],
        )
        db.upsert_graph_relation(
            self.paths.state_db,
            source_entity_id=left,
            target_entity_id=right,
            relation_type="reinterpreted_as",
            confidence=0.8,
            source_span_ids=[sp],
            assertion_source="system_infers",
        )
        con_dir = self.paths.collections / "03_Concepts"
        con_dir.mkdir(parents=True, exist_ok=True)
        (con_dir / "CON-test.md").write_text("---\nname: residual learning\n---\n", encoding="utf-8")

        class ExploreClient:
            model = "fake"

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def chat(self, *args, **kwargs):
                return json.dumps({
                    "followup_questions": ["How does residual learning connect to ODEs?"],
                    "insight_candidates": [
                        {
                            "statement": "Residual blocks resemble Euler steps.",
                            "rationale": "The relation links residual learning and discretization.",
                            "source_span_ids": [sp],
                            "confidence": 0.8,
                            "needs_human_review": True,
                        }
                    ],
                })

        with patch("curator.llm.build_client", return_value=ExploreClient()):
            out = self._tool("curator_query")(
                question="what else connects residual learning?",
                workspace_path=str(self.ws),
            )

        self.assertTrue(out["ok"])
        self.assertEqual(out["trace"]["route"], "explore")
        # §31.8 unification: explore now grounds on the shared ContextService pack,
        # so it carries the same PACK-*/SNAP-*/budget metadata as the other routes.
        self.assertTrue(str(out["trace"]["pack_id"]).startswith("PACK-"))
        self.assertIsNotNone(out["trace"]["snapshot"])
        self.assertIsNotNone(out["trace"]["budget"])
        trace = db.get_query_trace(self.paths.state_db, out["trace"]["trace_id"])
        self.assertIsNotNone(trace)
        self.assertIn("context_service", trace["retrieval_trace"])
        explore_actions = [
            a for a in trace["retrieval_trace"]["context_service"]["actions"]
            if a["action_type"] == "explore"
        ]
        self.assertEqual(len(explore_actions), 1)

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
