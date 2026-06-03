"""v0.2.1 ingest orchestration helpers.

This module holds deterministic pieces of the planned async L1/L2/L3
orchestrator so tests and callers can share behavior before the long-running
worker is fully wired in.
"""

from __future__ import annotations
from . import constants as consts

import hashlib
import json
import re
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config as cfg
from . import constants as consts
from . import db
from . import page_writer
from . import parsers
from . import prompts

MAX_BATCH_CHARS = 50_000

_BATCH_EXTRACT_PROMPT = """\
Extract **ALL** independent knowledge units (Atoms) from the document below.

Rules:
- Each Atom MUST represent exactly one fact, claim, equation, or technique.
- If the document contains <!-- section:id page:N --> markers, record the closest section id and title for each atom.
- **You MUST return ONLY a valid JSON array. No other text.**
- LANGUAGE RULE: You MUST translate and write all extracted knowledge strictly in English, regardless of the source language.

Output format:
[
  {{
    "name": "Item name (concise, in English)",
    "claim_type": "one of: fact | claim | entity | procedure | relationship",
    "one_liner": "One-sentence core summary (in English)",
    "source_section_id": "Closest section id (or empty string)",
    "source_section_title": "Closest section title (or empty string)",
    "source_page": integer_page_number_or_null,
    "confidence": float_between_0.0_and_1.0
  }}
]

Document:
{chunk}
"""


@dataclass
class BatchAtomResult:
    atom_id: str
    staged_path: Path
    final_path: Path
    operation: str = "created"


def _split_into_batches(body: str, max_chars: int) -> list[str]:
    """Split structured L1 text on section markers without losing content."""
    if body == "":
        return [""]
    if len(body) <= max_chars:
        return [body]
    if "<!-- section:" not in body:
        return [body]

    parts = re.split(r"(?=<!-- section:)", body)
    batches: list[str] = []
    current: list[str] = []
    current_len = 0
    for part in parts:
        if current and current_len + len(part) > max_chars:
            batches.append("".join(current))
            current = [part]
            current_len = len(part)
        else:
            current.append(part)
            current_len += len(part)
    if current:
        batches.append("".join(current))
    return batches


def _content_hash(body_text: str) -> str:
    return hashlib.sha256(body_text.encode("utf-8")).hexdigest()[:16]


