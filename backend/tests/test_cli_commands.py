"""Phase 8 (v0.3.1): CLI prompt + insight commands."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from curator import config as cfg
from curator import db
from curator.cli import app
from curator.query import QueryResult


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

    def test_query_forwards_selected_workspace_to_orchestrator(self) -> None:
        ws = self.root / "01_Workspaces" / "ScopedLab"
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "curate.yml").write_text('project: "scoped"\n', encoding="utf-8")
        self.paths.concepts.mkdir(parents=True, exist_ok=True)
        (self.paths.concepts / "CON-test.md").write_text("---\nname: test\n---\n")
        captured: dict = {}

        class FakeClient:
            def close(self) -> None:
                pass

        def capture_repl(paths, client, callbacks, run_kwargs, **kwargs):
            captured.update(run_kwargs)

        with (
            patch("curator.commands.core._start_client", return_value=FakeClient()),
            patch("curator.commands.core._run_query_repl", side_effect=capture_repl),
        ):
            res = self.runner.invoke(
                app, ["query", "scoped question", "--workspace", str(ws)]
            )

        self.assertEqual(res.exit_code, 0, res.stdout)
        self.assertEqual(captured["workspace_path"], str(ws.resolve()))

    def test_query_invalid_workspace_policy_fails_concisely(self) -> None:
        ws = self.root / "01_Workspaces" / "InvalidQueryLab"
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "curate.yml").write_text(
            'project: "invalid"\nsources:\n  include: "   "\n',
            encoding="utf-8",
        )
        self.paths.concepts.mkdir(parents=True, exist_ok=True)
        (self.paths.concepts / "CON-test.md").write_text("---\nname: test\n---\n")

        with (
            patch("curator.commands.core._start_client") as start_client,
            patch("curator.commands.core._run_query_repl") as run_repl,
        ):
            res = self.runner.invoke(
                app, ["query", "scoped question", "--workspace", str(ws)]
            )

        self.assertEqual(res.exit_code, 1)
        self.assertIn("Query configuration failed", res.stdout)
        self.assertNotIn("Traceback", res.stdout)
        start_client.assert_not_called()
        run_repl.assert_not_called()

    def test_query_does_not_process_pending_sources(self) -> None:
        self.paths.concepts.mkdir(parents=True, exist_ok=True)
        (self.paths.concepts / "CON-test.md").write_text("---\nname: test\n---\n")

        class FakeClient:
            def close(self) -> None:
                pass

        with (
            patch("curator.commands.core.db.get_pending_count", return_value=3),
            patch("curator.commands.core.add") as add_command,
            patch("curator.commands.core._start_client", return_value=FakeClient()),
            patch("curator.commands.core._run_query_repl", return_value=False),
        ):
            res = self.runner.invoke(app, ["query", "read only question"])

        self.assertEqual(res.exit_code, 0, res.stdout)
        add_command.assert_not_called()
        self.assertNotIn("running add before query", res.stdout)

    def test_query_prints_non_streaming_answer(self) -> None:
        self.paths.concepts.mkdir(parents=True, exist_ok=True)
        (self.paths.concepts / "CON-test.md").write_text("---\nname: test\n---\n")

        class FakeClient:
            def close(self) -> None:
                return None

        def complete_query(paths, client, callbacks, run_kwargs, **kwargs):
            callbacks.on_complete(
                QueryResult(
                    question="visible question",
                    answer="Visible synthesized answer.",
                )
            )
            return False

        with (
            patch("curator.commands.core._start_client", return_value=FakeClient()),
            patch(
                "curator.commands.core._run_query_repl",
                side_effect=complete_query,
            ),
        ):
            res = self.runner.invoke(app, ["query", "visible question"])

        self.assertEqual(res.exit_code, 0, res.stdout)
        self.assertIn("Visible synthesized answer.", res.stdout)

    def test_query_failure_exits_one_after_cleanup_without_traceback(self) -> None:
        self.paths.concepts.mkdir(parents=True, exist_ok=True)
        (self.paths.concepts / "CON-test.md").write_text("---\nname: test\n---\n")
        closed = False

        class FakeClient:
            def close(self) -> None:
                nonlocal closed
                closed = True

        def fail_query(paths, client, callbacks, run_kwargs, **kwargs):
            callbacks.on_error("Antigravity CLI returned no output.")
            return True

        with (
            patch("curator.commands.core._start_client", return_value=FakeClient()),
            patch(
                "curator.commands.core._run_query_repl",
                side_effect=fail_query,
            ),
        ):
            res = self.runner.invoke(app, ["query", "failing question"])

        self.assertEqual(res.exit_code, 1, res.stdout)
        self.assertTrue(closed)
        self.assertIn("Antigravity CLI returned no output.", res.stdout)
        self.assertNotIn("Traceback", res.stdout)

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
