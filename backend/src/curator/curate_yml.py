"""curate.yml — Knowledge Requirement Specification loader.

Each workspace in 01_Workspaces/{Project_Name}/ may carry a curate.yml
that declares:
  - sources: which files from 02_Wiki, 03_Notes, 04_Resources to pull in
  - domains/topics: relevance boost terms for search
  - min_confidence: confidence floor for surfaced evidence

Used by:
  - the QueryOrchestrator  →  the dynamic curation lens (KRS bias) over the DAG
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
class CurateReferenceMode:
    """Reference Mode policy for external sources (Zotero/linked PDFs)."""

    allow_external: bool = True
    require_rebind_approval: bool = True


@dataclass
class CurateGoal:
    """Why the workspace exists and what a successful Exhibition enables."""

    primary: str = ""
    audience: str = "generalist"  # researcher | engineer | learner | writer | generalist
    deliverables: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)


@dataclass
class CurateKnowledge:
    """Knowledge scope: domains, topics, disambiguation, false-merge guards."""

    domains: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    disambiguation_keywords: list[str] = field(default_factory=list)
    avoid_merges: list[str] = field(default_factory=list)


@dataclass
class CurateOutput:
    """Output contract for staged Exhibitions."""

    format: str = "exhibition"
    style: str = "dense-technical"
    citation_style: str = "curator-source-spans"
    include_sections: list[str] = field(default_factory=list)


@dataclass
class CurateReasoning:
    """Allowed retrieval/reasoning modes and exploration policy."""

    default_mode: str = "auto"
    allowed_modes: list[str] = field(
        default_factory=lambda: ["local", "global", "explore"]
    )
    exploration_enabled: bool = True
    max_followups: int = 5
    require_insight_candidates: bool = False


@dataclass
class CurateVerification:
    """Evidence verification policy."""

    min_confidence: float = 0.60
    high_threshold: float = 0.85
    require_source_spans: bool = True
    allow_general_knowledge: bool = False
    contradiction_policy: str = "surface-and-flag"  # surface-and-flag | merge-allowed | needs-review


@dataclass
class CurateBackprop:
    """Backprop / feedback policy."""

    enabled: bool = True
    source_truth_policy: str = "never_rewrite_original_source"
    derived_insight_policy: str = "record_then_promote_or_patch_generated"
    ambiguous_merge_policy: str = "needs_review"


@dataclass
class CuratePrompts:
    """Prompt profile and per-prompt overrides."""

    profile: str = "default"
    output_language: str = "same_as_latest_request"
    prompt_overrides: dict[str, str] = field(default_factory=dict)


@dataclass
class CurateSpec:
    """Parsed contents of a workspace curate.yml file.

    v0.3.1 adds the structured Knowledge Requirement Specification sections
    (goal, knowledge, output, reasoning, verification, backprop, prompts). The
    legacy ``persona``/``min_confidence`` fields remain for the current pipeline
    until it is rebuilt; the v0.3.1 ``CurationPolicy`` is compiled from the new
    sections, not from persona.
    """

    project: str
    description: str = ""
    vault_root: str = ""
    sources: CurateSources = field(default_factory=CurateSources)
    reference_mode: CurateReferenceMode = field(default_factory=CurateReferenceMode)
    min_confidence: float = 0.60
    persona: ArtistPersona = field(default_factory=ArtistPersona)
    # v0.3.1 KRS sections
    goal: CurateGoal = field(default_factory=CurateGoal)
    knowledge: CurateKnowledge = field(default_factory=CurateKnowledge)
    output: CurateOutput = field(default_factory=CurateOutput)
    reasoning: CurateReasoning = field(default_factory=CurateReasoning)
    verification: CurateVerification = field(default_factory=CurateVerification)
    backprop: CurateBackprop = field(default_factory=CurateBackprop)
    prompts: CuratePrompts = field(default_factory=CuratePrompts)

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

    # Reference Mode (nested under sources)
    ref_raw = sources_raw.get("reference_mode", {}) if isinstance(sources_raw, dict) else {}
    if isinstance(ref_raw, dict):
        reference_mode = CurateReferenceMode(
            allow_external=bool(ref_raw.get("allow_external", True)),
            require_rebind_approval=bool(ref_raw.get("require_rebind_approval", True)),
        )
    else:
        reference_mode = CurateReferenceMode()

    return CurateSpec(
        project=project.strip(),
        description=str(raw.get("description", "") or ""),
        vault_root=str(raw.get("vault_root", "") or ""),
        sources=sources,
        reference_mode=reference_mode,
        min_confidence=min_confidence,
        persona=artist_persona,
        goal=_parse_goal(raw.get("goal", {})),
        knowledge=_parse_knowledge(raw.get("knowledge", {})),
        output=_parse_output(raw.get("output", {})),
        reasoning=_parse_reasoning(raw.get("reasoning", {})),
        verification=_parse_verification(raw.get("verification", {}), min_confidence),
        backprop=_parse_backprop(raw.get("backprop", {})),
        prompts=_parse_prompts(raw.get("prompts", {})),
    )


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _parse_goal(raw: object) -> "CurateGoal":
    d = _as_dict(raw)
    return CurateGoal(
        primary=str(d.get("primary", "") or ""),
        audience=str(d.get("audience", "generalist") or "generalist"),
        deliverables=_str_list_from("deliverables", d),
        success_criteria=_str_list_from("success_criteria", d),
    )


def _parse_knowledge(raw: object) -> "CurateKnowledge":
    d = _as_dict(raw)
    return CurateKnowledge(
        domains=_str_list_from("domains", d),
        topics=_str_list_from("topics", d),
        disambiguation_keywords=_str_list_from("disambiguation_keywords", d),
        avoid_merges=_str_list_from("avoid_merges", d),
    )


def _parse_output(raw: object) -> "CurateOutput":
    d = _as_dict(raw)
    return CurateOutput(
        format=str(d.get("format", "exhibition") or "exhibition"),
        style=str(d.get("style", "dense-technical") or "dense-technical"),
        citation_style=str(d.get("citation_style", "curator-source-spans") or "curator-source-spans"),
        include_sections=_str_list_from("include_sections", d),
    )


def _parse_reasoning(raw: object) -> "CurateReasoning":
    d = _as_dict(raw)
    allowed = _str_list_from("allowed_modes", d)
    return CurateReasoning(
        default_mode=str(d.get("default_mode", "auto") or "auto"),
        allowed_modes=allowed or ["local", "global", "explore"],
        exploration_enabled=bool(d.get("exploration_enabled", True)),
        max_followups=int(d.get("max_followups", 5) or 5),
        require_insight_candidates=bool(d.get("require_insight_candidates", False)),
    )


def _parse_verification(raw: object, fallback_min_conf: float) -> "CurateVerification":
    d = _as_dict(raw)
    return CurateVerification(
        min_confidence=float(d.get("min_confidence", fallback_min_conf)),
        high_threshold=float(d.get("high_threshold", 0.85)),
        require_source_spans=bool(d.get("require_source_spans", True)),
        allow_general_knowledge=bool(d.get("allow_general_knowledge", False)),
        contradiction_policy=str(d.get("contradiction_policy", "surface-and-flag") or "surface-and-flag"),
    )


def _parse_backprop(raw: object) -> "CurateBackprop":
    d = _as_dict(raw)
    return CurateBackprop(
        enabled=bool(d.get("enabled", True)),
        source_truth_policy=str(d.get("source_truth_policy", "never_rewrite_original_source") or "never_rewrite_original_source"),
        derived_insight_policy=str(d.get("derived_insight_policy", "record_then_promote_or_patch_generated") or "record_then_promote_or_patch_generated"),
        ambiguous_merge_policy=str(d.get("ambiguous_merge_policy", "needs_review") or "needs_review"),
    )


def _parse_prompts(raw: object) -> "CuratePrompts":
    d = _as_dict(raw)
    overrides_raw = d.get("prompt_overrides", {})
    overrides = {str(k): str(v) for k, v in overrides_raw.items()} if isinstance(overrides_raw, dict) else {}
    return CuratePrompts(
        profile=str(d.get("profile", "default") or "default"),
        output_language=str(d.get("output_language", "same_as_latest_request") or "same_as_latest_request"),
        prompt_overrides=overrides,
    )


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


# ---------------------------------------------------------------------------
# v0.3.1 compiled curation policy
# ---------------------------------------------------------------------------

VALID_ROUTES: frozenset[str] = frozenset(
    {"local", "global", "explore", "source-section"}
)
VALID_AUDIENCES: frozenset[str] = frozenset(
    {"researcher", "engineer", "learner", "writer", "generalist"}
)
VALID_CONTRADICTION_POLICIES: frozenset[str] = frozenset(
    {"surface-and-flag", "merge-allowed", "needs-review"}
)


@dataclass(frozen=True)
class CurationPolicy:
    """Runtime policy compiled from a workspace's curate.yml.

    This is the executable form of the Knowledge Requirement Specification that
    drives source selection, query routing, verification, and backprop.
    """

    workspace_id: str
    project: str
    source_include: tuple[str, ...]
    source_exclude: tuple[str, ...]
    allowed_routes: frozenset[str]
    default_route: str
    prompt_profile: str
    output_language: str
    require_source_spans: bool
    allow_general_knowledge: bool
    contradiction_policy: str
    backprop_enabled: bool
    exploration_enabled: bool
    max_explore_followups: int
    min_confidence: float
    high_threshold: float
    avoid_merges: tuple[str, ...]


def _slug(name: str) -> str:
    return name.strip().replace(" ", "-").lower()


def workspace_id_for(workspace_path: Path | None, spec: CurateSpec) -> str:
    if workspace_path is not None:
        return workspace_path.name
    return _slug(spec.project) or "default"


def compile_curate_policy(
    spec: CurateSpec, workspace_path: Path | None = None
) -> CurationPolicy:
    """Compile a CurateSpec into an executable CurationPolicy."""
    allowed = frozenset(r for r in spec.reasoning.allowed_modes if r in VALID_ROUTES)
    if not allowed:
        allowed = VALID_ROUTES
    default_route = spec.reasoning.default_mode
    if default_route != "auto" and default_route not in allowed:
        default_route = "auto"
    return CurationPolicy(
        workspace_id=workspace_id_for(workspace_path, spec),
        project=spec.project,
        source_include=tuple(spec.sources.include),
        source_exclude=tuple(spec.sources.exclude),
        allowed_routes=allowed,
        default_route=default_route,
        prompt_profile=spec.prompts.profile,
        output_language=spec.prompts.output_language,
        require_source_spans=spec.verification.require_source_spans,
        allow_general_knowledge=spec.verification.allow_general_knowledge,
        contradiction_policy=spec.verification.contradiction_policy,
        backprop_enabled=spec.backprop.enabled,
        exploration_enabled=spec.reasoning.exploration_enabled,
        max_explore_followups=spec.reasoning.max_followups,
        min_confidence=spec.verification.min_confidence,
        high_threshold=spec.verification.high_threshold,
        avoid_merges=tuple(spec.knowledge.avoid_merges),
    )


def validate_curate_spec(spec: CurateSpec) -> list[str]:
    """Return a list of human-readable validation errors (empty = valid)."""
    errors: list[str] = []
    if not spec.project:
        errors.append("project must be a non-empty string")
    if spec.goal.audience and spec.goal.audience not in VALID_AUDIENCES:
        errors.append(
            f"goal.audience '{spec.goal.audience}' must be one of {sorted(VALID_AUDIENCES)}"
        )
    for mode in spec.reasoning.allowed_modes:
        if mode not in VALID_ROUTES:
            errors.append(f"reasoning.allowed_modes has unknown route '{mode}'")
    if spec.reasoning.default_mode not in VALID_ROUTES | {"auto"}:
        errors.append(
            f"reasoning.default_mode '{spec.reasoning.default_mode}' is not a valid route"
        )
    if (
        spec.reasoning.default_mode not in ("auto",)
        and spec.reasoning.default_mode not in spec.reasoning.allowed_modes
    ):
        errors.append(
            f"reasoning.default_mode '{spec.reasoning.default_mode}' is not in allowed_modes"
        )
    if spec.verification.contradiction_policy not in VALID_CONTRADICTION_POLICIES:
        errors.append(
            f"verification.contradiction_policy '{spec.verification.contradiction_policy}' is invalid"
        )
    for label, value in (
        ("verification.min_confidence", spec.verification.min_confidence),
        ("verification.high_threshold", spec.verification.high_threshold),
    ):
        if not 0.0 <= value <= 1.0:
            errors.append(f"{label} must be in [0.0, 1.0], got {value}")
    if spec.reasoning.max_followups < 0:
        errors.append("reasoning.max_followups must be >= 0")
    return errors


def curate_spec_hash(workspace_path: Path) -> str:
    """Stable hash of a workspace's curate.yml content (empty string if absent)."""
    import hashlib

    curate_file = workspace_path / consts.FILE_CURATE_YML
    if not curate_file.exists():
        return ""
    data = curate_file.read_bytes()
    return hashlib.sha256(data).hexdigest()[:16]
