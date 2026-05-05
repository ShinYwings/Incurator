"""curate.yml — Knowledge Requirement Specification loader.

Each workspace in 01_Workspaces/{Project_Name}/ may carry a curate.yml
that declares:
  - sources: which files from 02_Wiki, 03_Notes, 04_Resources to pull in
  - domains/topics: relevance filters for Exhibition staging
  - min_confidence: confidence floor for surfaced Exhibitions
  - scope: DAG layer restriction for search

Used by:
  - wiki curate --workspace  →  L4 Exhibition staging filtered by sources
  - search_curator MCP tool  →  scoped search with WORKSPACE_PATH env var
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


_VALID_SCOPES = frozenset(["all", "contexts", "atoms", "concepts", "exhibitions"])


@dataclass
class CurateSources:
    """Source selection: which vault files to pull knowledge from."""

    include: list[str] = field(default_factory=list)
    """Glob patterns relative to vault root, e.g. '03_Notes/**', '02_Wiki/ml/'.
    Empty list = include all sources (no filter)."""

    exclude: list[str] = field(default_factory=list)
    """Glob patterns to exclude, evaluated after include. E.g. '03_Notes/private/**'."""


@dataclass
class CurateSpec:
    """Parsed contents of a workspace curate.yml file."""

    project: str
    description: str = ""
    sources: CurateSources = field(default_factory=CurateSources)
    domains: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    min_confidence: float = 0.60
    scope: str = "all"

    def matches_sources(self, source_path: str) -> bool:
        """Check if source_path matches this spec's include/exclude patterns.

        source_path is relative to vault root (e.g. '03_Notes/ai/transformers.md').
        If no include patterns are set, all sources match.
        """
        if not self.sources.include:
            return True

        path = source_path.lstrip("/")
        # Strip wikilink brackets if present: [[03_Notes/foo]] → 03_Notes/foo
        path = path.strip("[]").lstrip("/")
        candidates = {path}
        if "." not in Path(path).name:
            candidates.add(f"{path}.md")

        # Exclusions take priority
        for pattern in self.sources.exclude:
            if _matches_any(candidates, pattern):
                return False

        # Check inclusions
        for pattern in self.sources.include:
            if _matches_any(candidates, pattern):
                return True

        return False

    def boost_query(self, base_query: str) -> str:
        """Append domain/topic terms to a search query for relevance boosting."""
        extras = self.topics + self.domains
        if not extras:
            return base_query
        return f"{base_query} {' '.join(extras)}"


def load_curate_spec(workspace_path: Path) -> Optional[CurateSpec]:
    """Load and validate curate.yml from workspace_path.

    Returns None if the file does not exist. Raises ValueError if the
    file exists but contains invalid values.
    """
    curate_file = workspace_path / "curate.yml"
    if not curate_file.exists():
        return None

    try:
        raw = yaml.safe_load(curate_file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"curate.yml parse error in {workspace_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"curate.yml in {workspace_path} must be a YAML mapping")

    project = raw.get("project", "")
    if not project or not isinstance(project, str):
        raise ValueError(f"curate.yml in {workspace_path}: 'project' must be a non-empty string")

    min_confidence = raw.get("min_confidence", 0.60)
    try:
        min_confidence = float(min_confidence)
    except (TypeError, ValueError):
        raise ValueError(f"curate.yml in {workspace_path}: 'min_confidence' must be a float")
    if not (0.0 <= min_confidence <= 1.0):
        raise ValueError(
            f"curate.yml in {workspace_path}: 'min_confidence' must be in [0.0, 1.0], got {min_confidence}"
        )

    scope = raw.get("scope", "all")
    if scope not in _VALID_SCOPES:
        raise ValueError(
            f"curate.yml in {workspace_path}: 'scope' must be one of {sorted(_VALID_SCOPES)}, got {scope!r}"
        )

    def _str_list(key: str) -> list[str]:
        val = raw.get(key, []) or []
        if not isinstance(val, list):
            return []
        return [str(v) for v in val if v]

    # Parse sources block
    sources_raw = raw.get("sources", {}) or {}
    if isinstance(sources_raw, dict):
        sources = CurateSources(
            include=_str_list_from("include", sources_raw),
            exclude=_str_list_from("exclude", sources_raw),
        )
    else:
        sources = CurateSources()

    return CurateSpec(
        project=project.strip(),
        description=str(raw.get("description", "") or ""),
        sources=sources,
        domains=_str_list("domains"),
        topics=_str_list("topics"),
        min_confidence=min_confidence,
        scope=scope,
    )


def _str_list_from(key: str, d: dict) -> list[str]:
    val = d.get(key, []) or []
    if not isinstance(val, list):
        return []
    return [str(v) for v in val if v]


def _pattern_variants(pattern: str) -> set[str]:
    p = pattern.lstrip("/")
    variants = {p}
    if p.endswith("/*.md"):
        variants.add(p.removesuffix("/*.md"))
    if "/**/" in p:
        variants.add(p.replace("/**/", "/"))
    if p.endswith("/**/*.md"):
        variants.add(p.removesuffix("/**/*.md"))
        variants.add(p.removesuffix("/**/*.md") + "/*.md")
    return variants


def _matches_any(paths: set[str], pattern: str) -> bool:
    variants = _pattern_variants(pattern)
    return any(fnmatch.fnmatch(path, variant) for path in paths for variant in variants)


def find_workspaces(vault_root: Path) -> list[tuple[Path, CurateSpec]]:
    """Return all (workspace_path, spec) pairs found under 01_Workspaces/.

    Silently skips directories where curate.yml is absent or malformed.
    """
    workspaces_dir = vault_root / "01_Workspaces"
    if not workspaces_dir.exists():
        return []

    results: list[tuple[Path, CurateSpec]] = []
    for candidate in sorted(workspaces_dir.iterdir()):
        if not candidate.is_dir() or candidate.name.startswith("."):
            continue
        try:
            spec = load_curate_spec(candidate)
        except ValueError:
            spec = None
        if spec is not None:
            results.append((candidate, spec))
    return results
