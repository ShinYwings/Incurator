"""Hidden plugin commands for synthesis audit inspection."""

from __future__ import annotations

import json
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


def _seed_vault(root: Path) -> tuple[str, str]:
    paths = cfg.WikiPaths(root)
    cfg.save_config(paths, {})
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES ('04_Resources/r.md', 'h', 'md', 1, datetime('now'))"
        )
    span = db.upsert_source_span(
        paths.state_db,
        source_id=1,
        relpath="04_Resources/r.md",
        span_type="paragraph",
        content_hash="span-hash",
        text_preview="Evidence preview.",
    )
    report = db.upsert_community_report(
        paths.state_db,
        community_key="comm",
        title="Report",
        summary="summary",
        full_content="content",
        dependency_hash="dep",
        source_span_ids=[span],
        rank=0.5,
    )
    syn = db.upsert_synthesis_node(
        paths.state_db,
        title="Synthesis",
        statement="Statement",
        dependency_hash="syn-dep",
        community_report_ids=[report],
        source_span_ids=[span],
        confidence=0.75,
    )
    return syn, span


def test_plugin_synthesis_list_and_show(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = tmp_path / "vault"
    syn, span = _seed_vault(vault)

    listed = runner.invoke(
        app,
        ["plugin", "synthesis", "list", "--workspace-path", str(vault), "--limit", "5"],
        env={"HOME": str(tmp_path / "home")},
    )
    list_payload = _json_output(listed.output)

    assert listed.exit_code == 0
    assert list_payload["ok"] is True
    assert list_payload["synthesis"][0]["id"] == syn
    assert list_payload["synthesis"][0]["sourceSpanIds"] == [span]

    shown = runner.invoke(
        app,
        [
            "plugin",
            "synthesis",
            "show",
            "--synthesis-id",
            syn,
            "--workspace-path",
            str(vault),
        ],
        env={"HOME": str(tmp_path / "home")},
    )
    show_payload = _json_output(shown.output)

    assert shown.exit_code == 0
    assert show_payload["ok"] is True
    assert show_payload["audit"]["synthesis"]["id"] == syn
    assert show_payload["audit"]["source_spans"][0]["id"] == span


def test_public_inspect_synthesis_json(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = tmp_path / "vault"
    syn, span = _seed_vault(vault)

    result = runner.invoke(
        app,
        ["inspect", "synthesis", syn, "--json"],
        env={"HOME": str(tmp_path / "home"), "VAULT_ROOT": str(vault)},
    )
    payload = _json_output(result.output)

    assert result.exit_code == 0
    assert payload["ok"] is True
    assert payload["synthesis"]["id"] == syn
    assert payload["source_spans"][0]["id"] == span
