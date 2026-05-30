"""LLM compilation pipeline — multi-phase DAG build.

This module provides the core logic for high-level knowledge synthesis:
- Phase A (L2 Atoms) & Phase B (L3 Concepts): Driven by `wiki add`.
- Phase C (L4 Exhibitions): Driven by `wiki curate`.

The pipeline is sequential to ensure cross-source concepts and exhibitions 
emerge correctly. All IDs are UUID-based (ATM-/CON-/EXH-).
"""

from __future__ import annotations
from . import constants as consts

import json
import re
import shutil
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from collections import Counter, defaultdict

from pydantic import BaseModel, Field, ValidationError

from . import config as cfg
from . import constants as consts
from . import db
from . import page_writer
from . import parsers
from . import prompts
from .llm import LLMError


MAX_SOURCE_CHARS = 100_000
EXCERPT_CHARS = 4000


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class AtomCandidate(BaseModel):
    name: str
    type: str = consts.CLAIM_TYPE_FACT
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
    domain: str = ""
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


def invalidate_exh_cache_for_concept(concept_id: str, db_path: str) -> list[str]:
    """Mark unverified Exhibitions that depend on concept_id as cache-invalid."""
    state_db = Path(db_path)
    paths = cfg.WikiPaths(state_db.parent.parent)
    if not paths.exhibitions.exists():
        return []
    invalidated: list[str] = []
    for exh_path in sorted(paths.exhibitions.glob(f"{consts.PREFIX_L4}-*.md")):
        page = page_writer.read_page(exh_path)
        if not page:
            continue
        fm = page.frontmatter
        if bool(fm.get("is_verified_by_human", False)):
            continue
        core = fm.get("core_concepts", [])
        if isinstance(core, str):
            core_values = [core]
        elif isinstance(core, list):
            core_values = [str(v) for v in core]
        else:
            core_values = []
        if not any(str(v).rstrip("/").rsplit("/", 1)[-1] == concept_id for v in core_values):
            continue
        fm["is_cache_invalidated"] = True
        page.frontmatter = fm
        exh_path.write_text(page.to_markdown(), encoding="utf-8")
        invalidated.append(exh_path.stem)
    return invalidated


def _stream_page(client, messages, callbacks: IngestCallbacks) -> str:
    """Stream a page from LLM, collecting chunks via callbacks. Returns full text."""
    full = ""
    gen = client.chat_stream(messages, temperature=0.3)
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
        return _gen_id(consts.PREFIX_L2), False
    for md in paths.atoms.glob("*.md"):
        parsed = page_writer.read_page(md)
        if parsed and parsed.frontmatter.get("type") == consts.TYPE_L2:
            # Match by name in H1
            for line in parsed.body.splitlines():
                if line.startswith("# ") and name.lower() in line.lower():
                    return md.stem, True
    return _gen_id(consts.PREFIX_L2), False


def _is_valid_context_id(context_id: str) -> bool:
    return bool(context_id) and context_id.startswith(f"{consts.PREFIX_L1}-") and len(context_id) > 4


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
    curator_prefixes = (f"{consts.LAYER_L1}/", f"{consts.LAYER_L2}/", f"{consts.LAYER_L3}/", f"{consts.LAYER_L4}/")

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




def _disambiguate_concept_plan_titles(
    paths: cfg.WikiPaths,
    plans: list[ConceptPlan],
    workspace_keywords: list[str] | None = None,
) -> list[ConceptPlan]:
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
        suffix = _concept_plan_suffix(paths, plan, workspace_keywords=workspace_keywords or [])
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


def _concept_plan_suffix(
    paths: cfg.WikiPaths,
    plan: ConceptPlan,
    workspace_keywords: list[str] = [],
) -> str:
    # Disambiguation suffix for same-titled concepts.
    # If workspace_keywords are provided, prefer the one whose first word
    # matches the plan domain prefix (case-insensitive).
    # Fall back to domain slug first segment, then last 4 hex chars of atom ID.
    if workspace_keywords:
        domain_prefix = plan.domain.split("-")[0].lower() if plan.domain else ""
        for kw in workspace_keywords:
            if domain_prefix and kw.split()[0].lower() == domain_prefix:
                return kw
        # No match — use the first keyword as-is
        return workspace_keywords[0]
    if plan.domain:
        return plan.domain.split("-")[0].title()
    if plan.atom_ids:
        return plan.atom_ids[0][-4:].upper()
    return "Variant"


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
        "claim_type": parsed.frontmatter.get("claim_type", consts.CLAIM_TYPE_FACT),
        "one_liner": one_liner[:260],
    }


def _atom_embedding_text(paths: cfg.WikiPaths, atom_id: str) -> str:
    summary = _atom_summary(paths, atom_id)
    if not summary:
        return ""
    parts = [
        str(summary.get("name") or ""),
        str(summary.get("claim_type") or ""),
        str(summary.get("one_liner") or ""),
    ]
    return " | ".join(part for part in parts if part).strip()


def _get_embeddings(texts: list[str], client) -> list[list[float]] | None:
    """Return embeddings using provider-specific local paths, or None to fall back."""
    if not texts:
        return []

    embed_texts = getattr(client, "embed_texts", None)
    if callable(embed_texts):
        try:
            vectors = embed_texts(texts)
            if vectors and len(vectors) == len(texts):
                return [list(map(float, vec)) for vec in vectors]
        except Exception:
            pass

    active = getattr(client, "active_provider", client)
    host = getattr(active, "host", "")
    if host:
        vectors = _embed_via_ollama(texts, active)
        if vectors is not None:
            return vectors

    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        return None

    try:
        model = SentenceTransformer("all-MiniLM-L6-v2")
        vectors = model.encode(texts, convert_to_numpy=False)
        return [list(map(float, vec)) for vec in vectors]
    except Exception:
        return None


