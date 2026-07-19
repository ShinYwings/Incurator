"""Phase 8 (v0.3.1): CLI prompt + insight commands."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from curator import config as cfg
from curator import db
from curator.cli import app


class V031CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        self.paths.internal.mkdir(parents=True, exist_ok=True)
        cfg.save_config(self.paths, cfg.DEFAULT_CONFIG)
        db.init_db(self.paths.state_db)
        os.environ["VAULT_ROOT"] = str(self.root)

    def tearDown(self) -> None:
        os.environ.pop("VAULT_ROOT", None)
        self.tmp.cleanup()

    def test_prompt_list(self) -> None:
        res = self.runner.invoke(app, ["prompt", "list"])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("curator.knowledge_unit_extract", res.stdout)

    def test_prompt_list_family_filter(self) -> None:
        res = self.runner.invoke(app, ["prompt", "list", "--family", "query"])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("curator.query_router", res.stdout)
        self.assertNotIn("curator.source_map", res.stdout)

    def test_prompt_eval(self) -> None:
        res = self.runner.invoke(app, ["prompt", "eval"])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("eval fixtures passed", res.stdout)

    def test_prompt_show_unknown_exits_nonzero(self) -> None:
        res = self.runner.invoke(app, ["prompt", "show", "curator.nope"])
        self.assertEqual(res.exit_code, 1)

    def test_prompt_trace_roundtrip(self) -> None:
        tid = db.record_prompt_run(
            self.paths.state_db, prompt_id="curator.x", prompt_version="v1",
            family="f", input_hash="h",
        )
        res = self.runner.invoke(app, ["prompt", "trace", tid])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("curator.x", res.stdout)

    def test_plugin_curate_plan_json(self) -> None:
        ws = self.root / "01_Workspaces" / "Lab"
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "curate.yml").write_text(
            'project: "lab"\nreasoning:\n  default_mode: "local"\n  allowed_modes: ["local","global"]\n',
            encoding="utf-8",
        )
        res = self.runner.invoke(app, ["plugin", "curate", "plan", "--workspace-path", str(ws)])
        self.assertEqual(res.exit_code, 0)
        import json
        payload = json.loads(res.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["route"], "local")
        self.assertTrue(payload["planId"].startswith("PLAN-"))

    def test_plugin_invalid_curate_plan_exits_nonzero_without_persisting(self) -> None:
        import json

        ws = self.root / "01_Workspaces" / "InvalidLab"
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "curate.yml").write_text(
            'project: "invalid"\nreasoning:\n  allowed_modes: [bogus]\n',
            encoding="utf-8",
        )

        res = self.runner.invoke(
            app, ["plugin", "curate", "plan", "--workspace-path", str(ws)]
        )

        self.assertEqual(res.exit_code, 1)
        payload = json.loads(res.stdout)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["validationErrors"])
        with db.connect(self.paths.state_db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM curation_plans").fetchone()[0]
        self.assertEqual(count, 0)

    def test_plugin_insight_list_and_promote_json(self) -> None:
        import json
        ins = db.create_insight_candidate(
            self.paths.state_db, classification="derived_insight",
            statement="X relates to Y.", workspace_id="Lab",
        )
        res = self.runner.invoke(app, ["plugin", "insight", "list", "--workspace-path", str(self.root / "01_Workspaces" / "Lab")])
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(json.loads(res.stdout)["candidates"][0]["id"], ins)
        res = self.runner.invoke(app, ["plugin", "insight", "promote", "--insight-id", ins])
        self.assertEqual(res.exit_code, 0)
        self.assertTrue(json.loads(res.stdout)["promotedTo"].startswith("02_Wiki/"))

    def test_plugin_prompt_trace_json(self) -> None:
        import json
        tid = db.record_prompt_run(
            self.paths.state_db, prompt_id="curator.y", prompt_version="v1",
            family="f", input_hash="h",
        )
        res = self.runner.invoke(app, ["plugin", "prompt", "trace", "--trace-id", tid])
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(json.loads(res.stdout)["promptId"], "curator.y")

    def test_insight_list_and_promote(self) -> None:
        ins = db.create_insight_candidate(
            self.paths.state_db, classification="derived_insight",
            statement="Residual blocks ~ Euler steps.", workspace_id="Lab",
        )
        res = self.runner.invoke(app, ["insight", "list", "--status", "pending"])
        self.assertEqual(res.exit_code, 0)
        self.assertIn(ins, res.stdout)

        res = self.runner.invoke(app, ["insight", "promote", ins])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("02_Wiki/", res.stdout)
        self.assertEqual(
            db.get_insight_candidate(self.paths.state_db, ins)["status"], "promoted"
        )


if __name__ == "__main__":
    unittest.main()
