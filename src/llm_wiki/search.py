"""Search backend — wraps the bundled QMD binary at `src/qmd/bin/qmd`.

QMD provides BM25 + vector + LLM-rerank search over markdown collections.
We use it as the retrieval engine for the Curator's `.curator/Collections/`
DAG. The Python side never embeds qmd as a library — we shell out to the
TypeScript CLI (it ships compiled `dist/`) and parse `--json` output.

The binary is resolved in this order:
  1. `WIKI_QMD_BIN` env var (explicit override)
  2. The bundled copy at `<repo>/src/qmd/bin/qmd`
  3. `qmd` on PATH (system install)

Search and indexing degrade gracefully when qmd is missing — ingest and
lint still work; only `wiki ask` / `wiki reindex` require it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import config as cfg


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class SearchHit:
    """One ranked search result."""

    full_path: str           # relpath inside `.curator/Collections/`, e.g. '02_Atoms/ATM-abc12345.md'
    title: str = ""
    score: float = 0.0
    snippet: str = ""
    full_content: str = ""   # populated when hydrate=True
    docid: str = ""          # qmd's content-hash short id (#abc123)


@dataclass
class SearchResults:
    """Ranked list of hits returned from one query call."""

    hits: list[SearchHit] = field(default_factory=list)
    fallback_mode: str = ""  # set when hybrid fell back (e.g. "lex" after GPU OOM)

    def __len__(self) -> int:
        return len(self.hits)

    def __iter__(self) -> Iterable[SearchHit]:
        return iter(self.hits)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SearchBackendError(Exception):
    """The qmd binary failed, returned malformed output, or timed out."""


class QmdNotInstalled(SearchBackendError):
    """No qmd binary found via env override, bundled copy, or PATH."""


# ---------------------------------------------------------------------------
# Binary resolution
# ---------------------------------------------------------------------------


# Repo-relative path to the bundled qmd launcher. `__file__` lives at
# `<repo>/src/llm_wiki/search.py`, so .parent.parent points at `<repo>/src`,
# and the bundled binary is `<repo>/src/qmd/bin/qmd`.
_BUNDLED_QMD = Path(__file__).resolve().parent.parent / "qmd" / "bin" / "qmd"


def get_qmd_binary() -> Path | None:
    """Resolve the qmd binary. Returns None if no source can be found."""
    override = os.environ.get("WIKI_QMD_BIN")
    if override:
        p = Path(override).expanduser()
        if p.exists() and os.access(p, os.X_OK):
            return p
    if _BUNDLED_QMD.exists() and os.access(_BUNDLED_QMD, os.X_OK):
        return _BUNDLED_QMD
    import shutil
    on_path = shutil.which("qmd")
    return Path(on_path) if on_path else None


def is_available() -> bool:
    """True if a qmd binary can be found AND responds to --version."""
    bin_path = get_qmd_binary()
    if bin_path is None:
        return False
    try:
        result = subprocess.run(
            [str(bin_path), "--version"], capture_output=True, timeout=5,
            env=_qmd_env(None),
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def get_version() -> str | None:
    """Return the qmd version string, or None if unavailable."""
    bin_path = get_qmd_binary()
    if bin_path is None:
        return None
    try:
        result = subprocess.run(
            [str(bin_path), "--version"], capture_output=True, text=True, timeout=5,
            env=_qmd_env(None),
        )
        if result.returncode == 0:
            return result.stdout.strip() or result.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _require_binary() -> Path:
    bin_path = get_qmd_binary()
    if bin_path is None:
        raise QmdNotInstalled(
            "qmd not found. Build the bundled copy with "
            "`cd src/qmd && bun install && bun run build`, "
            "or set WIKI_QMD_BIN to a qmd binary."
        )
    return bin_path


def _qmd_env(paths: cfg.WikiPaths | None) -> dict[str, str]:
    """Build the env that pins qmd to this project's per-vault config + DB.

    `QMD_CONFIG_DIR` controls where qmd looks for `index.yml`; `INDEX_PATH`
    pins the sqlite database. Both live under `.curator/qmd/` so the search
    state travels with the vault.

    Also injects the nodeenv node/bin directory into PATH so that the `bin/qmd`
    launcher script can find `node` even when it is not on the system PATH.
    """
    import sys
    env = dict(os.environ)

    # Ensure nodeenv-installed node is on PATH (takes priority if system node is absent)
    nodeenv_bin = Path(sys.prefix) / "node" / "bin"
    if nodeenv_bin.exists():
        existing_path = env.get("PATH", "")
        if str(nodeenv_bin) not in existing_path.split(os.pathsep):
            env["PATH"] = str(nodeenv_bin) + os.pathsep + existing_path

    if paths is not None:
        paths.qmd_dir.mkdir(parents=True, exist_ok=True)
        env["QMD_CONFIG_DIR"] = str(paths.qmd_dir)
        env["INDEX_PATH"] = str(paths.qmd_db)
    return env


def _run_qmd(
    args: list[str],
    *,
    timeout: int = 60,
    cwd: Path | None = None,
    paths: cfg.WikiPaths | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke qmd with the given args. Raises SearchBackendError on failure.

    When `paths` is provided, the call is scoped to that project's qmd
    config + DB via env vars; otherwise it inherits the parent environment
    (used only by `is_available()` / `get_version()`).
    """
    bin_path = _require_binary()
    try:
        return subprocess.run(
            [str(bin_path), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            env=_qmd_env(paths) if paths is not None else None,
        )
    except subprocess.TimeoutExpired as e:
        raise SearchBackendError(f"qmd timed out after {timeout}s: {' '.join(args)}") from e
    except FileNotFoundError as e:
        raise QmdNotInstalled(f"qmd binary not found at {bin_path}") from e
    except OSError as e:
        raise SearchBackendError(f"qmd invocation failed: {e}") from e


# ---------------------------------------------------------------------------
# Project bootstrap (called from `wiki init`)
# ---------------------------------------------------------------------------


_QMD_TEMPLATE = Path(__file__).resolve().parent / "templates" / "qmd-index.yml"


def write_qmd_config(paths: cfg.WikiPaths, *, overwrite: bool = False) -> bool:
    """Render the per-project `index.yml` from the template.

    Returns True if the file was written, False if it already existed and
    `overwrite=False`. The template's `__COLLECTIONS_PATH__` placeholder is
    substituted with the absolute path to `.curator/Collections/`.
    """
    if paths.qmd_config_file.exists() and not overwrite:
        return False
    if not _QMD_TEMPLATE.exists():
        raise SearchBackendError(
            f"qmd config template missing at {_QMD_TEMPLATE}"
        )
    template = _QMD_TEMPLATE.read_text(encoding="utf-8")
    rendered = template.replace(
        "__COLLECTIONS_PATH__", str(paths.collections.resolve())
    )
    paths.qmd_dir.mkdir(parents=True, exist_ok=True)
    paths.qmd_config_file.write_text(rendered, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------


def update_index(paths: cfg.WikiPaths, *, embed: bool = False) -> None:
    """Refresh qmd's index for this project's Curator collection.

    Runs `qmd update` (re-indexes all configured collections) and optionally
    `qmd embed` to compute vector embeddings for semantic search.

    Requires `paths.qmd_config_file` to already exist — written by `wiki init`
    via `write_qmd_config()`.
    """
    if not paths.qmd_config_file.exists():
        raise SearchBackendError(
            f"qmd config not found at {paths.qmd_config_file}. "
            f"Run `wiki init` (or call search.write_qmd_config(paths)) first."
        )
    result = _run_qmd(
        ["update"], timeout=300, cwd=paths.collections, paths=paths
    )
    if result.returncode != 0:
        raise SearchBackendError(
            f"qmd update failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    if embed:
        result = _run_qmd(
            ["embed"], timeout=600, cwd=paths.collections, paths=paths
        )
        if result.returncode != 0:
            raise SearchBackendError(
                f"qmd embed failed (exit {result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


_QMD_URI_RE = re.compile(r"^/?qmd://[^/]+/")


def _normalize_qmd_path(raw: str) -> str:
    """Strip qmd://<collection>/ URI prefix and any leading slash."""
    cleaned = _QMD_URI_RE.sub("", raw)
    return cleaned.lstrip("/")


def _mode_to_subcommand(mode: str) -> str:
    """Map our 'hybrid'|'lex'|'vec' to qmd's subcommand."""
    if mode == "lex":
        return "search"     # BM25 only, no LLM
    if mode == "vec":
        return "vsearch"    # vector only, no rerank
    return "query"          # hybrid + rerank (default)


def query(
    paths: cfg.WikiPaths,
    question: str,
    *,
    mode: str = "hybrid",
    limit: int = 8,
    min_score: float = 0.0,
    collections: list[str] | None = None,
    hydrate: bool = True,
    rerank: bool = True,
) -> SearchResults:
    """Run a qmd search and return ranked, optionally hydrated, hits.

    Args:
        paths:        Wiki project paths.
        question:     User query string.
        mode:         'hybrid' (BM25+vec+rerank), 'lex' (BM25), 'vec' (vector).
        limit:        Max number of hits before min_score filtering.
        min_score:    Drop hits with score below this threshold.
        collections:  Restrict search to these qmd collection names. None ⇒ all.
                      The Curator uses a single 'curator' collection, so this
                      is rarely set; kept for caller flexibility.
        hydrate:      Re-fetch full markdown for each hit via `qmd get --full`.
        rerank:       Hybrid mode applies rerank by default; setting False
                      falls back to BM25 alone for speed.
    """
    subcmd = _mode_to_subcommand(mode)
    args: list[str] = [subcmd, question, "--json", "-n", str(limit)]

    # Hybrid mode without rerank → drop down to BM25-only `search`
    if mode == "hybrid" and not rerank:
        args[0] = "search"

    if collections:
        for col in collections:
            args.extend(["-c", col])

    result = _run_qmd(args, timeout=60, cwd=paths.collections, paths=paths)
    if result.returncode != 0:
        raise SearchBackendError(
            f"qmd {subcmd} failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )

    stdout_str = result.stdout or ""
    start_idx = stdout_str.find("[")
    if start_idx == -1:
        start_idx = stdout_str.find("{")

    end_idx = stdout_str.rfind("]")
    if end_idx == -1:
        end_idx = stdout_str.rfind("}")

    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        stdout_str = stdout_str[start_idx:end_idx + 1]

    if not stdout_str.strip():
        stdout_str = "[]"

    try:
        payload: Any = json.loads(stdout_str)
    except json.JSONDecodeError as e:
        raise SearchBackendError(f"qmd returned malformed JSON: {e}\nRaw output:\n{result.stdout}") from e

    raw_hits = payload if isinstance(payload, list) else payload.get("results", [])
    hits: list[SearchHit] = []
    for r in raw_hits:
        if not isinstance(r, dict):
            continue
        score = float(r.get("score", 0.0) or 0.0)
        if score < min_score:
            continue
        path = _normalize_qmd_path(str(r.get("file") or r.get("path") or ""))
        hits.append(
            SearchHit(
                full_path=path,
                title=str(r.get("title") or "").strip(),
                score=score,
                snippet=str(r.get("snippet") or r.get("context") or "").strip(),
                docid=str(r.get("docid") or "").lstrip("#"),
            )
        )

    if hydrate and hits:
        _hydrate_hits(paths, hits)

    return SearchResults(hits=hits)


def _hydrate_hits(paths: cfg.WikiPaths, hits: list[SearchHit]) -> None:
    """Populate `full_content` on each hit by reading from disk.

    Reading from disk is faster than spawning `qmd get` per hit, and the
    files are colocated with the Curator anyway. qmd's hits already give us
    the relative path inside the collection.
    """
    for hit in hits:
        if not hit.full_path:
            continue
        on_disk = paths.collections / hit.full_path
        if on_disk.exists() and on_disk.is_file():
            try:
                hit.full_content = on_disk.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
