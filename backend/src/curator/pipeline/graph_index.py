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
from .claim_support import _extract_latex
from .chunking import client_optimal_chunk_chars

__all__ = [
    "GraphExtractionResult", "GraphData",
    "extract_graph_data", "persist_graph_data", "extract_entities_and_relations",
]


@dataclass
class GraphExtractionResult:
    entity_ids: dict[str, str] = field(default_factory=dict)  # canonical_name -> ENT-id
    relation_ids: list[str] = field(default_factory=list)
    trace_id: str = ""
    ok: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass
class GraphData:
    """In-memory graph extraction result (no DB writes) — lets the LLM run during
    staging (behind the publish gate) and persistence happen only after the gate
    (SYSTEM_BEHAVIOR §26.3 copy-on-stage). ``entities``/``relations`` are the raw
    parsed model objects paired with the prompt-run id that produced them."""

    entities: list[tuple[Any, str]] = field(default_factory=list)
    relations: list[tuple[Any, str]] = field(default_factory=list)
    trace_id: str = ""
    ok: bool = True
    errors: list[str] = field(default_factory=list)


def _units_block(units: list[dict]) -> str:
    lines = []
    for u in units:
        spans = ", ".join(u.get("source_span_ids") or [])
        lines.append(
            f'{u["id"]} ({u.get("unit_type","claim")}) [{spans}]: {u.get("statement","")}'
        )
    return "\n".join(lines)


def extract_graph_data(
    db_path: Path,
    client: Any,
    *,
    units: list[dict],
    valid_span_ids: list[str],
    curate_spec_hash: str = "",
) -> GraphData:
    """Run the entity/relation LLM extraction and return the parsed graph IN
    MEMORY (no DB writes for entities/relations). Persistence is deferred to
    :func:`persist_graph_data` inside the publish step, so a graph LLM failure
    occurs behind the publish gate and never leaves a published generation
    without its graph (SYSTEM_BEHAVIOR §26.3).

    ``units`` are ``knowledge_units`` rows (with ``source_span_ids`` decoded).
    """
    if not units:
        return GraphData(ok=True)

    max_chars = client_optimal_chunk_chars(client)

    batches: list[list[dict]] = []
    current_batch: list[dict] = []
    current_chars = 0

    import copy
    refined_units: list[dict] = []
    for u in units:
        statement = u.get("statement") or ""
        # Formula-bearing units stay intact: truncating their tail can silently
        # alter the mathematical claim. Oversized prose-only units may truncate.
        if len(statement) > max_chars - 500 and not _extract_latex(statement):
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

    collected_entities: list[tuple[Any, str]] = []
    collected_relations: list[tuple[Any, str]] = []
    last_trace_id = ""
    all_errors: list[str] = []
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

        # Collect parsed objects IN MEMORY (no DB writes); persisted only after
        # the publish gate clears (copy-on-stage, §26.3).
        for entity in getattr(result.parsed, "entities", []):
            collected_entities.append((entity, result.trace_id))
        for rel in getattr(result.parsed, "relations", []):
            collected_relations.append((rel, result.trace_id))

    return GraphData(
        entities=collected_entities,
        relations=collected_relations,
        trace_id=last_trace_id,
        ok=all_ok,
        errors=all_errors,
    )


