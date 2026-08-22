"""Entity/relation graph extraction (L3 graph).

Builds the knowledge graph (typed entities + typed, directed, confidence-scored
relations) from knowledge units via the registered
``curator.entity_relation_extract`` contract. Relation endpoints must resolve to
declared entities; the prompt validator enforces that. Records land in the
``graph_entities`` / ``graph_relations`` DB tables (the source of truth).
"""

from __future__ import annotations

import logging

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import db, prompting
from .claim_support import _extract_latex
from .chunking import client_optimal_chunk_chars, subdivision_chars

_log = logging.getLogger(__name__)

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


# Attempts per graph batch before it is reported failed. The agy CLI refuses a
# tool request in `-p` mode and exits 1, and the refusal is NOT deterministic per
# input — measured live, the same batch went through on its 3rd and 7th tries.
#
# Rate, measured on the live run and split by cause (an earlier reading of "83%"
# had conflated the two): of 11 failures, 5 were 429 capacity and 6 were
# permission denials, against 4 successes. Capacity is re-raised, not retried, so
# the rate that matters here is 6 refusals per 10 non-capacity calls — about 60%.
# At that rate 30 attempts leave a per-batch failure chance of 0.6**30 ≈ 2e-7.
#
# The CAP is not the cost. Expected attempts per batch is 1/0.4 = 2.5, so an
# 87-batch source costs ~218 calls; the cap only bounds the tail.
_MAX_BATCH_ATTEMPTS = 30


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
    # Floored: the bare `max_chars - 500` went NEGATIVE for a client reporting a
    # budget at or below the overlap allowance, and as a slice bound that keeps
    # the statement's HEAD only by accident of the value's magnitude — it
    # amputates the tail, and erases a statement shorter than the shortfall
    # entirely, leaving the model nothing but `... [TRUNCATED]` to extract from
    # (v0.61.2).
    keep_chars = subdivision_chars(max_chars)
    for u in units:
        statement = u.get("statement") or ""
        # Formula-bearing units stay intact: truncating their tail can silently
        # alter the mathematical claim. Oversized prose-only units may truncate.
        if len(statement) > keep_chars and not _extract_latex(statement):
            u_copy = copy.copy(u)
            u_copy["statement"] = statement[:keep_chars] + "... [TRUNCATED]"
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

    # Resume (ROADMAP 5c). A batch that already validated in an earlier run is
    # replayed from `graph_batch_results` instead of being paid for again.
    #
    # The source is DERIVED rather than passed: every unit row already carries
    # `source_id`, and a generation belongs to exactly one source, so a parameter
    # would only add a way to pass the wrong one. Callers whose units predate
    # this (the back-compat wrapper, older tests) simply do not stage.
    source_ids = {
        int(u["source_id"]) for u in units if u.get("source_id") is not None
    }
    if len(source_ids) > 1:
        resume_source_id = 0
        _log.warning(
            "graph resume disabled: batch units span %d sources %s",
            len(source_ids), sorted(source_ids),
        )
    else:
        resume_source_id = source_ids.pop() if source_ids else 0
    staged_before = (
        db.count_graph_batch_results(db_path, resume_source_id)
        if resume_source_id
        else 0
    )
    reused = 0
    extracted = 0

    for index, batch in enumerate(batches, start=1):
        # Send only the spans THIS batch can legitimately cite (ROADMAP 5d).
        #
        # `client_optimal_chunk_chars` bounds the units block; it does not bound
        # the rendered prompt, which also carried every span id of the source on
        # every batch. Measured on the reference vault's largest source: a
        # 15,981-char units block against a 124,669-char span block — 87% of a
        # 143,582-char prompt — where the batch cites a median of 67 of those
        # 8,905 ids. Across 24 batches that is 3.45 MB sent for 476 KB of need,
        # so the source burned its provider quota about 7x faster than required.
        #
        # Narrowing removes nothing the model could legitimately use: a relation
        # is grounded in the spans its own units carry, and a citation outside
        # the batch was never supportable. The narrowed list is the CONTRACT, so
        # validation uses the same set — telling the model one allowed list and
        # judging it by another is how a prompt and its validator drift apart.
        batch_span_ids = sorted(
            {s for u in batch for s in (u.get("source_span_ids") or [])}
        )
        # A batch whose units cite nothing would otherwise get an EMPTY allowed
        # list, which forbids every citation the model could make. Fall back to
        # the source's list rather than shipping an impossible contract.
        allowed_span_ids = batch_span_ids or valid_span_ids
        input_obj = contract.input_model(
            units_block=_units_block(batch),
            valid_span_ids_block="\n".join(allowed_span_ids),
        )

        # The resume key is the digest of the fully rendered prompt, the same
        # value `run_prompt` records in `prompt_runs.input_hash`. Rendering here
        # duplicates what the runner does internally; that is pure string
        # formatting against a provider round-trip measured in seconds.
        input_hash = ""
        if resume_source_id:
            input_hash = prompting.render_prompt(contract, input_obj).input_hash
            cached = db.get_graph_batch_result(db_path, resume_source_id, input_hash)
            if cached is not None:
                staged_trace = str(cached["trace_id"] or "")
                parsed_cached = _parse_staged_payload(str(cached["payload"]), contract)
                if parsed_cached is None:
                    # Unreadable payload — most likely written by an older
                    # contract shape. Re-extract rather than publish a graph
                    # nobody can account for.
                    _log.warning(
                        "graph batch %d/%d: staged payload unreadable, re-extracting",
                        index, len(batches),
                    )
                else:
                    for entity in getattr(parsed_cached, "entities", []):
                        collected_entities.append((entity, staged_trace))
                    for rel in getattr(parsed_cached, "relations", []):
                        collected_relations.append((rel, staged_trace))
                    if staged_trace:
                        last_trace_id = staged_trace
                    reused += 1
                    continue
        # A provider exception used to escape this loop entirely: validation
        # failures were guarded by the `continue` below, but `run_prompt` closes
        # its trace and RE-RAISES, so one refusal unwound the caller's staging
        # block and killed the compile.
        #
        # That is fatal at scale because publishing needs EVERY batch. Measured
        # on the live vault: source 45 needs ~87 batches, agy refused 43% of
        # calls (4 ok / 3 failed), so the expected number of batches completed
        # before the first abort was 1/0.43 = 2.3 — the run aborted after 2 —
        # and P(87 clean) was about 7e-22. The refusal is nondeterministic, so
        # re-running the same batch usually goes through.
        result = None
        refusal = ""
        for attempt in range(1, _MAX_BATCH_ATTEMPTS + 1):
            try:
                result = prompting.run_prompt(
                    db_path,
                    client,
                    contract,
                    input_obj,
                    validation_context={"valid_span_ids": set(allowed_span_ids)},
                    source_span_ids=allowed_span_ids,
                    curate_spec_hash=curate_spec_hash,
                )
                break
            except Exception as exc:  # noqa: BLE001 - see above; never fatal here
                # A CAPACITY refusal is NOT retried here. Retrying a 429 in a
                # tight loop spends the budget against a rate limit and undoes
                # v0.61.1, which exists so a refused job is left queued and the
                # worker reports how long to wait. Ask the client rather than
                # matching on the message: `_is_transient`'s substring matching
                # is exactly what misclassified a permanent failure once already.
                from ..ingest_worker import _capacity_wait

                if _capacity_wait(client) > 0:
                    raise
                refusal = f"{type(exc).__name__}: {exc}"
                _log.warning(
                    "graph batch %d/%d attempt %d/%d failed: %s",
                    index, len(batches), attempt, _MAX_BATCH_ATTEMPTS, refusal,
                )

        if result is None:
            # Exhausted. Report it the same way a validation failure reports —
            # ok=False with the reason — so the caller's error boundary stays the
            # single place that decides what a failed graph means.
            all_ok = False
            all_errors.append(
                f"graph batch {index}/{len(batches)} failed after "
                f"{_MAX_BATCH_ATTEMPTS} attempts: {refusal}"
            )
            continue

        if result.trace_id:
            last_trace_id = result.trace_id

        if not (result.ok and result.parsed is not None):
            all_ok = False
            if hasattr(result, "validation") and result.validation:
                all_errors.extend(result.validation.errors)
            continue

        # Stage the validated batch BEFORE collecting it, in its own
        # transaction, so an interruption after this point does not re-pay it.
        # Only a validated result is cacheable (D6): caching a refusal would
        # replay the refusal forever.
        if resume_source_id and input_hash:
            try:
                db.put_graph_batch_result(
                    db_path,
                    source_id=resume_source_id,
                    input_hash=input_hash,
                    payload=result.parsed.model_dump_json(),
                    trace_id=result.trace_id or "",
                )
            except Exception:  # noqa: BLE001 - staging is an optimisation
                # Never fail an extraction that succeeded because the cache
                # could not be written. The cost of losing this row is one
                # re-paid batch on the next run, not a failed compile.
                _log.warning(
                    "graph batch %d/%d: could not stage the result (non-fatal)",
                    index, len(batches), exc_info=True,
                )
        extracted += 1

        # Collect parsed objects IN MEMORY (no DB writes); persisted only after
        # the publish gate clears (copy-on-stage, §26.3).
        for entity in getattr(result.parsed, "entities", []):
            collected_entities.append((entity, result.trace_id))
        for rel in getattr(result.parsed, "relations", []):
            collected_relations.append((rel, result.trace_id))

    if resume_source_id:
        _log.info(
            "graph batches for source %d: reused %d/%d, extracted %d",
            resume_source_id, reused, len(batches), extracted,
        )
        if staged_before and reused == 0:
            # The realistic silent failure. Batch boundaries are cut at the
            # client's chunk size, so a provider failover resizes every batch and
            # misses every key; shifted unit ids do the same. Both are legitimate
            # misses that re-pay in full -- and look exactly like a run that
            # never had a cache. Say which it was.
            _log.warning(
                "graph resume matched NOTHING for source %d though %d staged "
                "batches exist: batch boundaries or unit ids moved (chunk size "
                "%d, %d batches this run). The source re-pays in full.",
                resume_source_id, staged_before, max_chars, len(batches),
            )

    return GraphData(
        entities=collected_entities,
        relations=collected_relations,
        trace_id=last_trace_id,
        ok=all_ok,
        errors=all_errors,
    )


def _parse_staged_payload(payload: str, contract: Any) -> Any | None:
    """Rebuild a staged batch through the contract's own output model.

    Uses the model rather than a hand-rolled dict walk: a resumed run replaces
    the provider's parsed output with this, so a dropped optional field would
    publish a DIFFERENT graph than a clean run with nothing to flag it.
    """
    model = getattr(contract, "output_model", None)
    if model is None:
        return None
    try:
        return model.model_validate_json(payload)
    except Exception:  # noqa: BLE001 - an unreadable row must not be fatal
        _log.debug("staged graph payload could not be parsed", exc_info=True)
        return None


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
