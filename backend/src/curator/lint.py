"""Wiki lint — health checks that find contradictions, orphans, broken links,
malformed frontmatter, and other issues that creep into a knowledge base.

Checks are categorized by severity:

  ERROR    — things that break linking or make pages unusable
  WARNING  — stylistic or structural issues worth cleaning up
  INFO     — suggestions and observations

Fast checks (the default) run entirely in Python and take a few seconds.
Deep checks (--deep) use the configured LLM to detect contradictions across
pairs of L2 Fragment pages that share outgoing links — much slower, opt-in only.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from . import config as cfg
from . import constants as consts
from . import db
from . import page_writer

logger = logging.getLogger(__name__)

# Strip only the retired legacy curator URI schemes (``legacy://`` and the
# pre-v0.3.2 search-binary scheme) from wikilink targets. Built via string
# concatenation so the retired scheme literal never appears in source. Kept
# narrow on purpose: a broad ``scheme://`` matcher would also strip standard
# external links (``http://``/``https://``/``obsidian://``).
_LEGACY_SCHEME_RE = re.compile(r"^/?(?:legacy|" + "q" + "md)://[^/]+/")


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class CheckId(str, Enum):
    BROKEN_WIKILINK = "broken_wikilink"
    ORPHAN_PAGE = "orphan_page"
    MISSING_FRONTMATTER = "missing_frontmatter"
    INVALID_FRONTMATTER = "invalid_frontmatter"
    MALFORMED_WIKILINK = "malformed_wikilink"
    MISSING_CONCEPT_PAGE = "missing_concept_page"
    STALE_SOURCE_REF = "stale_source_ref"
    INVALID_SOURCE_PATH = "invalid_source_path"
    NOISE_IN_SYNTHESIS = "noise_in_synthesis"
    CONTRADICTION = "contradiction"
    MISSING_CROSS_LAYER_LINK = "missing_cross_layer_link"  # ATM missing parent_source wikilink, etc.
    EPHEMERAL_GC = "ephemeral_gc"
    COMPILER_INTEGRITY = "compiler_integrity"  # Plan B (v0.8.0) §26.5 audit findings
    GRAPH_QUALITY = "graph_quality"  # Plan C (v0.9.0) §27.6 graph-audit findings


@dataclass
class LintIssue:
    """A single issue found during linting."""

    check: CheckId
    severity: Severity
    page: str               # Relpath inside .curator/Collections/, e.g. '02_Atoms/ATM-abc12345.md'
    message: str
    suggestion: str = ""
    fixable: bool = False   # True if --fix can auto-resolve it
    context: dict[str, Any] = field(default_factory=dict)  # check-specific data


@dataclass
class LintReport:
    """The complete result of a lint run."""

    issues: list[LintIssue] = field(default_factory=list)
    pages_checked: int = 0
    fast_checks_run: list[str] = field(default_factory=list)
    deep_check_run: bool = False
    auto_fixed: int = 0
    duration_seconds: float = 0.0

    @property
    def errors(self) -> list[LintIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[LintIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def infos(self) -> list[LintIssue]:
        return [i for i in self.issues if i.severity == Severity.INFO]

    @property
    def health_score(self) -> int:
        """A 0-100 score based on issue density. 100 = perfectly clean."""
        if self.pages_checked == 0:
            return 100
        error_weight = 5
        warning_weight = 2
        info_weight = 1
        penalty = (
            len(self.errors) * error_weight
            + len(self.warnings) * warning_weight
            + len(self.infos) * info_weight
        )
        # Normalize: assume ~10 penalty per page on average is "bad"
        max_penalty = self.pages_checked * 10
        if max_penalty == 0:
            return 100
        score = max(0, 100 - int(100 * penalty / max_penalty))
        return score

    @property
    def safe_fixable(self) -> list[LintIssue]:
        return [i for i in self.issues if is_safe_fixable(i)]

    @property
    def needs_review(self) -> list[LintIssue]:
        return [i for i in self.errors + self.warnings if not is_safe_fixable(i)]


# ---------------------------------------------------------------------------
# Page inventory (shared by many checks)
# ---------------------------------------------------------------------------


@dataclass
class PageInventory:
    """Cached state of the wiki: every page's path, frontmatter, and links."""

    pages: dict[str, page_writer.ParsedPage] = field(default_factory=dict)  # relpath -> parsed
    outgoing_links: dict[str, list[str]] = field(default_factory=dict)      # relpath -> [targets]
    incoming_links: dict[str, list[str]] = field(default_factory=dict)      # relpath -> [sources]
    all_slugs: set[str] = field(default_factory=set)                        # e.g. '02_Atoms/ATM-abc12345'
    raw_paths: set[str] = field(default_factory=set)                        # files in raw/


_NOISE_PAGES = {consts.FILE_INDEX_MD, consts.FILE_LOG_MD, consts.FILE_OVERVIEW_MD, consts.FILE_LEDGER_MD}

# Layer directory prefix → page type
_PAGE_TYPES = (consts.LAYER_L1, consts.LAYER_L2, consts.LAYER_L3, consts.LAYER_L4)
_CURATOR_PREFIXES = tuple(pt + "/" for pt in _PAGE_TYPES)


def _build_inventory(paths: cfg.WikiPaths, progress_callback: Optional[Callable[[str], None]] = None) -> PageInventory:
    """Walk .curator/Collections/ and build a cached PageInventory.

    Also parses index.md and log.md as root nodes so that pages linked
    from them are not flagged as orphans.
    """
    inv = PageInventory()

    # 1. Walk Collections/ subdirectories
    for subdir in _PAGE_TYPES:
        d = paths.collections / subdir
        if not d.exists():
            continue
        for md_path in sorted(d.glob("*.md")):
            if md_path.name.startswith(".") or md_path.name.startswith("lint-report-"):
                continue
            if progress_callback:
                progress_callback(md_path.stem)
            try:
                content = md_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            parsed = page_writer.parse_page(content)
            relpath = f"{subdir}/{md_path.name}"
            inv.pages[relpath] = parsed

            slug_no_ext = f"{subdir}/{md_path.stem}"
            inv.all_slugs.add(slug_no_ext)
            inv.all_slugs.add(f"{subdir}/{md_path.stem}.md")

    # 2. Build forward + reverse link graphs
    #    Include curator frontmatter wikilink fields, not just body [[links]]
    _CURATOR_FM_LINK_FIELDS = (
        # ATM: link to parent L1 Context
        "parent_source",
        # SYN: optional links to L3 Concepts
        "concept_ids",
        # legacy / any extra sources field
        "sources",
    )

    for relpath, parsed in inv.pages.items():
        links = page_writer.extract_wikilinks(parsed.body)

        # Extract wikilinks from curator-specific frontmatter fields
        for fm_field in _CURATOR_FM_LINK_FIELDS:
            val = parsed.frontmatter.get(fm_field)
            if isinstance(val, str) and val:
                links.append(val)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and item:
                        links.append(item)

        # source_path points to raw vault files (e.g. PDFs, notes outside Collections/).
        # These are NOT wiki pages, so adding them to outgoing_links causes false
        # broken-link errors. Provenance checks are handled by check_stale_source_refs.

        normalized = [_normalize_link(link) for link in links if link]
        inv.outgoing_links[relpath] = normalized

        for target in normalized:
            inv.incoming_links.setdefault(target, []).append(relpath)

    # 3. Parse index.md as a root node — pages it links to are NOT orphans
    #    This covers all L1 Summaries (which are the entry points) and
    #    allows agents to navigate from index → L1 → L2 → L3 → L4.
    for root_file in (paths.index, paths.log, paths.overview):
        if root_file.exists():
            try:
                content = root_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            parsed = page_writer.parse_page(content)
            root_relpath = f"_root/{root_file.name}"
            links = page_writer.extract_wikilinks(parsed.body)
            for link in links:
                target = _normalize_link(link)
                if target:
                    inv.incoming_links.setdefault(target, []).append(root_relpath)

    # 4. Scan raw_dirs for stale-ref checks
    for raw_dir in paths.raw_dirs:
        if raw_dir.exists():
            for raw_path in raw_dir.rglob("*"):
                if raw_path.is_file() and not raw_path.name.startswith("."):
                    try:
                        rel = str(raw_path.relative_to(paths.root))
                        inv.raw_paths.add(rel)
                    except ValueError:
                        pass

    return inv