def _parse_batch_atoms_json(raw: str) -> list[dict[str, Any]]:
    """Parse an LLM JSON array response, tolerating markdown fences."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end >= start:
        text = text[start : end + 1]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        from .llm import LLMError
        raise LLMError(f"Failed to parse batch atoms JSON: {e}")
    if not isinstance(parsed, list):
        from .llm import LLMError
        raise LLMError(f"Expected JSON array, got {type(parsed).__name__}")
    return [item for item in parsed if isinstance(item, dict)]


def _clamp_confidence(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    return min(1.0, max(0.0, score))


def _yaml_scalar(value: Any) -> str:
    text = str(value).replace("\n", " ").strip()
    if not text:
        return '""'
    if re.search(r"[:#\[\]{},&*]|^\s|[\t]", text):
        return json.dumps(text, ensure_ascii=False)
    return text


def _build_atom_page_from_data(
    *,
    atom_id: str,
    data: dict[str, Any],
    context_id: str,
    relpath: str,
    today: str,
) -> str:
    """Build an Atom page from trusted structured extraction data."""
    name = str(data.get("name") or atom_id).strip()
    one_liner = str(data.get("one_liner") or data.get("claim") or "").strip()
    claim_type = str(data.get("claim_type") or data.get("type") or consts.CLAIM_TYPE_FACT).strip() or consts.CLAIM_TYPE_FACT
    section_id = str(data.get("source_section_id") or "").strip()
    section_title = str(data.get("source_section_title") or "").strip()
    source_page = data.get("source_page") or data.get("page") or ""
    confidence = _clamp_confidence(data.get("confidence", data.get("confidence_score", 0.0)))

    body = (
        f"# {name}\n\n"
        "## Definition / Claim\n\n"
        f"{one_liner}\n\n"
        "## Context\n\n"
        f"Source section: {section_title or section_id or 'unknown'}"
        f"{f' (page {source_page})' if source_page != '' else ''}.\n\n"
        "## Constraints\n\n"
        "- Needs human verification if used for high-stakes claims.\n\n"
        "## Relations\n\n"
        f"[[{consts.LAYER_L1}/{context_id}]]\n"
    )
    frontmatter = [
        "---",
        f"id: {atom_id}",
        f"type: {consts.TYPE_L2}",
        f"parent_source: {consts.LAYER_L1}/{context_id}",
        f"source_path: {_yaml_scalar(relpath)}",
        f"claim_type: {_yaml_scalar(claim_type)}",
        f"confidence_score: {confidence:.1f}",
        "contradicts: []",
        "is_verified_by_human: false",
        "is_flagged_for_agent: false",
        f"last_updated: {today}",
        f"content_hash: {_content_hash(body)}",
    ]
    if section_id:
        frontmatter.append(f"source_section_id: {_yaml_scalar(section_id)}")
    if section_title:
        frontmatter.append(f"source_section_title: {_yaml_scalar(section_title)}")
    if source_page != "":
        frontmatter.append(f"source_page: {source_page}")
    frontmatter.append("---")
    return "\n".join(frontmatter) + "\n\n" + body


def _gen_atom_id() -> str:
    return f"{consts.PREFIX_L2}-" + uuid.uuid4().hex[:8]


def _ctx_body_only(ctx_content: str) -> str:
    """Strip YAML frontmatter from a CTX page, return body text only."""
    if not ctx_content.startswith("---"):
        return ctx_content
    end = ctx_content.find("\n---\n", 4)
    if end == -1:
        return ctx_content
    return ctx_content[end + 5:]


def _hydrate_on_demand_ctx_body(paths: cfg.WikiPaths, ctx_path: Path, relpath: str, fallback_body: str) -> str:
    """Rebuild Source Sections from the original source for compact large-document L1."""
    ctx_page = page_writer.read_page(ctx_path)
    if not ctx_page or ctx_page.frontmatter.get("source_text_policy") != "on_demand":
        return fallback_body

    try:
        from .ingest_raw import _extract_structural_sections, _resolve_reference_source

        source_path = Path(relpath).expanduser()
        if not source_path.is_absolute():
            source_path = paths.root / relpath
        parsed = parsers.parse(_resolve_reference_source(paths, source_path))
        sections = _extract_structural_sections(parsed)
    except Exception:
        return fallback_body

    hydrated: list[str] = []
    for idx, section in enumerate(sections, 1):
        sid = str(section.get("id") or f"s{idx}")
        page = int(section.get("page") or 1)
        level = max(2, min(int(section.get("level") or 2), 6))
        title = str(section.get("title") or f"Section {idx}")
        text = str(section.get("text") or "").strip()
        hydrated.append(
            "\n".join(
                [
                    f"<!-- section:{sid} page:{page} -->",
                    f"{'#' * level} {title}",
                    "",
                    text,
                ]
            ).strip()
        )
    return "\n\n".join(part for part in hydrated if part) or fallback_body


def _extract_atoms_from_chunk(
    chunk: str,
    client: Any,
    paths: cfg.WikiPaths,
    context_id: str,
    relpath: str,
    today: str,
    staging: Path,
) -> list[BatchAtomResult]:
    """Call LLM once for one document chunk, parse JSON atoms, write staged pages."""
    from .llm import ChatMessage, LLMError

    prompt = _BATCH_EXTRACT_PROMPT.format(chunk=chunk)
    messages = [
        ChatMessage(role="system", content=prompts.CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=prompt)
    ]
    
    max_retries = 2
    atoms_data = None
    
    raw = ""
    for attempt in range(max_retries + 1):
        try:
            raw = client.chat(messages, json_mode=True, temperature=0.1 + (attempt * 0.1))
            atoms_data = _parse_batch_atoms_json(raw)
            break
        except LLMError as e:
            if attempt == max_retries:
                raise
            feedback = f"Your previous response was invalid JSON. Error: {e}\nPlease try again and return ONLY a valid JSON array."
            # Append failed response and feedback for self-correction
            messages.append(ChatMessage(role="assistant", content=raw))
            messages.append(ChatMessage(role="user", content=feedback))

    if not atoms_data:
        return []
    results: list[BatchAtomResult] = []
    for atom_data in atoms_data:
        if not atom_data.get("name"):
            continue
        atom_id = _gen_atom_id()
        page_content = _build_atom_page_from_data(
            atom_id=atom_id,
            data=atom_data,
            context_id=context_id,
            relpath=relpath,
            today=today,
        )
        final_path = paths.atoms / f"{atom_id}.md"
        staged_path = staging / f"{consts.LAYER_L2}__{atom_id}.md"
        staged_path.write_text(page_content, encoding="utf-8")
        results.append(BatchAtomResult(
            atom_id=atom_id,
            staged_path=staged_path,
            final_path=final_path,
            operation="created",
        ))
    return results


def _extract_section_index(body: str) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    pattern = re.compile(
        r"(?m)^-\s+`(?P<section_id>s\d+)`\s+p\.(?P<page>\d+)\s+—\s+\*\*(?P<title>.*?)\*\*:"
    )
    for match in pattern.finditer(body):
        title = match.group("title").strip()
        index[title.lower()] = {
            "source_section_id": match.group("section_id"),
            "source_section_title": title,
            "source_page": int(match.group("page")),
        }
    return index


def _fallback_atoms_from_l1_candidates(
    body: str,
    paths: cfg.WikiPaths,
    context_id: str,
    relpath: str,
    today: str,
    staging: Path,
) -> list[BatchAtomResult]:
    """Create low-confidence Atoms from L1 candidates when the LLM is unavailable."""
    section_index = _extract_section_index(body)
    in_candidates = False
    candidates: list[dict[str, Any]] = []
    for line in body.splitlines():
        if re.match(r"^##\s+(?:\d+\.\s+)?Atom Candidates\s*$", line):
            in_candidates = True
            continue
        if in_candidates and line.startswith("## "):
            break
        if not in_candidates or not line.startswith("- ["):
            continue
        match = re.match(r"^-\s+\[(?P<type>[^\]]+)\]\s+(?P<name>[^:]+):\s*(?P<one_liner>.*)$", line)
        if not match:
            continue
        name = match.group("name").strip()
        one_liner = match.group("one_liner").strip()
        if not name:
            continue
        section_meta = section_index.get(name.lower(), {})
        page_match = re.search(r"starting on page\s+(\d+)", one_liner)
        data = {
            "name": name,
            "claim_type": match.group("type").strip() or consts.CLAIM_TYPE_FACT,
            "one_liner": one_liner,
            "source_section_id": section_meta.get("source_section_id", ""),
            "source_section_title": section_meta.get("source_section_title", name),
            "source_page": section_meta.get("source_page") or (int(page_match.group(1)) if page_match else ""),
            "confidence": 0.35,
        }
        candidates.append(data)

    results: list[BatchAtomResult] = []
    for data in candidates:
        atom_id = _gen_atom_id()
        page_content = _build_atom_page_from_data(
            atom_id=atom_id,
            data=data,
            context_id=context_id,
            relpath=relpath,
            today=today,
        )
        final_path = paths.atoms / f"{atom_id}.md"
        staged_path = staging / f"{consts.LAYER_L2}__{atom_id}.md"
        staged_path.write_text(page_content, encoding="utf-8")
        results.append(BatchAtomResult(
            atom_id=atom_id,
            staged_path=staged_path,
            final_path=final_path,
            operation="created",
        ))
    return results


def run_l2_batch_extraction(
    paths: cfg.WikiPaths,
    client: Any,
    ctx_path: Path,
    context_id: str,
    relpath: str,
    today: str,
    staging: Path,
) -> list[BatchAtomResult]:
    """Batch-extract all L2 Atoms from a CTX file: 1-3 LLM calls regardless of document size.

    Reads the CTX body (with embedded section markers), splits into at most a few
    batches, and calls the LLM once per batch with a JSON extraction prompt.
    This replaces the legacy per-atom orchestrator approach (N LLM calls → 1-3).
    """
    ctx_content = ctx_path.read_text(encoding="utf-8")
    body = _ctx_body_only(ctx_content)
    body = _hydrate_on_demand_ctx_body(paths, ctx_path, relpath, body)
    client_chunk_chars = getattr(client, "optimal_chunk_chars", MAX_BATCH_CHARS)
    try:
        max_batch_chars = int(client_chunk_chars)
    except (TypeError, ValueError):
        max_batch_chars = MAX_BATCH_CHARS
    max_batch_chars = max(100, min(MAX_BATCH_CHARS, max_batch_chars))
    batches = _split_into_batches(body, max_batch_chars)

    from .llm import LLMError

    def _fallback() -> list[BatchAtomResult]:
        return _fallback_atoms_from_l1_candidates(
            body, paths, context_id, relpath, today, staging
        )

    if len(batches) <= 1:
        try:
            return _extract_atoms_from_chunk(
                batches[0], client, paths, context_id, relpath, today, staging
            )
        except LLMError:
            return _fallback()

    clone = getattr(client, "clone", None)
    type_clone = getattr(type(client), "clone", None)
    if not callable(clone) or not callable(type_clone):
        all_results: list[BatchAtomResult] = []
        for batch in batches:
            try:
                all_results.extend(
                    _extract_atoms_from_chunk(
                        batch, client, paths, context_id, relpath, today, staging
                    )
                )
            except LLMError:
                return _fallback()
        return all_results

    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_results: list[BatchAtomResult] = []
    max_workers = min(3, len(batches))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                _extract_atoms_from_chunk,
                batch,
                clone(),
                paths,
                context_id,
                relpath,
                today,
                staging,
            )
            for batch in batches
        ]
        try:
            for future in as_completed(futures):
                all_results.extend(future.result())
        except LLMError:
            return _fallback()
    return all_results


def _expand_downstream_via_sql(paths: cfg.WikiPaths, node_ids: list[str]) -> set[str]:
    """Return node_ids plus all transitive downstream DAG nodes from dag_edges."""
    if not node_ids:
        return set()
    affected = set(node_ids)
    queue: deque[str] = deque(node_ids)
    with db.connect(paths.state_db) as conn:
        while queue:
            current = queue.popleft()
            rows = conn.execute(
                "SELECT to_id FROM dag_edges WHERE from_id = ?",
                (current,),
            ).fetchall()
            for row in rows:
                to_id = str(row["to_id"])
                if to_id not in affected:
                    affected.add(to_id)
                    queue.append(to_id)
    return affected
