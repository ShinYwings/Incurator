"""LLM compilation pipeline — multi-phase DAG build.

This module provides the core logic for high-level knowledge synthesis:
- Phase A (L2 Atoms) & Phase B (L3 Concepts): Driven by `wiki add`.
- Phase C (L4 Exhibitions): Driven by `wiki curate`.

The pipeline is sequential to ensure cross-source concepts and exhibitions 
emerge correctly. All IDs are UUID-based (ATM-/CON-/EXH-).
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from pydantic import BaseModel, Field, ValidationError

from . import config as cfg
from . import db
from . import page_writer
from . import parsers
from . import prompts
from .llm import LLMError, OllamaClient


MAX_SOURCE_CHARS = 100_000
EXCERPT_CHARS = 4000


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class AtomCandidate(BaseModel):
    name: str
    type: str = "fact"
    one_liner: str


class SummaryData(BaseModel):
    title: str
    domain: str = ""
    summary: str
    key_claims: list[str] = Field(default_factory=list)
    atom_candidates: list[AtomCandidate] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ConceptPlan(BaseModel):
    name: str
    domain: str = ""
    atom_ids: list[str]
    description: str


class ConceptClusterResult(BaseModel):
    concepts: list[ConceptPlan] = Field(default_factory=list)


class SynthesisPlan(BaseModel):
    topic: str
    concept_ids: list[str]
    confidence: float = 0.7
    rationale: str = ""


class SynthesisPlanResult(BaseModel):
    synthesis_plans: list[SynthesisPlan] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class PageChange:
    id: str          # CTX-/ATM-/CON-/EXH- UUID
    path: str        # relative to .curator/Collections/
    layer: str       # '01_Contexts' | '02_Atoms' | '03_Concepts' | '04_Exhibitions'
    operation: str   # 'created' | 'updated'


@dataclass
class IngestResult:
    source_id: int
    source_title: str
    fragments_created: int = 0
    fragments_updated: int = 0
    themes_created: int = 0
    curations_created: int = 0
    changes: list[PageChange] = field(default_factory=list)
    error: str | None = None
    skipped: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None and not self.skipped

    @property
    def pages_created(self) -> int:
        return self.fragments_created + self.themes_created + self.curations_created

    @property
    def pages_updated(self) -> int:
        return self.fragments_updated


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


class IngestCallbacks:
    def on_start(self, source_id: int, source_title: str, context_id: str) -> None: ...
    def on_pass1_start(self, fragment_count: int) -> None: ...
    def on_fragment_drafting(self, fragment_id: str, name: str, operation: str) -> None: ...
    def on_stream_chunk(self, chunk: str) -> None: ...
    def on_fragment_written(self, change: PageChange) -> None: ...
    def on_pass2_start(self, fragment_count: int) -> None: ...
    def on_theme_drafting(self, theme_id: str, name: str) -> None: ...
    def on_theme_written(self, change: PageChange) -> None: ...
    def on_pass3_start(self, theme_count: int) -> None: ...
    def on_curation_drafting(self, cur_id: str, topic: str) -> None: ...
    def on_curation_written(self, change: PageChange) -> None: ...
    def on_finalizing(self) -> None: ...
    def on_complete(self, result: IngestResult) -> None: ...
    def on_error(self, error: str) -> None: ...
    def ask_confirm(self, summary: SummaryData) -> bool:
        return True


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("\n", 1)
        text = parts[1] if len(parts) == 2 else text
        if text.rstrip().endswith("```"):
            text = text.rsplit("```", 1)[0]
    start = text.find("{")
    if start == -1:
        return text
    depth, in_str, escape = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False; continue
        if c == "\\":
            escape = True; continue
        if c == '"':
            in_str = not in_str; continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return text[start:]


def _parse_json_model(raw: str, model_class):
    json_str = _extract_json(raw)
    import re

    def _sanitize_string_content(match):
        s = match.group(0)
        content = s[1:-1]
        new_content = []
        i = 0
        while i < len(content):
            if content[i] == '\\':
                if i + 1 < len(content):
                    nxt = content[i + 1]
                    if nxt in '"\\/bfnrt':
                        new_content.append('\\' + nxt)
                        i += 2
                        continue
                    elif nxt == 'u' and i + 5 < len(content) and all(c in '0123456789abcdefABCDEF' for c in content[i+2:i+6]):
                        new_content.append('\\' + content[i+1:i+6])
                        i += 6
                        continue
                new_content.append('\\\\')
                i += 1
            else:
                new_content.append(content[i])
                i += 1
        return '"' + "".join(new_content) + '"'

    json_str = re.sub(r'"([^"\\]|\\.)*"', _sanitize_string_content, json_str)
    try:
        data = json.loads(json_str, strict=False)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e
    try:
        return model_class(**data)
    except ValidationError as e:
        raise ValueError(f"Schema mismatch: {e}") from e


def _build_excerpt(text: str, max_chars: int = EXCERPT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[... truncated ...]"


def _mark_source_status(paths, source_id, status, last_ingested=None, error_reason=None):
    with db.connect(paths.state_db) as conn:
        if last_ingested and error_reason:
            conn.execute(
                "UPDATE sources SET status = ?, last_ingested = ?, error_reason = ? WHERE id = ?",
                (status, last_ingested, error_reason, source_id),
            )
        elif last_ingested:
            conn.execute(
                "UPDATE sources SET status = ?, last_ingested = ? WHERE id = ?",
                (status, last_ingested, source_id),
            )
        elif error_reason:
            conn.execute(
                "UPDATE sources SET status = ?, error_reason = ? WHERE id = ?",
                (status, error_reason, source_id),
            )
        else:
            conn.execute("UPDATE sources SET status = ? WHERE id = ?", (status, source_id))


def _record_ingest_run(paths, source_id, started, mode, created, updated, error):
    with db.connect(paths.state_db) as conn:
        conn.execute(
            """INSERT INTO ingest_runs
               (started_at, finished_at, source_id, mode, pages_created, pages_updated, error)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (_now_iso(), _now_iso(), source_id, mode, created, updated, error),
        )


def _stream_page(client, messages, callbacks: IngestCallbacks) -> str:
    """Stream a page from LLM, collecting chunks via callbacks. Returns full text."""
    full = ""
    gen = client.chat_stream(messages, thinking=False, temperature=0.3)
    try:
        while True:
            chunk = next(gen)
            callbacks.on_stream_chunk(chunk)
            full += chunk
    except StopIteration as stop:
        if stop.value:
            full = stop.value
    text = page_writer.strip_llm_noise(full)
    return page_writer.sanitize_wikilinks(text)


# ---------------------------------------------------------------------------
# Pass 1 — L2 Fragments
# ---------------------------------------------------------------------------


def _find_existing_atom(paths: cfg.WikiPaths, name: str) -> tuple[str, bool]:
    """Check if an Atom page for this concept name already exists.
    Returns (atom_id, exists).
    """
    if not paths.atoms.exists():
        return _gen_id("ATM"), False
    for md in paths.atoms.glob("*.md"):
        parsed = page_writer.read_page(md)
        if parsed and parsed.frontmatter.get("type") == "atom":
            # Match by name in H1
            for line in parsed.body.splitlines():
                if line.startswith("# ") and name.lower() in line.lower():
                    return md.stem, True
    return _gen_id("ATM"), False


def _is_valid_context_id(context_id: str) -> bool:
    return bool(context_id) and context_id.startswith("CTX-") and len(context_id) > 4


def _strip_embedded_frontmatter(body: str) -> str:
    body = re.sub(
        r"(?is)\s*```(?:ya?ml|markdown|md)?\s*\n---\s*\n.*?\n---\s*\n```\s*",
        "\n\n",
        body,
    )
    return re.sub(r"(?is)^\s*---\s*\n.*?\n---\s*", "", body, count=1).strip()


def _source_path_link(relpath: str) -> str:
    return f"[[{relpath.removesuffix('.md')}]]"


def _section_text(body: str, heading: str) -> str:
    pattern = re.compile(
        rf"(?is)^##\s+{re.escape(heading)}\s*$\n?(.*?)(?=^##\s+|\Z)",
        re.MULTILINE,
    )
    match = pattern.search(body)
    return match.group(1).strip() if match else ""