def persist_graph_data(
    db_path: Path,
    data: GraphData,
    *,
    conn: Any = None,
    units: list[dict] | None = None,
    source_lineage_hash: str = "",
) -> GraphExtractionResult:
    """Upsert a previously-extracted :class:`GraphData` into graph_entities /
    graph_relations. No LLM; called inside the publish transaction so the graph
    rows publish — and roll back — atomically with the generation (a publish
    failure leaves no leaked graph). Pass ``conn`` to join that transaction.

    When ``units`` and ``source_lineage_hash`` are supplied (the live compile
    path), each persisted relation also AGGREGATES one ``graph_relation_supports``
    row per asserting knowledge unit, keyed by the source's lineage (§27.2). A
    relation is mapped to its asserting unit by span intersection — never by a
    broad all-span fallback (SYSTEM_BEHAVIOR §27.2). One source contributes exactly one independent
    lineage, which is already enough to reach the ``active`` floor (§27.2:
    >=1 lineage; only 0 is ``unsupported``). Further independent sources add
    corroboration as a confidence signal rather than an admission gate."""
    name_to_id: dict[str, str] = {}
    relation_ids: list[str] = []
    for entity, trace_id in data.entities:
        ent_id = db.upsert_graph_entity(
            db_path,
            canonical_name=entity.canonical_name,
            entity_type=entity.entity_type,
            description=entity.description,
            source_span_ids=entity.source_span_ids,
            prompt_run_id=trace_id,
            conn=conn,
        )
        name_to_id[entity.canonical_name] = ent_id

    # span -> [(unit_id, support_status)] index, used to attribute relation support
    # to the exact knowledge unit(s) whose evidence carries the relation's spans.
    span_units: dict[str, list[tuple[str, str]]] = {}
    if units and source_lineage_hash:
        for u in units:
            status = "verified" if u.get("support_status") == "verified" else "unchecked"
            for sid in u.get("source_span_ids") or []:
                span_units.setdefault(str(sid), []).append((str(u["id"]), status))

    for rel, trace_id in data.relations:
        src = name_to_id.get(rel.source)
        tgt = name_to_id.get(rel.target)
        if not src or not tgt:
            continue  # validator should have caught this; skip defensively
        rel_id = db.upsert_graph_relation(
            db_path,
            source_entity_id=src,
            target_entity_id=tgt,
            relation_type=rel.relation_type,
            description=rel.description,
            assertion_source=rel.assertion_source,
            source_span_ids=rel.source_span_ids,
            confidence=rel.confidence,
            prompt_run_id=trace_id,
            conn=conn,
        )
        relation_ids.append(rel_id)
        if span_units:
            _write_relation_supports(
                db_path, rel, rel_id, span_units, source_lineage_hash, conn=conn
            )
    return GraphExtractionResult(
        entity_ids=name_to_id, relation_ids=relation_ids,
        trace_id=data.trace_id, ok=data.ok, errors=data.errors,
    )


def _write_relation_supports(
    db_path: Path,
    rel: Any,
    rel_id: str,
    span_units: dict[str, list[tuple[str, str]]],
    source_lineage_hash: str,
    *,
    conn: Any = None,
) -> None:
    """Aggregate one support row per asserting unit for ``rel`` (§27.2). The
    asserting units are those whose evidence spans intersect the relation's cited
    spans; each contributes a support carrying the intersecting spans and this
    source's lineage. No matching unit → no support (correctly unsupported — never
    a broad-span fallback)."""
    rel_spans = [str(s) for s in (rel.source_span_ids or [])]
    # unit_id -> (status, intersecting spans) for the units that assert this relation
    per_unit: dict[str, tuple[str, list[str]]] = {}
    for sid in rel_spans:
        for unit_id, status in span_units.get(sid, []):
            cur = per_unit.setdefault(unit_id, (status, []))
            cur[1].append(sid)
            # a verified attribution wins over an unchecked one for the same unit
            if status == "verified" and cur[0] != "verified":
                per_unit[unit_id] = ("verified", cur[1])
    for unit_id, (status, spans) in per_unit.items():
        db.upsert_graph_relation_support(
            db_path,
            relation_id=rel_id,
            knowledge_unit_id=unit_id,
            # Dedup the intersecting spans: a span id repeated in the relation's
            # cited array would otherwise be appended twice (the writer also
            # canonicalizes defensively, so support_hash stays stable either way).
            source_span_ids=sorted(set(spans)),
            source_lineage_hash=source_lineage_hash,
            assertion_source=getattr(rel, "assertion_source", "source_states"),
            confidence=getattr(rel, "confidence", 0.0),
            support_status=status,
            conn=conn,
        )


def extract_entities_and_relations(
    db_path: Path,
    client: Any,
    *,
    units: list[dict],
    valid_span_ids: list[str],
    curate_spec_hash: str = "",
) -> GraphExtractionResult:
    """Extract AND persist entities/relations (back-compat convenience). New
    callers that need copy-on-stage atomicity should call ``extract_graph_data``
    during staging and ``persist_graph_data`` after the publish gate."""
    data = extract_graph_data(
        db_path, client, units=units, valid_span_ids=valid_span_ids,
        curate_spec_hash=curate_spec_hash,
    )
    if not data.ok:
        return GraphExtractionResult(ok=False, errors=data.errors, trace_id=data.trace_id)
    return persist_graph_data(db_path, data)
