import re
from pathlib import Path

from curator import constants as consts
from curator.workspace.provisioner import (
    detect_agent_from_client_info,
    normalize_agent,
    portable_vault_root,
    prepare_workspace,
)


def _vault_root_value(curate_path: Path) -> str:
    content = curate_path.read_text(encoding="utf-8")
    match = re.search(r"^vault_root:\s*(.*)$", content, flags=re.MULTILINE)
    assert match, f"no vault_root line in {curate_path}"
    return match.group(1).strip().strip("\"'")


FORBIDDEN_WORKSPACE_TEMPLATE_TERMS = (
    ".agents/USER_REPORT.md",
    ".agents/ROADMAP.md",
    ".agents/drafts",
    "PLAN_TEMPLATE",
    "skeleton plan",
    "knowledge_sync_bridge.md",
    "vault_root defined in AGENTS.md",
    "Papers/",
    "methodology.md",
    "Incurator project",
    "Incurator 프로젝트",
)


def test_backend_does_not_contain_local_tool_state() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    backend_root = repo_root / "backend"
    forbidden = [
        repo_root / ".ruff_cache",
        repo_root / ".mypy_cache",
        repo_root / ".pytest_cache",
        backend_root / ".venv",
        backend_root / ".venv-dev",
        backend_root / ".ruff_cache",
        backend_root / ".mypy_cache",
        backend_root / ".pytest_cache",
        backend_root / "uv.lock",
    ]

    existing = [path.relative_to(repo_root).as_posix() for path in forbidden if path.exists()]

    assert existing == []