def _body_to_required_sections(body: str, headings: list[str], fallback_title: str = "") -> str:
    body = _strip_embedded_frontmatter(page_writer.sanitize_wikilinks(body or ""))
    lines = body.splitlines()
    title_lines = [line for line in lines if line.startswith("# ") and not line.startswith("## ")]
    title = title_lines[0].strip() if title_lines else (f"# {fallback_title}" if fallback_title else "")

    converted = body
    for heading in headings:
        converted = re.sub(
            rf"(?im)^\s*[-*]\s+\*\*{re.escape(heading)}\*\*:\s*",
            f"## {heading}\n",
            converted,
        )

    parts = [title] if title else []
    for heading in headings:
        text = _section_text(converted, heading)
        if not text and heading == "Relations":
            text = ""
        parts.append(f"## {heading}\n\n{text}".rstrip())
    return "\n\n".join(parts).strip()


def _strip_out_of_scope_curator_links(body: str, allowed_targets: set[str]) -> str:
    """Unlink curator DAG targets that are not part of the trusted write plan."""
    curator_prefixes = ("01_Contexts/", "02_Atoms/", "03_Concepts/", "04_Exhibitions/")

    def repl(match: re.Match[str]) -> str:
        inner = match.group(1)
        target, _, alias = inner.partition("|")
        target = target.strip().removesuffix(".md")
        if not target.startswith(curator_prefixes):
            return match.group(0)
        if target in allowed_targets:
            return f"[[{inner}]]"
        return alias.strip() or target.rsplit("/", 1)[-1]

    return re.sub(r"\[\[([^\]]+)\]\]", repl, body)


def _is_llm_refusal(content: str) -> bool:
    lowered = content.lower()
    refusal_markers = (
        "i am unable to write",
        "i can't write",
        "i cannot write",
        "i do not have the",
        "write_file",
        "run_shell_command",
    )
    return any(marker in lowered for marker in refusal_markers)


_TOPIC_BOUNDARY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "retrieval": (
        "rag",
        "retrieval-augmented",
        "retrieval augmented",
        "bm25",
        "dense passage",
        "dpr",
        "retriever",
        "knowledge base",
    ),
    "gaussian_splatting": (
        "gaussian splatting",
        "gaussian primitive",
        "radiance field",
        "ewa",
        "elliptical weighted average",
        "homography",
        "conic",
        "volume rendering",
        "rasterization",
        "normal consistency",
        "depth distortion",
    ),
}


def _atom_topic_signature(paths: cfg.WikiPaths, atom_id: str) -> set[str]:
    page = page_writer.read_page(paths.atoms / f"{atom_id}.md")
    if not page:
        return set()
    text_parts = [page.body, str(page.frontmatter.get("claim_type", "") or "")]
    parent = str(page.frontmatter.get("parent_source", "") or "")
    if parent:
        ctx_id = parent.strip().strip("[]").rsplit("/", 1)[-1].removesuffix(".md")
        ctx_page = page_writer.read_page(paths.contexts / f"{ctx_id}.md")
        if ctx_page:
            text_parts.extend(
                [
                    str(ctx_page.frontmatter.get("domain", "") or ""),
                    str(ctx_page.frontmatter.get("source_path", "") or ""),
                    ctx_page.body[:1200],
                ]
            )
    text = "\n".join(text_parts).lower()
    return {
        topic
        for topic, keywords in _TOPIC_BOUNDARY_KEYWORDS.items()
        if any(_contains_topic_keyword(text, keyword) for keyword in keywords)
    }


def _contains_topic_keyword(text: str, keyword: str) -> bool:
    escaped = re.escape(keyword.lower())
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None


def _plan_crosses_hard_topic_boundary(paths: cfg.WikiPaths, plan: ConceptPlan) -> bool:
    """Reject known false merges before drafting expensive L3 pages."""
    signatures = [_atom_topic_signature(paths, aid) for aid in plan.atom_ids]
    concrete = [sig for sig in signatures if sig]
    if not concrete:
        return False
    union: set[str] = set().union(*concrete)
    if len(union) <= 1:
        return False
    # Preserve truly cross-domain atoms; block clusters that merely juxtapose
    # unrelated single-domain atoms through abstract vocabulary.
    if all(union.issubset(sig) for sig in concrete):
        return False
    return True


def _split_plan_by_topic_boundary(paths: cfg.WikiPaths, plan: ConceptPlan) -> list[ConceptPlan]:
    if not _plan_crosses_hard_topic_boundary(paths, plan):
        return [plan]
    groups: dict[str, list[str]] = {}
    for atom_id in plan.atom_ids:
        signature = _atom_topic_signature(paths, atom_id)
        for topic in sorted(signature):
            groups.setdefault(topic, []).append(atom_id)
    split: list[ConceptPlan] = []
    topic_titles = {
        "retrieval": "Retrieval Knowledge",
        "gaussian_splatting": "Gaussian Splatting Geometry",
    }
    for topic, atom_ids in groups.items():
        unique_atom_ids = list(dict.fromkeys(atom_ids))
        if len(unique_atom_ids) < 2:
            continue
        split.append(
            ConceptPlan(
                name=topic_titles.get(topic, f"{plan.name} ({topic})"),
                domain=topic.replace("_", " "),
                atom_ids=unique_atom_ids,
                description=(
                    f"Boundary-preserving split from rejected mixed cluster "
                    f"{plan.name!r}: {plan.description}"
                ),
            )
        )
    return split


def _disambiguate_concept_plan_titles(paths: cfg.WikiPaths, plans: list[ConceptPlan]) -> list[ConceptPlan]:
    """Give same-titled concepts stable mechanism suffixes before writing."""
    counts: dict[str, int] = {}
    for plan in plans:
        counts[plan.name.strip().lower()] = counts.get(plan.name.strip().lower(), 0) + 1
    updated: list[ConceptPlan] = []
    for plan in plans:
        key = plan.name.strip().lower()
        if counts.get(key, 0) <= 1:
            updated.append(plan)
            continue
        suffix = _concept_plan_suffix(paths, plan)
        name = plan.name
        if suffix and suffix.lower() not in name.lower():
            name = f"{name} - {suffix}"
        updated.append(
            ConceptPlan(
                name=name,
                domain=plan.domain,
                atom_ids=plan.atom_ids,
                description=plan.description,
            )
        )
    return updated


def _concept_plan_suffix(paths: cfg.WikiPaths, plan: ConceptPlan) -> str:
    bodies: list[str] = []
    for aid in plan.atom_ids[:8]:
        page = page_writer.read_page(paths.atoms / f"{aid}.md")
        if page:
            bodies.append(page.body)
    text = " ".join(bodies).lower()
    if any(word in text for word in ("depth", "normal", "regularization", "loss")):
        return "Regularization"
    if any(word in text for word in ("projection", "homography", "conic", "ray", "screen")):
        return "Projection"
    if any(word in text for word in ("bm25", "dense", "retrieval", "passage")):
        return "Sparse/Dense"
    if any(word in text for word in ("kernel", "covariance", "gaussian", "ewa")):
        return "Kernels"
    return "Mechanism"


def _page_title(page: page_writer.ParsedPage, fallback: str) -> str:
    for line in page.body.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            if title:
                return title
    for key in ("name", "title"):
        value = str(page.frontmatter.get(key, "") or "").strip()
        if value:
            return value
    return fallback


def _section_excerpt(body: str, heading: str, max_chars: int = 360) -> str:
    pattern = rf"(?ims)^##\s+{re.escape(heading)}\s*$\n(?P<section>.*?)(?=^##\s+|\Z)"
    match = re.search(pattern, body or "")
    if not match:
        return ""
    section = re.sub(r"\s+", " ", match.group("section")).strip()
    return section[:max_chars]


def _atom_summary(paths: cfg.WikiPaths, atom_id: str) -> dict | None:
    parsed = page_writer.read_page(paths.atoms / f"{atom_id}.md")
    if not parsed:
        return None
    one_liner = _section_excerpt(parsed.body, "Definition / Claim")
    if not one_liner:
        one_liner = _section_excerpt(parsed.body, "Context")
    if not one_liner:
        for line in parsed.body.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                one_liner = line
                break
    return {
        "id": atom_id,
        "name": _page_title(parsed, atom_id),
        "claim_type": parsed.frontmatter.get("claim_type", "fact"),
        "one_liner": one_liner[:260],
    }


def _atom_context_id(paths: cfg.WikiPaths, atom_id: str) -> str:
    page = page_writer.read_page(paths.atoms / f"{atom_id}.md")
    if not page:
        return ""
    parent = str(page.frontmatter.get("parent_source", "") or "")
    parent = parent.strip()
    if parent.startswith("[[") and parent.endswith("]]"):
        parent = parent[2:-2]
    return parent.rsplit("/", 1)[-1].removesuffix(".md")


