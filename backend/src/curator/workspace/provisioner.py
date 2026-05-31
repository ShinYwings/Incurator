"""Workspace agent-rule template rendering.

This module installs incurator managed rule files into an arbitrary workspace
without overwriting user-authored rules outside managed blocks.
"""

from __future__ import annotations
from .. import constants as consts

import re
from dataclasses import dataclass, field
from pathlib import Path


VALID_AGENTS = frozenset({consts.AGENT_CODEX, consts.BACKEND_CLAUDE_CODE, consts.BACKEND_ANTIGRAVITY_CLI, consts.AGENT_NONE})

MANAGED_START = consts.MANAGED_START
MANAGED_END = consts.MANAGED_END




@dataclass
class CurateTemplateData:
    project: str
    description: str
    min_confidence: float = 0.60
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)


@dataclass
class WorkspacePrepareResult:
    workspace: Path
    agent: str
    created: list[Path] = field(default_factory=list)
    updated: list[Path] = field(default_factory=list)
    preserved: list[Path] = field(default_factory=list)
    # "empty" | "agent-only" | "full"  (set by prepare_workspace before any writes)
    scenario: str = consts.SCENARIO_EMPTY

    def touched(self) -> list[Path]:
        return self.created + self.updated


def default_project_name(path: Path) -> str:
    """Return a safe project id from a workspace path name."""
    name = re.sub(r"[^a-zA-Z0-9_-]", "-", path.name).strip("-")
    return name or "workspace"


def detect_workspace_scenario(workspace: Path, agent: str) -> str:
    """Classify the current state of a workspace directory.

    Returns one of three strings:
      "empty"      — no curate.yml and no known agent-rule files present.
      "agent-only" — some agent setup exists (top-level rule file or curate.yml)
                     but the Curator runtime rules are not yet installed.
      "full"       — curate.yml and .agents/curator/runtime/{agent}.md both exist;
                     Curator is already integrated.
    """
    has_curate = (workspace / consts.FILE_CURATE_YML).exists()
    try:
        top_target, _ = top_level_target(_normalize_agent(agent))
    except ValueError:
        top_target = consts.FILE_CLAUDE_MD  # safe fallback for unknown agents

    has_curator_rules = (workspace / ".agents" / "curator" / "runtime" / f"{_normalize_agent(agent)}.md").exists()

    if has_curate and has_curator_rules:
        return consts.SCENARIO_FULL

    has_top_level = (workspace / top_target).exists()
    has_curator_dir = (workspace / ".agents" / "curator").exists()

    if has_curate or has_top_level or has_curator_dir or _has_any_agent_file(workspace):
        return consts.SCENARIO_AGENT_ONLY

    return consts.SCENARIO_EMPTY


def _has_any_agent_file(workspace: Path) -> bool:
    """Return True if any well-known top-level agent rule file exists."""
    for candidate in (consts.FILE_CLAUDE_MD, consts.FILE_AGENTS_MD):
        if (workspace / candidate).exists():
            return True
    return False


def prepare_workspace(
    *,
    vault_root: Path,
    workspace: Path,
    agent: str = consts.AGENT_CODEX,
    curate_data: CurateTemplateData | None = None,
    force_curate: bool = False,
    install_rules: bool = True,
    install_managed_block: bool = True,
    template_root: Path | None = None,
) -> WorkspacePrepareResult:
    """Ensure curate.yml and selected agent rules exist for a workspace.

    Existing top-level rule files are preserved outside incurator managed blocks.
    Files under `.agents/curator/` are owned by incurator and are overwritten on
    sync so template changes propagate.
    """
    agent = _normalize_agent(agent)
    vault_root = vault_root.expanduser().resolve()
    workspace = workspace.expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    scenario = detect_workspace_scenario(workspace, agent)
    result = WorkspacePrepareResult(workspace=workspace, agent=agent, scenario=scenario)
    _ensure_curate_yml(vault_root, workspace, curate_data, force_curate, result)

    if install_rules and agent != consts.AGENT_NONE:
        _install_rule_templates(vault_root, workspace, agent, result, template_root, install_managed_block)

    return result