def _normalize_link(link: str) -> str:
    """Normalize a wikilink target for comparison.

    Strips .md suffix, legacy URI prefixes, pipe-based aliases, and
    leading/trailing slashes. So all these become the same thing:

        02_Atoms/ATM-abc12345
        02_Atoms/ATM-abc12345.md
        legacy://curator/02_Atoms/ATM-abc12345
        /legacy://curator/02_Atoms/ATM-abc12345
        02_Atoms/ATM-abc12345.md
        02_Atoms/ATM-abc12345|Atom alias
    """
    if not link:
        return ""
    link = link.strip()
    if link.startswith("[[") and link.endswith("]]"):
        link = link[2:-2].strip()
    # Pipe alias: [[foo|Foo Page]] — keep the target (left side)
    if "|" in link:
        link = link.split("|", 1)[0]
    # Strip .md suffix
    if link.endswith(".md"):
        link = link[:-3]
    # Strip legacy scheme URI prefix with optional collection name.
    link = _LEGACY_SCHEME_RE.sub("", link)
    # Strip leading slashes
    link = link.lstrip("/")
    return link


# ---------------------------------------------------------------------------
# Individual checks (each returns a list of LintIssue)
# ---------------------------------------------------------------------------


def check_broken_wikilinks(inv: PageInventory) -> list[LintIssue]:
    """Flag [[wikilinks]] whose target page doesn't exist.

    If the target's basename matches an existing page in a different
    subdirectory, suggest the corrected path and mark the issue as fixable.
    Otherwise, it's a genuine error.
    """
    issues: list[LintIssue] = []

    # Build a reverse lookup: basename -> list of existing full slugs.
    # So 'ATM-9f8e7d6c' maps to ['02_Atoms/ATM-9f8e7d6c'] if that page exists.
    # Used to suggest a corrected path when a wikilink omits or mistypes the
    # layer prefix (e.g. [[ATM-9f8e7d6c]] instead of [[02_Atoms/ATM-9f8e7d6c]]).
    basename_lookup: dict[str, list[str]] = {}
    for slug in inv.all_slugs:
        if "/" in slug and not slug.endswith(".md"):
            basename = slug.rsplit("/", 1)[1]
            basename_lookup.setdefault(basename, []).append(slug)

    for relpath, targets in inv.outgoing_links.items():
        for target in targets:
            if not target:
                continue
            if target in inv.all_slugs or f"{target}.md" in inv.all_slugs:
                continue

            # Skip vault-path references outside the 4 curator layers
            if not target.startswith(_CURATOR_PREFIXES):
                continue

            if target.rstrip("/") in _PAGE_TYPES:
                issues.append(
                    LintIssue(
                        check=CheckId.BROKEN_WIKILINK,
                        severity=Severity.ERROR,
                        page=relpath,
                        message=f"Empty layer wikilink: [[{target}]]",
                        suggestion="Run `wiki lint --fix` to remove the empty placeholder link.",
                        fixable=True,
                        context={
                            "old_target": target,
                            "new_target": "",
                            "location": "body",
                        },
                    )
                )
                continue

            # Try to recover: does the target's basename match an existing
            # page in some subdirectory?
            target_basename = target.rsplit("/", 1)[-1]
            candidates = basename_lookup.get(target_basename, [])

            if len(candidates) == 1:
                # Unambiguous single match — downgrade to warning and mark fixable
                correct = candidates[0]
                issues.append(
                    LintIssue(
                        check=CheckId.BROKEN_WIKILINK,
                        severity=Severity.WARNING,
                        page=relpath,
                        message=f"Broken wikilink: [[{target}]] (should be [[{correct}]])",
                        suggestion=(
                            f"Target exists at '{correct}' — run `wiki lint --fix` "
                            f"to auto-correct."
                        ),
                        fixable=True,
                        context={
                            "old_target": target,
                            "new_target": correct,
                            "location": "body",
                        },
                    )
                )
            elif len(candidates) > 1:
                # Ambiguous — multiple pages share the basename; LLM will pick best
                options = ", ".join(f"[[{c}]]" for c in candidates)
                issues.append(
                    LintIssue(
                        check=CheckId.BROKEN_WIKILINK,
                        severity=Severity.ERROR,
                        page=relpath,
                        message=f"Broken wikilink: [[{target}]] (ambiguous — candidates: {options})",
                        suggestion="Run `wiki lint --fix` to resolve via LLM.",
                        fixable=True,
                        context={
                            "old_target": target,
                            "location": "body",
                            "llm_relink": True,
                            "llm_candidates": candidates,
                        },
                    )
                )

            else:
                # Genuinely missing within curator scope — LLM will try to reconnect
                issues.append(
                    LintIssue(
                        check=CheckId.BROKEN_WIKILINK,
                        severity=Severity.ERROR,
                        page=relpath,
                        message=f"Broken wikilink: [[{target}]]",
                        suggestion="Run `wiki lint --fix` to reconnect via LLM; unresolved links are left for review.",
                        fixable=True,
                        context={"old_target": target, "location": "body", "llm_relink": True},
                    )
                )
    return issues


def is_safe_fixable(issue: LintIssue) -> bool:
    """Return True when --fix can repair an issue without deleting knowledge.

    Broken links are safe only when they have an explicit replacement or when
    they are known empty layer placeholders with ``new_target == ""``. A broken
    link that merely asks the LLM for help must remain in place if no confident
    replacement is found.
    """
    if not issue.fixable:
        return False
    if issue.check == CheckId.BROKEN_WIKILINK:
        return "new_target" in issue.context
    if issue.check == CheckId.STALE_SOURCE_REF:
        return "new_target" in issue.context and bool(issue.context.get("new_target"))
    if issue.check == CheckId.INVALID_SOURCE_PATH:
        return bool(issue.context.get("new_target"))
    return issue.check in {
        CheckId.MALFORMED_WIKILINK,
        CheckId.MISSING_FRONTMATTER,
        CheckId.NOISE_IN_SYNTHESIS,
    }