def _fallback_concept_name(paths: cfg.WikiPaths, atom_ids: list[str]) -> tuple[str, str]:
    signatures: set[str] = set()
    for atom_id in atom_ids:
        signatures.update(_atom_topic_signature(paths, atom_id))
    if "retrieval" in signatures:
        return "Retrieval Knowledge", "retrieval"
    if "gaussian_splatting" in signatures:
        return "Gaussian Splatting Geometry", "gaussian splatting"
    context_id = _atom_context_id(paths, atom_ids[0]) if atom_ids else ""
    context = page_writer.read_page(paths.contexts / f"{context_id}.md") if context_id else None
    if context:
        domain = str(context.frontmatter.get("domain", "") or "").strip()
        return _page_title(context, "Source Knowledge"), domain
    return "Source Knowledge", ""


def _add_unassigned_atom_fallback_plans(
    paths: cfg.WikiPaths,
    plans: list[ConceptPlan],
    atom_ids: list[str],
) -> list[ConceptPlan]:
    """Ensure every coherent source/topic group has a Concept even if LLM omits it."""
    assigned: set[str] = set()
    valid_atoms = set(atom_ids)
    for plan in plans:
        assigned.update(aid for aid in plan.atom_ids if aid in valid_atoms)
    unassigned = [aid for aid in atom_ids if aid not in assigned]
    if not unassigned:
        return plans

    groups: dict[tuple[str, str], list[str]] = {}
    for atom_id in unassigned:
        signature = _atom_topic_signature(paths, atom_id)
        topic = sorted(signature)[0] if signature else "source"
        context_id = _atom_context_id(paths, atom_id)
        groups.setdefault((topic, context_id), []).append(atom_id)

    completed = list(plans)
    for (_topic, _context_id), grouped_atoms in groups.items():
        unique_atom_ids = list(dict.fromkeys(grouped_atoms))
        if len(unique_atom_ids) < 2:
            continue
        name, domain = _fallback_concept_name(paths, unique_atom_ids)
        completed.append(
            ConceptPlan(
                name=name,
                domain=domain,
                atom_ids=unique_atom_ids,
                description=(
                    "Fallback coverage cluster created because the L3 clustering "
                    "model omitted these related Atoms from any Concept."
                ),
            )
        )
    return completed


def _concept_topic_signature(paths: cfg.WikiPaths, concept_id: str) -> set[str]:
    concept = page_writer.read_page(paths.concepts / f"{concept_id}.md")
    if not concept:
        return set()
    signature: set[str] = set()
    for atom_id in _concept_atom_ids(concept):
        signature.update(_atom_topic_signature(paths, atom_id))
    text = "\n".join(
        [
            str(concept.frontmatter.get("domain", "") or ""),
            concept.body[:2000],
        ]
    ).lower()
    for topic, keywords in _TOPIC_BOUNDARY_KEYWORDS.items():
        if any(_contains_topic_keyword(text, keyword) for keyword in keywords):
            signature.add(topic)
    return signature


def _split_synthesis_plan_by_topic_boundary(paths: cfg.WikiPaths, plan: SynthesisPlan) -> list[SynthesisPlan]:
    signatures = [_concept_topic_signature(paths, cid) for cid in plan.concept_ids]
    concrete = [sig for sig in signatures if sig]
    if not concrete:
        return [plan]
    union: set[str] = set().union(*concrete)
    if len(union) <= 1 or all(union.issubset(sig) for sig in concrete):
        return [plan]

    groups: dict[str, list[str]] = {}
    for concept_id in plan.concept_ids:
        for topic in sorted(_concept_topic_signature(paths, concept_id)):
            groups.setdefault(topic, []).append(concept_id)

    topic_titles = {
        "retrieval": "Retrieval Knowledge Packaging",
        "gaussian_splatting": "Gaussian Splatting Geometry Packaging",
    }
    split: list[SynthesisPlan] = []
    for topic, concept_ids in groups.items():
        unique_concept_ids = list(dict.fromkeys(concept_ids))
        if not unique_concept_ids:
            continue
        split.append(
            SynthesisPlan(
                topic=topic_titles.get(topic, f"{plan.topic} ({topic})"),
                concept_ids=unique_concept_ids,
                confidence=min(plan.confidence, 0.85),
                rationale=(
                    f"Boundary-preserving split from rejected mixed exhibition "
                    f"{plan.topic!r}: {plan.rationale}"
                ),
            )
        )
    return split


