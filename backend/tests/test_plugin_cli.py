import json
import re
from pathlib import Path
from unittest.mock import patch

import click
from typer.testing import CliRunner

from curator import config as cfg
from curator import db
from curator import llm
from curator.cli import app


def _json_output(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    assert start >= 0 and end > start, text
    return json.loads(text[start : end + 1])


def test_plugin_zotero_namespace_is_hidden_but_callable(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = tmp_path / "vault"
    cfg.save_config(cfg.WikiPaths(vault), {"external": {"zotero": {"enabled": True, "roots": []}}})

    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    assert "plugin" not in help_result.output
    assert "zotero" not in help_result.output

    old_result = runner.invoke(app, ["zotero", "search", "--query", "x"])
    assert old_result.exit_code != 0

    status_result = runner.invoke(
        app,
        [
            "plugin",
            "zotero",
            "status",
            "--custom-paths",
            str(tmp_path),
            "--workspace-path",
            str(vault),
        ],
        env={"HOME": str(tmp_path / "home")},
    )
    status_payload = _json_output(status_result.output)
    assert status_result.exit_code == 0
    assert status_payload["state"] in {"db_missing", "not_configured"}

    result = runner.invoke(
        app,
        [
            "plugin",
            "zotero",
            "search",
            "--query",
            "x",
            "--custom-paths",
            str(tmp_path),
            "--workspace-path",
            str(vault),
        ],
        env={"HOME": str(tmp_path / "home")},
    )
    payload = _json_output(result.output)
    assert result.exit_code == 0
    assert "ok" in payload


def test_advanced_command_groups_are_hidden_but_callable() -> None:
    runner = CliRunner()

    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    clean_output = click.unstyle(help_result.output)
    # `jobs` is hidden in v0.3.2 (item 14): the canonical path is `wiki update`,
    # which drains the queue synchronously.
    for name in ("plugin", "testbed", "devices", "mcp", "jobs"):
        assert name not in clean_output
    assert re.search(r"│\s+sources\s+", clean_output) is None
    # `wiki update` is the visible one-shot ingest command (item 14).
    assert re.search(r"│\s+update\s+", clean_output) is not None
    # `curate` and `refresh` (frozen-Exhibition commands) were removed in v0.3.1.
    assert re.search(r"│\s+curate\s+", clean_output) is None
    assert re.search(r"│\s+refresh\s+", clean_output) is None
    assert re.search(r"│\s+source\s+", clean_output) is not None

    for args in (
        ["plugin", "--help"],
        ["plugin", "version"],
        ["plugin", "source", "--help"],
        ["plugin", "pdf", "--help"],
        ["testbed", "--help"],
        ["devices", "--help"],
        ["mcp", "--help"],
        ["source", "--help"],
    ):
        result = runner.invoke(app, args)
        assert result.exit_code == 0

    assert runner.invoke(app, ["sources", "--help"]).exit_code != 0
    # `update` is now a real command; `jobs` is hidden but still callable.
    assert runner.invoke(app, ["update", "--help"]).exit_code == 0
    assert runner.invoke(app, ["jobs", "--help"]).exit_code == 0


def test_plugin_version_returns_build_fields() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["plugin", "version"])
    payload = _json_output(result.output)

    assert result.exit_code == 0
    assert payload["ok"] is True
    assert payload["version"]
    assert payload["build"]["backend_version"]
    assert payload["build"]["plugin_version"]
    assert "git_commit" in payload["build"]
    assert "schema" in payload["build"]
    # repo_path key always present (string when editable install, null otherwise)
    assert "repo_path" in payload


def test_plugin_version_runs_without_a_vault(tmp_path: Path, monkeypatch) -> None:
    # `wiki plugin version` powers the update check and MUST NOT require a vault.
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["plugin", "version"])
    payload = _json_output(result.output)
    assert result.exit_code == 0
    assert payload["ok"] is True
    assert "repo_path" in payload