_CLIENT_INFO_MAP = {
    consts.CLOUD_CLAUDE: consts.BACKEND_CLAUDE_CODE,
    consts.CLOUD_ANTIGRAVITY: consts.BACKEND_ANTIGRAVITY_CLI,
    consts.AGENT_CODEX: consts.BACKEND_CODEX_CLI,
}


def detect_agent_from_client_info(client_name: str) -> str:
    """Map an MCP clientInfo.name string to an incurator agent runtime slug.

    Falls back to 'codex' for unrecognised clients.
    """
    name_lower = (client_name or "").lower()
    for key, agent in _CLIENT_INFO_MAP.items():
        if key in name_lower:
            return agent
    return consts.AGENT_CODEX


def merge_mcp_settings(settings_path: Path, *, vault_root: Path, workspace: Path) -> None:
    """Merge VAULT_ROOT and WORKSPACE_PATH into a Claude Code settings.json.

    Creates the file and parent dirs if needed. Existing unrelated fields
    are preserved; only `mcpServers.incurator.env` is touched.
    """
    import json

    settings_path.parent.mkdir(parents=True, exist_ok=True)

    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    else:
        data = {}

    mcp_servers = data.setdefault("mcpServers", {})
    incurator = mcp_servers.setdefault("incurator", {})
    incurator.setdefault("command", "wiki")
    incurator.setdefault("args", ["mcp"])
    env = incurator.setdefault("env", {})
    env["VAULT_ROOT"] = str(vault_root.expanduser().resolve())
    env["WORKSPACE_PATH"] = str(workspace.expanduser().resolve())

    settings_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def render_mcp_snippet(*, vault_root: Path, workspace: Path) -> str:
    """Return a generic MCP JSON snippet with VAULT_ROOT and WORKSPACE_PATH."""
    vault_root = vault_root.expanduser().resolve()
    workspace = workspace.expanduser().resolve()
    return f'''{{
  "mcpServers": {{
    "incurator": {{
      "command": "wiki",
      "args": ["mcp"],
      "env": {{
        "VAULT_ROOT": "{vault_root}",
        "WORKSPACE_PATH": "{workspace}"
      }}
    }}
  }}
}}'''


