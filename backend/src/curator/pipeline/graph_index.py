"""Entity/relation graph extraction (L3 graph).

Builds the knowledge graph (typed entities + typed, directed, confidence-scored
relations) from knowledge units via the registered
``curator.entity_relation_extract`` contract. Relation endpoints must resolve to
declared entities; the prompt validator enforces that. Records land in the
``graph_entities`` / ``graph_relations`` DB tables (the source of truth).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import db, prompting

__all__ = ["GraphExtractionResult", "extract_entities_and_relations"]


@dataclass
class GraphExtractionResult:
    entity_ids: dict[str, str] = field(default_factory=dict)  # canonical_name -> ENT-id
    relation_ids: list[str] = field(default_factory=list)
    trace_id: str = ""
    ok: bool = False
    errors: list[str] = field(default_factory=list)


def _units_block(units: list[dict]) -> str:
    lines = []
    for u in units:
        spans = ", ".join(u.get("source_span_ids") or [])
        lines.append(
            f'{u["id"]} ({u.get("unit_type","claim")}) [{spans}]: {u.get("statement","")}'
        )
    return "\n".join(lines)


def extract_entities_and_relations(
    db_path: Path,
    client: Any,
    *,
    units: list[dict],
    valid_span_ids: list[str],
    curate_spec_hash: str = "",
) -> GraphExtractionResult:
    """Extract and persist entities/relations from knowledge units.

    ``units`` are ``knowledge_units`` rows (with ``source_span_ids`` decoded).
    """
    if not units:
        return GraphExtractionResult(ok=True)

    try:
        max_chars = int(client.optimal_chunk_chars())
    except Exception:
        max_chars = 60000

    batches = []
    current_batch = []
    current_chars = 0

    import copy
    refined_units = []
    for u in units:
        statement = u.get("statement") or ""
        # Defensive truncation: units shouldn't be massive, but if they are, truncate to fit context
        if len(statement) > max_chars - 500:
            u_copy = copy.copy(u)
            u_copy["statement"] = statement[:max_chars - 500] + "... [TRUNCATED]"
            refined_units.append(u_copy)
        else:
            refined_units.append(u)

    for u in refined_units:
        statement = u.get("statement") or ""
        unit_type = u.get("unit_type") or "claim"
        spans_str = ", ".join(u.get("source_span_ids") or [])
        # Rough estimate of unit length in prompt
        unit_len = len(str(u["id"])) + len(unit_type) + len(spans_str) + len(statement) + 30
        
        if current_batch and current_chars + unit_len > max_chars:
            batches.append(current_batch)
            current_batch = [u]
            current_chars = unit_len
        else:
            current_batch.append(u)
            current_chars += unit_len

    if current_batch:
        batches.append(current_batch)

    name_to_id: dict[str, str] = {}
    all_relation_ids: list[str] = []
    last_trace_id = ""
    all_errors = []
    all_ok = True

    contract = prompting.REGISTRY.get("curator.entity_relation_extract")

    for batch in batches:
        input_obj = contract.input_model(
            units_block=_units_block(batch),
            valid_span_ids_block="\n".join(valid_span_ids),
        )
        result = prompting.run_prompt(
            db_path,
            client,
            contract,
            input_obj,
            validation_context={"valid_span_ids": set(valid_span_ids)},
            source_span_ids=valid_span_ids,
            curate_spec_hash=curate_spec_hash,
        )

        if result.trace_id:
            last_trace_id = result.trace_id

        if not (result.ok and result.parsed is not None):
            all_ok = False
            if hasattr(result, "validation") and result.validation:
                all_errors.extend(result.validation.errors)
            continue

        # Persist entities first so relation endpoints resolve.
        for entity in getattr(result.parsed, "entities", []):
            ent_id = db.upsert_graph_entity(
                db_path,
                canonical_name=entity.canonical_name,
                entity_type=entity.entity_type,
                description=entity.description,
                source_span_ids=entity.source_span_ids,
                prompt_run_id=result.trace_id,
            )
            name_to_id[entity.canonical_name] = ent_id

        for rel in getattr(result.parsed, "relations", []):
            src = name_to_id.get(rel.source)
            tgt = name_to_id.get(rel.target)
            if not src or not tgt:
                # Validator should have caught this; skip defensively.
                continue
            rel_id = db.upsert_graph_relation(
                db_path,
                source_entity_id=src,
                target_entity_id=tgt,
                relation_type=rel.relation_type,
                description=rel.description,
                assertion_source=rel.assertion_source,
                source_span_ids=rel.source_span_ids,
                confidence=rel.confidence,
                prompt_run_id=result.trace_id,
            )
            all_relation_ids.append(rel_id)

    return GraphExtractionResult(
        entity_ids=name_to_id,
        relation_ids=all_relation_ids,
        trace_id=last_trace_id,
        ok=all_ok,
        errors=all_errors,
    )
