from pathlib import Path


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
    assert 'cache_dir = "../.cache/mypy"' in pyproject
    assert backend_check.exists()
    assert ".venv-dev/bin" in backend_check.read_text(encoding="utf-8")
    assert '$ROOT_DIR/.cache/mypy' in backend_check.read_text(encoding="utf-8")


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