def test_git_like_source_aliases_are_callable() -> None:
    runner = CliRunner()

    assert runner.invoke(app, ["ls", "--help"]).exit_code != 0

    for args in (["source", "ls", "--help"], ["source", "list", "--help"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 0


def test_jobs_cancel_and_rerun_commands_mutate_queue(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    cfg.save_config(paths, {})
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        source_id = conn.execute(
            """
            INSERT INTO sources
                (relpath, content_hash, file_type, bytes, added_at,
                 l1_status, l2_status, l3_status)
            VALUES ('04_Resources/paper.md', 'abc123abc123abc1', 'md', 12,
                    datetime('now'), 'done', 'pending', 'pending')
            """
        ).lastrowid
    job_id = db.enqueue_job(paths.state_db, int(source_id), "l2_atoms")

    cancel = runner.invoke(app, ["jobs", "cancel", str(job_id)], env={"VAULT_ROOT": str(vault)})
    assert cancel.exit_code == 0
    with db.connect(paths.state_db) as conn:
        assert conn.execute("SELECT state FROM ingest_jobs WHERE id = ?", (job_id,)).fetchone()["state"] == "cancelled"

    rerun = runner.invoke(app, ["jobs", "rerun", str(job_id)], env={"VAULT_ROOT": str(vault)})
    assert rerun.exit_code == 0
    with db.connect(paths.state_db) as conn:
        assert conn.execute("SELECT state FROM ingest_jobs WHERE id = ?", (job_id,)).fetchone()["state"] == "queued"


def test_plugin_query_returns_sessionless_trace(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    vault = tmp_path / "vault"
    cfg.save_config(cfg.WikiPaths(vault), {})

    def fake_curator_query(  # noqa: ARG001
        paths,
        *,
        question: str,
        input_language: str = "",
        english_query: str = "",
        final_output_language: str = "",
        workspace_path: str = "",
        force_new: bool = False,
    ):
        return {
            "ok": True,
            "question": question,
            "input_language": input_language,
            "english_query": english_query,
            "final_output_language": final_output_language,
            "answer": "Grounded answer",
            "trace": {
                "matched_concepts": ["CON-1234abcd"],
                "source_ids": [],
                "source_paths": ["03_Concepts/CON-1234abcd.md"],
                "latency_ms": 5,
                "l3_complete": True,
            },
        }

    from curator import plugin_api

    monkeypatch.setattr(plugin_api, "curator_query", fake_curator_query)
    result = runner.invoke(
        app,
        [
            "plugin",
            "query",
            "--question",
            "What does this concept imply?",
            "--input-language",
            "English",
            "--english-query",
            "What does this concept imply?",
            "--final-output-language",
            "English",
            "--workspace-path",
            str(vault),
        ],
    )

    payload = _json_output(result.output)
    assert result.exit_code == 0
    removed_artifact_key = "exhibition" + "_id"
    removed_cache_key = "cache" + "_hit"
    assert removed_artifact_key not in payload
    assert removed_cache_key not in payload
    assert payload["input_language"] == "English"
    assert payload["english_query"] == "What does this concept imply?"
    assert payload["final_output_language"] == "English"


def test_plugin_query_returns_context_service_trace_fields(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    cfg.save_config(paths, {})
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath,content_hash,file_type,bytes,added_at) "
            "VALUES ('04_Resources/context.md','c1','md',1,datetime('now'))"
        )
    span = db.upsert_source_span(
        paths.state_db,
        source_id=1,
        relpath="04_Resources/context.md",
        span_type="paragraph",
        content_hash="c1",
        section_title="Context",
        text_preview="residual learning",
    )
    db.upsert_graph_entity(
        paths.state_db,
        canonical_name="residual learning",
        entity_type="concept",
        source_span_ids=[span],
    )
    paths.concepts.mkdir(parents=True, exist_ok=True)
    (paths.concepts / "CON-test.md").write_text(
        "---\nname: residual learning\n---\n",
        encoding="utf-8",
    )

    class AnswerClient:
        model = "fake"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def chat(self, *args, **kwargs):
            return json.dumps({
                "answer": "Residual learning eases optimization.",
                "source_span_ids": [span],
                "used_report_ids": [],
                "confidence": 0.8,
            })

    with patch.object(llm, "build_client", return_value=AnswerClient()):
        result = runner.invoke(
            app,
            [
                "plugin",
                "query",
                "--question",
                "What does residual learning do?",
                "--workspace-path",
                str(vault),
            ],
        )

    payload = _json_output(result.output)
    assert result.exit_code == 0
    assert payload["ok"] is True
    assert payload["answer"] == "Residual learning eases optimization."
    assert payload["route"] == "local"
    assert payload["trace_id"].startswith("QTR-")
    assert payload["pack_id"].startswith("PACK-")
    assert payload["snapshot"]["snapshot_id"].startswith("SNAP-")
    assert payload["budget"]["used_tokens"] <= payload["budget"]["limit_tokens"]
    assert payload["source_span_ids"] == [span]
    assert payload["prompt_trace_ids"]
    assert payload["pack_id"] == payload["trace"]["pack_id"]
    assert payload["snapshot"] == payload["trace"]["snapshot"]
    assert payload["budget"] == payload["trace"]["budget"]
    assert payload["prompt_trace_ids"] == payload["trace"]["prompt_trace_ids"]
    assert payload["trace"]["pack_id"].startswith("PACK-")
    assert payload["trace"]["snapshot"]["snapshot_id"].startswith("SNAP-")
    assert payload["trace"]["budget"]["used_tokens"] <= payload["trace"]["budget"]["limit_tokens"]
    assert payload["trace"]["source_span_ids"] == [span]
    assert payload["trace"]["prompt_trace_ids"]
    assert payload["trace"]["matched_concepts"] == []
    traces = db.list_query_traces(paths.state_db)
    assert len(traces) == 1
    trace = db.get_query_trace(paths.state_db, payload["trace_id"])
    assert trace is not None
    assert trace["retrieval_trace"]["context_service"]["pack_id"] == payload["pack_id"]


def test_plugin_context_fetch_returns_evidence_pack_without_answer(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    cfg.save_config(paths, {})
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath,content_hash,file_type,bytes,added_at) "
            "VALUES ('x.md','c1','md',1,datetime('now'))"
        )
    span = db.upsert_source_span(
        paths.state_db,
        source_id=1,
        relpath="x.md",
        span_type="paragraph",
        content_hash="c1",
        section_title="Context",
        text_preview="residual learning",
    )
    db.upsert_graph_entity(
        paths.state_db,
        canonical_name="residual learning",
        entity_type="concept",
        source_span_ids=[span],
    )

    class NoAnswerClient:
        model = "fake"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def chat(self, *args, **kwargs):
            raise AssertionError("plugin context fetch must not synthesize")

    with patch.object(llm, "build_client", return_value=NoAnswerClient()):
        result = runner.invoke(
            app,
            [
                "plugin",
                "context",
                "fetch",
                "--query",
                "What does residual learning do?",
                "--workspace-path",
                str(vault),
                "--limit-tokens",
                "512",
            ],
        )

    payload = _json_output(result.output)
    assert result.exit_code == 0
    assert payload["ok"] is True
    assert payload["operation"] == "context_fetch"
    assert "answer" not in payload
    assert payload["pack_id"].startswith("PACK-")
    assert payload["trace_id"].startswith("QTR-")
    assert payload["snapshot"]["snapshot_id"].startswith("SNAP-")
    assert payload["budget"]["limit_tokens"] == 512
    assert payload["items"]
    assert payload["evidence"]
    assert payload["source_span_ids"] == [span]


def test_plugin_context_expand_and_verify_use_existing_pack(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    cfg.save_config(paths, {})
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath,content_hash,file_type,bytes,added_at) "
            "VALUES ('x.md','c1','md',1,datetime('now'))"
        )
    span = db.upsert_source_span(
        paths.state_db,
        source_id=1,
        relpath="x.md",
        span_type="paragraph",
        content_hash="c1",
        section_title="Context",
        text_preview="Context budget evidence 1.",
    )
    for idx in range(1, 7):
        db.upsert_graph_entity(
            paths.state_db,
            canonical_name=f"context budget evidence {idx}",
            entity_type="concept",
            description="Compact grounded evidence for budget packing.",
            source_span_ids=[span],
        )

    fetch = runner.invoke(
        app,
        [
            "plugin",
            "context",
            "fetch",
            "--query",
            "context budget evidence",
            "--workspace-path",
            str(vault),
            "--limit-tokens",
            "20",
        ],
    )
    pack = _json_output(fetch.output)
    assert fetch.exit_code == 0
    assert pack["next"]

    expand = runner.invoke(
        app,
        [
            "plugin",
            "context",
            "expand",
            "--pack-id",
            pack["pack_id"],
            "--handle",
            pack["next"][0]["handle"],
            "--expected-snapshot-id",
            pack["snapshot"]["snapshot_id"],
            "--limit-tokens",
            "80",
            "--workspace-path",
            str(vault),
        ],
    )
    expanded = _json_output(expand.output)
    assert expand.exit_code == 0
    assert expanded["ok"] is True
    assert expanded["operation"] == "context_expand"
    assert expanded["root_pack_id"] == pack["pack_id"]
    assert expanded["items"]

    verify = runner.invoke(
        app,
        [
            "plugin",
            "context",
            "verify",
            "--pack-id",
            pack["pack_id"],
            "--verification-handle",
            expanded["items"][0]["verification_handle"],
            "--expected-snapshot-id",
            pack["snapshot"]["snapshot_id"],
            "--workspace-path",
            str(vault),
        ],
    )
    verified = _json_output(verify.output)
    assert verify.exit_code == 0
    assert verified["ok"] is True
    assert verified["operation"] == "context_verify"
    assert verified["item"]["record_id"] == expanded["items"][0]["record_id"]
    assert verified["locator"]

    feedback = runner.invoke(
        app,
        [
            "plugin",
            "context",
            "feedback",
            "--trace-id",
            pack["trace_id"],
            "--pack-id",
            pack["pack_id"],
            "--feedback-type",
            "incorrect",
            "--statement",
            "Cited span does not support the claim.",
            "--client",
            "obsidian",
            "--purpose",
            "ground",
            "--target-item-id",
            expanded["items"][0]["record_id"],
            "--reviewed-span-id",
            str(span),
            "--workspace-path",
            str(vault),
        ],
    )
    recorded = _json_output(feedback.output)
    assert feedback.exit_code == 0
    assert recorded["ok"] is True
    assert recorded["operation"] == "context_feedback"
    assert recorded["feedback_id"].startswith("FBK-")
    assert recorded["review_status"] == "pending"
    assert recorded["ranking_or_truth_mutated"] is False

    bad = runner.invoke(
        app,
        [
            "plugin",
            "context",
            "feedback",
            "--trace-id",
            pack["trace_id"],
            "--pack-id",
            pack["pack_id"],
            "--feedback-type",
            "not_a_type",
            "--statement",
            "x",
            "--workspace-path",
            str(vault),
        ],
    )
    rejected = _json_output(bad.output)
    assert rejected["ok"] is False
    assert rejected["error_type"] == "invalid_feedback_type"


def test_devices_default_status_lists_syncthing_only_profiles(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = tmp_path / "vault"
    curator_dir = vault / ".curator"
    curator_dir.mkdir(parents=True)
    (curator_dir / "settings.yml").write_text("version: 1\n", encoding="utf-8")
    
    from curator import device_registry
    registry_path = device_registry.registry_path(vault)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "version": 1,
                "devices": {
                    "MACOS-DEVICE": {"device_id": "MACOS-DEVICE", "name": "MacOS"},
                    "LINUX-DEVICE": {"device_id": "LINUX-DEVICE", "name": "shin"},
                },
                "syncthing": {},
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["devices"], env={"VAULT_ROOT": str(vault)})

    assert result.exit_code == 0
    assert "Synced Devices" in result.output
    assert "MacOS" in result.output
    assert "shin" in result.output
