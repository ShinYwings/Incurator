"""Characterization tests for CM-1 command-surface decomposition.

These tests lock the transport surfaces before splitting `cli.py`,
`mcp_server.py`, and `plugin_api.py` into packages. They intentionally assert
existing names and import paths rather than new behavior.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import click
import typer
from typer.testing import CliRunner

from curator import config as cfg
from curator import db, plugin_api
from curator.cli import (
    _filter_sync_structural_issues,
    _maybe_auto_export,
    _parse_persona_done_response,
    _run_curator_persona_wizard,
    app,
)
from curator.mcp_server import build_server


def _click_root() -> click.Command:
    command = typer.main.get_command(app)
    assert hasattr(command, "commands")
    return command


def _command_names(command: click.Command) -> list[str]:
    commands = getattr(command, "commands", None)
    if isinstance(commands, dict):
        return sorted(commands)
    return []


def _json_output(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    assert start >= 0 and end > start, text
    return json.loads(text[start : end + 1])


def _mcp_tools() -> dict:
    server = build_server()
    tools = getattr(server._tool_manager, "_tools", {})
    assert isinstance(tools, dict)
    return tools


def test_cli_root_command_tree_is_stable() -> None:
    root = _click_root()

    assert _command_names(root) == [
        "add",
        "build",
        "config",
        "db",
        "devices",
        # v0.70.0. This list is a refactor-safety snapshot, not a frozen command
        # set -- the module docstring says it locks the surface before splitting
        # cli.py, "rather than new behavior". A genuinely new command belongs
        # here; the test's job is to make adding one deliberate, which it did.
        "gc",
        "init",
        "insight",
        "inspect",
        "jobs",
        "lint",
        "mcp",
        "migrate",
        "models",
        "persona",
        "plugin",
        "prompt",
        "query",
        "reindex",
        "reset",
        "source",
        "status",
        "sync",
        "testbed",
        "update",
        "version",
        "workspace",
    ]

    hidden_groups = {
        name for name, command in root.commands.items()
        if bool(getattr(command, "hidden", False))
    }
    assert hidden_groups == {"devices", "jobs", "mcp", "models", "plugin", "testbed"}

    assert _command_names(root.commands["source"]) == [
        # `dedupe-paths` (v0.78.0) merges sources whose paths differ only by
        # Unicode normalisation form. It reports by default and writes only under
        # `--apply`, because merging two sources rewrites the user's data.
        "clear-graph-cache", "dedupe-paths", "list", "ls", "retry", "rm", "show",
    ]
    assert _command_names(root.commands["db"]) == ["autosync", "export", "import"]
    assert _command_names(root.commands["mcp"]) == ["connect", "install"]
    assert _command_names(root.commands["config"]) == ["get", "models", "provider", "secret", "set"]
    assert _command_names(root.commands["plugin"]) == [
        "context",
        "correction",
        "curate",
        "git",
        "insight",
        "models",
        "pdf",
        "promote",
        "prompt",
        "query",
        # v0.62.4: the plugin can persist its provider key outside data.json.
        # Its key and the backend's are configured separately on purpose, so this
        # stores under its own name and shares only the encryption.
        "secret",
        "source",
        "synthesis",
        "trace",
        "version",
        "zotero",
    ]


def test_cli_help_and_hidden_commands_are_stable() -> None:
    runner = CliRunner()

    root_help = runner.invoke(app, ["--help"])
    assert root_help.exit_code == 0
    clean_root = click.unstyle(root_help.output)
    assert "plugin" not in clean_root
    assert "mcp" not in clean_root
    assert "jobs" not in clean_root
    assert "update" in clean_root
    assert "source" in clean_root

    for args, expected in (
        (["db", "autosync", "--help"], "autosync"),
        (["plugin", "source", "register", "--help"], "register"),
        (["mcp", "install", "--help"], "install"),
    ):
        result = runner.invoke(app, args)
        assert result.exit_code == 0
        assert expected in click.unstyle(result.output)


def test_cli_compatibility_imports_remain_available() -> None:
    assert callable(_maybe_auto_export)
    assert callable(_filter_sync_structural_issues)
    assert callable(_parse_persona_done_response)
    assert callable(_run_curator_persona_wizard)


def test_mcp_tool_names_and_representative_signatures_are_stable() -> None:
    tools = _mcp_tools()
    assert sorted(tools) == [
        "check_ingest_status",
        "check_source_status",
        "curator_add_all",
        "curator_add_knowledge",
        "curator_build_all",
        "curator_build_source",
        "curator_check_workspace",
        "curator_dismiss_contradiction",
        "curator_explore",
        "curator_fetch_context",
        "curator_find_contradictions",
        "curator_get_node",
        "curator_get_pdf_context",
        "curator_get_pdf_toc",
        "curator_get_prompt_trace",
        "curator_get_provenance",
        "curator_get_provider_config",
        "curator_get_version",
        "curator_get_zotero_annotations",
        "curator_get_zotero_item_metadata",
        "curator_import_source",
        "curator_ingest_source",
        "curator_layer_index",
        "curator_lint",
        "curator_list_external_resources",
        "curator_list_insight_candidates",
        "curator_plan_workspace",
        "curator_promote_insight",
        "curator_propose_correction",
        "curator_query",
        "curator_rebind_source",
        "curator_register_source",
        "curator_reindex",
        "curator_resolve_contradiction",
        "curator_resolve_zotero_pdf",
        "curator_search_sources",
        "curator_search_zotero_items",
        "curator_set_provider_config",
        "curator_status",
        "curator_sync",
        "curator_traverse_evidence",
        "curator_update_artist_persona",
        "curator_update_curator_persona",
        "curator_update_node",
        "curator_validate_curate_spec",
        "curator_workspace_init",
        "fetch_document_section",
        "get_available_models",
        "promote_answer",
        "search_curator",
    ]

    expected = {
        "curator_register_source": [
            "source_id",
            "relpath",
            "source_path",
            "file_path",
            "path",
            "force",
            "build",
            "workspace_path",
        ],
        "curator_query": ["question", "workspace_path", "force_new"],
        "curator_get_pdf_context": [
            "file_path",
            "query",
            "page_num",
            "radius",
            "max_pages",
            "workspace_path",
        ],
        "check_source_status": [
            "file_hash",
            "source_id",
            "relpath",
            "source_path",
            "file_path",
            "path",
            "status_filter",
            "limit",
            "workspace_path",
        ],
    }
    for name, parameters in expected.items():
        signature = inspect.signature(tools[name].fn)
        assert list(signature.parameters) == parameters


def test_mcp_provider_config_loads_the_packaged_model_catalogue(
    tmp_path: Path, monkeypatch
) -> None:
    curator_dir = tmp_path / ".curator"
    curator_dir.mkdir()
    (curator_dir / "settings.yml").write_text(
        "llm:\n  primary: antigravity-cli::gemini-3.5-flash\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
    monkeypatch.setenv("CURATOR_DISABLE_INGEST_WORKER", "1")

    result = _mcp_tools()["curator_get_provider_config"].fn(
        workspace_path=str(tmp_path)
    )

    assert result["ok"] is True
    assert result["models_json"]["schema_version"] >= 1
    assert "antigravity" in result["models_json"]["providers"]


def test_plugin_api_exports_and_validation_envelopes_are_stable(tmp_path: Path) -> None:
    expected_exports = [
        "_parse_pdf_pages_cached",
        "_safe_pdf_page_cache_key",
        "curator_query",
        "durable_l1_section",
        "expand_context",
        "feedback_context",
        "fetch_context",
        "import_source",
        "pdf_context",
        "promote_answer",
        "rebind_source",
        "register_source",
        "search_sources",
        "source_dict",
        "source_row",
        "source_status",
        "verify_context",
    ]
    for name in expected_exports:
        assert hasattr(plugin_api, name), name

    paths = cfg.WikiPaths(tmp_path / "vault")
    cfg.save_config(paths, {})
    db.init_db(paths.state_db)

    assert plugin_api.source_status(paths, file_hash="missing") == {
        "registered": False,
        "source_id": None,
        "l1_complete": False,
        "l2_complete": False,
        "l3_complete": False,
        "l4_complete": False,
        "jobs_pending": [],
    }
    assert plugin_api.fetch_context(paths, query_text="") == {
        "ok": False,
        "operation": "context_fetch",
        "error": "query is required",
    }
    assert plugin_api.expand_context(
        paths,
        pack_id="",
        handles=[],
        expected_snapshot_id="",
    ) == {
        "ok": False,
        "operation": "context_expand",
        "error": "pack_id is required",
    }
    assert plugin_api.promote_answer(paths, question="", answer="") == {
        "ok": False,
        "error": "question and answer are required",
    }


def test_plugin_version_json_command_stays_vault_independent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["plugin", "version"])
    payload = _json_output(result.output)

    assert result.exit_code == 0
    assert payload["ok"] is True
    assert "version" in payload
    assert "build" in payload
    assert "repo_path" in payload


def test_wiki_query_cannot_write_to_the_dag() -> None:
    """`wiki query` is read-only: no flag turns an answer into an L2 Atom.

    `--update` called `add_atom_from_insight`, which wrote an ATM markdown file
    straight into the derived `Collections/` projection with no `knowledge_units`
    row behind it — an orphan the DB never knew about and any re-projection
    would drop. It also contradicted SYSTEM_BEHAVIOR §22.2, which requires
    backprop to be correction-driven and independent of query artifacts.
    Corrections go through the insight lifecycle (`wiki insight`) instead.
    """
    runner = CliRunner()

    result = runner.invoke(app, ["query", "--help"])
    assert result.exit_code == 0
    help_text = click.unstyle(result.output)
    assert "--update" not in help_text

    rejected = runner.invoke(app, ["query", "anything", "--update"])
    assert rejected.exit_code != 0

    from curator.commands import common as common_module

    assert "update_knowledge" not in inspect.signature(
        common_module._run_query_repl
    ).parameters