def _enforce_atom_contract(
    content: str,
    *,
    atom_id: str,
    candidate: AtomCandidate,
    context_id: str,
    relpath: str,
    today: str,
) -> str:
    """Force L2 Atom machine fields from trusted pipeline state.

    The LLM drafts the prose, but DAG identity/provenance must come from code.
    """
    content = page_writer.strip_llm_noise(content)
    if _is_llm_refusal(content):
        raise LLMError(f"Refusal/tool-use response while drafting atom {atom_id}")
    parsed = page_writer.parse_page(page_writer.sanitize_wikilinks(content))
    fm = parsed.frontmatter or {}

    confidence = fm.get("confidence_score", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(1.0, max(0.0, confidence))

    contradicts = fm.get("contradicts", [])
    if not isinstance(contradicts, list):
        contradicts = []

    parsed.frontmatter = {
        "id": atom_id,
        "type": "atom",
        "parent_source": f"01_Contexts/{context_id}",
        "source_path": _source_path_link(relpath),
        "claim_type": candidate.type or "fact",
        "confidence_score": confidence,
        "contradicts": contradicts,
        "is_verified_by_human": bool(fm.get("is_verified_by_human", False)),
        "is_flagged_for_agent": bool(fm.get("is_flagged_for_agent", False)),
        "last_updated": today,
    }

    body = _body_to_required_sections(
        parsed.body or "",
        ["Definition / Claim", "Context", "Constraints", "Relations"],
        fallback_title=candidate.name,
    )
    parent_link = f"[[01_Contexts/{context_id}]]"
    body = re.sub(
        rf"\[\[01_Contexts/(?!{re.escape(context_id)}(?:\]\]|[#|]))[^\]]*\]\]",
        "",
        body,
    )
    body = re.sub(r"(?m)^\s*[-*]\s*$\n?", "", body)
    if parent_link not in body:
        body = re.sub(
            r"(?is)(^##\s+Relations\s*$\n?)",
            rf"\1\n{parent_link}\n",
            body,
            count=1,
            flags=re.MULTILINE,
        )
    parsed.body = body
    return parsed.to_markdown()


def _enforce_concept_contract(
    content: str,
    *,
    concept_id: str,
    plan: ConceptPlan,
    today: str,
) -> str:
    content = page_writer.strip_llm_noise(content)
    if _is_llm_refusal(content):
        raise LLMError(f"Refusal/tool-use response while drafting concept {concept_id}")
    parsed = page_writer.parse_page(page_writer.sanitize_wikilinks(content))
    fm = parsed.frontmatter or {}
    try:
        confidence = float(fm.get("confidence_score", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(1.0, max(0.0, confidence))
    atom_ids = [aid for aid in plan.atom_ids if isinstance(aid, str) and aid.startswith("ATM-")]
    parsed.frontmatter = {
        "id": concept_id,
        "type": "concept",
        "domain": plan.domain or "",
        "confidence_score": confidence,
        "last_updated": today,
    }
    body = _body_to_required_sections(
        parsed.body or "",
        ["1. Core Architecture", "2. Interaction of Atoms", "3. Mathematical Framework", "4. Open Questions", "Relations"],
        fallback_title=plan.name,
    )
    allowed_targets = {f"02_Atoms/{aid}" for aid in atom_ids}
    body = _strip_out_of_scope_curator_links(body, allowed_targets)
    relations = "\n".join(f"[[02_Atoms/{aid}]]" for aid in atom_ids)
    if relations:
        body = re.sub(
            r"(?is)(^##\s+Relations\s*$\n?).*?\Z",
            rf"\1\n{relations}\n",
            body,
            count=1,
            flags=re.MULTILINE,
        )
    parsed.body = body
    return parsed.to_markdown()


def _concept_atom_ids(page: page_writer.ParsedPage | None) -> list[str]:
    """Concept dependencies are stored as `## Relations` Atom wikilinks."""
    if not page:
        return []
    ids: list[str] = []
    for target in page_writer.extract_relation_targets(page.body, prefix="02_Atoms/"):
        atom_id = target.rsplit("/", 1)[-1]
        if atom_id.startswith("ATM-") and atom_id not in ids:
            ids.append(atom_id)
    return ids


def _enforce_exhibition_contract(
    content: str,
    *,
    exh_id: str,
    plan: SynthesisPlan,
    today: str,
) -> str:
    content = page_writer.strip_llm_noise(content)
    if _is_llm_refusal(content):
        raise LLMError(f"Refusal/tool-use response while drafting exhibition {exh_id}")
    parsed = page_writer.parse_page(page_writer.sanitize_wikilinks(content))
    fm = parsed.frontmatter or {}
    try:
        confidence = float(fm.get("confidence_score", plan.confidence))
    except (TypeError, ValueError):
        confidence = plan.confidence
    confidence = min(1.0, max(0.0, confidence))
    concept_ids = [cid for cid in plan.concept_ids if isinstance(cid, str) and cid.startswith("CON-")]
    parsed.frontmatter = {
        "id": exh_id,
        "type": "exhibition",
        "core_concepts": [f"03_Concepts/{cid}" for cid in concept_ids],
        "confidence_score": confidence,
        "last_updated": today,
    }
    body = _strip_embedded_frontmatter(parsed.body or "")
    allowed_targets = {f"03_Concepts/{cid}" for cid in concept_ids}
    body = _strip_out_of_scope_curator_links(body, allowed_targets)
    body = re.sub(r"(?im)^##\s+", r"### ", body)
    required = [
        "- **1. Executive Brief**:",
        "- **2. Theoretical Foundation**:",
        "- **3. Actionable Directives for Agent**:",
    ]
    for label in required:
        if label not in body:
            body = f"{body.rstrip()}\n\n{label} "
    parsed.body = body.strip()
    return parsed.to_markdown()


def _run_pass1_atoms(
    paths: cfg.WikiPaths,
    client,
    callbacks: IngestCallbacks,
    summary_data: SummaryData,
    context_id: str,
    relpath: str,
    excerpt: str,
    today: str,
    staging: Path,
) -> list[tuple[Path, Path, PageChange]]:
    """Draft L2 Atom pages for all atom_candidates in summary_data."""
    staged: list[tuple[Path, Path, PageChange]] = []

    callbacks.on_pass1_start(len(summary_data.atom_candidates))

    for candidate in summary_data.atom_candidates:
        atom_id, exists = _find_existing_atom(paths, candidate.name)
        operation = "updated" if exists else "created"
        callbacks.on_fragment_drafting(atom_id, candidate.name, operation)

        final_path = paths.atoms / f"{atom_id}.md"
        staged_path = staging / f"02_Atoms__{atom_id}.md"

        if exists:
            existing_content = page_writer.read_page(final_path)
            existing_md = existing_content.to_markdown() if existing_content else ""
            messages = prompts.build_merge_atom_messages(
                existing_content=existing_md,
                name=candidate.name,
                new_context_id=context_id,
                new_source_path=relpath,
                new_description=candidate.one_liner,
                excerpt=excerpt,
                today=today,
            )
        else:
            messages = prompts.build_fragment_page_messages(
                fragment_id=atom_id,
                name=candidate.name,
                fragment_type=candidate.type,
                one_liner=candidate.one_liner,
                context_id=context_id,
                source_path=relpath,
                excerpt=excerpt,
                today=today,
            )

        content = _stream_page(client, messages, callbacks)
        if not content:
            raise LLMError(f"Empty response for atom '{candidate.name}'")
        content = _enforce_atom_contract(
            content,
            atom_id=atom_id,
            candidate=candidate,
            context_id=context_id,
            relpath=relpath,
            today=today,
        )

        staged_path.write_text(content, encoding="utf-8")
        change = PageChange(
            id=atom_id,
            path=f"02_Atoms/{atom_id}.md",
            layer="02_Atoms",
            operation=operation,
        )
        staged.append((staged_path, final_path, change))
        callbacks.on_fragment_written(change)

    return staged


# ---------------------------------------------------------------------------
# Pass 2 — L3 Themes
# ---------------------------------------------------------------------------


def _run_pass2_concepts(
    paths: cfg.WikiPaths,
    client,
    callbacks: IngestCallbacks,
    atom_ids: list[str],
    today: str,
    staging: Path,
) -> list[tuple[Path, Path, PageChange]]:
    """Cluster atoms into L3 Concept pages."""
    staged: list[tuple[Path, Path, PageChange]] = []

    if len(atom_ids) < 2:
        return staged  # Need at least 2 atoms to cluster

    atom_summaries = []
    for aid in atom_ids:
        summary = _atom_summary(paths, aid)
        if summary:
            atom_summaries.append(summary)

    callbacks.on_pass2_start(len(atom_summaries))

    # Get clustering plan
    cluster_messages = prompts.build_concept_clustering_messages(atom_summaries)
    try:
        raw = client.chat(cluster_messages, thinking=False, json_mode=True, temperature=0.2)
        cluster_result: ConceptClusterResult = _parse_json_model(raw, ConceptClusterResult)
    except (ValueError, LLMError) as e:
        import sys
        print(f"Warning: Concept clustering failed: {e}", file=sys.stderr)
        return staged  # Non-fatal — skip concept layer for this run

    plans: list[ConceptPlan] = []
    for plan in cluster_result.concepts:
        plans.extend(_split_plan_by_topic_boundary(paths, plan))
    plans = _add_unassigned_atom_fallback_plans(paths, plans, atom_ids)
    plans = _disambiguate_concept_plan_titles(paths, plans)

    for plan in plans:
        if len(plan.atom_ids) < 2:
            continue
        concept_id = _gen_id("CON")
        callbacks.on_theme_drafting(concept_id, plan.name)

        # Build atoms content for the concept page prompt
        # Note: headings use plain ID (no wikilink) to prevent LLM double-wrapping in output
        atoms_content = ""
        for aid in plan.atom_ids:
            ap = page_writer.read_page(paths.atoms / f"{aid}.md")
            if ap:
                atoms_content += f"\n### Atom {aid}\n{ap.body[:600]}\n"

        messages = prompts.build_theme_page_messages(
            theme_id=concept_id,
            name=plan.name,
            domain=plan.domain,
            fragment_ids=plan.atom_ids,
            fragments_content=atoms_content,
            today=today,
        )
        content = _stream_page(client, messages, callbacks)
        if not content:
            continue
        content = _enforce_concept_contract(
            content,
            concept_id=concept_id,
            plan=plan,
            today=today,
        )
        parsed_content = page_writer.parse_page(content)
        try:
            confidence = float(parsed_content.frontmatter.get("confidence_score", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < 0.5:
            continue

        final_path = paths.concepts / f"{concept_id}.md"
        staged_path = staging / f"03_Concepts__{concept_id}.md"
        staged_path.write_text(content, encoding="utf-8")
        change = PageChange(
            id=concept_id,
            path=f"03_Concepts/{concept_id}.md",
            layer="03_Concepts",
            operation="created",
        )
        staged.append((staged_path, final_path, change))
        callbacks.on_theme_written(change)

    return staged


def _set_l3_result_status(
    paths: cfg.WikiPaths,
    source_ids: list[int],
    concept_staged: list[tuple[Path, Path, PageChange]],
) -> None:
    """Reflect global L3 clustering outcome without changing Curator schema."""
    if not source_ids:
        return
    has_atoms = paths.atoms.exists() and any(paths.atoms.glob("ATM-*.md"))
    if concept_staged:
        covered_source_ids = _source_ids_with_l3_coverage(paths, source_ids)
        missing_source_ids = [sid for sid in source_ids if sid not in covered_source_ids]
        if covered_source_ids:
            db.set_sources_layer_status(paths.state_db, covered_source_ids, "l3", "done")
        if missing_source_ids:
            db.set_sources_layer_status(
                paths.state_db,
                missing_source_ids,
                "l3",
                "error",
                error="concept_coverage_missing",
            )
    elif has_atoms:
        db.set_sources_layer_status(
            paths.state_db,
            source_ids,
            "l3",
            "error",
            error="concept_clustering_failed",
        )
    else:
        db.set_sources_layer_status(paths.state_db, source_ids, "l3", "skipped")


def _source_ids_with_l2_done(paths: cfg.WikiPaths) -> list[int]:
    with db.connect(paths.state_db) as conn:
        rows = conn.execute(
            "SELECT id FROM sources WHERE l2_status = 'done' ORDER BY id ASC"
        ).fetchall()
    return [int(row["id"]) for row in rows]


def _source_ids_with_l3_coverage(paths: cfg.WikiPaths, source_ids: list[int]) -> list[int]:
    if not source_ids:
        return []
    context_by_source: dict[int, str] = {}
    with db.connect(paths.state_db) as conn:
        placeholders = ",".join("?" for _ in source_ids)
        rows = conn.execute(
            f"SELECT id, context_id FROM sources WHERE id IN ({placeholders})",
            tuple(source_ids),
        ).fetchall()
    for row in rows:
        context_id = str(row["context_id"] or "")
        if context_id.startswith("CTX-"):
            context_by_source[int(row["id"])] = context_id

    atom_context: dict[str, str] = {}
    if paths.atoms.exists():
        for atom_path in paths.atoms.glob("ATM-*.md"):
            context_id = _atom_context_id(paths, atom_path.stem)
            if context_id:
                atom_context[atom_path.stem] = context_id

    covered_contexts: set[str] = set()
    if paths.concepts.exists():
        for concept_path in paths.concepts.glob("CON-*.md"):
            concept = page_writer.read_page(concept_path)
            for atom_id in _concept_atom_ids(concept):
                context_id = atom_context.get(atom_id)
                if context_id:
                    covered_contexts.add(context_id)

    return [
        source_id
        for source_id, context_id in context_by_source.items()
        if context_id in covered_contexts
    ]


def _source_ids_with_l2_done_and_l3_unset(paths: cfg.WikiPaths) -> list[int]:
    with db.connect(paths.state_db) as conn:
        rows = conn.execute(
            "SELECT id FROM sources "
            "WHERE l2_status = 'done' AND l3_status IN ('pending', 'skipped') "
            "ORDER BY id ASC"
        ).fetchall()
    return [int(row["id"]) for row in rows]


def _mark_existing_l3_done_if_present(paths: cfg.WikiPaths) -> None:
    if paths.concepts.exists() and any(paths.concepts.glob("CON-*.md")):
        source_ids = _source_ids_with_l2_done_and_l3_unset(paths)
        if source_ids:
            db.set_sources_layer_status(paths.state_db, source_ids, "l3", "done")


# ---------------------------------------------------------------------------
# Pass 3 — L4 Curations
# ---------------------------------------------------------------------------


def _run_pass3_synthesis(
    paths: cfg.WikiPaths,
    client,
    callbacks: IngestCallbacks,
    concept_ids: list[str],
    today: str,
    staging: Path,
) -> list[tuple[Path, Path, PageChange]]:
    """Build L4 Exhibition pages from concept clusters."""
    staged: list[tuple[Path, Path, PageChange]] = []

    if not concept_ids:
        return staged

    concept_summaries = []
    for cid in concept_ids:
        cp = page_writer.read_page(paths.concepts / f"{cid}.md")
        if cp:
            # Prefer frontmatter name, then H1 heading, then ID
            name = cp.frontmatter.get("name", "")
            if not name:
                for line in cp.body.splitlines():
                    if line.startswith("# "):
                        name = line[2:].strip()
                        break
            if not name:
                name = cid
            concept_summaries.append({
                "id": cid,
                "name": name,
                "domain": cp.frontmatter.get("domain", ""),
                "atom_count": len(_concept_atom_ids(cp)),
            })

    callbacks.on_pass3_start(len(concept_summaries))

    plan_messages = prompts.build_curation_planning_messages(concept_summaries)
    try:
        raw = client.chat(plan_messages, thinking=False, json_mode=True, temperature=0.2)
        plan_result: SynthesisPlanResult = _parse_json_model(raw, SynthesisPlanResult)
    except (ValueError, LLMError) as e:
        import sys
        print(f"Warning: Synthesis planning failed: {e}", file=sys.stderr)
        return staged

    plans: list[SynthesisPlan] = []
    for plan in plan_result.synthesis_plans:
        plans.extend(_split_synthesis_plan_by_topic_boundary(paths, plan))

    for plan in plans:
        if not plan.concept_ids:
            continue
        exh_id = _gen_id("EXH")
        callbacks.on_curation_drafting(exh_id, plan.topic)

        # Note: headings use plain ID (no wikilink) to prevent LLM double-wrapping in output
        concepts_content = ""
        flagged_ids: list[str] = []
        for cid in plan.concept_ids:
            cp = page_writer.read_page(paths.concepts / f"{cid}.md")
            if cp:
                concepts_content += f"\n### Concept {cid}\n{cp.body[:4000]}\n"
                for atm_id in _concept_atom_ids(cp):
                    atm_path = paths.atoms / f"{atm_id}.md"
                    atm_page = page_writer.read_page(atm_path)
                    if atm_page and atm_page.frontmatter.get("is_flagged_for_agent") is True:
                        if atm_id not in flagged_ids:
                            flagged_ids.append(atm_id)

        messages = prompts.build_curation_page_messages(
            curation_id=exh_id,
            topic=plan.topic,
            theme_ids=plan.concept_ids,
            themes_content=concepts_content,
            confidence=plan.confidence,
            today=today,
            flagged_fragment_ids=flagged_ids,
        )
        content = _stream_page(client, messages, callbacks)
        if not content:
            continue
        content = _enforce_exhibition_contract(
            content,
            exh_id=exh_id,
            plan=plan,
            today=today,
        )

        final_path = paths.exhibitions / f"{exh_id}.md"
        staged_path = staging / f"04_Exhibitions__{exh_id}.md"
        staged_path.write_text(content, encoding="utf-8")
        change = PageChange(
            id=exh_id,
            path=f"04_Exhibitions/{exh_id}.md",
            layer="04_Exhibitions",
            operation="created",
        )
        staged.append((staged_path, final_path, change))
        callbacks.on_curation_written(change)

    return staged


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------


def ingest_source(
    paths: cfg.WikiPaths,
    source_id: int,
    client,
    callbacks: IngestCallbacks,
    *,
    mode: str = "interactive",
    thinking_for_extraction: bool = True,
) -> IngestResult:
    """Phase A — extract L2 Atoms from a single source.

    Concepts and Synthesis are built globally AFTER all sources are processed.
    Call ingest_pending() to run the full pipeline.
    """
    started = _now_iso()

    # Load source row
    with db.connect(paths.state_db) as conn:
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        if row is None:
            result = IngestResult(source_id=source_id, source_title="?",
                                  error=f"No source with id {source_id}")
            callbacks.on_error(result.error)
            return result
        source_row = dict(row)

    context_id = source_row.get("context_id") or ""
    file_path = paths.root / source_row["relpath"]
    db.set_source_layer_status(paths.state_db, source_id, "l2", "running")

    # Parse source
    try:
        parsed = parsers.parse(file_path)
    except parsers.ParserError as e:
        result = IngestResult(source_id=source_id, source_title=source_row["relpath"],
                              error=f"Parse failed: {e}")
        _mark_source_status(paths, source_id, "error", error_reason="parse_error")
        db.set_source_layer_status(paths.state_db, source_id, "l2", "error", error=result.error)
        _record_ingest_run(paths, source_id, started, mode, 0, 0, result.error)
        callbacks.on_error(result.error)
        return result

    callbacks.on_start(source_id, parsed.title, context_id)

    if not _is_valid_context_id(context_id):
        result = IngestResult(
            source_id=source_id,
            source_title=parsed.title,
            error=f"Missing or invalid L1 Context ID for {source_row['relpath']}",
        )
        _mark_source_status(paths, source_id, "error", error_reason="missing_context")
        db.set_source_layer_status(paths.state_db, source_id, "l1", "error", error=result.error)
        db.set_source_layer_status(paths.state_db, source_id, "l2", "pending", error=result.error)
        _record_ingest_run(paths, source_id, started, mode, 0, 0, result.error)
        callbacks.on_error(result.error)
        return result

    # Load or regenerate L1 context data
    summary_data: SummaryData | None = None
    context_path = paths.contexts / f"{context_id}.md"
    sum_page = page_writer.read_page(context_path)
    if sum_page is None:
        result = IngestResult(
            source_id=source_id,
            source_title=parsed.title,
            error=f"L1 Context page does not exist: 01_Contexts/{context_id}.md",
        )
        _mark_source_status(paths, source_id, "error", error_reason="missing_context")
        db.set_source_layer_status(paths.state_db, source_id, "l1", "error", error=result.error)
        db.set_source_layer_status(paths.state_db, source_id, "l2", "pending", error=result.error)
        _record_ingest_run(paths, source_id, started, mode, 0, 0, result.error)
        callbacks.on_error(result.error)
        return result

    # Extract atom_candidates from the context page body
    candidates = []
    in_candidates = False
    for line in sum_page.body.splitlines():
        if re.match(r"^##\s+(?:\d+\.\s+)?(?:Atom|Fragmentation) Candidates\s*$", line):
            in_candidates = True
            continue
        if in_candidates and line.startswith("## "):
            break
        if in_candidates and line.startswith("- ["):
            # Format: - [type] Name: one_liner
            try:
                type_end = line.index("]")
                atype = line[3:type_end]
                rest = line[type_end + 2:]
                name, one_liner = rest.split(":", 1) if ":" in rest else (rest, "")
                candidates.append(AtomCandidate(
                    name=name.strip(),
                    type=atype.strip(),
                    one_liner=one_liner.strip(),
                ))
            except (ValueError, IndexError):
                pass
    summary_data = SummaryData(
        title=parsed.title,
        domain=sum_page.frontmatter.get("domain", ""),
        summary="",
        atom_candidates=candidates,
        tags=sum_page.frontmatter.get("tags", []),
    )

    if summary_data is None or not summary_data.atom_candidates:
        # Re-run Pass 0 inline (summary was missing or malformed)
        source_text = parsed.text[:MAX_SOURCE_CHARS]
        messages = prompts.build_summary_messages(parsed.title, source_text)
        try:
            raw = client.chat(messages, thinking=thinking_for_extraction, json_mode=True, temperature=0.2)
            summary_data = _parse_json_model(_extract_json(raw), SummaryData)
        except (ValueError, LLMError) as e:
            result = IngestResult(source_id=source_id, source_title=parsed.title,
                                  error=f"Summary extraction failed: {e}")
            _mark_source_status(paths, source_id, "error", error_reason="llm_error")
            db.set_source_layer_status(paths.state_db, source_id, "l2", "error", error=result.error)
            _record_ingest_run(paths, source_id, started, mode, 0, 0, result.error)
            callbacks.on_error(result.error)
            return result

    # Interactive confirmation
    if mode == "interactive" and not callbacks.ask_confirm(summary_data):
        result = IngestResult(source_id=source_id, source_title=parsed.title, skipped=True)
        callbacks.on_complete(result)
        return result

    today = _now_iso()
    max_excerpt = getattr(client, "optimal_chunk_chars", 30000)
    excerpt = _build_excerpt(parsed.text, max_chars=max_excerpt)
    staging = Path(tempfile.mkdtemp(prefix="curator-ingest-"))

    try:
        all_staged: list[tuple[Path, Path, PageChange]] = []

        # Pass 1 — L2 Fragments
        try:
            atom_staged = _run_pass1_atoms(
                paths, client, callbacks, summary_data, context_id,
                source_row["relpath"], excerpt, today, staging,
            )
            all_staged.extend(atom_staged)
        except LLMError as e:
            result = IngestResult(source_id=source_id, source_title=parsed.title,
                                  error=f"Fragment pass failed: {e}")
            _mark_source_status(paths, source_id, "error", error_reason="llm_error")
            db.set_source_layer_status(paths.state_db, source_id, "l2", "error", error=result.error)
            _record_ingest_run(paths, source_id, started, mode, 0, 0, result.error)
            callbacks.on_error(result.error)
            return result

        new_fragment_ids = [c.id for _, _, c in atom_staged if c.layer == "02_Atoms"]
        # Phase A: commit Atom files immediately
        callbacks.on_finalizing()
        changes: list[PageChange] = []
        fragments_created = fragments_updated = 0

        for staged_path, final_path, change in atom_staged:
            final_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged_path, final_path)
            changes.append(change)
            if change.operation == "created":
                fragments_created += 1
            else:
                fragments_updated += 1

        # Mark source as ingested in DB (fragments written)
        _mark_source_status(paths, source_id, "curated", last_ingested=_now_iso())
        db.set_source_layer_status(paths.state_db, source_id, "l2", "done")
        _record_ingest_run(paths, source_id, started, mode,
                           fragments_created, fragments_updated, error=None)

        result = IngestResult(
            source_id=source_id,
            source_title=parsed.title,
            fragments_created=fragments_created,
            fragments_updated=fragments_updated,
            changes=changes,
        )
        callbacks.on_complete(result)
        return result

    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _auto_discover_pending(paths: cfg.WikiPaths) -> tuple[int, int]:
    """Scan raw_dirs for files not yet tracked. 
    Returns (discovered_count, removed_count).
    """
    from . import ingest_raw
    with db.connect(paths.state_db) as conn:
        rows = conn.execute("SELECT id, relpath FROM sources").fetchall()
        tracked = {row["relpath"]: row["id"] for row in rows}

    valid_prefixes = tuple(str(d.relative_to(paths.root)) for d in paths.raw_dirs)

    orphans = []
    for relpath, sid in tracked.items():
        if not (paths.root / relpath).exists() or not relpath.startswith(valid_prefixes):
            orphans.append(sid)

    removed = 0
    if orphans:
        with db.connect(paths.state_db) as conn:
            conn.execute(
                f"DELETE FROM sources WHERE id IN ({','.join('?' * len(orphans))})",
                orphans,
            )
        removed = len(orphans)
        for relpath in [k for k, v in tracked.items() if v in orphans]:
            del tracked[relpath]

    discovered = 0
    for raw_dir in paths.raw_dirs:
        if not raw_dir.exists():
            continue
        for file_path in raw_dir.rglob("*"):
            if not file_path.is_file() or file_path.name.startswith("."):
                continue
            if not parsers.is_supported(file_path):
                continue
            try:
                relpath = str(file_path.relative_to(paths.root))
            except ValueError:
                continue
            if relpath in tracked:
                continue
            outcome = ingest_raw.add_file(paths, file_path)
            if outcome.result == ingest_raw.AddResult.ADDED:
                discovered += 1
    return discovered, removed



# ---------------------------------------------------------------------------
# Phase B — Global L3 Themes (all Fragments → Themes)
# ---------------------------------------------------------------------------


def _run_global_pass2_concepts(
    paths: cfg.WikiPaths,
    client,
    callbacks: IngestCallbacks,
    today: str,
    staging: Path,
) -> list[tuple[Path, Path, PageChange]]:
    """Phase B: cluster ALL existing Atom files into L3 Concepts."""
    if not paths.atoms.exists():
        return []
    all_atom_ids = [
        md.stem for md in sorted(paths.atoms.glob("*.md"))
        if not md.name.startswith(".")
    ]
    if len(all_atom_ids) < 2:
        return []
    return _run_pass2_concepts(paths, client, callbacks, all_atom_ids, today, staging)


# ---------------------------------------------------------------------------
# Phase C — Global L4 Curations (all Themes → Curations)
# ---------------------------------------------------------------------------


def _run_global_pass3_synthesis(
    paths: cfg.WikiPaths,
    client,
    callbacks: IngestCallbacks,
    today: str,
    staging: Path,
) -> list[tuple[Path, Path, PageChange]]:
    """Phase C: build L4 Exhibitions from ALL existing Concept files."""
    if not paths.concepts.exists():
        return []
    all_concept_ids = [
        md.stem for md in sorted(paths.concepts.glob("*.md"))
        if not md.name.startswith(".")
    ]
    if len(all_concept_ids) < 1:
        return []
    return _run_pass3_synthesis(paths, client, callbacks, all_concept_ids, today, staging)


# ---------------------------------------------------------------------------
# Phase D helpers — ledger + overview
# ---------------------------------------------------------------------------


def _update_ledger(paths: cfg.WikiPaths) -> None:
    """Rebuild ledger.md with current collection stats."""
    total_contexts  = sum(1 for _ in paths.contexts.glob("*.md"))   if paths.contexts.exists()   else 0
    total_atoms     = sum(1 for _ in paths.atoms.glob("*.md"))       if paths.atoms.exists()      else 0
    total_concepts  = sum(1 for _ in paths.concepts.glob("*.md"))    if paths.concepts.exists()   else 0
    total_exhibs    = sum(1 for _ in paths.exhibitions.glob("*.md")) if paths.exhibitions.exists() else 0

    with db.connect(paths.state_db) as conn:
        row = conn.execute(
            "SELECT COUNT(*) as n, MAX(last_ingested) as last FROM sources WHERE status='curated'"
        ).fetchone()
        curated_sources = row["n"] if row else 0
        last_ingested = row["last"] if row else ""

    lines = [
        "---",
        "title: Ledger",
        "type: ledger",
        f"updated: {_now_iso()}",
        "---",
        "",
        "# .curator/ledger.md \u2014 Knowledge Ledger",
        "",
        "> Auto-maintained by the Curator engine. Updated after every curate. DO NOT edit manually.",
        "",
        "## Collection Stats",
        "",
        "| Layer | Count |",
        "| --- | --- |",
        f"| Sources curated | {curated_sources} |",
        f"| L1 Contexts    | {total_contexts} |",
        f"| L2 Atoms       | {total_atoms} |",
        f"| L3 Concepts    | {total_concepts} |",
        f"| L4 Exhibitions | {total_exhibs} |",
        "",
        f"*Last curated: {last_ingested or 'never'}*",
        "",
    ]
    paths.ledger.parent.mkdir(parents=True, exist_ok=True)
    paths.ledger.write_text("\n".join(lines), encoding="utf-8")


def _update_overview(paths: cfg.WikiPaths) -> None:
    """Refresh overview.md — summarise every layer in Collections/."""

    def _read_layer(directory: "Path | None") -> list[tuple[str, str, str]]:
        """Return (slug, title, summary) for each .md in directory."""
        if directory is None or not directory.exists():
            return []
        results = []
        for md in sorted(directory.glob("*.md")):
            if md.name.startswith("."):
                continue
            parsed = page_writer.read_page(md)
            title = md.stem
            summary = ""
            if parsed:
                fm = parsed.frontmatter
                title = fm.get("title", title)
                summary = fm.get("summary", "")
                if not summary:
                    # fall back to first non-empty body line
                    for line in (parsed.body or "").splitlines():
                        line = line.strip().lstrip("#").strip()
                        if line and not line.startswith(">"):
                            summary = line[:120]
                            break
            results.append((md.stem, str(title), str(summary)))
        return results

    contexts    = _read_layer(paths.contexts    if paths.contexts.exists()    else None)
    atoms       = _read_layer(paths.atoms       if paths.atoms.exists()       else None)
    concepts    = _read_layer(paths.concepts    if paths.concepts.exists()    else None)
    exhibitions = _read_layer(paths.exhibitions if paths.exhibitions.exists() else None)

    # Domain distribution from L1
    domains: dict[str, int] = {}
    for md in sorted((paths.contexts.glob("*.md") if paths.contexts.exists() else [])):
        if md.name.startswith("."):
            continue
        parsed = page_writer.read_page(md)
        if parsed:
            d = parsed.frontmatter.get("domain", "").strip()
            if d:
                domains[d] = domains.get(d, 0) + 1

    lines = [
        "---",
        "title: Domain Manifest",
        "type: overview",
        f"updated: {_now_iso()}",
        "---",
        "",
        "# .curator/overview.md \u2014 Collections Summary",
        "",
        "> Auto-maintained by the Curator engine. Updated after every curate. DO NOT edit manually.",
        "",
        "## Stats",
        "",
        "| Layer | Count |",
        "| --- | --- |",
        f"| L1 Contexts    | {len(contexts)} |",
        f"| L2 Atoms       | {len(atoms)} |",
        f"| L3 Concepts    | {len(concepts)} |",
        f"| L4 Exhibitions | {len(exhibitions)} |",
        "",
    ]

    if domains:
        lines += ["## Knowledge Domains", ""]
        for domain, count in sorted(domains.items(), key=lambda x: -x[1]):
            lines.append(f"- **{domain}** \u2014 {count} source(s)")
        lines.append("")

    def _layer_section(heading: str, layer_dir: str, entries: list[tuple[str, str, str]]) -> None:
        lines.append(f"## {heading}")
        lines.append("")
        if not entries:
            lines.append("*No pages yet.*")
            lines.append("")
            return
        for slug, title, summary in entries:
            link = f"[[{layer_dir}/{slug}|{title}]]"
            if summary:
                lines.append(f"- {link} — {summary}")
            else:
                lines.append(f"- {link}")
        lines.append("")

    _layer_section("L1 — Contexts",    "01_Contexts",    contexts)
    _layer_section("L2 — Atoms",       "02_Atoms",       atoms)
    _layer_section("L3 — Concepts",    "03_Concepts",    concepts)
    _layer_section("L4 — Exhibitions", "04_Exhibitions", exhibitions)

    paths.overview.parent.mkdir(parents=True, exist_ok=True)
    paths.overview.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------


def ingest_pending(
    paths: cfg.WikiPaths,
    client,
    callbacks_factory: Callable[[], IngestCallbacks],
    *,
    mode: str = "interactive",
    auto_discover: bool = True,
    thinking_for_extraction: bool = True,
    force: bool = False,
) -> list[IngestResult]:
    """Run the full global sequential pipeline over all pending sources.

    Phase A: each pending source → L2 Fragments (sequential, per-source)
    Phase B: ALL Fragment files  → L3 Themes    (global clustering)
    Phase C: ALL Theme files     → L4 Curations (global synthesis)
    Phase D: rebuild index, append log, update ledger + overview

    force=True resets all curated sources back to force_pending so they
    are re-processed even if their content has not changed.
    """
    if auto_discover:
        _auto_discover_pending(paths)

    if force:
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "UPDATE sources SET status = 'force_pending', error_reason = NULL, "
                "l2_status = 'pending', l3_status = 'pending', l4_status = 'pending', layer_error = NULL "
                "WHERE status IN ('curated', 'error')"
            )

    with db.connect(paths.state_db) as conn:
        rows = conn.execute(
            "SELECT id FROM sources WHERE status IN ('pending', 'force_pending', 'error') ORDER BY id ASC"
        ).fetchall()
        pending_ids = [row["id"] for row in rows]

    # Phase A — Atoms per source
    results: list[IngestResult] = []
    for sid in pending_ids:
        cb = callbacks_factory()
        result = ingest_source(paths, sid, client, cb, mode=mode,
                               thinking_for_extraction=thinking_for_extraction)
        results.append(result)
        if result.error and "Ollama" in (result.error or ""):
            break

    has_concepts = any(paths.concepts.glob("*.md")) if paths.concepts.exists() else False
    any_ok = any(r.ok for r in results)
    if not any_ok and not force and has_concepts:
        _mark_existing_l3_done_if_present(paths)
        return results

    today = _now_iso()
    staging = Path(tempfile.mkdtemp(prefix="curator-global-"))
    try:
        cb = callbacks_factory()

        # Phase B — global Concepts
        concept_staged = _run_global_pass2_concepts(paths, client, cb, today, staging)
        for staged_path, final_path, _ in concept_staged:
            final_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged_path, final_path)
        ok_source_ids = [r.source_id for r in results if r.ok]
        l3_source_ids = _source_ids_with_l2_done(paths) if concept_staged else ok_source_ids
        _set_l3_result_status(paths, l3_source_ids, concept_staged)

        # Phase C — global Synthesis (reads freshly-written concepts too)
        syn_staged = _run_global_pass3_synthesis(paths, client, cb, today, staging)
        for staged_path, final_path, _ in syn_staged:
            final_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged_path, final_path)
        db.set_sources_layer_status(paths.state_db, ok_source_ids, "l4", "done")

        # Phase D — rebuild index, log, ledger, overview
        all_changes = [c for _, _, c in concept_staged + syn_staged]
        page_writer.rebuild_index(paths, today)
        if all_changes:
            log_bullets = [f"{c.operation}: [[{c.path.replace('.md', '')}]]" for c in all_changes]
            page_writer.append_log_entry(paths, today, "curate", "global pipeline", log_bullets)
        _update_ledger(paths)
        _update_overview(paths)

    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return results


# ---------------------------------------------------------------------------
# v0.1.0 entry points — pipeline split (wiki add = L1-L3, wiki curate = L4)
# ---------------------------------------------------------------------------


def run_l1_to_l3(
    paths: cfg.WikiPaths,
    client,
    callbacks_factory: Callable[[], IngestCallbacks],
    *,
    mode: str = "interactive",
    auto_discover: bool = True,
    thinking_for_extraction: bool = True,
    force: bool = False,
) -> list[IngestResult]:
    """Run L1→L3 pipeline (Atoms + Concepts) for all pending sources.

    Does NOT generate L4 Exhibitions. Call run_l4_scoped() separately.

    Phase A: each pending source → L2 Atoms (sequential, per-source)
    Phase B: ALL Atom files     → L3 Concepts (global clustering)
    Phase D: rebuild index, ledger, overview
    """
    if auto_discover:
        _auto_discover_pending(paths)

    if force:
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "UPDATE sources SET status = 'force_pending', error_reason = NULL, "
                "l2_status = 'pending', l3_status = 'pending', l4_status = 'pending', layer_error = NULL "
                "WHERE status IN ('curated', 'error')"
            )

    with db.connect(paths.state_db) as conn:
        rows = conn.execute(
            "SELECT id FROM sources WHERE status IN ('pending', 'force_pending', 'error') ORDER BY id ASC"
        ).fetchall()
        pending_ids = [row["id"] for row in rows]

    results: list[IngestResult] = []
    for sid in pending_ids:
        cb = callbacks_factory()
        result = ingest_source(paths, sid, client, cb, mode=mode,
                               thinking_for_extraction=thinking_for_extraction)
        results.append(result)
        if result.error and "Ollama" in (result.error or ""):
            break

    has_concepts = any(paths.concepts.glob("*.md")) if paths.concepts.exists() else False
    any_ok = any(r.ok for r in results)
    if not any_ok and not force and has_concepts:
        _mark_existing_l3_done_if_present(paths)
        return results

    today = _now_iso()
    staging = Path(tempfile.mkdtemp(prefix="curator-l3-"))
    try:
        cb = callbacks_factory()
        concept_staged = _run_global_pass2_concepts(paths, client, cb, today, staging)
        for staged_path, final_path, _ in concept_staged:
            final_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged_path, final_path)
        ok_source_ids = [r.source_id for r in results if r.ok]
        l3_source_ids = _source_ids_with_l2_done(paths) if concept_staged else ok_source_ids
        _set_l3_result_status(paths, l3_source_ids, concept_staged)

        all_changes = [c for _, _, c in concept_staged]
        page_writer.rebuild_index(paths, today)
        if all_changes:
            log_bullets = [f"{c.operation}: [[{c.path.replace('.md', '')}]]" for c in all_changes]
            page_writer.append_log_entry(paths, today, "add", "L1-L3 pipeline", log_bullets)
        _update_ledger(paths)
        _update_overview(paths)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return results


