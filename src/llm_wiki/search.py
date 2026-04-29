"""Search backend (QMD) — stub module.

QMD (Query Markup Documents) provides BM25 + vector + rerank search over
the wiki's markdown pages.  This module wraps the QMD CLI binary.

If QMD is not installed, the search features degrade gracefully —
ingest and lint still work, only `wiki ask` and `wiki reindex` require it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from . import config as cfg


class SearchBackendError(Exception):
    """Raised when the QMD binary fails or is misconfigured."""


def is_available() -> bool:
    """Return True if the ``qmd`` binary is on PATH."""
    try:
        result = subprocess.run(
            ["qmd", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_version() -> str | None:
    """Return the QMD version string, or None if unavailable."""
    try:
        result = subprocess.run(
            ["qmd", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def update_index(paths: cfg.WikiPaths, *, embed: bool = False) -> None:
    """Run ``qmd index`` to rebuild the search index.

    Args:
        paths: Wiki project paths.
        embed: If True, also compute embeddings for vector search.
    """
    if not is_available():
        raise SearchBackendError(
            "qmd is not installed. Install it with: npm install -g @tobilu/qmd"
        )

    cmd = ["qmd", "index", str(paths.wiki)]
    if embed:
        cmd.append("--embed")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise SearchBackendError(
                f"qmd index failed (exit {result.returncode}): {result.stderr}"
            )
    except subprocess.TimeoutExpired:
        raise SearchBackendError("qmd index timed out after 120 seconds")
    except FileNotFoundError:
        raise SearchBackendError("qmd binary not found")


def search_wiki(
    paths: cfg.WikiPaths,
    query: str,
    *,
    limit: int = 8,
    min_score: float = 0.0,
    rerank: bool = True,
) -> list[dict[str, Any]]:
    """Search the wiki and return ranked results.

    Returns a list of dicts with keys: path, score, title, snippet.
    """
    if not is_available():
        raise SearchBackendError("qmd is not installed")

    cmd = ["qmd", "search", str(paths.wiki), query, "--limit", str(limit), "--json"]
    if rerank:
        cmd.append("--rerank")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise SearchBackendError(
                f"qmd search failed (exit {result.returncode}): {result.stderr}"
            )
    except subprocess.TimeoutExpired:
        raise SearchBackendError("qmd search timed out")
    except FileNotFoundError:
        raise SearchBackendError("qmd binary not found")

    import json
    try:
        results = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    if not isinstance(results, list):
        results = results.get("results", [])

    # Filter by min_score
    if min_score > 0:
        results = [r for r in results if r.get("score", 0) >= min_score]

    return results