def test_backend_tooling_is_pinned_to_repo_root_state() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    pyproject = (repo_root / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    backend_check = repo_root / "scripts" / "backend-check"

    assert "[tool.uv]" in pyproject
    assert "managed = false" in pyproject
    assert 'cache_dir = "../.cache/pytest"' in pyproject
    assert 'cache-dir = "../.cache/ruff"' in pyproject
    assert "[tool.ruff.lint]" in pyproject
    assert 'select = ["E4", "E7", "E9", "F"]' in pyproject
    assert 'cache_dir = "../.cache/mypy"' in pyproject
    assert backend_check.exists()
    helper = backend_check.read_text(encoding="utf-8")
    assert ".venv-dev/bin" in helper
    assert '-c "$ROOT_DIR/backend/pyproject.toml"' in helper
    assert 'cache_dir=$ROOT_DIR/.cache/pytest' in helper
    assert '$ROOT_DIR/.cache/mypy' in helper


def test_backend_validation_docs_do_not_reintroduce_active_uv_exports() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    checked_paths = [
        repo_root / "AGENTS.md",
        repo_root / "CLAUDE.md",
        repo_root / ".github" / "workflows" / "ci.yml",
        repo_root / ".github" / "pull_request_template.md",
        repo_root / "docs" / "guides" / "AGENT_WORKFLOW_GUIDE.md",
        repo_root / "docs" / "guides" / "AGENT_WORKFLOW_GUIDE_KR.md",
        repo_root / "docs" / "guides" / "CONTRIBUTION_GUIDE.md",
        repo_root / "docs" / "guides" / "CONTRIBUTION_GUIDE_KR.md",
    ]

    for path in checked_paths:
        text = path.read_text(encoding="utf-8")
        assert "uv run --directory backend --active" not in text
        assert "export VIRTUAL_ENV" not in text


def test_runtime_temp_and_cache_files_stay_in_repo_cache_or_vault_curator() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    llm = (repo_root / "backend" / "src" / "curator" / "llm.py").read_text(encoding="utf-8")
    zotero = (repo_root / "backend" / "src" / "curator" / "zotero.py").read_text(encoding="utf-8")
    zotero_integration = (
        repo_root / "backend" / "src" / "curator" / "zotero_integration.py"
    ).read_text(encoding="utf-8")
    ingest_llm = (repo_root / "backend" / "src" / "curator" / "ingest_llm.py").read_text(
        encoding="utf-8"
    )

    assert "tempfile.mktemp" not in llm
    assert "tempfile.gettempdir" not in llm
    assert 'dir=_repo_cache_dir("llm", "agy_logs")' in llm
    assert 'dir=_repo_cache_dir("llm", "codex_outputs")' in llm
    assert 'temp_dir = str(_repo_cache_dir("llm", "tmp"))' in llm
    assert '"TMPDIR": temp_dir' in llm

    assert "tempfile.gettempdir" not in zotero
    assert "zotero_temp_" not in zotero
    assert 'cfg.get_global_config_dir().parent / "zotero_sqlite"' in zotero

    assert "tempfile.gettempdir" not in zotero_integration
    assert "zotero_search_" not in zotero_integration
    assert "zotero_meta_" not in zotero_integration
    assert "_copy_db_to_repo_temp(db_path)" in zotero_integration

    assert "tempfile.mkdtemp" not in ingest_llm
    assert "curator-insight-" not in ingest_llm


def test_workspace_templates_do_not_embed_repo_local_agent_workflows() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    template_root = repo_root / "backend" / "src" / "curator" / "workspace" / "templates"

    checked = [
        path
        for path in template_root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]

    assert checked
    for path in checked:
        text = path.read_text(encoding="utf-8", errors="replace")
        for term in FORBIDDEN_WORKSPACE_TEMPLATE_TERMS:
            assert term not in text, f"{path.relative_to(repo_root)} leaks repo-local term {term!r}"


def test_workspace_prepare_installs_only_selected_agent_rule_file(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    workspace = vault / "workspace"

    result = prepare_workspace(
        vault_root=vault,
        workspace=workspace,
        agent=consts.AGENT_CODEX,
    )

    assert (workspace / consts.FILE_AGENTS_MD).exists()
    assert not (workspace / consts.FILE_CLAUDE_MD).exists()
    assert (workspace / ".agents" / "curator" / "runtime" / "codex.md").exists()
    assert not (workspace / ".agents" / "curator" / "runtime" / "antigravity-cli.md").exists()
    assert result.touched()

    agents_text = (workspace / consts.FILE_AGENTS_MD).read_text(encoding="utf-8")
    assert "Runtime guidance: `.agents/curator/runtime/codex.md`" in agents_text
    assert "antigravity-cli.md" not in agents_text


def test_workspace_prepare_updates_shared_agents_file_to_selected_runtime(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    workspace = vault / "workspace"

    prepare_workspace(vault_root=vault, workspace=workspace, agent=consts.AGENT_CODEX)
    prepare_workspace(
        vault_root=vault,
        workspace=workspace,
        agent=consts.BACKEND_ANTIGRAVITY_CLI,
    )

    agents_text = (workspace / consts.FILE_AGENTS_MD).read_text(encoding="utf-8")
    assert "Runtime guidance: `.agents/curator/runtime/antigravity-cli.md`" in agents_text
    assert (workspace / ".agents" / "curator" / "runtime" / "antigravity-cli.md").exists()


def test_workspace_prepare_rendered_files_do_not_leak_repo_local_agent_workflows(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    workspace = vault / "workspace"

    prepare_workspace(vault_root=vault, workspace=workspace, agent=consts.AGENT_CODEX)

    rendered = [
        path
        for path in workspace.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]
    assert rendered
    for path in rendered:
        text = path.read_text(encoding="utf-8", errors="replace")
        for term in FORBIDDEN_WORKSPACE_TEMPLATE_TERMS:
            assert term not in text, f"{path.relative_to(workspace)} leaks repo-local term {term!r}"


def test_codex_client_detection_uses_workspace_agent_slug() -> None:
    assert detect_agent_from_client_info("Codex") == consts.AGENT_CODEX
    assert detect_agent_from_client_info("codex-cli") == consts.AGENT_CODEX


def test_workspace_agent_aliases_normalize_to_supported_runtime_slugs() -> None:
    assert normalize_agent("codex-cli") == consts.AGENT_CODEX
    assert normalize_agent("antigravity") == consts.BACKEND_ANTIGRAVITY_CLI
    assert normalize_agent("claude") == consts.BACKEND_CLAUDE_CODE


def test_in_vault_workspace_gets_relative_portable_vault_root(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    workspace = vault / consts.DIR_WORKSPACES / "proj"

    prepare_workspace(vault_root=vault, workspace=workspace, agent=consts.AGENT_NONE)

    curate = workspace / consts.FILE_CURATE_YML
    # An in-vault workspace two levels deep resolves to the vault via "../..".
    assert _vault_root_value(curate) == "../.."
    # And it must NOT bake in the absolute generating-device path.
    assert str(vault) not in curate.read_text(encoding="utf-8")


def test_outside_vault_workspace_still_gets_relative_vault_root(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    workspace = tmp_path / "external_ws"

    prepare_workspace(vault_root=vault, workspace=workspace, agent=consts.AGENT_NONE)

    value = _vault_root_value(workspace / consts.FILE_CURATE_YML)
    # Sibling directories: relative path hops up one and back down into the vault.
    assert value == "../vault"
    assert (workspace / value).resolve() == vault.resolve()


def test_healing_preserves_correct_relative_vault_root(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    workspace = vault / consts.DIR_WORKSPACES / "proj"
    prepare_workspace(vault_root=vault, workspace=workspace, agent=consts.AGENT_NONE)

    curate = workspace / consts.FILE_CURATE_YML
    before = curate.read_text(encoding="utf-8")

    # Re-running provisioning must not clobber the already-correct "../..".
    result = prepare_workspace(vault_root=vault, workspace=workspace, agent=consts.AGENT_NONE)

    assert curate.read_text(encoding="utf-8") == before
    assert curate in result.preserved
    assert curate not in result.updated


def test_healing_rewrites_stale_absolute_vault_root_to_portable(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    workspace = vault / consts.DIR_WORKSPACES / "proj"
    prepare_workspace(vault_root=vault, workspace=workspace, agent=consts.AGENT_NONE)

    curate = workspace / consts.FILE_CURATE_YML
    # Simulate a curate.yml that was synced from another device with that
    # device's absolute vault path baked in.
    stale = curate.read_text(encoding="utf-8").replace(
        'vault_root: "../.."', 'vault_root: "/Volumes/OtherDevice/second_brain"'
    )
    curate.write_text(stale, encoding="utf-8")

    result = prepare_workspace(vault_root=vault, workspace=workspace, agent=consts.AGENT_NONE)

    assert _vault_root_value(curate) == "../.."
    assert curate in result.updated


def test_healing_preserves_correct_absolute_vault_root(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    workspace = vault / consts.DIR_WORKSPACES / "proj"
    prepare_workspace(vault_root=vault, workspace=workspace, agent=consts.AGENT_NONE)

    curate = workspace / consts.FILE_CURATE_YML
    # A correct *absolute* path that points at this very vault is also valid and
    # must be left untouched (user may have set it deliberately).
    abs_value = str(vault.resolve())
    swapped = curate.read_text(encoding="utf-8").replace(
        'vault_root: "../.."', f'vault_root: "{abs_value}"'
    )
    curate.write_text(swapped, encoding="utf-8")

    result = prepare_workspace(vault_root=vault, workspace=workspace, agent=consts.AGENT_NONE)

    assert _vault_root_value(curate) == abs_value
    assert curate in result.preserved


def test_healing_handles_backslash_absolute_fallback_without_regex_corruption(
    tmp_path: Path, monkeypatch
) -> None:
    # On Windows a cross-drive workspace falls back to an absolute vault_root with
    # backslashes (e.g. C:\Users\...). Those chars (\U, \1) would be parsed as
    # escape sequences / backreferences if the re.sub replacement were a plain
    # string, raising re.error or corrupting the path. Healing must write it
    # verbatim.
    import curator.workspace.provisioner as prov

    vault = tmp_path / "vault"
    workspace = vault / consts.DIR_WORKSPACES / "proj"
    prepare_workspace(vault_root=vault, workspace=workspace, agent=consts.AGENT_NONE)

    curate = workspace / consts.FILE_CURATE_YML
    stale = curate.read_text(encoding="utf-8").replace(
        'vault_root: "../.."', 'vault_root: "/somewhere/stale"'
    )
    curate.write_text(stale, encoding="utf-8")

    windows_path = r"C:\Users\1data\vault"
    monkeypatch.setattr(prov, "portable_vault_root", lambda *a, **k: windows_path)

    result = prepare_workspace(vault_root=vault, workspace=workspace, agent=consts.AGENT_NONE)

    assert _vault_root_value(curate) == windows_path
    assert curate in result.updated


def test_portable_vault_root_helper_inside_vault(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    workspace = vault / "01_Workspaces" / "proj"
    workspace.mkdir(parents=True)
    assert portable_vault_root(vault, workspace) == "../.."


def test_mcp_resolves_relative_vault_root_against_workspace(tmp_path: Path, monkeypatch) -> None:
    # A relative vault_root (as written by provisioning) must resolve against the
    # workspace dir, NOT the process CWD — the device-portability guarantee.
    from curator import mcp_server

    vault = tmp_path / "vault"
    workspace = vault / consts.DIR_WORKSPACES / "proj"
    prepare_workspace(vault_root=vault, workspace=workspace, agent=consts.AGENT_NONE)
    assert _vault_root_value(workspace / consts.FILE_CURATE_YML) == "../.."

    # Minimal vault marker so resolution accepts it.
    (vault / consts.INTERNAL_DIR).mkdir(parents=True, exist_ok=True)
    (vault / consts.INTERNAL_DIR / consts.SETTINGS_FILE).write_text(
        "llm:\n  provider: ollama\n", encoding="utf-8"
    )

    monkeypatch.delenv("VAULT_ROOT", raising=False)
    # Run from an unrelated CWD to prove resolution is workspace-relative.
    monkeypatch.chdir(tmp_path)

    paths = mcp_server._resolve_paths(hint_path=str(workspace))
    assert paths.root.resolve() == vault.resolve()
