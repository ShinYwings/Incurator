"""The agy MCP wiring must fail loudly, not silently.

Four separate defects in this area reached a real session before anything
complained, and the last one surfaced as a *permission* error three steps removed
from its cause: the assistant had no vault-search tool, reached for a shell `rg`,
and `command(wiki)` correctly refused it.

`agy_mcp_registration_problem` exists so `wiki status` can say what is actually
wrong. These tests pin each way it can be wrong — a check that cannot detect the
failure it was written for is the recurring shape this repo keeps hitting.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from curator.commands.common import agy_mcp_registration_problem


@pytest.fixture()
def wired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A correctly registered vault: server present, command real, permission granted."""
    vault = tmp_path / "vault"
    vault.mkdir()
    wiki = tmp_path / "bin" / "wiki"
    wiki.parent.mkdir(parents=True)
    wiki.write_text("#!/bin/sh\n")
    gemini = Path.home() / ".gemini"
    (gemini / "config").mkdir(parents=True, exist_ok=True)
    (gemini / "config" / "mcp_config.json").write_text(
        json.dumps({"mcpServers": {"incurator": {
            "command": str(wiki), "args": ["mcp"],
            "env": {"VAULT_ROOT": str(vault)}}}})
    )
    (gemini / "antigravity-cli").mkdir(parents=True, exist_ok=True)
    (gemini / "antigravity-cli" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["read_file(*)", "command(wiki)", "mcp(*)"]}})
    )
    return vault


def _registry() -> Path:
    return Path.home() / ".gemini" / "config" / "mcp_config.json"


def test_a_correctly_wired_vault_reports_no_problem(wired: Path) -> None:
    assert agy_mcp_registration_problem(wired) == ""


def test_it_notices_the_server_missing_entirely(wired: Path) -> None:
    """The v0.73.2 failure: the plugin's wholesale write deleted the entry."""
    _registry().write_text(json.dumps({"mcpServers": {"something_else": {}}}))
    problem = agy_mcp_registration_problem(wired)
    assert "not registered" in problem
    assert "search this vault" in problem


def test_it_notices_a_registry_that_does_not_exist(wired: Path) -> None:
    _registry().unlink()
    assert "no MCP registry" in agy_mcp_registration_problem(wired)


def test_it_notices_a_command_that_cannot_start(wired: Path) -> None:
    """The v0.71.0 failure: a bare `wiki` that a spawned process cannot find, or
    an absolute path into a venv that has since been removed."""
    d = json.loads(_registry().read_text())
    d["mcpServers"]["incurator"]["command"] = "/nonexistent/bin/wiki"
    _registry().write_text(json.dumps(d))
    assert "does not exist" in agy_mcp_registration_problem(wired)


def test_it_notices_registration_against_a_different_vault(wired: Path) -> None:
    """The pytest-leak failure: VAULT_ROOT pointing at a deleted temp directory."""
    d = json.loads(_registry().read_text())
    d["mcpServers"]["incurator"]["env"]["VAULT_ROOT"] = "/tmp/some-other-vault"
    _registry().write_text(json.dumps(d))
    assert "not this vault" in agy_mcp_registration_problem(wired)


def test_it_notices_the_missing_wildcard_permission(wired: Path) -> None:
    """The other v0.71.0 failure: scoped `mcp(...)` rules grant nothing."""
    p = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
    p.write_text(json.dumps({"permissions": {"allow": [
        "read_file(*)", "command(wiki)", "mcp(incurator)"]}}))
    assert "mcp(*)" in agy_mcp_registration_problem(wired)


def test_a_malformed_registry_is_reported_not_swallowed(wired: Path) -> None:
    _registry().write_text("{ not json")
    assert "not readable as JSON" in agy_mcp_registration_problem(wired)
