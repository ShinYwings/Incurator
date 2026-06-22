import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from curator import config as cfg
from curator.cli import app
from curator.git_manager import GitManager


pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )


def _json_output(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    assert start >= 0 and end > start, text
    return json.loads(text[start : end + 1])


@pytest.fixture
def git_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    cfg.save_config(cfg.WikiPaths(vault), {})
    _git(vault, "init")
    _git(vault, "config", "user.email", "test@example.com")
    _git(vault, "config", "user.name", "Test User")
    (vault / "note.md").write_text("first version\nstable selected phrase\n", encoding="utf-8")
    _git(vault, "add", "note.md", ".curator/settings.yml")
    _git(vault, "commit", "-m", "Initial note")
    return vault


def test_status_reports_not_a_git_repository(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()

    status = GitManager(vault).status()

    assert status["ok"] is False
    assert status["error"] == "not_a_git_repository"
    assert status["repo"]["is_repo"] is False


def test_status_counts_worktree_and_warns_when_curator_not_ignored(git_vault: Path) -> None:
    (git_vault / "note.md").write_text("changed\n", encoding="utf-8")
    (git_vault / "new.md").write_text("new\n", encoding="utf-8")

    status = GitManager(git_vault).status()

    assert status["ok"] is True
    assert status["repo"]["is_repo"] is True
    assert status["working_tree"]["clean"] is False
    assert status["working_tree"]["unstaged"] == 1
    assert status["working_tree"]["untracked"] == 1
    assert ".curator/ is not ignored" in status["warnings"]


def test_history_finds_selected_text_change(git_vault: Path) -> None:
    (git_vault / "note.md").write_text(
        "second version\nstable selected phrase changed\n",
        encoding="utf-8",
    )
    _git(git_vault, "add", "note.md")
    _git(git_vault, "commit", "-m", "Change selected phrase")

    history = GitManager(git_vault).history(
      file_path=git_vault / "note.md",
      query="stable selected phrase",
      limit=5,
    )

    assert history["ok"] is True
    assert history["file_path"] == "note.md"
    assert history["exact_match"] is True
    assert history["commits"]
    assert "Change selected phrase" in {c["subject"] for c in history["commits"]}
    assert any("stable selected phrase" in c.get("patch", "") for c in history["commits"])


def test_history_rejects_paths_outside_vault(git_vault: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("x", encoding="utf-8")

    history = GitManager(git_vault).history(file_path=outside, query="x")

    assert history["ok"] is False
    assert history["error"] == "path_outside_vault"


def test_push_succeeds_against_local_bare_remote(git_vault: Path, tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], text=True, capture_output=True, check=True)
    _git(git_vault, "branch", "-M", "main")
    _git(git_vault, "remote", "add", "origin", str(remote))
    _git(git_vault, "push", "-u", "origin", "main")

    (git_vault / "note.md").write_text("after scheduled commit\n", encoding="utf-8")
    _git(git_vault, "add", "note.md")
    _git(git_vault, "commit", "-m", "Scheduled commit")

    before = GitManager(git_vault).status()
    assert before["repo"]["ahead"] == 1

    pushed = GitManager(git_vault).push()

    assert pushed["ok"] is True
    assert pushed["branch"] == "main"
    after = GitManager(git_vault).status()
    assert after["repo"]["ahead"] == 0


def test_push_refuses_missing_upstream(git_vault: Path) -> None:
    pushed = GitManager(git_vault).push()

    assert pushed["ok"] is False
    assert pushed["error"] == "missing_upstream"


def test_commit_all_uses_gitignore_scope(git_vault: Path) -> None:
    (git_vault / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (git_vault / "tracked.md").write_text("tracked\n", encoding="utf-8")
    (git_vault / "ignored.txt").write_text("ignored\n", encoding="utf-8")

    committed = GitManager(git_vault).commit_all("Explicit manual commit")

    assert committed["ok"] is True
    assert committed["commit"]
    tracked = _git(git_vault, "ls-files").stdout.splitlines()
    assert "tracked.md" in tracked
    assert "ignored.txt" not in tracked


def test_plugin_git_status_cli_returns_json(git_vault: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["plugin", "git", "status", "--workspace-path", str(git_vault)],
        env={"VAULT_ROOT": str(git_vault)},
    )
    payload = _json_output(result.output)

    assert result.exit_code == 0
    assert payload["ok"] is True
    assert payload["repo"]["is_repo"] is True


def test_plugin_git_history_cli_returns_json(git_vault: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "plugin",
            "git",
            "history",
            "--workspace-path",
            str(git_vault),
            "--file-path",
            str(git_vault / "note.md"),
            "--query",
            "stable selected phrase",
        ],
        env={"VAULT_ROOT": str(git_vault)},
    )
    payload = _json_output(result.output)

    assert result.exit_code == 0
    assert payload["ok"] is True
    assert payload["file_path"] == "note.md"