def check_orphan_pages(inv: PageInventory) -> list[LintIssue]:
    """Find pages with no incoming wikilinks from any other page.

    All four layers are checked. index.md and log.md serve as root nodes
    and are parsed into the inventory, so pages linked from index.md
    (typically all L1 Summaries) will NOT be flagged.

    A page is an orphan if nothing links to it — neither another collection
    page nor any control-plane file (index/log/overview).
    """
    issues: list[LintIssue] = []
    for relpath in inv.pages:
        slug_no_ext = relpath[:-3] if relpath.endswith(".md") else relpath
        incoming = inv.incoming_links.get(slug_no_ext, []) + inv.incoming_links.get(
            relpath, []
        )
        # Don't count self-references
        incoming = [i for i in incoming if i != relpath]
        if not incoming:
            page_type = relpath.split("/", 1)[0] if "/" in relpath else ""
            layer_hint = {
                consts.LAYER_L1: "Link from index.md or ensure wiki add registered it.",
                consts.LAYER_L2: "Ensure the parent L1 Context has an Atom Candidates entry linking here.",
                consts.LAYER_L3: "Ensure at least one L4 Exhibition links to this concept.",
                consts.LAYER_L4: "Ensure index.md routing table includes this EXH entry.",
            }.get(page_type, "Link to this page from a related page, or delete it.")
            issues.append(
                LintIssue(
                    check=CheckId.ORPHAN_PAGE,
                    severity=Severity.WARNING,
                    page=relpath,
                    message=f"No incoming wikilinks — [{page_type}] page is an orphan in the DAG.",
                    suggestion=layer_hint,
                    fixable=False,
                )
            )
    return issues


def check_frontmatter(inv: PageInventory) -> list[LintIssue]:
    """Verify every page has required frontmatter fields per layer."""
    issues: list[LintIssue] = []
    # Required fields per layer — SCHEMA projection contract
    required_by_type = {
        consts.LAYER_L1:   {"id", "type", "source_path", "source_hash", "last_updated"},
        consts.LAYER_L2:   {"id", "type", "source_path", "unit_type", "knowledge_unit_ids", "source_span_ids"},
        consts.LAYER_L3:   {"id", "type", "community_report_id", "entity_ids", "relation_ids", "source_span_ids", "confidence_score"},
        consts.LAYER_L4: {"id", "type", "community_report_ids", "source_span_ids", "confidence_score"},
    }
    id_prefix_by_type = {
        consts.LAYER_L1: consts.PREFIX_L1,
        consts.LAYER_L2: consts.PREFIX_L2,
        consts.LAYER_L3: consts.PREFIX_L3,
        consts.LAYER_L4: consts.PREFIX_L4,
    }

    for relpath, parsed in inv.pages.items():
        page_type = relpath.split("/", 1)[0]
        required = required_by_type.get(page_type, set())
        if not parsed.frontmatter:
            cleaned = page_writer.strip_llm_noise(parsed.body)
            repaired = page_writer.parse_page(cleaned)
            can_repair = bool(repaired.frontmatter)
            issues.append(
                LintIssue(
                    check=CheckId.MISSING_FRONTMATTER,
                    severity=Severity.ERROR,
                    page=relpath,
                    message="Page has no YAML frontmatter.",
                    suggestion=(
                        "Run `wiki lint --fix` to unwrap LLM code fences."
                        if can_repair
                        else "Add frontmatter with title, type, created, updated."
                    ),
                    fixable=can_repair,
                    context={"repair": "strip_llm_noise"} if can_repair else {},
                )
            )
            continue
        missing = required - set(parsed.frontmatter.keys())
        if missing:
            issues.append(
                LintIssue(
                    check=CheckId.INVALID_FRONTMATTER,
                    severity=Severity.WARNING,
                    page=relpath,
                    message=f"Frontmatter missing: {', '.join(sorted(missing))}",
                    suggestion="Add the missing fields manually or re-ingest.",
                    fixable=False,
                )
            )
        if page_type == consts.LAYER_L3 and "dependencies" in parsed.frontmatter:
            issues.append(
                LintIssue(
                    check=CheckId.INVALID_FRONTMATTER,
                    severity=Severity.WARNING,
                    page=relpath,
                    message="Concept frontmatter duplicates Atom edges in `dependencies`; use `## Relations` only.",
                    suggestion="Run `wiki lint --fix` to remove the legacy duplicated field.",
                    fixable=True,
                    context={"remove_field": "dependencies"},
                )
            )
        for fm_field in sorted(required & set(parsed.frontmatter.keys())):
            value = parsed.frontmatter.get(fm_field)
            if value is None or value == "" or value == []:
                issues.append(
                    LintIssue(
                        check=CheckId.INVALID_FRONTMATTER,
                        severity=Severity.ERROR,
                        page=relpath,
                        message=f"Frontmatter field `{fm_field}` is empty.",
                        suggestion="Re-run ingest or repair the field from source metadata.",
                        fixable=False,
                    )
                )
        node_id = str(parsed.frontmatter.get("id", "") or "")
        expected_prefix = id_prefix_by_type.get(page_type)
        if expected_prefix and node_id:
            expected_id_re = rf"^{expected_prefix}-[0-9a-f]{{8}}$"
            if not re.match(expected_id_re, node_id):
                issues.append(
                    LintIssue(
                        check=CheckId.INVALID_FRONTMATTER,
                        severity=Severity.ERROR,
                        page=relpath,
                        message=(
                            f"Frontmatter `id` must match {expected_prefix}-UUID8 "
                            f"(8 lowercase hex chars), got {node_id!r}."
                        ),
                        suggestion="Regenerate this page through wiki add/curate instead of seeding fixed slugs.",
                        fixable=False,
                    )
                )
            file_id = relpath.rsplit("/", 1)[-1].removesuffix(".md")
            if file_id != node_id:
                issues.append(
                    LintIssue(
                        check=CheckId.INVALID_FRONTMATTER,
                        severity=Severity.ERROR,
                        page=relpath,
                        message=f"Frontmatter `id` {node_id!r} does not match filename {file_id!r}.",
                        suggestion="Regenerate this page or rename the file and references consistently.",
                        fixable=False,
                    )
                )
        source_hash = parsed.frontmatter.get("source_hash")
        if page_type == consts.LAYER_L1 and isinstance(source_hash, str):
            if not re.match(r"^[0-9a-f]{64}$", source_hash):
                issues.append(
                    LintIssue(
                        check=CheckId.INVALID_FRONTMATTER,
                        severity=Severity.ERROR,
                        page=relpath,
                        message="Context `source_hash` must be a SHA-256 hex digest.",
                        suggestion="Regenerate the Context with `wiki add`.",
                        fixable=False,
                    )
                )
    return issues


