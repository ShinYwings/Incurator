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

    try:
        max_chars = int(client.optimal_chunk_chars())
    except Exception:
        max_chars = 60000

    from ..ingest_raw import _chunk_text
    refined_spans = []
    for s in spans:
        title = s.get("section_title") or ""
        text = s.get("text") or ""
        span_len = len(str(s["id"])) + len(title) + len(text) + 50
        
        if span_len > max_chars:
            # Subdivide the massive span text
            sub_texts = _chunk_text(text, chunk_size=max_chars - 500, overlap=500)
            for i, sub in enumerate(sub_texts):
                refined_spans.append({
                    "id": s["id"],
                    "section_title": f"{title} (Part {i+1})",
                    "text": sub
                })
        else:
            refined_spans.append(s)

    batches = []
    current_batch = []
    current_chars = 0

    for s in refined_spans:
        title = s.get("section_title") or ""
        text = s.get("text") or ""
        span_len = len(str(s["id"])) + len(title) + len(text) + 50
        
        if current_batch and current_chars + span_len > max_chars:
            batches.append(current_batch)
            current_batch = [s]
            current_chars = span_len
        else:
            current_batch.append(s)
            current_chars += span_len

    if current_batch:
        batches.append(current_batch)

    contract = prompting.REGISTRY.get("curator.knowledge_unit_extract")
    all_unit_ids: list[str] = []
    last_trace_id = ""
    all_errors = []
    all_ok = True

    for batch in batches:
        valid_ids = [s["id"] for s in batch]
        input_obj = contract.input_model(
            source_title=source_title,
            spans_block=_spans_block(batch),
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

        if result.trace_id:
            last_trace_id = result.trace_id

        if not result.ok:
            all_ok = False
            if hasattr(result, "validation") and result.validation:
                all_errors.extend(result.validation.errors)
            continue

        if result.parsed is not None:
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
                span_rows = {
                    str(row["id"]): row
                    for row in db.get_source_spans_by_ids(db_path, unit.source_span_ids)
                }
                proposed_roles = dict(unit.support_roles)
                if not proposed_roles and unit.source_span_ids:
                    proposed_roles = {
                        sid: "primary" if i == 0 else "contextual"
                        for i, sid in enumerate(unit.source_span_ids)
                    }
                for span_id, role in proposed_roles.items():
                    span = span_rows.get(span_id)
                    if span is None or span_id not in unit.source_span_ids:
                        continue
                    db.upsert_claim_support(
                        db_path,
                        knowledge_unit_id=uid,
                        source_span_id=span_id,
                        support_role=role,
                        support_status="unchecked",
                        evidence_hash=str(span["content_hash"]),
                    )
                all_unit_ids.append(uid)

    return KnowledgeUnitResult(
        unit_ids=all_unit_ids,
        trace_id=last_trace_id,
        ok=all_ok,
        errors=all_errors,
    )
