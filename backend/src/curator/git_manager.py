"""Safe Git/GitHub helpers for plugin-local repository workflows."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


class GitManager:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def status(self) -> dict[str, Any]:
        repo_root = self._repo_root()
        if repo_root is None:
            return {
                "ok": False,
                "repo": {"is_repo": False, "root": str(self.root)},
                "error": "not_a_git_repository",
                "message": "The active vault is not a git repository.",
            }

        branch = self._git_text(["branch", "--show-current"]) or "HEAD"
        upstream = self._git_text(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
        ahead = 0
        behind = 0
        remote_url = ""
        if upstream:
            counts = self._git_text(["rev-list", "--left-right", "--count", "HEAD...@{u}"])
            if counts:
                parts = counts.split()
                if len(parts) >= 2:
                    ahead = self._to_int(parts[0])
                    behind = self._to_int(parts[1])
            remote = upstream.split("/", 1)[0]
            remote_url = self._git_text(["remote", "get-url", remote]) or ""

        worktree = self._working_tree_counts()
        warnings: list[str] = []
        if (self.root / ".curator").exists() and not self._is_ignored(".curator/"):
            warnings.append(".curator/ is not ignored")

        gh_status = self._github_status()

        return {
            "ok": True,
            "repo": {
                "is_repo": True,
                "root": str(repo_root),
                "branch": branch,
                "upstream": upstream or "",
                "ahead": ahead,
                "behind": behind,
                "remote_url": remote_url,
                "github_authenticated": gh_status["authenticated"],
                "github_account": gh_status["account"],
            },
            "working_tree": worktree,
            "warnings": warnings,
        }

    def recent_commits(self, limit: int = 10) -> dict[str, Any]:
        if self._repo_root() is None:
            return self._not_repo()
        limit = max(1, min(100, int(limit)))
        raw = self._git_text([
            "log",
            f"--max-count={limit}",
            "--date=iso",
            "--format=%H%x1f%an%x1f%ad%x1f%s",
        ])
        commits = [self._parse_commit_header(line) for line in raw.splitlines() if line.strip()]
        return {"ok": True, "commits": [c for c in commits if c]}

    def diff_stat(self) -> dict[str, Any]:
        if self._repo_root() is None:
            return self._not_repo()
        raw = self._git_text(["diff", "--stat"]) or ""
        staged = self._git_text(["diff", "--cached", "--stat"]) or ""
        return {"ok": True, "stat": raw[:4000], "staged_stat": staged[:4000]}

    def history(
        self,
        *,
        file_path: Path | str,
        query: str = "",
        limit: int = 10,
    ) -> dict[str, Any]:
        if self._repo_root() is None:
            return self._not_repo()
        resolved = self._resolve_inside_root(file_path)
        if resolved is None:
            return {
                "ok": False,
                "error": "path_outside_vault",
                "message": "Git history path must be inside the vault root.",
            }
        relpath = resolved.relative_to(self.root).as_posix()
        limit = max(1, min(50, int(limit)))
        excerpt = self._normalize_query(query)

        commits: list[dict[str, Any]] = []
        exact_match = False
        if excerpt:
            commits = self._log_with_patch(relpath, limit, grep_regex=excerpt)
            exact_match = bool(commits)
        if not commits:
            commits = self._log_with_patch(relpath, limit)

        return {
            "ok": True,
            "file_path": relpath,
            "query_excerpt": excerpt,
            "exact_match": exact_match if excerpt else False,
            "commits": commits,
        }

    def push(self) -> dict[str, Any]:
        status = self.status()
        if not status.get("ok"):
            return status
        repo = status["repo"]
        worktree = status["working_tree"]
        if worktree["conflicted"] > 0:
            return {"ok": False, "error": "conflicted_worktree", "message": "Resolve conflicts before pushing."}
        if not repo.get("upstream"):
            return {"ok": False, "error": "missing_upstream", "message": "Current branch has no upstream remote."}
        ahead = int(repo.get("ahead") or 0)
        behind = int(repo.get("behind") or 0)
        if ahead > 0 and behind > 0:
            return {"ok": False, "error": "diverged_branch", "message": "Branch has diverged from upstream."}
        if behind > 0:
            return {"ok": False, "error": "branch_behind", "message": "Branch is behind upstream; pull/rebase manually first."}
        result = self._run(["push"], check=False, timeout=120)
        if result.returncode != 0:
            return {
                "ok": False,
                "error": "push_failed",
                "message": (result.stderr or result.stdout).strip()[:1000],
            }
        return {
            "ok": True,
            "branch": repo.get("branch", ""),
            "upstream": repo.get("upstream", ""),
            "stdout": result.stdout.strip()[:1000],
            "stderr": result.stderr.strip()[:1000],
        }

    def commit_all(self, message: str) -> dict[str, Any]:
        message = message.strip()
        if not message:
            return {"ok": False, "error": "empty_message", "message": "Commit message is required."}
        status = self.status()
        if not status.get("ok"):
            return status
        worktree = status["working_tree"]
        if worktree["conflicted"] > 0:
            return {"ok": False, "error": "conflicted_worktree", "message": "Resolve conflicts before committing."}
        if worktree["clean"]:
            return {"ok": False, "error": "nothing_to_commit", "message": "No non-ignored changes to commit."}

        self._run(["add", "-A"], check=True)
        result = self._run(["commit", "-m", message], check=False)
        if result.returncode != 0:
            return {
                "ok": False,
                "error": "commit_failed",
                "message": (result.stderr or result.stdout).strip()[:1000],
            }
        commit_hash = self._git_text(["rev-parse", "HEAD"]) or ""
        return {"ok": True, "commit": commit_hash, "message": message}

    def _not_repo(self) -> dict[str, Any]:
        return {
            "ok": False,
            "repo": {"is_repo": False, "root": str(self.root)},
            "error": "not_a_git_repository",
            "message": "The active vault is not a git repository.",
        }

    def _repo_root(self) -> Path | None:
        raw = self._git_text(["rev-parse", "--show-toplevel"])
        return Path(raw).resolve() if raw else None

    def _working_tree_counts(self) -> dict[str, Any]:
        raw = self._git_bytes(["status", "--porcelain=v1", "-z"])
        entries = [e for e in raw.decode("utf-8", errors="replace").split("\0") if e]
        staged = unstaged = untracked = conflicted = 0
        i = 0
        while i < len(entries):
            entry = entries[i]
            code = entry[:2]
            if code.startswith("R") or code.startswith("C"):
                i += 1
            if code == "??":
                untracked += 1
            elif "U" in code or code in {"AA", "DD"}:
                conflicted += 1
            else:
                if code[0] != " ":
                    staged += 1
                if code[1] != " ":
                    unstaged += 1
            i += 1
        return {
            "clean": staged == 0 and unstaged == 0 and untracked == 0 and conflicted == 0,
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
            "conflicted": conflicted,
        }

    def _log_with_patch(self, relpath: str, limit: int, grep_regex: str = "") -> list[dict[str, Any]]:
        args = [
            "log",
            f"--max-count={limit}",
            "--date=iso",
            "--format=%x1e%H%x1f%an%x1f%ad%x1f%s",
            "--patch",
            "--follow",
        ]
        if grep_regex:
            args.append(f"-G{re.escape(grep_regex)}")
        args.extend(["--", relpath])
        raw = self._git_text(args, timeout=30) or ""
        commits: list[dict[str, Any]] = []
        for record in raw.split("\x1e"):
            record = record.strip("\n")
            if not record:
                continue
            header, _, patch = record.partition("\n")
            parsed = self._parse_commit_header(header)
            if not parsed:
                continue
            parsed["patch"] = patch[:4000]
            commits.append(parsed)
        return commits

    def _parse_commit_header(self, header: str) -> dict[str, str] | None:
        parts = header.split("\x1f")
        if len(parts) < 4:
            return None
        return {"hash": parts[0], "author": parts[1], "date": parts[2], "subject": parts[3]}

    def _resolve_inside_root(self, file_path: Path | str) -> Path | None:
        candidate = Path(file_path).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError:
            return None
        return resolved

    def _normalize_query(self, query: str) -> str:
        return re.sub(r"\s+", " ", query).strip()[:160]

    def _is_ignored(self, relpath: str) -> bool:
        result = self._run(["check-ignore", "-q", relpath], check=False)
        return result.returncode == 0

    def _github_status(self) -> dict[str, Any]:
        if shutil.which("gh") is None:
            return {"authenticated": False, "account": ""}
        result = subprocess.run(
            ["gh", "auth", "status"],
            cwd=self.root,
            text=True,
            capture_output=True,
            timeout=10,
        )
        text = f"{result.stdout}\n{result.stderr}"
        account = ""
        match = re.search(r"Logged in to .* as ([^\s]+)", text)
        if match:
            account = match.group(1)
        return {"authenticated": result.returncode == 0, "account": account}

    def _git_text(self, args: list[str], timeout: int = 20) -> str:
        result = self._run(args, check=False, timeout=timeout)
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    def _git_bytes(self, args: list[str], timeout: int = 20) -> bytes:
        if shutil.which("git") is None:
            raise FileNotFoundError("git")
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return result.stdout if result.returncode == 0 else b""

    def _run(
        self,
        args: list[str],
        *,
        check: bool = False,
        timeout: int = 20,
    ) -> subprocess.CompletedProcess[str]:
        if shutil.which("git") is None:
            raise FileNotFoundError("git")
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=check,
        )

    def _to_int(self, value: str) -> int:
        try:
            return int(value)
        except ValueError:
            return 0
