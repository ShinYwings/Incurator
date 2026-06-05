import pytest
import os
import subprocess
from pathlib import Path
from curator.git_manager import GitManager, GitStatus

@pytest.fixture
def temp_git_repo(tmp_path: Path):
    """Creates a temporary git repository for testing."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_dir), check=True)
    
    # Create an initial commit
    (repo_dir / "README.md").write_text("# Test Repo")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), check=True)
    
    return repo_dir

def test_git_status_clean(temp_git_repo: Path):
    manager = GitManager(temp_git_repo)
    status = manager.get_status()
    assert isinstance(status, GitStatus)
    assert status.is_dirty is False
    assert status.untracked_files == []
    assert status.modified_files == []
    assert status.branch != ""

def test_git_status_dirty(temp_git_repo: Path):
    # Add an untracked file
    (temp_git_repo / "new_file.md").write_text("Hello")
    
    # Modify an existing file
    (temp_git_repo / "README.md").write_text("# Test Repo Modified")
    
    manager = GitManager(temp_git_repo)
    status = manager.get_status()
    
    assert status.is_dirty is True
    assert "new_file.md" in status.untracked_files
    assert "README.md" in status.modified_files

def test_git_commit_all(temp_git_repo: Path):
    (temp_git_repo / "new_file.md").write_text("Hello")
    manager = GitManager(temp_git_repo)
    
    commit_hash = manager.commit_all("Add new file")
    assert commit_hash is not None
    assert len(commit_hash) >= 7
    
    status = manager.get_status()
    assert status.is_dirty is False

def test_git_log(temp_git_repo: Path):
    manager = GitManager(temp_git_repo)
    logs = manager.get_recent_commits(limit=5)
    assert len(logs) == 1
    assert "Initial commit" in logs[0]