def run_l3_from_existing_atoms(
    paths: cfg.WikiPaths,
    client,
    callbacks_factory: Callable[[], IngestCallbacks],
) -> list[PageChange]:
    """Regenerate L3 Concepts from existing L2 Atoms without touching L1/L2.

    L3 clustering is global, so this replaces the current Concept set. Existing
    L4 Exhibitions are invalidated because their Concept inputs may disappear.
    """
    today = _now_iso()
    source_ids = _source_ids_with_l2_done(paths)
    staging = Path(tempfile.mkdtemp(prefix="curator-l3-only-"))
    try:
        cb = callbacks_factory()
        concept_staged = _run_global_pass2_concepts(paths, client, cb, today, staging)
        if paths.concepts.exists():
            for md_path in paths.concepts.glob("CON-*.md"):
                md_path.unlink()
        if paths.exhibitions.exists():
            for md_path in paths.exhibitions.glob("EXH-*.md"):
                md_path.unlink()
        for staged_path, final_path, _ in concept_staged:
            final_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged_path, final_path)

        _set_l3_result_status(paths, source_ids, concept_staged)
        if source_ids:
            db.set_sources_layer_status(paths.state_db, source_ids, "l4", "pending")

        changes = [c for _, _, c in concept_staged]
        page_writer.rebuild_index(paths, today)
        if changes:
            log_bullets = [f"{c.operation}: [[{c.path.replace('.md', '')}]]" for c in changes]
            page_writer.append_log_entry(paths, today, "add", "L3-only regeneration", log_bullets)
        _update_ledger(paths)
        _update_overview(paths)
        return changes
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _get_scoped_concept_ids(
    paths: cfg.WikiPaths,
    curate_spec,
) -> list[str]:
    """Return Concept IDs whose Atoms trace back to sources matching curate_spec.

    Traces: CON → ATM.parent_source → fnmatch against curate_spec.sources.include/exclude.
    If curate_spec has no include patterns, all concepts are returned.
    """
    if not paths.concepts.exists():
        return []

    all_concept_ids = [
        md.stem for md in sorted(paths.concepts.glob("*.md"))
        if not md.name.startswith(".")
    ]

    if not curate_spec.sources.include:
        return all_concept_ids

    def _context_source_path(context_link: str) -> str:
        target = str(context_link or "").strip()
        if target.startswith("[[") and target.endswith("]]"):
            target = target[2:-2].strip()
        if "|" in target:
            target = target.split("|", 1)[0].strip()
        context_id = target.rsplit("/", 1)[-1].removesuffix(".md")
        if not context_id.startswith("CTX-"):
            return ""
        ctx_page = page_writer.read_page(paths.contexts / f"{context_id}.md")
        if not ctx_page:
            return ""
        source_path = str(ctx_page.frontmatter.get("source_path", "") or "")
        if source_path.startswith("[[") and source_path.endswith("]]"):
            source_path = source_path[2:-2].strip()
        if "|" in source_path:
            source_path = source_path.split("|", 1)[0].strip()
        return source_path

    scoped = []
    for cid in all_concept_ids:
        cp = page_writer.read_page(paths.concepts / f"{cid}.md")
        if not cp:
            continue
        for atm_id in _concept_atom_ids(cp):
            atm_page = page_writer.read_page(paths.atoms / f"{atm_id}.md")
            if not atm_page:
                continue
            parent_source = atm_page.frontmatter.get("parent_source", "")
            source_path = _context_source_path(str(parent_source or ""))
            if source_path and curate_spec.matches_sources(source_path):
                scoped.append(cid)
                break
    return scoped


