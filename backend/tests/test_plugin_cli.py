import json
import re
from pathlib import Path

from typer.testing import CliRunner

from curator import config as cfg
from curator import db
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
    for name in ("plugin", "testbed", "devices", "mcp"):
        assert name not in help_result.output
    assert re.search(r"│\s+sources\s+", help_result.output) is None
    assert re.search(r"│\s+update\s+", help_result.output) is None
    assert re.search(r"│\s+refresh\s+", help_result.output) is not None
    assert re.search(r"│\s+curate\s+", help_result.output) is None
    assert re.search(r"│\s+source\s+", help_result.output) is not None

    for args in (
        ["plugin", "--help"],
        ["plugin", "version"],
        ["plugin", "source", "--help"],
        ["plugin", "pdf", "--help"],
        ["testbed", "--help"],
        ["devices", "--help"],
        ["mcp", "--help"],
        ["curate", "--help"],
        ["source", "--help"],
        ["refresh", "--help"],
    ):
        result = runner.invoke(app, args)
        assert result.exit_code == 0

    assert runner.invoke(app, ["sources", "--help"]).exit_code != 0
    assert runner.invoke(app, ["update", "--help"]).exit_code != 0


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


def test_plugin_query_returns_exhibition_identity(monkeypatch, tmp_path: Path) -> None:
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
            "exhibition_id": "EXH-1234abcd",
            "cache_hit": False,
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
    assert payload["exhibition_id"] == "EXH-1234abcd"
    assert payload["input_language"] == "English"
    assert payload["english_query"] == "What does this concept imply?"
    assert payload["final_output_language"] == "English"
    assert payload["trace"]["matched_concepts"] == ["CON-1234abcd"]


def test_devices_default_status_lists_syncthing_only_profiles(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = tmp_path / "vault"
    curator_dir = vault / ".curator"
    curator_dir.mkdir(parents=True)
    (curator_dir / "config.yml").write_text("version: 1\n", encoding="utf-8")
    (curator_dir / "devices.json").write_text(
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