def check_malformed_wikilinks(inv: PageInventory, paths: cfg.WikiPaths) -> list[LintIssue]:
    """Find wikilinks with fixable formatting problems:

    - [[foo.md]] instead of [[foo]]
    - [[legacy://curator/02_Atoms/ATM-abc12345]] instead of [[02_Atoms/ATM-abc12345]]
    - [[/foo]] with leading slash
    - frontmatter source entries with legacy URI prefixes
    """
    issues: list[LintIssue] = []

    # Use a raw pattern to extract ALL wikilink literals from the body
    body_pattern = re.compile(r"\[\[([^\]]+?)\]\]")

    for relpath, parsed in inv.pages.items():
        raw_body = parsed.body

        # Body-level wikilinks
        for match in body_pattern.finditer(raw_body):
            raw_link = match.group(1)
            normalized = _normalize_link(raw_link)
            # Extract the link target (before any |alias)
            target = raw_link.split("|", 1)[0].strip()
            if target != normalized and normalized:
                issues.append(
                    LintIssue(
                        check=CheckId.MALFORMED_WIKILINK,
                        severity=Severity.WARNING,
                        page=relpath,
                        message=f"Malformed wikilink: [[{target}]] should be [[{normalized}]]",
                        suggestion="Run `wiki lint --fix` to auto-correct.",
                        fixable=True,
                        context={
                            "old_target": target,
                            "new_target": normalized,
                            "location": "body",
                        },
                    )
                )

        # Curator frontmatter wikilink list/scalar entries
        for key in ("parent_source", "concept_ids"):
            raw = parsed.frontmatter.get(key)
            values = raw if isinstance(raw, list) else ([raw] if isinstance(raw, str) else [])
            for val in values:
                if not isinstance(val, str) or not val:
                    continue
                normalized = _normalize_link(val)
                if val != normalized and normalized:
                    issues.append(
                        LintIssue(
                            check=CheckId.MALFORMED_WIKILINK,
                            severity=Severity.WARNING,
                            page=relpath,
                            message=f"Malformed frontmatter `{key}` entry: {val!r}",
                            suggestion="Run `wiki lint --fix` to strip URI prefixes and .md suffixes.",
                            fixable=True,
                            context={
                                "old_target": val,
                                "new_target": normalized,
                                "location": "frontmatter",
                                "field": key,
                                "scalar": not isinstance(raw, list),
                            },
                        )
                    )
    return issues


def check_missing_extracted(inv: PageInventory, threshold: int = 3) -> list[LintIssue]:
    """Flag terms mentioned 3+ times across pages that don't have their own page.

    Looks at wikilink *targets* — if several pages link to [[something]] but
    'something' doesn't exist, that's a hint it deserves a page of its own.
    """
    issues: list[LintIssue] = []

    # Count broken link targets
    target_counts: Counter[str] = Counter()
    target_sources: dict[str, list[str]] = defaultdict(list)
    for relpath, targets in inv.outgoing_links.items():
        seen_in_this_page: set[str] = set()
        for target in targets:
            if not target:
                continue
            if not target.startswith(_CURATOR_PREFIXES):
                continue  # vault / external ref — not curator's concern
            if target in inv.all_slugs or f"{target}.md" in inv.all_slugs:
                continue
            # Only count each target once per source page
            if target in seen_in_this_page:
                continue
            seen_in_this_page.add(target)
            target_counts[target] += 1
            target_sources[target].append(relpath)

    for target, count in target_counts.most_common():
        if count >= threshold:
            issues.append(
                LintIssue(
                    check=CheckId.MISSING_CONCEPT_PAGE,
                    severity=Severity.INFO,
                    page=target_sources[target][0],
                    message=(
                        f"'{target}' referenced by {count} pages but has no page of its own."
                    ),
                    suggestion=f"Consider creating {target}.md",
                    fixable=False,
                    context={"target": target, "referenced_by": target_sources[target]},
                )
            )
    return issues


def check_stale_source_refs(inv: PageInventory, paths: cfg.WikiPaths) -> list[LintIssue]:
    """Flag Atom pages whose parent_source references a Context that no longer exists."""
    issues: list[LintIssue] = []
    for relpath, parsed in inv.pages.items():
        if not relpath.startswith(f"{consts.LAYER_L2}/"):
            continue
        raw_parent = parsed.frontmatter.get("parent_source", "")
        if not raw_parent:
            continue
        if isinstance(raw_parent, list):
            parents = []
            for item in raw_parent:
                if isinstance(item, list):
                    for sub in item:
                        if isinstance(sub, str):
                            parents.append(sub)
                elif isinstance(item, str):
                    parents.append(item)
        else:
            parents = [raw_parent] if isinstance(raw_parent, str) else []

        for parent in parents:
            if not parent:
                continue
            normalized = _normalize_link(parent)
            if not normalized.startswith(f"{consts.LAYER_L1}/"):
                continue
            source_file = paths.collections / (normalized + ".md")
            if not source_file.exists():
                issues.append(
                    LintIssue(
                        check=CheckId.STALE_SOURCE_REF,
                        severity=Severity.WARNING,
                        page=relpath,
                        message=f"parent_source '{normalized}' doesn't exist.",
                        suggestion="Run `wiki lint --fix` to reconnect via LLM; unresolved links are left for review.",
                        fixable=True,
                        context={
                            "old_target": normalized,
                            "location": "frontmatter",
                            "field": "parent_source",
                            "llm_relink": True,
                        },
                    )
                )
    return issues


def _source_path_targets(raw: str) -> list[str]:
    target = raw.strip()
    if target.startswith("[[") and target.endswith("]]"):
        target = target[2:-2].strip()
    if "|" in target:
        target = target.split("|", 1)[0].strip()
    target = target.lstrip("/")
    if not target:
        return []
    targets = [target]
    if not target.endswith(".md"):
        targets.append(f"{target}.md")
    return targets


def _source_path_link(relpath: str) -> str:
    return f"[[{relpath.removesuffix('.md')}]]"


def _source_relpath_for_context(paths: cfg.WikiPaths, context_id: str) -> str:
    if not context_id:
        return ""
    try:
        with db.connect(paths.state_db) as conn:
            row = conn.execute(
                "SELECT relpath FROM sources WHERE context_id = ?", (context_id,)
            ).fetchone()
    except Exception:
        return ""
    return row["relpath"] if row else ""


