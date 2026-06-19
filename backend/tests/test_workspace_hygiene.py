from pathlib import Path


def test_backend_does_not_contain_local_tool_state() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    backend_root = repo_root / "backend"
    forbidden = [
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
    assert 'cache_dir = "../.pytest_cache"' in pyproject
    assert 'cache-dir = "../.ruff_cache"' in pyproject
    assert 'cache_dir = "../.mypy_cache"' in pyproject
    assert backend_check.exists()
    assert ".venv-dev/bin" in backend_check.read_text(encoding="utf-8")


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
