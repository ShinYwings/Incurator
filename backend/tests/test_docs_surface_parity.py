"""G18 docs/code parity guards for public tool and plugin settings surfaces."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


def _plugin_settings_keys() -> list[str]:
    source = _read("plugin/src/types.ts")
    match = re.search(r"export interface PluginSettings\s*\{(?P<body>.*?)\n\}", source, re.S)
    assert match, "PluginSettings interface not found in plugin/src/types.ts"

    keys: list[str] = []
    for line in match.group("body").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("*"):
            continue
        key_match = re.match(r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)\??\s*:", stripped)
        if key_match:
            keys.append(key_match.group("key"))
    return keys


def _mcp_tool_names() -> list[str]:
    source = _read("backend/src/curator/mcp_server.py")
    names = re.findall(r"@mcp\.tool\(\)\s*\n\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)", source)
    names.extend(re.findall(r"mcp\.tool\(\)\(([A-Za-z_][A-Za-z0-9_]*)\)", source))
    return sorted(set(names))


def test_plugin_settings_keys_are_documented_in_plugin_schema() -> None:
    schema = _read("docs/specs/plugin_schema/PLUGIN_SCHEMA.md")
    missing = [key for key in _plugin_settings_keys() if key not in schema]
    assert not missing, f"PluginSettings keys missing from PLUGIN_SCHEMA.md: {missing}"


def test_mcp_tools_are_documented_in_english_and_korean_guides() -> None:
    english = _read("docs/guides/MCP_USER_GUIDE.md")
    korean = _read("docs/guides/MCP_USER_GUIDE_KR.md")
    names = _mcp_tool_names()

    missing_english = [name for name in names if name not in english]
    missing_korean = [name for name in names if name not in korean]

    assert not missing_english, f"MCP tools missing from MCP_USER_GUIDE.md: {missing_english}"
    assert not missing_korean, f"MCP tools missing from MCP_USER_GUIDE_KR.md: {missing_korean}"


def test_failure_atlas_directory_has_role_index() -> None:
    index = REPO_ROOT / "docs/specs/failure_atlas/README.md"
    assert index.exists(), "failure_atlas needs a README explaining specs vs frozen test oracles"

    text = index.read_text(encoding="utf-8")
    for required in [
        "FAILURE_ATLAS.md",
        "EVALUATION_BASELINE.md",
        "PROGRAM_HANDOFFS.md",
        "D2_HOLDOUT_RESULT.yml",
        "fixture_corpus.yml",
        "qrels.yml",
        "support_labels.yml",
        "plan_b_compiler_gold.yml",
        "cases/F*.yml",
        "frozen",
        "test",
    ]:
        assert required in text, f"failure_atlas README must document {required}"


def test_curate_yml_reference_is_single_sourced_from_user_guide() -> None:
    user_guide = _read("docs/guides/USER_GUIDE.md")
    user_guide_kr = _read("docs/guides/USER_GUIDE_KR.md")
    workflow = _read("docs/guides/WORKFLOW_GUIDE.md")
    workflow_kr = _read("docs/guides/WORKFLOW_GUIDE_KR.md")

    for required in [
        "goal:",
        "sources:",
        "knowledge:",
        "output:",
        "reasoning:",
        "verification:",
        "backprop:",
        "prompts:",
    ]:
        assert required in user_guide, f"USER_GUIDE curate.yml reference missing {required}"
        assert required in user_guide_kr, f"USER_GUIDE_KR curate.yml reference missing {required}"

    assert "# Key fields in curate.yml:" not in workflow
    assert "# curate.yml 핵심 필드:" not in workflow_kr
    assert "USER_GUIDE.md#curateyml--workspace-configuration-reference" in workflow
    assert "USER_GUIDE_KR.md#curateyml--워크스페이스-설정-레퍼런스" in workflow_kr


def test_cli_reference_is_single_sourced_from_user_guide() -> None:
    workflow = _read("docs/guides/WORKFLOW_GUIDE.md")
    workflow_kr = _read("docs/guides/WORKFLOW_GUIDE_KR.md")
    plugin = _read("docs/guides/PLUGIN_GUIDE.md")
    plugin_kr = _read("docs/guides/PLUGIN_GUIDE_KR.md")

    english_anchor = "USER_GUIDE.md#cli-reference"
    korean_anchor = "USER_GUIDE_KR.md#cli-reference"

    assert english_anchor in workflow
    assert korean_anchor in workflow_kr
    assert english_anchor in plugin
    assert korean_anchor in plugin_kr