def run_l4_scoped(
    paths: cfg.WikiPaths,
    client,
    callbacks: IngestCallbacks,
    curate_spec,
    today: str,
    staging: Path,
) -> list[tuple[Path, Path, PageChange]]:
    """Run L4 Exhibition synthesis, optionally scoped by curate_spec source filters.

    curate_spec may be None for unscoped global synthesis.
    """
    if curate_spec is not None and curate_spec.sources.include:
        concept_ids = _get_scoped_concept_ids(paths, curate_spec)
    else:
        if not paths.concepts.exists():
            return []
        concept_ids = [
            md.stem for md in sorted(paths.concepts.glob("*.md"))
            if not md.name.startswith(".")
        ]
    if not concept_ids:
        return []
    return _run_pass3_synthesis(paths, client, callbacks, concept_ids, today, staging)


def add_atom_from_insight(
    paths: cfg.WikiPaths,
    client,
    insight_text: str,
    today: str,
    source_hint: str = "conversational",
) -> Optional[str]:
    """Create a new L2 Atom from a conversational insight or query answer.

    Returns the new atom_id, or None on failure.
    """
    messages = prompts.build_summary_messages("Conversational Insight", insight_text[:4000])
    try:
        raw = client.chat(messages, thinking=False, json_mode=True, temperature=0.2)
        summary_data = _parse_json_model(_extract_json(raw), SummaryData)
    except (ValueError, LLMError):
        return None

    if not summary_data.atom_candidates:
        return None

    candidate = summary_data.atom_candidates[0]
    atom_id = _gen_id("ATM")

    messages = prompts.build_fragment_page_messages(
        fragment_id=atom_id,
        name=candidate.name,
        fragment_type=candidate.type,
        one_liner=candidate.one_liner,
        context_id="",
        source_path=source_hint,
        excerpt=insight_text[:2000],
        today=today,
    )

    tmp_staging = Path(tempfile.mkdtemp(prefix="curator-insight-"))
    try:
        full = ""
        gen = client.chat_stream(messages, thinking=False, temperature=0.3)
        try:
            while True:
                chunk = next(gen)
                full += chunk
        except StopIteration as stop:
            if stop.value:
                full = stop.value

        content = page_writer.strip_llm_noise(full)
        content = page_writer.sanitize_wikilinks(content)
        if not content:
            return None

        final_path = paths.atoms / f"{atom_id}.md"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_text(content, encoding="utf-8")
        return atom_id
    except Exception:
        return None
    finally:
        shutil.rmtree(tmp_staging, ignore_errors=True)