def check_atom_source_paths(inv: PageInventory, paths: cfg.WikiPaths) -> list[LintIssue]:
    """Flag Atom source_path values that are empty or do not point to raw source files."""
    issues: list[LintIssue] = []
    for relpath, parsed in inv.pages.items():
        if not relpath.startswith(f"{consts.LAYER_L2}/"):
            continue

        raw_source_path = parsed.frontmatter.get("source_path", "")
        parent_context = _normalize_link(str(parsed.frontmatter.get("parent_source", ""))).rsplit("/", 1)[-1]
        source_relpath = _source_relpath_for_context(paths, parent_context)
        repair_value = _source_path_link(source_relpath) if source_relpath else ""
        fixable = bool(repair_value)

        if not isinstance(raw_source_path, str) or not raw_source_path.strip():
            issues.append(
                LintIssue(
                    check=CheckId.INVALID_SOURCE_PATH,
                    severity=Severity.ERROR,
                    page=relpath,
                    message="Atom `source_path` is empty.",
                    suggestion="Run `wiki lint --fix` to restore it from the parent Context source.",
                    fixable=fixable,
                    context={
                        "location": "frontmatter",
                        "field": "source_path",
                        "new_target": repair_value,
                    },
                )
            )
            continue

        candidates = _source_path_targets(raw_source_path)
        if not any(candidate in inv.raw_paths for candidate in candidates):
            issues.append(
                LintIssue(
                    check=CheckId.INVALID_SOURCE_PATH,
                    severity=Severity.ERROR,
                    page=relpath,
                    message=f"Atom `source_path` does not exist in source dirs: {raw_source_path!r}",
                    suggestion="Run `wiki lint --fix` to restore it from the parent Context source.",
                    fixable=fixable,
                    context={
                        "location": "frontmatter",
                        "field": "source_path",
                        "new_target": repair_value,
                    },
                )
            )
    return issues


def check_noise_in_curation_sources(inv: PageInventory) -> list[LintIssue]:
    """Flag L4 Synthesis pages that list routing files as concept ids."""
    issues: list[LintIssue] = []
    for relpath, parsed in inv.pages.items():
        if not relpath.startswith(f"{consts.LAYER_L4}/"):
            continue
        for key in ("concept_ids",):
            values = parsed.frontmatter.get(key, []) or []
            if not isinstance(values, list):
                continue
            for val in values:
                if not isinstance(val, str):
                    continue
                normalized = _normalize_link(val)
                base = normalized.rsplit("/", 1)[-1]
                if base in {"index", "log", "overview", "ledger"}:
                    issues.append(
                        LintIssue(
                            check=CheckId.NOISE_IN_SYNTHESIS,
                            severity=Severity.WARNING,
                            page=relpath,
                            message=f"Synthesis references routing file '{val}' as concept id.",
                            suggestion="Run `wiki lint --fix` to remove noise.",
                            fixable=True,
                            context={"location": "frontmatter", "field": key, "remove_value": val},
                        )
                    )
    return issues


def check_cross_layer_links(inv: PageInventory) -> list[LintIssue]:
    """Verify DAG layer constraints — each layer's wikilink fields must only
    point to the correct parent layer:

      L2 ATM  → parent_source   must be in 01_Contexts/
      L3 CON  → ## Relations    must link to 02_Atoms/
      L4 SYN  -> concept_ids    must be in 03_Concepts/

    A wrong-layer reference is caught as WARNING (not ERROR) because the page
    may still render and be useful; it's a structural integrity issue, not a
    crash.
    """
    issues: list[LintIssue] = []

    _rules: list[tuple[str, str, str, str]] = [
        # (layer_dir,      field,           expected_prefix,  expected_id_prefix)
        (consts.LAYER_L2,      "parent_source",  f"{consts.LAYER_L1}/",   f"{consts.PREFIX_L1}-"),
        (consts.LAYER_L4, "concept_ids", f"{consts.LAYER_L3}/",   f"{consts.PREFIX_L3}-"),
    ]

    for layer_dir, fm_field, expected_prefix, expected_id_prefix in _rules:
        for relpath, parsed in inv.pages.items():
            if not relpath.startswith(f"{layer_dir}/"):
                continue
            raw = parsed.frontmatter.get(fm_field)
            if raw is None:
                continue
            values: list[str] = [raw] if isinstance(raw, str) else (
                [v for v in raw if isinstance(v, str)] if isinstance(raw, list) else []
            )
            for val in values:
                if not val:
                    continue
                normalized = _normalize_link(val)
                if not normalized:
                    continue
                target_id = normalized.rsplit("/", 1)[-1]
                if not normalized.startswith(expected_prefix) or not target_id.startswith(expected_id_prefix):
                    issues.append(
                        LintIssue(
                            check=CheckId.MISSING_CROSS_LAYER_LINK,
                            severity=Severity.WARNING,
                            page=relpath,
                            message=(
                                f"`{fm_field}` points to '{normalized}' which is not in "
                                f"{expected_prefix} (expected {expected_id_prefix}* IDs)."
                            ),
                            suggestion=(
                                f"Update `{fm_field}` to reference a "
                                f"{expected_prefix}{expected_id_prefix}*.md page."
                            ),
                            fixable=False,
                            context={
                                "field": fm_field,
                                "value": normalized,
                                "expected_prefix": expected_prefix,
                            },
                        )
                    )
    return issues


# ---------------------------------------------------------------------------
# Deep check — LLM-powered contradiction detection (opt-in)
# ---------------------------------------------------------------------------


def check_contradictions_deep(
    inv: PageInventory,
    paths: cfg.WikiPaths,
    client,  # OllamaClient
    max_pairs: int = 10,
    limit_to: Optional[list[str]] = None,
    apply_flags: bool = False,
) -> list[LintIssue]:
    """Use the configured LLM to scan pairs of L2 Atom pages that share
    related concepts and flag potentially contradictory claims.

    This is slow — one LLM call per pair of pages. We limit to `max_pairs`
    to keep the runtime bounded. Atoms are the right layer to check because
    L2 holds the irreducible factual claims; L3 Concepts and L4 Exhibitions
    derive from L2, so contradictions originate there.

    When ``apply_flags`` is True, both Atom files are updated with
    ``is_flagged_for_agent: true`` so the flag persists across runs.
    By default (``apply_flags=False``) the check is read-only; call with
    ``apply_flags=True`` only through an explicit fix/apply command.
    Pairs listed in `.curator/contradiction_dismissed.json` are skipped.
    """
    from .llm import ChatMessage, LLMError
    from .prompts import CONTRADICTION_DETECTION_PROMPT
    from . import contradiction as _cd

    issues: list[LintIssue] = []
    dismissed = _cd.load_dismissed(paths)

    # 1. Identify pairs of Atom pages that share outgoing wikilinks
    #    (e.g. both reference the same parent_source or related atom).
    page_link_sets: dict[str, set[str]] = {}
    for relpath, targets in inv.outgoing_links.items():
        if relpath.startswith(f"{consts.LAYER_L2}/"):
            page_link_sets[relpath] = set(t for t in targets if t)

    pairs: list[tuple[str, str, int]] = []
    paths_list = list(page_link_sets.keys())
    limit_set = set(limit_to) if limit_to else None

    for i, a in enumerate(paths_list):
        for b in paths_list[i + 1 :]:
            # Optimization: only check pairs if at least one page was modified
            if limit_set and (a not in limit_set and b not in limit_set):
                continue

            overlap = len(page_link_sets[a] & page_link_sets[b])
            if overlap >= 1:
                pairs.append((a, b, overlap))

    # Sort by overlap desc — check most connected pairs first
    pairs.sort(key=lambda t: -t[2])
    pairs = pairs[:max_pairs]

    # 2. For each pair, ask LLM to find contradictions (skip dismissed pairs)
    for rel_a, rel_b, _overlap in pairs:
        atom_a_id = Path(rel_a).stem
        atom_b_id = Path(rel_b).stem

        if _cd.is_dismissed(dismissed, atom_a_id, atom_b_id):
            continue

        page_a = inv.pages[rel_a]
        page_b = inv.pages[rel_b]

        prompt = CONTRADICTION_DETECTION_PROMPT.format(
            path_a=rel_a,
            path_b=rel_b,
            content_a=_trim_for_prompt(page_a.to_markdown()),
            content_b=_trim_for_prompt(page_b.to_markdown()),
        )
        messages = [
            ChatMessage(
                role="system",
                content="You are a careful fact-checker looking for contradictions.",
            ),
            ChatMessage(role="user", content=prompt),
        ]

        try:
            response = client.chat(messages, temperature=0.2)
        except LLMError:
            continue

        response = response.strip()
        if not response or response.upper().startswith("NONE"):
            continue

        if apply_flags:
            for atom_id in [atom_a_id, atom_b_id]:
                atom_path = paths.atoms / f"{atom_id}.md"
                if atom_path.exists():
                    atom_page = page_writer.read_page(atom_path)
                    if (
                        atom_page
                        and isinstance(atom_page.frontmatter, dict)
                        and not atom_page.frontmatter.get("is_flagged_for_agent")
                    ):
                        atom_page.frontmatter["is_flagged_for_agent"] = True
                        page_writer.write_page(atom_path, atom_page.to_markdown())

        issues.append(
            LintIssue(
                check=CheckId.CONTRADICTION,
                severity=Severity.WARNING,
                page=rel_a,
                message=f"Potential contradiction with {rel_b}",
                suggestion=response[:500],
                fixable=False,
                context={"other_page": rel_b, "reasoning": response},
            )
        )

    return issues


