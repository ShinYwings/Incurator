"""Workspace agent-rule template rendering.

This module installs InCurator managed rule files into an arbitrary workspace
without overwriting user-authored rules outside managed blocks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


VALID_AGENTS = frozenset({"codex", "claude-code", "gemini-cli", "antigravity", "none"})

MANAGED_START = "<!-- incurator:start -->"
MANAGED_END = "<!-- incurator:end -->"

ANTIGRAVITY_START = "# incurator:start"
ANTIGRAVITY_END = "# incurator:end"


@dataclass
class CurateTemplateData:
    project: str
    description: str
    domains: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    min_confidence: float = 0.60
    scope: str = "all"


@dataclass
class WorkspacePrepareResult:
    workspace: Path
    agent: str
    created: list[Path] = field(default_factory=list)
    updated: list[Path] = field(default_factory=list)
    preserved: list[Path] = field(default_factory=list)

    def touched(self) -> list[Path]:
        return self.created + self.updated


def default_project_name(path: Path) -> str:
    """Return a safe project id from a workspace path name."""
    name = re.sub(r"[^a-zA-Z0-9_-]", "-", path.name).strip("-")
    return name or "workspace"


def prepare_workspace(
    *,
    wiki_root: Path,
    workspace: Path,
    agent: str = "codex",
    curate_data: CurateTemplateData | None = None,
    force_curate: bool = False,
    install_rules: bool = True,
    template_root: Path | None = None,
) -> WorkspacePrepareResult:
    """Ensure curate.yml and selected agent rules exist for a workspace.

    Existing top-level rule files are preserved outside llm-wiki managed blocks.
    Files under `.agents/curator/` are owned by llm-wiki and are overwritten on
    sync so template changes propagate.
    """
    agent = _normalize_agent(agent)
    wiki_root = wiki_root.expanduser().resolve()
    workspace = workspace.expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    result = WorkspacePrepareResult(workspace=workspace, agent=agent)
    _ensure_curate_yml(workspace, curate_data, force_curate, result)

    if install_rules and agent != "none":
        _install_rule_templates(wiki_root, workspace, agent, result, template_root)

    return result


def render_mcp_snippet(*, wiki_root: Path, workspace: Path) -> str:
    """Return a generic MCP JSON snippet with WIKI_ROOT and WORKSPACE_PATH."""
    wiki_root = wiki_root.expanduser().resolve()
    workspace = workspace.expanduser().resolve()
    return f'''{{
  "mcpServers": {{
    "incurator": {{
      "command": "wiki",
      "args": ["mcp"],
      "env": {{
        "WIKI_ROOT": "{wiki_root}",
        "WORKSPACE_PATH": "{workspace}"
      }}
    }}
  }}
}}'''


def _normalize_agent(agent: str) -> str:
    normalized = (agent or "codex").strip().lower()
    aliases = {
        "claude": "claude-code",
        "gemini": "gemini-cli",
        "antigravity-gemini": "antigravity",
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


def _values(wiki_root: Path, workspace: Path, agent: str) -> dict[str, str]:
    return {
        "project_name": default_project_name(workspace),
        "workspace_path": str(workspace),
        "wiki_root": str(wiki_root),
        "agent_runtime": agent,
        "curate_yml_path": str(workspace / "curate.yml"),
    }


def _ensure_curate_yml(
    workspace: Path,
    data: CurateTemplateData | None,
    force: bool,
    result: WorkspacePrepareResult,
) -> None:
    curate_path = workspace / "curate.yml"
    if curate_path.exists() and not force:
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
    content = _replace_yaml_list(content, "domains", data.domains)
    content = _replace_yaml_list(content, "topics", data.topics)
    content = re.sub(r"min_confidence: .+", f"min_confidence: {data.min_confidence:.2f}", content)
    content = re.sub(r'scope: ".+"', f'scope: "{data.scope}"', content)

    _write_file(curate_path, content, result)


def _replace_yaml_list(content: str, key: str, values: list[str]) -> str:
    if not values:
        return content
    lines = [f"{key}:"]
    lines.extend(f'  - "{_escape_yaml_string(v)}"' for v in values)
    rendered = "\n".join(lines)
    return re.sub(rf"{key}: \[\]", rendered, content)


def _escape_yaml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _install_rule_templates(
    wiki_root: Path,
    workspace: Path,
    agent: str,
    result: WorkspacePrepareResult,
    template_root: Path | None = None,
) -> None:
    values = _values(wiki_root, workspace, agent)

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

    target_path, block_template = _top_level_target(agent)
    block = _render_template(block_template, values, template_root)
    _upsert_managed_block(workspace / target_path, block, agent, result)


def _top_level_target(agent: str) -> tuple[str, str]:
    if agent == "codex":
        return "AGENTS.md", "managed/AGENTS.md"
    if agent == "claude-code":
        return "CLAUDE.md", "managed/CLAUDE.md"
    if agent == "gemini-cli":
        return "GEMINI.md", "managed/GEMINI.md"
    if agent == "antigravity":
        return ".antigravity/rules.yaml", "managed/antigravity.rules.yaml"
    raise ValueError(f"unsupported agent: {agent}")


def _upsert_managed_block(path: Path, block: str, agent: str, result: WorkspacePrepareResult) -> None:
    if agent == "antigravity":
        start, end = ANTIGRAVITY_START, ANTIGRAVITY_END
    else:
        start, end = MANAGED_START, MANAGED_END

    block = block.strip()
    new_block = f"{start}\n{block}\n{end}\n"
    old = path.read_text(encoding="utf-8") if path.exists() else ""

    if start in old and end in old:
        pattern = re.compile(re.escape(start) + r".*?" + re.escape(end) + r"\n?", re.S)
        new = pattern.sub(new_block, old)
    elif old.strip():
        new = old.rstrip() + "\n\n" + new_block
    else:
        new = new_block

    _write_file(path, new, result)


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