def _normalize_agent(agent: str) -> str:
    normalized = (agent or consts.AGENT_CODEX).strip().lower()
    aliases = {
        consts.CLOUD_CLAUDE: consts.BACKEND_CLAUDE_CODE,


        consts.CLOUD_ANTIGRAVITY: consts.BACKEND_ANTIGRAVITY_CLI,
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in VALID_AGENTS:
        raise ValueError(f"agent must be one of {sorted(VALID_AGENTS)}, got {agent!r}")
    return normalized


def _template_root(template_root: Path | None = None) -> Path:
    if template_root is not None:
        return template_root.expanduser().resolve()
    return Path(__file__).parent / "templates" / "workspace_rules"


def _render_template(rel_path: str, values: dict[str, str], template_root: Path | None = None) -> str:
    text = (_template_root(template_root) / rel_path).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text.rstrip() + "\n"


def _values(vault_root: Path, workspace: Path, agent: str) -> dict[str, str]:
    return {
        "project_name": default_project_name(workspace),
        "workspace_path": str(workspace),
        "vault_root": str(vault_root),
        "agent_runtime": agent,
        "curate_yml_path": str(workspace / consts.FILE_CURATE_YML),
    }


def _ensure_curate_yml(
    vault_root: Path,
    workspace: Path,
    data: CurateTemplateData | None,
    force: bool,
    result: WorkspacePrepareResult,
) -> None:
    curate_path = workspace / consts.FILE_CURATE_YML
    if curate_path.exists() and not force:
        # Heal stale vault_root without touching any other fields
        try:
            content = curate_path.read_text(encoding="utf-8")
            healed = re.sub(
                r"^vault_root: .*$", f"vault_root: {vault_root}", content, flags=re.MULTILINE
            )
            if healed != content:
                curate_path.write_text(healed, encoding="utf-8")
                result.updated.append(curate_path)
            else:
                result.preserved.append(curate_path)
        except Exception:
            result.preserved.append(curate_path)
        return

    data = data or CurateTemplateData(
        project=default_project_name(workspace),
        description=f"Knowledge workspace for {default_project_name(workspace)}",
    )
    template = Path(__file__).parent / "templates" / "curate-template.yml"
    content = template.read_text(encoding="utf-8")
    content = content.replace("{{project_name}}", data.project)
    content = content.replace("{{description}}", data.description)
    content = content.replace("{{vault_root}}", str(vault_root))
    content = re.sub(r"min_confidence: .+", f"min_confidence: {data.min_confidence:.2f}", content)
    if data.include_patterns:
        content = _replace_sources_include(content, data.include_patterns)
    if data.exclude_patterns:
        content = _replace_sources_exclude(content, data.exclude_patterns)

    _write_file(curate_path, content, result)


def _replace_yaml_list(content: str, key: str, values: list[str]) -> str:
    if not values:
        return content
    lines = [f"{key}:"]
    lines.extend(f'  - "{_escape_yaml_string(v)}"' for v in values)
    rendered = "\n".join(lines)
    return re.sub(rf"{key}: \[\]", rendered, content)


def _replace_sources_include(content: str, patterns: list[str]) -> str:
    """Replace 'include: []' inside the sources block with actual patterns."""
    lines = ["include:"]
    lines.extend(f'    - "{_escape_yaml_string(p)}"' for p in patterns)
    rendered = "\n".join(lines)
    return re.sub(r"include: \[\]", rendered, content, count=1)


def _replace_sources_exclude(content: str, patterns: list[str]) -> str:
    """Replace 'exclude: []' inside the sources block with actual patterns."""
    lines = ["exclude:"]
    lines.extend(f'    - "{_escape_yaml_string(p)}"' for p in patterns)
    rendered = "\n".join(lines)
    return re.sub(r"exclude: \[\]", rendered, content, count=1)


def _escape_yaml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _install_rule_templates(
    vault_root: Path,
    workspace: Path,
    agent: str,
    result: WorkspacePrepareResult,
    template_root: Path | None = None,
    install_managed_block: bool = True,
) -> None:
    values = _values(vault_root, workspace, agent)

    owned_templates = {
        "owned/shared/rules.md": ".agents/curator/shared/rules.md",
        "owned/shared/sync.md": ".agents/curator/shared/sync.md",
        "owned/shared/check_rule_sync.py": ".agents/curator/shared/check_rule_sync.py",
        f"owned/runtime/{agent}.md": f".agents/curator/runtime/{agent}.md",
    }
    workflow_dir = _template_root(template_root) / "owned" / "workflows"
    if workflow_dir.exists():
        for workflow_path in sorted(workflow_dir.glob("*.md")):
            src = f"owned/workflows/{workflow_path.name}"
            owned_templates[src] = f".agents/curator/workflows/{workflow_path.name}"

    for src, dest in owned_templates.items():
        _write_file(workspace / dest, _render_template(src, values, template_root), result)

    if install_managed_block:
        # Install managed blocks for ALL known agents — don't guess which one
        # is connecting. Every agent session-start file gets the Curator block.
        for _install_agent in (consts.BACKEND_CODEX_CLI, consts.BACKEND_CLAUDE_CODE, consts.BACKEND_ANTIGRAVITY_CLI):
            try:
                _target_path, _block_tmpl = top_level_target(_install_agent)
                _block = _render_template(
                    _block_tmpl,
                    {**values, "agent_runtime": _install_agent},
                    template_root,
                )
                _upsert_managed_block(workspace / _target_path, _block, _install_agent, result)
            except Exception:
                pass


def top_level_target(agent: str) -> tuple[str, str]:
    """Return (rule_file_path, managed_block_template) for an agent."""
    if agent == consts.BACKEND_CODEX_CLI or agent == consts.BACKEND_ANTIGRAVITY_CLI:
        return consts.FILE_AGENTS_MD, f"managed/{consts.FILE_AGENTS_MD}"
    if agent == consts.BACKEND_CLAUDE_CODE:
        return consts.FILE_CLAUDE_MD, f"managed/{consts.FILE_CLAUDE_MD}"
    raise ValueError(f"unsupported agent: {agent}")


def _upsert_managed_block(path: Path, block: str, agent: str, result: WorkspacePrepareResult) -> None:
    start, end = MANAGED_START, MANAGED_END

    block = block.strip()
    new_block = f"{start}\n{block}\n{end}\n"
    old = path.read_text(encoding="utf-8") if path.exists() else ""

    if start in old and end in old:
        pattern = re.compile(re.escape(start) + r".*?" + re.escape(end) + r"\n?", re.S)
        new = pattern.sub(new_block, old)
    elif old.strip():
        new = new_block + "\n" + old.lstrip()
    else:
        new = new_block

    _write_file(path, new, result)


def make_rule_integration_prompt(existing_content: str, agent: str, workspace_path: str) -> str:
    """Build the LLM prompt that integrates Curator hooks into an existing rule file."""
    return (
        "You are integrating Curator knowledge navigation into an existing agent rule file.\n\n"
        "Curator requires three behavioral rules:\n"
        "1. **Session start**: call `curator_check_workspace()` MCP tool before responding to any domain query\n"
        "2. **Every domain query**: call `search_curator('<query>')` FIRST; "
        "use Curator results as primary evidence; fall back to local files only if Curator returns nothing\n"
        "3. **Session end**: follow `.agents/curator/workflows/session_closeout.md`\n\n"
        f"Workspace: {workspace_path}\n"
        f"File format: Markdown\n\n"
        "Existing rule file:\n"
        "---\n"
        f"{existing_content}\n"
        "---\n\n"
        "Rewrite the rule file to naturally integrate these Curator requirements.\n"
        "Constraints:\n"
        "- Preserve ALL existing rules and instructions verbatim\n"
        "- Add Curator hooks at semantically appropriate steps (session start, query loop, session end)\n"
        "- If no session start step exists, insert one at the beginning\n"
        "- Do NOT remove, shorten, or paraphrase any existing content\n"
        "- Output ONLY the modified file content — no prose, no explanation, no fences"
    )


def make_integration_copy_prompt(agent: str, rule_file: str) -> str:
    """Return a copy-paste prompt the user can give to their agent for manual integration."""
    return (
        f"Please update `{rule_file}` to integrate Curator knowledge navigation.\n\n"
        "Add these three behavioral requirements at the appropriate places in the workflow:\n\n"
        "1. **Session start**: call `curator_check_workspace()` MCP tool "
        "before responding to any domain query\n"
        "2. **Every domain query**: call `search_curator('<your query>')` FIRST — "
        "use Curator results as primary evidence; fall back to local files only if "
        "Curator returns nothing, and state clearly when you do\n"
        "3. **Session end**: follow `.agents/curator/workflows/session_closeout.md`\n\n"
        "Preserve all existing rules. Add these requirements at semantically appropriate steps."
    )


def _write_file(path: Path, content: str, result: WorkspacePrepareResult) -> None:
    existed = path.exists()
    old = path.read_text(encoding="utf-8") if existed else None
    content = content.rstrip() + "\n"
    if old == content:
        result.preserved.append(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    (result.updated if existed else result.created).append(path)