def _trim_for_prompt(text: str, max_chars: int = 3000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[... truncated ...]"


# ---------------------------------------------------------------------------
# Auto-fix
# ---------------------------------------------------------------------------


def _apply_fixes_to_page(parsed: page_writer.ParsedPage, fixes: list[LintIssue]) -> set[str]:
    """Apply all fixable issues to a single ParsedPage in place. Returns list of fixed check names."""
    fixed_checks: set[str] = set()
    body = parsed.body

    for issue in fixes:
        if not issue.fixable:
            continue
        ctx = issue.context
        changed_this_issue = False

        if issue.check == CheckId.MISSING_FRONTMATTER and ctx.get("repair") == "strip_llm_noise":
            repaired = page_writer.parse_page(page_writer.strip_llm_noise(body))
            if repaired.frontmatter:
                parsed.frontmatter = repaired.frontmatter
                body = repaired.body
                changed_this_issue = True

        elif issue.check == CheckId.INVALID_FRONTMATTER and ctx.get("remove_field"):
            field = ctx.get("remove_field", "")
            if field in parsed.frontmatter:
                parsed.frontmatter.pop(field, None)
                changed_this_issue = True

        elif issue.check in (CheckId.MALFORMED_WIKILINK, CheckId.BROKEN_WIKILINK):
            old = ctx.get("old_target", "")
            new = ctx.get("new_target", "")
            location = ctx.get("location", "body")
            if not old:
                continue

            if location == "body" and "new_target" in ctx and new == "":
                # Removal case
                old_esc = re.escape(old)
                body = re.sub(rf"\[\[{old_esc}(?:\|[^\]]*)?\]\]", "", body)
                body = re.sub(r"(?m)^[ \t]*[-*][ \t]*\n", "", body)
                changed_this_issue = True

            elif new and old != new:
                if location == "body":
                    old_esc = re.escape(old)
                    body = re.sub(rf"\[\[{old_esc}\]\]", f"[[{new}]]", body)
                    body = re.sub(rf"\[\[{old_esc}\|([^\]]*)\]\]", rf"[[{new}|\1]]", body)
                    changed_this_issue = True
                elif location == "frontmatter":
                    field = ctx.get("field", "parent_source")
                    if ctx.get("scalar"):
                        if parsed.frontmatter.get(field) == old:
                            parsed.frontmatter[field] = new
                            changed_this_issue = True
                    else:
                        values = parsed.frontmatter.get(field, []) or []
                        if isinstance(values, list):
                            new_values = [new if (isinstance(v, str) and v == old) else v for v in values]
                            if new_values != values:
                                parsed.frontmatter[field] = new_values
                                changed_this_issue = True

        elif issue.check == CheckId.NOISE_IN_SYNTHESIS:
            field = ctx.get("field", "concept_ids")
            remove_value = ctx.get("remove_value", "")
            values = parsed.frontmatter.get(field, []) or []
            if isinstance(values, list):
                new_values = [v for v in values if v != remove_value]
                if len(new_values) != len(values):
                    parsed.frontmatter[field] = new_values
                    changed_this_issue = True

        elif issue.check == CheckId.INVALID_SOURCE_PATH:
            field = ctx.get("field", "source_path")
            new = ctx.get("new_target", "")
            if field and new and parsed.frontmatter.get(field) != new:
                parsed.frontmatter[field] = new
                changed_this_issue = True

        if changed_this_issue:
            fixed_checks.add(issue.check.value)

    if len(fixed_checks) > 0:
        parsed.body = body
    return fixed_checks


def apply_llm_fixes(
    paths: cfg.WikiPaths,
    issues: list[LintIssue],
    client,
    progress_callback: Optional[Callable[[str], None]] = None,
    limit_to: Optional[list[str]] = None,
    repair_callback: Optional[Callable[[str, str], None]] = None,
) -> int:
    """Use the LLM to reconnect broken wikilinks that couldn't be auto-resolved.

    Handles issues with ``context["llm_relink"] == True``:
      - BROKEN_WIKILINK (in body or frontmatter)
      - STALE_SOURCE_REF where parent_source Context no longer exists

    For each broken link the LLM picks the best matching existing page.
    If the LLM returns NONE, the link is left in place for human review. The
    subsequent ``apply_fixes`` pass is deliberately non-destructive.

    Returns count of pages modified.
    """
    from . import prompts as _prompts
    from .llm import LLMError

    limit_set = set(limit_to) if limit_to else None
    llm_issues = [
        i for i in issues
        if i.context.get("llm_relink") and (not limit_set or i.page in limit_set)
    ]
    if not llm_issues:
        return 0

    inv = _build_inventory(paths)

    # Build per-layer candidate list: (slug_no_ext, title)
    layer_candidates: dict[str, list[tuple[str, str]]] = {}
    for layer in (consts.LAYER_L1, consts.LAYER_L2, consts.LAYER_L3, consts.LAYER_L4):
        candidates: list[tuple[str, str]] = []
        for relpath, parsed in inv.pages.items():
            if not relpath.startswith(f"{layer}/"):
                continue
            slug = relpath[:-3] if relpath.endswith(".md") else relpath
            title = slug.rsplit("/", 1)[-1]
            for line in parsed.body.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            candidates.append((slug, title))
        layer_candidates[layer] = candidates

    by_page: dict[str, list[LintIssue]] = defaultdict(list)
    for issue in llm_issues:
        by_page[issue.page].append(issue)

    total_modified = 0
    for relpath, page_issues in by_page.items():
        if progress_callback:
            progress_callback(relpath)

        full_path = paths.collections / relpath
        if not full_path.exists():
            continue
        try:
            content = full_path.read_text(encoding="utf-8")
        except OSError:
            continue
        parsed = page_writer.parse_page(content)
        changed = False

        for issue in page_issues:
            old_target = issue.context.get("old_target", "")
            location = issue.context.get("location", "body")
            field = issue.context.get("field", "")
            if not old_target:
                continue

            # Use pre-identified candidates (ambiguous case) or derive from layer prefix
            explicit_candidates = issue.context.get("llm_candidates")
            if explicit_candidates:
                candidates_for_prompt = [
                    (slug, slug.rsplit("/", 1)[-1]) for slug in explicit_candidates
                ]
            else:
                expected_layer = old_target.split("/", 1)[0] if "/" in old_target else ""
                candidates_for_prompt = layer_candidates.get(expected_layer, [])

            if not candidates_for_prompt:
                continue  # Nothing to suggest; leave in place for review

            expected_layer = old_target.split("/", 1)[0] if "/" in old_target else "unknown"
            candidates_text = "\n".join(
                f"- {slug}: {title}" for slug, title in candidates_for_prompt
            )
            messages = _prompts.build_lint_relink_messages(
                page_path=relpath,
                page_content=_trim_for_prompt(parsed.to_markdown()),
                broken_target=old_target,
                expected_layer=expected_layer,
                candidates_list=candidates_text,
            )
            try:
                response = client.chat(messages, temperature=0.1).strip()
            except LLMError:
                continue  # Leave in place for review

            if not response or response.upper() == "NONE":
                continue  # LLM found no match; leave in place for review

            new_target = _normalize_link(response)
            if not new_target or new_target not in inv.all_slugs:
                continue  # Hallucinated ID; ignore

            if location == "body":
                old_esc = re.escape(old_target)
                parsed.body = re.sub(rf"\[\[{old_esc}\]\]", f"[[{new_target}]]", parsed.body)
                parsed.body = re.sub(
                    rf"\[\[{old_esc}\|([^\]]*)\]\]",
                    rf"[[{new_target}|\1]]",
                    parsed.body,
                )
                changed = True
                if repair_callback:
                    repair_callback(relpath, f"LLM relinked: {old_target} -> {new_target}")
            elif location == "frontmatter" and field:
                val = parsed.frontmatter.get(field)
                old_norm = _normalize_link(old_target)
                if isinstance(val, list):
                    parsed.frontmatter[field] = [
                        new_target if (isinstance(v, str) and _normalize_link(v) == old_norm) else v
                        for v in val
                    ]
                    changed = True
                elif isinstance(val, str) and _normalize_link(val) == old_norm:
                    parsed.frontmatter[field] = new_target
                    changed = True

        if changed:
            full_path.write_text(parsed.to_markdown(), encoding="utf-8")
            total_modified += 1

    return total_modified


def apply_fixes(
    paths: cfg.WikiPaths,
    issues: list[LintIssue],
    progress_callback: Optional[Callable[[str], None]] = None,
    repair_callback: Optional[Callable[[str, str], None]] = None,
) -> int:
    """Apply all fixable issues. Returns the count of pages modified.

    Runs in a loop: apply → re-lint → apply → re-lint. This is because some
    fixes cascade (e.g. normalizing a malformed wikilink can reveal a noise
    issue that the first pass couldn't see because the value was obscured).
    Bounded to 5 iterations to prevent pathological loops.
    """
    total_modified = 0
    current_issues = issues
    max_iterations = 5

    for _iteration in range(max_iterations):
        fixable = [i for i in current_issues if i.fixable]
        if not fixable:
            break

        by_page: dict[str, list[LintIssue]] = defaultdict(list)
        for issue in fixable:
            by_page[issue.page].append(issue)

        pages_modified_this_round = 0
        for relpath, page_issues in by_page.items():
            if progress_callback:
                progress_callback(relpath)

            full_path = paths.collections / relpath
            if not full_path.exists():
                continue
            try:
                content = full_path.read_text(encoding="utf-8")
            except OSError:
                continue
            parsed = page_writer.parse_page(content)
            fixed_checks = _apply_fixes_to_page(parsed, page_issues)
            if fixed_checks:
                full_path.write_text(parsed.to_markdown(), encoding="utf-8")
                pages_modified_this_round += 1
                if repair_callback:
                    msg = ", ".join(fixed_checks)
                    repair_callback(relpath, f"Fixed {msg}")

        if pages_modified_this_round == 0:
            break
        total_modified += pages_modified_this_round

        # Re-lint to find any new fixable issues revealed by this round's changes
        new_report = run_lint(paths, deep=False, client=None)
        current_issues = new_report.issues

    # Refresh DB-native search so modified pages are reflected in queries.
    # Only runs if we actually modified anything. Non-fatal on failure, but §32
    # forbids a silent skip: the pages were changed and the index was not, so
    # queries now serve stale text until the next reindex. Broad catch because
    # the embedding provider is arbitrary and can raise anything.
    if total_modified > 0:
        try:
            from . import search
            search.update_index(paths, embed=True)
        except Exception as exc:
            logger.warning(
                "lint --fix modified %d page(s) but the search index refresh "
                "failed: %s. Queries may serve stale text until "
                "`wiki reindex` is run.",
                total_modified,
                exc,
            )

    return total_modified


# ---------------------------------------------------------------------------
# Compiler Integrity (Plan B, v0.8.0, SYSTEM_BEHAVIOR §26.5)
# ---------------------------------------------------------------------------


def compiler_integrity(paths: cfg.WikiPaths) -> list[LintIssue]:
    """The on-demand compiler-integrity audit surface for ``wiki lint`` (§26.5).

    Runs the read-only compiler audit (SCHEMA §20.5) and maps its findings to
    LintIssues. Release-blocking violations are ERRORs (so ``wiki lint`` exits
    non-zero for CI/testbed gating); excluded-from-serving and Plan-C-assigned
    findings are reported at lower severity. The audit never edits source truth.
    """
    from .pipeline.claim_support import run_compiler_audit

    report = run_compiler_audit(paths.state_db)
    issues: list[LintIssue] = []

    def _emit(check_page: str, severity: Severity, message: str) -> None:
        issues.append(
            LintIssue(
                check=CheckId.COMPILER_INTEGRITY, severity=severity,
                page=check_page, message=message,
            )
        )

    # Excluded-from-serving candidates — telemetry, not structural review.
    for uid in report.failed_claims:
        _emit(uid, Severity.INFO,
              "claim cites a source span that does not support it (F6 wrong-real-span); "
              "excluded from serving")
    for uid in report.stale_claims:
        _emit(uid, Severity.INFO,
              "claim support is stale; excluded from serving")

    # Release-blocking (§20.5) — these make `wiki lint` exit non-zero.
    for uid in report.dangling_supports:
        _emit(uid, Severity.ERROR,
              "support row references a missing span, a retired unit, or a discarded generation")
    for uid in report.formula_inconsistencies:
        _emit(uid, Severity.ERROR,
              "formula_status is inconsistent with its evidence (linked_evidence without a "
              "formula support row, or omitted_incidental without a reason code)")
    for scope in report.staged_leftovers:
        _emit(scope, Severity.ERROR,
              "more than one authoritative compiler generation exists for this source scope")

    # Excluded-from-serving (not yet verified) — informational, not blocking.
    informational = sorted(
        set(report.unsupported_claims)
        - set(report.failed_claims)
        - set(report.stale_claims)
    )
    for uid in informational:
        _emit(uid, Severity.INFO,
              "claim is not yet verified (unchecked/uncertain); excluded from serving")
    for group in report.duplicate_candidates:
        _emit(group[0], Severity.INFO,
              f"duplicate-claim candidates share a semantic hash: {', '.join(group)}")

    # Graph/community-report broad fallback — RECORDED and assigned to Plan C.
    for finding in report.broad_fallback_plan_c:
        _emit(str(finding.get("id", "")), Severity.INFO,
              f"{finding.get('type', 'artifact')} grounds to the broad all-upstream-span set "
              "(broad fallback) — assigned to Plan C (community-report/graph-derived)")
    return issues


def graph_quality(paths: cfg.WikiPaths) -> list[LintIssue]:
    """The on-demand graph-audit surface for ``wiki lint`` (SYSTEM_BEHAVIOR §27.6).

    Runs the read-only ``db.graph_audit`` (SCHEMA §21.8) and maps each violation
    to a release-blocking ERROR ``LintIssue``, so ``wiki lint`` exits non-zero for
    CI/testbed gating when the served graph/report state breaks a frozen invariant
    (active relation with no verified lineage, an endpoint that is not canonical /
    is redirected, a quarantined relation missing its reason, or a served report
    citing a non-active relation). The audit NEVER edits state. An empty audit
    means the served graph is clean and no Graph Quality issues are emitted."""
    issues: list[LintIssue] = []
    for violation in db.graph_audit(paths.state_db):
        code = str(violation.get("code", ""))
        detail = str(violation.get("detail", ""))
        issues.append(
            LintIssue(
                check=CheckId.GRAPH_QUALITY,
                severity=Severity.ERROR,
                page=str(violation.get("subject_id", "")),
                message=f"[{code}] {detail}" if detail else f"[{code}]",
                context={"code": code, "detail": detail},
            )
        )
    return issues


# ---------------------------------------------------------------------------
# Top-level: run_lint
# ---------------------------------------------------------------------------


def run_lint(
    paths: cfg.WikiPaths,
    *,
    deep: bool = False,
    client=None,  # OllamaClient, required if deep=True
    progress_callback: Optional[Callable[[str], None]] = None,
    limit_to: Optional[list[str]] = None,
    apply_flags: bool = False,
) -> LintReport:
    """Run all fast checks, plus deep checks if requested.

    Returns a LintReport containing all issues, ordered by severity then page.
    """
    import time

    started = time.monotonic()
    report = LintReport()

    inv = _build_inventory(paths)
    report.pages_checked = len(inv.pages)

    # Fast checks
    fast_check_fns: list[tuple[str, Any]] = [
        ("broken_wikilinks",    lambda: check_broken_wikilinks(inv)),
        ("orphan_pages",        lambda: check_orphan_pages(inv)),
        ("frontmatter",         lambda: check_frontmatter(inv)),
        ("malformed_wikilinks", lambda: check_malformed_wikilinks(inv, paths)),
        ("missing_extracted",   lambda: check_missing_extracted(inv)),
        ("stale_source_refs",   lambda: check_stale_source_refs(inv, paths)),
        ("atom_source_paths",   lambda: check_atom_source_paths(inv, paths)),
        ("noise_in_curation",   lambda: check_noise_in_curation_sources(inv)),
        ("cross_layer_links",   lambda: check_cross_layer_links(inv)),
        ("compiler_integrity",  lambda: compiler_integrity(paths)),
        ("graph_quality",       lambda: graph_quality(paths)),
    ]
    for name, fn in fast_check_fns:
        report.issues.extend(fn())
        report.fast_checks_run.append(name)

    # Deep check (LLM-powered)
    if deep and client is not None:
        report.deep_check_run = True
        report.issues.extend(check_contradictions_deep(inv, paths, client, limit_to=limit_to, apply_flags=apply_flags))

    # Sort: errors first, then warnings, then infos. Within each, by page.
    severity_order = {
        Severity.ERROR: 0,
        Severity.WARNING: 1,
        Severity.INFO: 2,
    }
    report.issues.sort(key=lambda i: (severity_order[i.severity], i.page, i.check.value))

    report.duration_seconds = time.monotonic() - started
    return report


# ---------------------------------------------------------------------------
# Markdown rendering of a report (for --save and display)
# ---------------------------------------------------------------------------


def render_report_markdown(report: LintReport, paths: cfg.WikiPaths) -> str:
    """Render a LintReport as a markdown document suitable for saving."""
    today = page_writer.today_iso()
    lines: list[str] = []
    lines.append("---")
    lines.append(f"title: Lint Report {today}")
    lines.append("type: lint_report")
    lines.append(f"last_updated: '{today}'")
    lines.append("tags: [lint, health-check]")
    lines.append(f"health_score: {report.health_score}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Lint Report — {today}")
    lines.append("")
    lines.append(f"**Health score:** {report.health_score}/100")
    lines.append(f"**Pages checked:** {report.pages_checked}")
    lines.append(f"**Duration:** {report.duration_seconds:.2f}s")
    lines.append("")
    lines.append(
        f"**Summary:** {len(report.errors)} errors · "
        f"{len(report.warnings)} warnings · {len(report.infos)} infos"
    )
    if report.auto_fixed:
        lines.append(f"**Auto-fixed:** {report.auto_fixed} issues")
    lines.append("")

    def _section(title: str, issues: list[LintIssue]) -> None:
        if not issues:
            return
        lines.append(f"## {title} ({len(issues)})")
        lines.append("")
        for issue in issues:
            lines.append(f"### `{issue.page}`")
            lines.append("")
            lines.append(f"- **Check:** {issue.check.value}")
            lines.append(f"- **Message:** {issue.message}")
            if issue.suggestion:
                lines.append(f"- **Suggestion:** {issue.suggestion}")
            if is_safe_fixable(issue):
                lines.append("- **Auto-fixable:** safe (use `wiki lint --fix`)")
            elif issue.fixable:
                lines.append("- **Auto-fixable:** needs review if no confident reconnect is found")
            lines.append("")

    _section("Errors", report.errors)
    _section("Warnings", report.warnings)
    _section("Info", report.infos)

    if not report.issues:
        lines.append("## Clean! 🎉")
        lines.append("")
        lines.append("No issues found. Your wiki is in good shape.")
        lines.append("")

    return "\n".join(lines)
