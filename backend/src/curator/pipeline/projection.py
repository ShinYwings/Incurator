"""Emit derived ``.curator/Collections`` markdown from DB records.

These markdown pages are the disposable qmd search corpus, projected from the
authoritative DB records. They are emitted, never edited as truth, so there is no
DB↔file drift (SYSTEM_BEHAVIOR_v0.3.1.md §22).
"""

from __future__ import annotations

import uuid

import yaml

__all__ = [
    "new_atom_id",
    "new_concept_id",
    "new_synthesis_id",
    "emit_atom_markdown",
    "emit_concept_markdown",
    "emit_synthesis_markdown",
]


def new_atom_id() -> str:
    return f"ATM-{uuid.uuid4().hex[:8]}"


def new_concept_id() -> str:
    return f"CON-{uuid.uuid4().hex[:8]}"


def new_synthesis_id() -> str:
    return f"SYN-{uuid.uuid4().hex[:8]}"


def _frontmatter(data: dict) -> str:
    body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{body}\n---\n"


def emit_atom_markdown(unit: dict, atom_id: str, *, source_path: str = "") -> str:
    """Render an ATM page (the projection of one knowledge_unit).

    ``unit`` is a ``knowledge_units`` row (with ``source_span_ids`` decoded to a
    list). The page carries span/unit/trace provenance per SCHEMA_v0.3.1 §13.
    """
    fm: dict = {
        "id": atom_id,
        "type": "atom",
        "unit_type": unit.get("unit_type", "claim"),
        "knowledge_unit_ids": [unit["id"]],
        "source_span_ids": list(unit.get("source_span_ids") or []),
        "truth_status": unit.get("truth_status", "source_supported"),
        "confidence_score": float(unit.get("confidence") or 0.0),
    }
    prompt_run_id = unit.get("prompt_run_id")
    if prompt_run_id:
        fm["prompt_trace_ids"] = [prompt_run_id]
    if source_path:
        fm["source_path"] = source_path

    title = unit.get("canonical_name") or "Knowledge Unit"
    statement = unit.get("statement") or ""
    return f"{_frontmatter(fm)}\n# {title}\n\n{statement}\n"


def emit_concept_markdown(report: dict, concept_id: str) -> str:
    """Render a CON page (the projection of one community_report).

    ``report`` is a ``community_reports`` row (with id lists decoded). The page is
    a derived qmd-corpus rendering of the community summary plus its graph/source
    provenance per SCHEMA_v0.3.1 §14.
    """
    fm: dict = {
        "id": concept_id,
        "type": "concept",
        "community_report_id": report.get("id", ""),
        "community_key": report.get("community_key", ""),
        "entity_ids": list(report.get("entity_ids") or []),
        "relation_ids": list(report.get("relation_ids") or []),
        "source_span_ids": list(report.get("source_span_ids") or []),
        "confidence_score": float(report.get("rank") or 0.0),
    }
    prompt_run_id = report.get("prompt_run_id")
    if prompt_run_id:
        fm["prompt_trace_ids"] = [prompt_run_id]

    title = report.get("title") or "Concept"
    summary = report.get("summary") or ""
    full = report.get("full_content") or ""
    findings = report.get("findings") or []
    parts = [f"{_frontmatter(fm)}", f"# {title}", "", summary, ""]
    if full:
        parts += ["## Report", "", full, ""]
    if findings:
        parts.append("## Findings")
        parts.append("")
        for f in findings:
            if isinstance(f, dict) and f.get("summary"):
                parts.append(f"- {f['summary']}")
        parts.append("")
    return "\n".join(parts)


def emit_synthesis_markdown(node: dict) -> str:
    """Render a SYN page (the projection of one synthesis_node).

    ``node`` is a ``synthesis_nodes`` row (with id lists decoded). The page is a
    derived qmd-corpus rendering of a shared, corpus-wide synthesized insight plus
    its concept/report/source provenance per SCHEMA_v0.3.1 §15.
    """
    fm: dict = {
        "id": node["id"],
        "type": "synthesis",
        "community_report_ids": list(node.get("community_report_ids") or []),
        "concept_ids": list(node.get("concept_ids") or []),
        "source_span_ids": list(node.get("source_span_ids") or []),
        "confidence_score": float(node.get("confidence") or 0.0),
    }
    prompt_run_id = node.get("prompt_run_id")
    if prompt_run_id:
        fm["prompt_trace_ids"] = [prompt_run_id]

    title = node.get("title") or "Synthesis"
    statement = node.get("statement") or ""
    full = node.get("full_content") or ""
    parts = [f"{_frontmatter(fm)}", f"# {title}", "", statement, ""]
    if full:
        parts += ["## Synthesis", "", full, ""]
    return "\n".join(parts)
