from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = "q" + "md"

SCAN_TARGETS = [
    "AGENTS.md",
    "CLAUDE.md",
    "backend/src",
    "backend/tests",
    "plugin/main.ts",
    "plugin/src",
    "plugin/styles.css",
    "scripts/build",
    "docs/guides",
    "docs/specs",
]

SKIP_PARTS = {"__pycache__", ".cache", ".pytest_cache", "node_modules", "dist"}


def _iter_text_files(root: Path):
    if root.is_file():
        yield root
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.suffix in {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".sqlite"}:
            continue
        yield path


def test_active_tree_has_no_retired_search_binary_references() -> None:
    offenders: list[str] = []
    for target in SCAN_TARGETS:
        root = REPO_ROOT / target
        if not root.exists():
            continue
        for path in _iter_text_files(root):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if FORBIDDEN in line.lower():
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert offenders == []
