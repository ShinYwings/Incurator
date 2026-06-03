"""LLM knowledge-unit extraction (L2).

Refines source spans into typed ``knowledge_units`` via the registered
``curator.knowledge_unit_extract`` contract. Every unit must cite real source
span ids (the prompt validator rejects invented ids). Units are persisted only
when the prompt run validates; a failed run writes no partial artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import db, prompting

__all__ = ["KnowledgeUnitResult", "extract_knowledge_units"]


@dataclass
class KnowledgeUnitResult:
    unit_ids: list[str] = field(default_factory=list)
    trace_id: str = ""
    ok: bool = False
    errors: list[str] = field(default_factory=list)


def _spans_block(spans: list[dict]) -> str:
    lines = []
    for s in spans:
        title = s.get("section_title") or ""
        lines.append(f'{s["id"]} [{title}]: {s["text"]}')
    return "\n\n".join(lines)


def extract_knowledge_units(
    db_path: Path,
    client: Any,
    *,
    source_id: int,
    source_title: str,
    spans: list[dict],
    curate_spec_hash: str = "",
) -> KnowledgeUnitResult:
    """Extract and persist knowledge units from in-memory spans.

    ``spans`` items are dicts with keys ``id``, ``text``, and optional
    ``section_title`` — the just-stored spans carrying their full text (DB stores
    only previews, so the caller passes full text here).
    """
    if not spans:
        return KnowledgeUnitResult(ok=True)

    valid_ids = [s["id"] for s in spans]
    contract = prompting.REGISTRY.get("curator.knowledge_unit_extract")
    input_obj = contract.input_model(
        source_title=source_title,
        spans_block=_spans_block(spans),
        valid_span_ids_block="\n".join(valid_ids),
    )
    result = prompting.run_prompt(
        db_path,
        client,
        contract,
        input_obj,
        validation_context={"valid_span_ids": set(valid_ids)},
        source_ids=[source_id],
        source_span_ids=valid_ids,
        curate_spec_hash=curate_spec_hash,
    )

    unit_ids: list[str] = []
    if result.ok and result.parsed is not None:
        for unit in getattr(result.parsed, "units", []):
            uid = db.upsert_knowledge_unit(
                db_path,
                unit_type=unit.unit_type,
                canonical_name=unit.canonical_name,
                statement=unit.statement,
                source_span_ids=unit.source_span_ids,
                source_id=source_id,
                confidence=unit.confidence,
                truth_status=unit.truth_status,
                prompt_run_id=result.trace_id,
            )
            unit_ids.append(uid)
    return KnowledgeUnitResult(
        unit_ids=unit_ids,
        trace_id=result.trace_id,
        ok=result.ok,
        errors=list(result.validation.errors),
    )