def _embed_via_ollama(texts: list[str], client) -> list[list[float]] | None:
    """Use Ollama's local embeddings endpoint when an Ollama host is available."""
    import httpx

    host = getattr(client, "host", "")
    if not host:
        return None
    embed_model = "nomic-embed-text"
    vectors: list[list[float]] = []
    try:
        with httpx.Client(timeout=30.0) as http:
            for text in texts:
                response = http.post(
                    f"{host}/api/embeddings",
                    json={"model": embed_model, "prompt": text},
                )
                response.raise_for_status()
                vector = response.json().get("embedding")
                if not isinstance(vector, list):
                    return None
                vectors.append([float(value) for value in vector])
    except Exception:
        return None
    return vectors


def _cosine_distance(a: list[float], b: list[float]) -> float:
    import math

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1.0 - (dot / (norm_a * norm_b))


def _cluster_embeddings_threshold(
    ids: list[str],
    embeddings: list[list[float]],
    eps: float,
) -> list[list[str]]:
    """Small dependency-free fallback for test/dev environments without sklearn."""
    clusters: list[list[str]] = []
    centroids: list[list[float]] = []
    for atom_id, vector in zip(ids, embeddings):
        best_idx = -1
        best_dist = 2.0
        for idx, centroid in enumerate(centroids):
            dist = _cosine_distance(vector, centroid)
            if dist < best_dist:
                best_idx = idx
                best_dist = dist
        if best_idx >= 0 and best_dist <= eps:
            clusters[best_idx].append(atom_id)
            size = len(clusters[best_idx])
            centroids[best_idx] = [
                (old * (size - 1) + new) / size
                for old, new in zip(centroids[best_idx], vector)
            ]
        else:
            clusters.append([atom_id])
            centroids.append(vector)
    return clusters


def cluster_atoms_by_embedding(
    paths: cfg.WikiPaths,
    atom_ids: list[str],
    client,
    eps: float = 0.35,
) -> list[list[str]] | None:
    """Cluster L2 Atoms by embeddings, avoiding the LLM clustering-plan call.

    Returns None when no embedding path is available so callers can fall back to
    the legacy LLM planner.
    """
    valid_ids: list[str] = []
    texts: list[str] = []
    for atom_id in atom_ids:
        text = _atom_embedding_text(paths, atom_id)
        if text:
            valid_ids.append(atom_id)
            texts.append(text)

    if not valid_ids:
        return []
    if len(valid_ids) == 1:
        return [valid_ids]

    embeddings = _get_embeddings(texts, client)
    if embeddings is None or len(embeddings) != len(valid_ids):
        return None

    try:
        import numpy as np
        from sklearn.cluster import DBSCAN

        labels = DBSCAN(eps=eps, min_samples=2, metric="cosine").fit_predict(
            np.array(embeddings)
        )
        clusters: dict[int, list[str]] = {}
        next_noise_label = max([int(label) for label in labels], default=-1) + 1
        for atom_id, label in zip(valid_ids, labels):
            effective_label = int(label)
            if effective_label == -1:
                effective_label = next_noise_label
                next_noise_label += 1
            clusters.setdefault(effective_label, []).append(atom_id)
        return list(clusters.values())
    except Exception:
        return _cluster_embeddings_threshold(valid_ids, embeddings, eps)


