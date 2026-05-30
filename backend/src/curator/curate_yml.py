"""curate.yml — Knowledge Requirement Specification loader.

Each workspace in 01_Workspaces/{Project_Name}/ may carry a curate.yml
that declares:
  - sources: which files from 02_Wiki, 03_Notes, 04_Resources to pull in
  - domains/topics: relevance boost terms for search
  - min_confidence: confidence floor for surfaced Exhibitions
  - exhibition: active workspace Exhibition ID (auto-set by wiki curate)

Used by:
  - wiki curate --workspace  →  L4 Exhibition staging filtered by sources
  - search_curator MCP tool  →  scoped search with WORKSPACE_PATH env var
"""

from __future__ import annotations
from . import constants as consts

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class CurateSources:
    """Source selection: which vault files to pull knowledge from."""

    include: list[str] = field(default_factory=list)
    """Glob patterns relative to vault root, e.g. '03_Notes/**', '02_Wiki/ml/'.
    Empty list = include all sources (no filter)."""

    exclude: list[str] = field(default_factory=list)
    """Glob patterns to exclude, evaluated after include. E.g. '03_Notes/private/**'."""


@dataclass
class ArtistPersona:
    """Artist persona — workspace-level context for domain-specific curation tuning."""

    domain: str = ""
    subdomain: str = ""
    goal: str = ""
    exhibition_intent: str = "engineer"  # researcher | engineer | learner
    disambiguation_keywords: list[str] = field(default_factory=list)
    confidence: dict = field(default_factory=lambda: {"high_threshold": 0.85, "low_threshold": 0.55})
    updated_at: str = ""


@dataclass
class CurateSpec:
    """Parsed contents of a workspace curate.yml file."""

    project: str
    description: str = ""
    vault_root: str = ""
    sources: CurateSources = field(default_factory=CurateSources)
    min_confidence: float = 0.60
    exhibition: str = ""
    persona: ArtistPersona = field(default_factory=ArtistPersona)

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
        extras = []
        if self.persona.domain:
            extras.append(self.persona.domain)
        if self.persona.subdomain:
            extras.append(self.persona.subdomain)
        if self.persona.disambiguation_keywords:
            extras.extend(self.persona.disambiguation_keywords)
        
        if not extras:
            return base_query
        return f"{base_query} {' '.join(extras)}"


def load_curate_spec(workspace_path: Path) -> Optional[CurateSpec]:
    """Load and validate curate.yml from workspace_path.

    Returns None if the file does not exist. Raises ValueError if the
    file exists but contains invalid values.
    """
    curate_file = workspace_path / consts.FILE_CURATE_YML
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

    # Parse persona block
    persona_raw = raw.get("persona", {}) or {}
    if isinstance(persona_raw, dict):
        conf_raw = persona_raw.get("confidence", {}) or {}
        if isinstance(conf_raw, dict):
            confidence = {
                "high_threshold": float(conf_raw.get("high_threshold", 0.85)),
                "low_threshold": float(conf_raw.get("low_threshold", 0.55)),
            }
        else:
            confidence = {"high_threshold": 0.85, "low_threshold": 0.55}
        artist_persona = ArtistPersona(
            domain=str(persona_raw.get("domain", "") or ""),
            subdomain=str(persona_raw.get("subdomain", "") or ""),
            # "goal" is canonical; "text" is accepted as fallback for forward compat
            goal=str(persona_raw.get("goal", persona_raw.get("text", "")) or ""),
            exhibition_intent=str(persona_raw.get("exhibition_intent", "engineer") or "engineer"),
            disambiguation_keywords=_str_list_from("disambiguation_keywords", persona_raw),
            confidence=confidence,
            updated_at=str(persona_raw.get("updated_at", "") or ""),
        )
    else:
        artist_persona = ArtistPersona()

    return CurateSpec(
        project=project.strip(),
        description=str(raw.get("description", "") or ""),
        vault_root=str(raw.get("vault_root", "") or ""),
        sources=sources,
        min_confidence=min_confidence,
        exhibition=str(raw.get("exhibition", "") or ""),
        persona=artist_persona,
    )


def write_exhibition_to_spec(workspace_path: Path, exh_id: str) -> None:
    """Update the `exhibition` field in curate.yml with the given EXH-ID.

    Reads the file as raw text and does a targeted replacement so that
    comments and formatting are preserved.
    """
    curate_file = workspace_path / consts.FILE_CURATE_YML
    if not curate_file.exists():
        return
    text = curate_file.read_text(encoding="utf-8")
    import re
    # Replace existing exhibition: "..." line (with or without quotes)
    new_line = f'exhibition: "{exh_id}"'
    if re.search(r'^exhibition:', text, re.MULTILINE):
        text = re.sub(r'^exhibition:.*$', new_line, text, flags=re.MULTILINE)
    else:
        text = text.rstrip() + f"\n{new_line}\n"
    curate_file.write_text(text, encoding="utf-8")


def _str_list_from(key: str, d: dict) -> list[str]:
    val = d.get(key, []) or []
    if not isinstance(val, list):
        return []
    return [str(v) for v in val if v]





def _matches_any(paths: set[str], pattern: str) -> bool:
    import re
    # Convert glob pattern to regex
    # Escaping special characters but keeping * and **
    regex_pattern = re.escape(pattern.lstrip("/"))
    # ** matches any characters including /
    regex_pattern = regex_pattern.replace(r"\*\*", ".*")
    # * matches any characters except /
    regex_pattern = regex_pattern.replace(r"\*", "[^/]*")
    # Add start/end anchors
    regex_pattern = f"^{regex_pattern}$"
    
    try:
        compiled = re.compile(regex_pattern)
    except re.error:
        # Fallback to literal match if regex is invalid
        return any(p.lstrip("/") == pattern.lstrip("/") for p in paths)

    return any(compiled.match(p.lstrip("/")) for p in paths)


def find_workspaces(vault_root: Path) -> list[tuple[Path, CurateSpec]]:
    """Return all (workspace_path, spec) pairs found under 01_Workspaces/.

    Silently skips directories where curate.yml is absent or malformed.
    """
    workspaces_dir = vault_root / consts.DIR_WORKSPACES
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