def _concept_plans_from_embedding_clusters(
    paths: cfg.WikiPaths,
    clusters: list[list[str]],
) -> list[ConceptPlan]:
    plans: list[ConceptPlan] = []
    for cluster in clusters:
        if len(cluster) < 2:
            continue
        name, domain = _fallback_concept_name(paths, cluster)
        summaries = [_atom_summary(paths, atom_id) for atom_id in cluster]
        snippets = [
            str(summary.get("one_liner") or summary.get("name") or "")
            for summary in summaries
            if summary
        ]
        description = "Embedding cluster from related Atoms."
        if snippets:
            description = " ".join(snippets)[:500]
        plans.append(
            ConceptPlan(
                name=name,
                domain=domain,
                atom_ids=cluster,
                description=description,
            )
        )
    return plans


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
        context_id = _atom_context_id(paths, atom_id)
        groups.setdefault(("source", context_id), []).append(atom_id)

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
        "type": consts.TYPE_L2,
        "parent_source": f"{consts.LAYER_L1}/{context_id}",
        "source_path": _source_path_link(relpath),
        "claim_type": candidate.type or consts.CLAIM_TYPE_FACT,
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
    parent_link = f"[[{consts.LAYER_L1}/{context_id}]]"
    body = re.sub(
        rf"\[\[{consts.LAYER_L1}/(?!{re.escape(context_id)}(?:\]\]|[#|]))[^\]]*\]\]",
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
    atom_ids = [aid for aid in plan.atom_ids if isinstance(aid, str) and aid.startswith(f"{consts.PREFIX_L2}-")]
    parsed.frontmatter = {
        "id": concept_id,
        "type": consts.TYPE_L3,
        "domain": plan.domain or "",
        "confidence_score": confidence,
        "last_updated": today,
    }
    body = _body_to_required_sections(
        parsed.body or "",
        ["1. Core Idea", "2. How the Atoms Connect", "3. Key Patterns", "4. Open Questions", "Relations"],
        fallback_title=plan.name,
    )
    allowed_targets = {f"{consts.LAYER_L2}/{aid}" for aid in atom_ids}
    body = _strip_out_of_scope_curator_links(body, allowed_targets)
    relations = "\n".join(f"[[{consts.LAYER_L2}/{aid}]]" for aid in atom_ids)
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
    for target in page_writer.extract_relation_targets(page.body, prefix=f"{consts.LAYER_L2}/"):
        atom_id = target.rsplit("/", 1)[-1]
        if atom_id.startswith(f"{consts.PREFIX_L2}-") and atom_id not in ids:
            ids.append(atom_id)
    return ids


def _enforce_exhibition_contract(
    content: str,
    *,
    exh_id: str,
    plan: SynthesisPlan,
    today: str,
    workspace: str | None = None,
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
    concept_ids = [cid for cid in plan.concept_ids if isinstance(cid, str) and cid.startswith(f"{consts.PREFIX_L3}-")]
    fm: dict = {
        "id": exh_id,
        "type": consts.TYPE_L4,
        "core_concepts": [f"{consts.LAYER_L3}/{cid}" for cid in concept_ids],
        "confidence_score": confidence,
        "last_updated": today,
    }
    if plan.domain:
        fm["domain"] = plan.domain
    if workspace:
        fm["workspace"] = workspace
    parsed.frontmatter = fm
    body = _strip_embedded_frontmatter(parsed.body or "")
    allowed_targets = {f"{consts.LAYER_L3}/{cid}" for cid in concept_ids}
    body = _strip_out_of_scope_curator_links(body, allowed_targets)
    body = re.sub(r"(?im)^##\s+", r"### ", body)
    required = [
        "- **1. Executive Brief**:",
        "- **2. Background & Evidence**:",
        "- **3. Actionable Directives for Agent**:",
        "- **4. Key Facts**:",
        "- **5. Open Questions**:",
    ]
    for label in required:
        if label not in body:
            body = f"{body.rstrip()}\n\n{label} "
    parsed.body = body.strip()
    return parsed.to_markdown()


def _run_atom_coordinator(
    paths: cfg.WikiPaths,
    client,
    new_atom_ids: list[str],
) -> int:
    """Detect and merge semantically duplicate atoms after L2 extraction.

    Compares newly created atoms against each other and against existing atoms
    in the same domain. Returns the count of merges performed.
    """
    if len(new_atom_ids) < 2:
        return 0

    today = _now_iso()

    # --- Build summary strings for new atoms ---
    def _atom_summary(atom_path: Path) -> str | None:
        parsed = page_writer.read_page(atom_path)
        if not parsed:
            return None
        fm = parsed.frontmatter
        atom_id = atom_path.stem
        name = fm.get("name") or fm.get("title") or atom_id
        domain = fm.get("domain") or ""
        one_liner = fm.get("one_liner") or ""
        return f"- {atom_id}: [{domain}] {name} — {one_liner}"

    # Group new atoms by domain
    domain_to_new: dict[str, list[str]] = {}
    for atom_id in new_atom_ids:
        atom_path = paths.atoms / f"{atom_id}.md"
        if not atom_path.exists():
            continue
        parsed = page_writer.read_page(atom_path)
        if not parsed:
            continue
        domain = parsed.frontmatter.get("domain") or consts.DOMAIN_GENERAL
        domain_to_new.setdefault(domain, []).append(atom_id)

    total_merges = 0

    for domain, new_ids in domain_to_new.items():
        # New atoms summary
        new_lines = [
            s for aid in new_ids
            if (s := _atom_summary(paths.atoms / f"{aid}.md")) is not None
        ]
        if len(new_lines) < 1:
            continue

        # Existing atoms in same domain (excluding new ones), capped at 50
        existing_lines: list[str] = []
        if paths.atoms.exists():
            new_id_set = set(new_ids)
            for md in paths.atoms.glob("*.md"):
                if md.stem in new_id_set:
                    continue
                parsed = page_writer.read_page(md)
                if not parsed:
                    continue
                if parsed.frontmatter.get("domain") != domain:
                    continue
                s = _atom_summary(md)
                if s:
                    existing_lines.append(s)
                if len(existing_lines) >= 50:
                    break

        # Skip coordinator if nothing to compare against
        all_ids = new_ids + [line.split(":")[0].strip("- ") for line in existing_lines]
        if len(all_ids) < 2:
            continue

        messages = prompts.build_atom_coordinator_messages(
            new_atoms_summary="\n".join(new_lines),
            existing_atoms_summary="\n".join(existing_lines),
            domain=domain,
        )
        try:
            response = client.chat(messages, temperature=0.1)
            content = response.content if hasattr(response, "content") else str(response)
        except Exception:
            continue

        # Parse merge_pairs from response
        import json as _json, re as _re
        match = _re.search(r'\{.*\}', content, _re.DOTALL)
        if not match:
            continue
        try:
            result = _json.loads(match.group())
        except Exception:
            continue

        for pair in result.get("merge_pairs", []):
            keep_id = pair.get("keep_id", "")
            absorb_id = pair.get("absorb_id", "")
            if not keep_id or not absorb_id:
                continue
            keep_path = paths.atoms / f"{keep_id}.md"
            absorb_path = paths.atoms / f"{absorb_id}.md"
            if not keep_path.exists() or not absorb_path.exists():
                continue

            # Merge: incorporate absorb content into keep via LLM
            absorb_parsed = page_writer.read_page(absorb_path)
            keep_parsed = page_writer.read_page(keep_path)
            if not absorb_parsed or not keep_parsed:
                continue

            absorb_fm = absorb_parsed.frontmatter
            keep_content = keep_parsed.to_markdown()

            # context_ids from absorbed atom
            absorb_ctx = absorb_fm.get("context_ids") or []
            if isinstance(absorb_ctx, str):
                absorb_ctx = [absorb_ctx]
            absorb_relpath = absorb_fm.get("source_path") or ""

            try:
                merge_messages = prompts.build_merge_atom_messages(
                    existing_content=keep_content,
                    name=absorb_fm.get("name") or absorb_fm.get("title") or absorb_id,
                    new_context_id=absorb_ctx[0] if absorb_ctx else "",
                    new_source_path=absorb_relpath,
                    new_description=absorb_fm.get("one_liner") or "",
                    excerpt="",
                    today=today,
                )
                merged_content = client.chat(merge_messages, temperature=0.2)
                merged_text = merged_content.content if hasattr(merged_content, "content") else str(merged_content)
            except Exception:
                continue

            if merged_text:
                keep_path.write_text(merged_text, encoding="utf-8")
                absorb_path.unlink(missing_ok=True)
                total_merges += 1

    return total_merges


def _process_one_atom(
    paths: cfg.WikiPaths,
    client,
    candidate: "AtomCandidate",
    context_id: str,
    relpath: str,
    excerpt: str,
    today: str,
    staging: Path,
    context_hint: str = "",
) -> tuple[Path, Path, "PageChange"]:
    """Process a single AtomCandidate → (staged_path, final_path, PageChange).

    Thread-safe: uses client.chat() (not streaming), writes to a unique staging file.
    context_hint is an optional focus note from the Orchestrator.
    """
    atom_id, exists = _find_existing_atom(paths, candidate.name)
    final_path = paths.atoms / f"{atom_id}.md"
    staged_path = staging / f"{consts.LAYER_L2}__{atom_id}.md"

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
        # Prepend context_hint to the excerpt if provided
        scoped_excerpt = (f"[Focus: {context_hint}]\n\n" + excerpt) if context_hint else excerpt
        messages = prompts.build_fragment_page_messages(
            fragment_id=atom_id,
            name=candidate.name,
            fragment_type=candidate.type,
            one_liner=candidate.one_liner,
            context_id=context_id,
            source_path=relpath,
            excerpt=scoped_excerpt,
            today=today,
        )

    # Use non-streaming chat for thread safety
    raw = client.chat(messages, temperature=0.3)
    content = page_writer.strip_llm_noise(raw if isinstance(raw, str) else (raw.content if hasattr(raw, "content") else str(raw)))
    content = page_writer.sanitize_wikilinks(content)
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
    operation = "updated" if exists else "created"
    change = PageChange(
        id=atom_id,
        path=f"{consts.LAYER_L2}/{atom_id}.md",
        layer=consts.LAYER_L2,
        operation=operation,
    )
    return staged_path, final_path, change


def _run_orchestrator_plan(
    summary_data: "SummaryData",
    client,
    paths: cfg.WikiPaths,
) -> list[dict] | None:
    """Ask LLM to decompose atom_candidates into parallel extraction tasks.

    Returns list of task dicts with keys: candidates (list[str]), context_hint (str).
    Returns None on any failure (caller falls back to sequential processing).
    """
    candidates_summary = "\n".join(
        f"- {c.name}: {c.one_liner}" for c in summary_data.atom_candidates
    )
    # Collect existing atoms in same domain (names + one_liners only, cap at 30)
    existing_lines: list[str] = []
    if paths.atoms.exists():
        for md in paths.atoms.glob("*.md"):
            parsed = page_writer.read_page(md)
            if not parsed:
                continue
            if parsed.frontmatter.get("domain") != summary_data.domain:
                continue
            name = parsed.frontmatter.get("name") or parsed.frontmatter.get("title") or md.stem
            one_liner = parsed.frontmatter.get("one_liner") or ""
            existing_lines.append(f"- {name}: {one_liner}")
            if len(existing_lines) >= 30:
                break

    messages = prompts.build_atom_orchestrator_messages(
        source_title=summary_data.title,
        domain=summary_data.domain,
        candidates_summary=candidates_summary,
        existing_atoms_summary="\n".join(existing_lines),
    )
    try:
        raw = client.chat(messages, temperature=0.1, json_mode=True)
        content = raw if isinstance(raw, str) else (raw.content if hasattr(raw, "content") else str(raw))
    except Exception:
        return None

    import json as _json, re as _re
    match = _re.search(r'\{.*\}', content, _re.DOTALL)
    if not match:
        return None
    try:
        parsed = _json.loads(match.group())
    except Exception:
        return None

    tasks = parsed.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return None

    # Validate: every candidate name must appear in exactly one task
    candidate_names = {c.name for c in summary_data.atom_candidates}
    covered: set[str] = set()
    for task in tasks:
        if not isinstance(task.get("candidates"), list):
            return None
        covered.update(task["candidates"])

    # If coverage is incomplete, add uncovered candidates to a catch-all task
    uncovered = candidate_names - covered
    if uncovered:
        tasks.append({"candidates": list(uncovered), "context_hint": ""})

    return tasks


def _extract_atoms_for_task(
    task: dict,
    paths: cfg.WikiPaths,
    client,
    summary_data: SummaryData,
    context_id: str,
    relpath: str,
    excerpt: str,
    today: str,
    staging: Path,
) -> list[tuple[Path, Path, PageChange]]:
    """Process all candidates in one orchestrator task using scope + context_hint.

    Thread-safe: called from ThreadPoolExecutor workers.
    scope frames the topic domain; context_hint focuses extraction within that scope.
    """
    scope = task.get("scope", "")
    hint = task.get("context_hint", "")
    combined_hint = f"[Scope: {scope}] {hint}".strip() if scope else hint

    name_to_candidate = {c.name: c for c in summary_data.atom_candidates}
    results: list[tuple[Path, Path, PageChange]] = []
    for cname in task.get("candidates", []):
        candidate = name_to_candidate.get(cname)
        if candidate is None:
            continue
        results.append(_process_one_atom(
            paths, client, candidate, context_id, relpath, excerpt, today, staging,
            context_hint=combined_hint,
        ))
    return results


def _run_sequential_atoms(
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
    """Sequential fallback: one atom at a time with streaming output."""
    staged: list[tuple[Path, Path, PageChange]] = []
    for candidate in summary_data.atom_candidates:
        atom_id, exists = _find_existing_atom(paths, candidate.name)
        final_path = paths.atoms / f"{atom_id}.md"
        staged_path = staging / f"{consts.LAYER_L2}__{atom_id}.md"
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
            content, atom_id=atom_id, candidate=candidate,
            context_id=context_id, relpath=relpath, today=today,
        )
        staged_path.write_text(content, encoding="utf-8")
        operation = "updated" if exists else "created"
        change = PageChange(
            id=atom_id, path=f"{consts.LAYER_L2}/{atom_id}.md",
            layer=consts.LAYER_L2, operation=operation,
        )
        staged.append((staged_path, final_path, change))
        callbacks.on_fragment_written(change)
    return staged


def _run_parallel_workers(
    tasks: list[dict],
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
    """Dispatch orchestrator tasks to ThreadPoolExecutor workers.

    Each task → _extract_atoms_for_task(). on_fragment_written collected in main thread.
    Falls back to _run_sequential_atoms() on any failure.
    """
    from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed as _ac

    staged: list[tuple[Path, Path, PageChange]] = []
    max_workers = min(3, len(tasks))

    _clone = getattr(client, "clone", None)

    try:
        with _TPE(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(
                    _extract_atoms_for_task,
                    task, paths, _clone() if callable(_clone) else client,
                    summary_data, context_id, relpath, excerpt, today, staging,
                ): task
                for task in tasks
            }
            for future in _ac(future_to_task):
                for result in future.result():  # re-raises on LLMError
                    staged.append(result)
                    callbacks.on_fragment_written(result[2])
    except Exception:
        staged.clear()
        staged = _run_sequential_atoms(
            paths, client, callbacks, summary_data,
            context_id, relpath, excerpt, today, staging,
        )
    return staged


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
    """Draft L2 Atom pages — orchestrated parallel execution with sequential fallback.

    Flow:
      1. Orchestrator LLM call → task decomposition (scope + candidates + context_hint)
      2. _run_parallel_workers: ThreadPoolExecutor per task via _extract_atoms_for_task
      3. Fallback: _run_sequential_atoms (streaming, single-threaded)
    """
    candidates = summary_data.atom_candidates
    callbacks.on_pass1_start(len(candidates))

    # Signal per-candidate start in main thread before dispatch (Rich-safe)
    for candidate in candidates:
        atom_id, exists = _find_existing_atom(paths, candidate.name)
        operation = "updated" if exists else "created"
        callbacks.on_fragment_drafting(atom_id, candidate.name, operation)

    # Orchestrator: decompose candidates into scoped tasks (best-effort)
    orch_tasks: list[dict] | None = None
    if len(candidates) >= 2:
        try:
            orch_tasks = _run_orchestrator_plan(summary_data, client, paths)
        except Exception:
            pass

    if orch_tasks:
        return _run_parallel_workers(
            orch_tasks, paths, client, callbacks, summary_data,
            context_id, relpath, excerpt, today, staging,
        )
    return _run_sequential_atoms(
        paths, client, callbacks, summary_data,
        context_id, relpath, excerpt, today, staging,
    )


# ---------------------------------------------------------------------------
# Pass 2 — L3 Themes
# ---------------------------------------------------------------------------


def _write_one_concept_plan(
    plan: ConceptPlan,
    client,
    paths: cfg.WikiPaths,
    staging: Path,
    today: str,
    workspace_context: str,
) -> tuple[Path, Path, PageChange, list[str]] | None:
    """Write one L3 Concept page using non-streaming chat. Thread-safe."""
    if len(plan.atom_ids) < 2:
        return None

    concept_id = _gen_id(consts.PREFIX_L3)
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
        workspace_context=workspace_context,
    )
    try:
        content = client.chat(messages, temperature=0.3)
    except LLMError:
        return None

    content = page_writer.strip_llm_noise(content)
    content = page_writer.sanitize_wikilinks(content)
    if not content:
        return None

    try:
        content = _enforce_concept_contract(content, concept_id=concept_id, plan=plan, today=today)
    except LLMError:
        return None

    parsed_content = page_writer.parse_page(content)
    try:
        confidence = float(parsed_content.frontmatter.get("confidence_score", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < 0.5:
        return None

    final_path = paths.concepts / f"{concept_id}.md"
    staged_path = staging / f"{consts.LAYER_L3}__{concept_id}.md"
    staged_path.write_text(content, encoding="utf-8")
    change = PageChange(
        id=concept_id,
        path=f"{consts.LAYER_L3}/{concept_id}.md",
        layer=consts.LAYER_L3,
        operation="created",
    )
    return staged_path, final_path, change, list(plan.atom_ids)


def _run_pass2_concepts(
    paths: cfg.WikiPaths,
    client,
    callbacks: IngestCallbacks,
    atom_ids: list[str],
    today: str,
    staging: Path,
    artist_persona=None,
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

    plans: list[ConceptPlan] = []
    embedding_clusters = cluster_atoms_by_embedding(paths, atom_ids, client)
    if embedding_clusters is not None:
        plans = _concept_plans_from_embedding_clusters(paths, embedding_clusters)
    else:
        # Fallback: ask the LLM for a clustering plan only when local embeddings
        # are unavailable.
        cluster_messages = prompts.build_concept_clustering_messages(atom_summaries)
        try:
            raw = client.chat(cluster_messages, json_mode=True, temperature=0.2)
            cluster_result: ConceptClusterResult = _parse_json_model(raw, ConceptClusterResult)
            plans = list(cluster_result.concepts)
        except (ValueError, LLMError) as e:
            print(f"Warning: Concept clustering failed: {e}", file=sys.stderr)
            return staged  # Non-fatal — skip concept layer for this run

    plans = _add_unassigned_atom_fallback_plans(paths, plans, atom_ids)
    workspace_keywords = (
        list(artist_persona.disambiguation_keywords)
        if artist_persona and artist_persona.disambiguation_keywords
        else []
    )
    plans = _disambiguate_concept_plan_titles(paths, plans, workspace_keywords=workspace_keywords)

    # Build workspace_context string for concept page prompts
    workspace_context = ""
    if artist_persona and artist_persona.goal:
        domain_label = f"Domain: {artist_persona.domain}" if artist_persona.domain else ""
        workspace_context = f"{domain_label}: {artist_persona.goal}" if domain_label else artist_persona.goal

    eligible_plans = [p for p in plans if len(p.atom_ids) >= 2]
    _clone = getattr(client, "clone", None)
    max_workers = min(3, len(eligible_plans)) if eligible_plans else 1

    from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed as _ac
    with _TPE(max_workers=max_workers) as executor:
        future_to_plan = {
            executor.submit(
                _write_one_concept_plan,
                plan,
                _clone() if callable(_clone) else client,
                paths, staging, today, workspace_context,
            ): plan
            for plan in eligible_plans
        }
        for future in _ac(future_to_plan):
            result = future.result()
            if result is None:
                continue
            staged_path, final_path, change, atom_ids = result
            staged.append((staged_path, final_path, change))
            callbacks.on_theme_written(change)
            for aid in atom_ids:
                db.insert_dag_edge(
                    paths.state_db,
                    from_id=aid,
                    to_id=change.id,
                    edge_type="clustered_to",
                    source_id=None,
                )

    return staged


def _set_l3_result_status(
    paths: cfg.WikiPaths,
    source_ids: list[int],
    concept_staged: list[tuple[Path, Path, PageChange]],
) -> None:
    """Reflect global L3 clustering outcome without changing Curator schema."""
    if not source_ids:
        return
    has_atoms = paths.atoms.exists() and any(paths.atoms.glob(f"{consts.PREFIX_L2}-*.md"))
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
        if context_id.startswith(f"{consts.PREFIX_L1}-"):
            context_by_source[int(row["id"])] = context_id

    atom_context: dict[str, str] = {}
    if paths.atoms.exists():
        for atom_path in paths.atoms.glob(f"{consts.PREFIX_L2}-*.md"):
            context_id = _atom_context_id(paths, atom_path.stem)
            if context_id:
                atom_context[atom_path.stem] = context_id

    covered_contexts: set[str] = set()
    if paths.concepts.exists():
        for concept_path in paths.concepts.glob(f"{consts.PREFIX_L3}-*.md"):
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
    if paths.concepts.exists() and any(paths.concepts.glob(f"{consts.PREFIX_L3}-*.md")):
        source_ids = _source_ids_with_l2_done_and_l3_unset(paths)
        if source_ids:
            db.set_sources_layer_status(paths.state_db, source_ids, "l3", "done")


# ---------------------------------------------------------------------------
# Pass 3 — L4 Curations
# ---------------------------------------------------------------------------


def _write_one_exhibition_plan(
    plan: SynthesisPlan,
    client,
    paths: cfg.WikiPaths,
    staging: Path,
    today: str,
    agent_context: str,
    exhibition_intent: str,
    workspace_project: str | None,
) -> tuple[Path, Path, PageChange] | None:
    """Write one L4 Exhibition page using non-streaming chat. Thread-safe."""
    if not plan.concept_ids:
        return None

    exh_id = _gen_id(consts.PREFIX_L4)
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
        domain=plan.domain,
        flagged_fragment_ids=flagged_ids,
        agent_context=agent_context,
        exhibition_intent=exhibition_intent,
    )
    try:
        content = client.chat(messages, temperature=0.3)
    except LLMError:
        return None

    content = page_writer.strip_llm_noise(content)
    content = page_writer.sanitize_wikilinks(content)
    if not content:
        return None

    try:
        content = _enforce_exhibition_contract(
            content, exh_id=exh_id, plan=plan, today=today, workspace=workspace_project
        )
    except LLMError:
        return None

    final_path = paths.exhibitions / f"{exh_id}.md"
    staged_path = staging / f"{consts.LAYER_L4}__{exh_id}.md"
    staged_path.write_text(content, encoding="utf-8")
    change = PageChange(
        id=exh_id,
        path=f"{consts.LAYER_L4}/{exh_id}.md",
        layer=consts.LAYER_L4,
        operation="created",
    )
    return staged_path, final_path, change


def _run_pass3_synthesis(
    paths: cfg.WikiPaths,
    client,
    callbacks: IngestCallbacks,
    concept_ids: list[str],
    today: str,
    staging: Path,
    workspace_project: str | None = None,
    artist_persona=None,
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

    # Pull thresholds from Artist persona if present
    high_threshold = 0.90
    low_threshold = 0.60
    if artist_persona and isinstance(artist_persona.confidence, dict):
        high_threshold = float(artist_persona.confidence.get("high_threshold", 0.90))
        low_threshold = float(artist_persona.confidence.get("low_threshold", 0.60))

    plan_messages = prompts.build_curation_planning_messages(
        concept_summaries,
        high_threshold=high_threshold,
        low_threshold=low_threshold,
    )
    try:
        raw = client.chat(plan_messages, json_mode=True, temperature=0.2)
        plan_result: SynthesisPlanResult = _parse_json_model(raw, SynthesisPlanResult)
    except (ValueError, LLMError) as e:
        print(f"Warning: Synthesis planning failed: {e}", file=sys.stderr)
        return staged

    plans: list[SynthesisPlan] = list(plan_result.synthesis_plans)

    # Workspace-scoped curation: merge all plans into one Exhibition.
    # One Exhibition per workspace is the spec invariant.
    if workspace_project and len(plans) > 1:
        all_concept_ids = list(dict.fromkeys(
            cid for p in plans for cid in p.concept_ids
        ))
        plans = [SynthesisPlan(
            topic=workspace_project,
            concept_ids=all_concept_ids,
            confidence=max(p.confidence for p in plans),
        )]

    # Build agent_context string for exhibition page prompts
    agent_context = ""
    if artist_persona and artist_persona.goal:
        agent_context = f"exhibition_intent:{artist_persona.exhibition_intent} — {artist_persona.goal}"

    exhibition_intent = artist_persona.exhibition_intent if artist_persona else ""
    eligible_plans = [p for p in plans if p.concept_ids]
    _clone = getattr(client, "clone", None)
    max_workers = min(2, len(eligible_plans)) if eligible_plans else 1

    from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed as _ac
    with _TPE(max_workers=max_workers) as executor:
        future_to_plan = {
            executor.submit(
                _write_one_exhibition_plan,
                plan,
                _clone() if callable(_clone) else client,
                paths, staging, today,
                agent_context, exhibition_intent, workspace_project,
            ): plan
            for plan in eligible_plans
        }
        for future in _ac(future_to_plan):
            result = future.result()
            if result is None:
                continue
            staged_path, final_path, change = result
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
    ) -> IngestResult:
    """Phase A — extract L2 Atoms from a single source.

    Concepts and Synthesis are built globally AFTER all sources are processed.
    Call run_l1_to_l3() to process all pending sources.
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
            error=f"L1 Context page does not exist: {consts.LAYER_L1}/{context_id}.md",
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
            raw = client.chat(messages_for_extraction, json_mode=True, temperature=0.2)
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
    relpath = source_row["relpath"]

    try:
        # Pass 1 — L2 Atoms (batch extraction primary, legacy orchestrator fallback)
        ctx_path = paths.contexts / f"{context_id}.md"
        batch_results = None
        if ctx_path.exists():
            from . import ingest_orchestrator as _orch
            try:
                batch_results = _orch.run_l2_batch_extraction(
                    paths, client, ctx_path, context_id, relpath, today, staging
                )
            except Exception:
                batch_results = None  # fall through to legacy path

        if batch_results is not None:
            # Convert BatchAtomResult → (staged, final, PageChange)
            atom_staged: list[tuple[Path, Path, PageChange]] = []
            for br in batch_results:
                change = PageChange(
                    id=br.atom_id,
                    path=f"{consts.LAYER_L2}/{br.atom_id}.md",
                    layer=consts.LAYER_L2,
                    operation=br.operation,
                )
                atom_staged.append((br.staged_path, br.final_path, change))
                callbacks.on_fragment_written(change)
        else:
            # Legacy: per-atom orchestrated parallel extraction
            try:
                atom_staged = _run_pass1_atoms(
                    paths, client, callbacks, summary_data, context_id,
                    relpath, excerpt, today, staging,
                )
            except LLMError as e:
                result = IngestResult(source_id=source_id, source_title=parsed.title,
                                      error=f"Fragment pass failed: {e}")
                _mark_source_status(paths, source_id, "error", error_reason="llm_error")
                db.set_source_layer_status(paths.state_db, source_id, "l2", "error", error=result.error)
                _record_ingest_run(paths, source_id, started, mode, 0, 0, result.error)
                callbacks.on_error(result.error)
                return result

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
                db.insert_dag_edge(
                    paths.state_db,
                    from_id=context_id,
                    to_id=change.id,
                    edge_type="extracted_from",
                    source_id=str(source_id),
                )
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
    artist_persona=None,
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
    return _run_pass2_concepts(paths, client, callbacks, all_atom_ids, today, staging, artist_persona=artist_persona)


# ---------------------------------------------------------------------------
# Phase C — Global L4 Curations (all Themes → Curations)
# ---------------------------------------------------------------------------


def _run_global_pass3_synthesis(
    paths: cfg.WikiPaths,
    client,
    callbacks: IngestCallbacks,
    today: str,
    staging: Path,
    artist_persona=None,
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
    return _run_pass3_synthesis(paths, client, callbacks, all_concept_ids, today, staging, artist_persona=artist_persona)


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

    _layer_section("L1 — Contexts",    consts.LAYER_L1,    contexts)
    _layer_section("L2 — Atoms",       consts.LAYER_L2,       atoms)
    _layer_section("L3 — Concepts",    consts.LAYER_L3,    concepts)
    _layer_section("L4 — Exhibitions", consts.LAYER_L4, exhibitions)

    paths.overview.parent.mkdir(parents=True, exist_ok=True)
    paths.overview.write_text("\n".join(lines), encoding="utf-8")

# ---------------------------------------------------------------------------
# Persona evolution helpers (D4)
# ---------------------------------------------------------------------------

def _collect_domains_from_contexts(paths: cfg.WikiPaths, ctx_ids: list[str]) -> list[str]:
    """Return unique non-empty domain strings from the given CTX frontmatters."""
    domains = []
    for ctx_id in ctx_ids:
        ctx_path = paths.contexts / f"{ctx_id}.md"
        if not ctx_path.exists():
            continue
        page = page_writer.read_page(ctx_path)
        if page:
            domain = page.frontmatter.get("domain", "")
            if domain and domain not in domains:
                domains.append(domain)
    return domains


def _append_domain_log(paths: cfg.WikiPaths, today: str, domains: list[str]) -> None:
    """Append a domain-seen line to .curator/log.md for persona evolution tracking."""
    log_line = f"<!-- domains:{','.join(domains)} date:{today} -->\n"
    try:
        with paths.log.open("a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass


def read_recent_domains(paths: cfg.WikiPaths, max_entries: int = 20) -> list[str]:
    """Read recently seen domains from log.md domain-log comments."""
    if not paths.log.exists():
        return []
    import re as _re
    text = paths.log.read_text(encoding="utf-8")
    seen: list[str] = []
    for m in _re.finditer(r"<!-- domains:([^>]+) date:[^>]+ -->", text):
        for d in m.group(1).split(","):
            d = d.strip()
            if d and d not in seen:
                seen.append(d)
        if len(seen) >= max_entries:
            break
    return seen[:max_entries]


# ---------------------------------------------------------------------------
# Entry points — pipeline split (wiki add = L1-L3, wiki curate = L4)
# ---------------------------------------------------------------------------


def run_l1_to_l3(
    paths: cfg.WikiPaths,
    client,
    callbacks_factory: Callable[[], IngestCallbacks],
    *,
    mode: str = "interactive",
    auto_discover: bool = True,
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
        result = ingest_source(paths, sid, client, cb, mode=mode)
        results.append(result)
        if result.error and "Ollama" in (result.error or ""):
            break

    has_concepts = any(paths.concepts.glob("*.md")) if paths.concepts.exists() else False
    any_ok = any(r.ok for r in results)
    if not any_ok and not force and has_concepts:
        _mark_existing_l3_done_if_present(paths)
        return results

    # Phase A½: Atom Coordinator — semantic dedup across newly extracted atoms
    new_atom_ids = [
        c.id for r in results if r.ok
        for c in r.changes if c.layer == consts.LAYER_L2
    ]
    if len(new_atom_ids) >= 2:
        try:
            merge_count = _run_atom_coordinator(paths, client, new_atom_ids)
            if merge_count:
                import logging as _log
                _log.getLogger(__name__).info("Atom coordinator merged %d duplicate(s)", merge_count)
        except Exception:
            pass  # coordinator is best-effort; never block L3

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

        # D4: record unique domains seen in this run so persona update can suggest refinements
        new_ctx_ids = [
            ch.id for r in results if r.ok
            for ch in r.changes if ch.layer == consts.LAYER_L1
        ]
        seen_domains = _collect_domains_from_contexts(paths, new_ctx_ids)
        if seen_domains:
            _append_domain_log(paths, today, seen_domains)

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
            for md_path in paths.concepts.glob(f"{consts.PREFIX_L3}-*.md"):
                md_path.unlink()
        if paths.exhibitions.exists():
            for md_path in paths.exhibitions.glob(f"{consts.PREFIX_L4}-*.md"):
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
        if not context_id.startswith(f"{consts.PREFIX_L1}-"):
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


def _count_followup_sections(body: str) -> int:
    """Count ## Follow-up: sections in an Exhibition body."""
    import re
    return len(re.findall(r"^## Follow-up:", body, re.MULTILINE))


def _extract_followup_questions(body: str) -> list[str]:
    """Extract the question text from ## Follow-up: sections."""
    import re
    return re.findall(r"^## Follow-up:\s*(.+)$", body, re.MULTILINE)


def _run_exhibition_refinement(
    paths: cfg.WikiPaths,
    client,
    callbacks: IngestCallbacks,
    exh_path: Path,
    curate_spec,
    today: str,
    staging: Path,
) -> list[tuple[Path, Path, PageChange]]:
    """Refine an existing Exhibition in-place by integrating accumulated Follow-up queries.

    Called when the workspace Exhibition already has 3+ Follow-up sections.
    """
    existing = page_writer.read_page(exh_path)
    if existing is None:
        return []

    followup_questions = _extract_followup_questions(existing.body or "")
    existing_content = existing.to_markdown()

    # Gather supporting concept content from core_concepts in frontmatter
    concepts_content = ""
    for ref in existing.frontmatter.get("core_concepts") or []:
        cid = str(ref).rsplit("/", 1)[-1]
        if not cid.startswith(f"{consts.PREFIX_L3}-"):
            continue
        cp = page_writer.read_page(paths.concepts / f"{cid}.md")
        if cp:
            concepts_content += f"\n### Concept {cid}\n{cp.body[:3000]}\n"

    messages = prompts.build_exhibition_refinement_messages(
        exh_id=exh_path.stem,
        today=today,
        existing_content=existing_content,
        followup_questions=followup_questions,
        concepts_content=concepts_content,
    )
    content = _stream_page(client, messages, callbacks)
    if not content:
        return []

    # Enforce the exhibition contract (keeps existing ID + frontmatter intact)
    plan = SynthesisPlan(
        topic=existing.frontmatter.get("workspace", exh_path.stem),
        concept_ids=[
            str(ref).rsplit("/", 1)[-1]
            for ref in (existing.frontmatter.get("core_concepts") or [])
        ],
        confidence=float(existing.frontmatter.get("confidence_score", 0.7)),
        domain=existing.frontmatter.get("domain", ""),
    )
    content = _enforce_exhibition_contract(
        content,
        exh_id=exh_path.stem,
        plan=plan,
        today=today,
    )

    staged_path = staging / f"{consts.LAYER_L4}__{exh_path.stem}.md"
    staged_path.write_text(content, encoding="utf-8")
    change = PageChange(
        id=exh_path.stem,
        path=f"{consts.LAYER_L4}/{exh_path.name}",
        layer=consts.LAYER_L4,
        operation="updated",
    )
    callbacks.on_curation_written(change)
    return [(staged_path, exh_path, change)]


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
    When a workspace Exhibition already exists with 3+ accumulated Follow-up queries,
    runs refinement mode (integrate queries, rewrite directives) instead of regenerating.
    """
    workspace_project = curate_spec.project if curate_spec is not None else None
    artist_persona = curate_spec.persona if curate_spec is not None else None

    # Refinement mode: re-run over an Exhibition that has accumulated queries
    if workspace_project:
        existing_exh = find_workspace_exhibition(paths, workspace_project)
        if existing_exh is not None:
            existing = page_writer.read_page(existing_exh)
            if existing is not None and _count_followup_sections(existing.body or "") >= 3:
                return _run_exhibition_refinement(
                    paths, client, callbacks, existing_exh, curate_spec, today, staging,
                )

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
    return _run_pass3_synthesis(
        paths, client, callbacks, concept_ids, today, staging,
        workspace_project=workspace_project,
        artist_persona=artist_persona,
    )


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
        raw = client.chat(messages, json_mode=True, temperature=0.2)
        summary_data = _parse_json_model(_extract_json(raw), SummaryData)
    except (ValueError, LLMError):
        return None

    if not summary_data.atom_candidates:
        return None

    candidate = summary_data.atom_candidates[0]
    atom_id = _gen_id(consts.PREFIX_L2)

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
        gen = client.chat_stream(messages, temperature=0.3)
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


def find_workspace_exhibition(paths: cfg.WikiPaths, project: str) -> Optional[Path]:
    """Return any existing Exhibition tagged for this workspace project.

    Intentionally ignores curate_spec_hash so stale Exhibitions are still found
    after curate.yml edits (the caller can re-curate to refresh them).
    """
    if not paths.exhibitions.exists() or not project:
        return None
    for md_path in sorted(paths.exhibitions.glob(f"{consts.PREFIX_L4}-*.md")):
        try:
            parsed = page_writer.read_page(md_path)
            if parsed and parsed.frontmatter.get("workspace") == project:
                if not parsed.frontmatter.get("superseded_by"):
                    return md_path
        except Exception:
            continue
    return None
