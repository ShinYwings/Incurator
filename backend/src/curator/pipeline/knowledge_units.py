"""LLM knowledge-unit extraction (L2).

Refines source spans into typed ``knowledge_units`` via the registered
``curator.knowledge_unit_extract`` contract. Every unit must cite real source
span ids (the prompt validator rejects invented ids). Units are persisted only
after every extraction batch validates; a failed extraction writes no partial
artifact.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import db, prompting
from .chunking import client_optimal_chunk_chars

__all__ = ["KnowledgeUnitResult", "extract_knowledge_units"]


@dataclass
class KnowledgeUnitResult:
    unit_ids: list[str] = field(default_factory=list)
    trace_id: str = ""
    ok: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass
class _PendingKnowledgeUnit:
    unit: Any
    prompt_run_id: str


@dataclass
class _BatchResult:
    units: list[_PendingKnowledgeUnit] = field(default_factory=list)
    trace_id: str = ""
    errors: list[str] = field(default_factory=list)


_MAX_RETRY_DEPTH = 5
_MIN_SINGLE_SPAN_RETRY_CHARS = 4000


def _spans_block(spans: list[dict]) -> str:
    lines = []
    for s in spans:
        title = s.get("section_title") or ""
        lines.append(f'{s["id"]} [{title}]: {s["text"]}')
    return "\n\n".join(lines)


def _span_len(span: dict) -> int:
    title = span.get("section_title") or ""
    text = span.get("text") or ""
    return len(str(span["id"])) + len(title) + len(text) + 50


def _unique_span_ids(spans: list[dict]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for span in spans:
        span_id = str(span["id"])
        if span_id in seen:
            continue
        seen.add(span_id)
        out.append(span_id)
    return out


def _split_batch_for_retry(batch: list[dict]) -> tuple[list[dict], list[dict]] | None:
    """Split a failed batch without changing its source-span provenance."""
    if not batch:
        return None
    if len(batch) > 1:
        total = sum(_span_len(span) for span in batch)
        midpoint = max(1, total // 2)
        running = 0
        split_at = 1
        for i, span in enumerate(batch, start=1):
            running += _span_len(span)
            if running >= midpoint:
                split_at = i
                break
        split_at = min(max(1, split_at), len(batch) - 1)
        return batch[:split_at], batch[split_at:]

    span = batch[0]
    text = str(span.get("text") or "")
    if len(text) <= _MIN_SINGLE_SPAN_RETRY_CHARS:
        return None
    midpoint = len(text) // 2
    overlap = min(500, max(0, len(text) // 20))
    left_text = text[: midpoint + overlap].strip()
    right_text = text[max(0, midpoint - overlap) :].strip()
    if not left_text or not right_text or left_text == text or right_text == text:
        return None
    title = span.get("section_title") or ""
    left = {
        **span,
        "section_title": f"{title} (retry part 1)" if title else "retry part 1",
        "text": left_text,
    }
    right = {
        **span,
        "section_title": f"{title} (retry part 2)" if title else "retry part 2",
        "text": right_text,
    }
    return [left], [right]


def _batch_failure_errors(label: str, batch: list[dict], result: Any) -> list[str]:
    raw_errors = ["prompt validation failed"]
    if hasattr(result, "validation") and result.validation:
        raw_errors = list(result.validation.errors) or raw_errors
    span_ids = _unique_span_ids(batch)
    span_preview = ", ".join(span_ids[:5])
    if len(span_ids) > 5:
        span_preview += ", ..."
    trace = f" trace={result.trace_id}" if getattr(result, "trace_id", "") else ""
    return [
        f"L2 extraction {label} failed for spans [{span_preview}]{trace}: {error}"
        for error in raw_errors
    ]


def _batch_hash(batch: list[dict]) -> str:
    """Deterministic hash of a batch by its (span_id, section_title) pairs."""
    key = sorted((str(s["id"]), s.get("section_title") or "") for s in batch)
    return hashlib.sha256(json.dumps(key, separators=(",", ":")).encode()).hexdigest()[:16]


def _discard_unpublished_units(db_path: Path, source_id: int) -> None:
    """Remove source-local units from runs that never reached a generation."""
    from ..db_sync import delete_rows_with_tombstones_on_connection

    with db.connect(db_path) as conn:
        delete_rows_with_tombstones_on_connection(
            conn,
            "claim_supports",
            "knowledge_unit_id IN ("
            "SELECT id FROM knowledge_units WHERE source_id = ? "
            "AND generation_id IS NULL AND retired_at IS NULL)",
            (source_id,),
        )
        conn.execute(
            "DELETE FROM knowledge_units WHERE source_id = ? "
            "AND generation_id IS NULL AND retired_at IS NULL",
            (source_id,),
        )


def _run_batch_with_retry(
    db_path: Path,
    client: Any,
    contract: Any,
    *,
    source_id: int,
    source_title: str,
    batch: list[dict],
    label: str,
    curate_spec_hash: str,
    depth: int = 0,
) -> _BatchResult:
    valid_ids = _unique_span_ids(batch)
    input_obj = contract.input_model(
        source_title=source_title,
        spans_block=_spans_block(batch),
        valid_span_ids_block="\n".join(valid_ids),
    )
    try:
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
    except Exception as exc:
        span_preview = ", ".join(valid_ids[:5])
        if len(valid_ids) > 5:
            span_preview += ", ..."
        return _BatchResult(
            errors=[
                f"L2 extraction {label} failed for spans [{span_preview}]: "
                f"{type(exc).__name__}: {exc}"
            ]
        )
    trace_id = result.trace_id or ""

    if result.ok:
        pending = [
            _PendingKnowledgeUnit(unit=unit, prompt_run_id=trace_id)
            for unit in getattr(result.parsed, "units", [])
        ]
        return _BatchResult(units=pending, trace_id=trace_id)

    if depth < _MAX_RETRY_DEPTH:
        split = _split_batch_for_retry(batch)
        if split is not None:
            left, right = split
            left_result = _run_batch_with_retry(
                db_path,
                client,
                contract,
                source_id=source_id,
                source_title=source_title,
                batch=left,
                label=f"{label}.1",
                curate_spec_hash=curate_spec_hash,
                depth=depth + 1,
            )
            if left_result.errors:
                return _BatchResult(
                    trace_id=left_result.trace_id or trace_id,
                    errors=left_result.errors,
                )
            right_result = _run_batch_with_retry(
                db_path,
                client,
                contract,
                source_id=source_id,
                source_title=source_title,
                batch=right,
                label=f"{label}.2",
                curate_spec_hash=curate_spec_hash,
                depth=depth + 1,
            )
            return _BatchResult(
                units=[*left_result.units, *right_result.units],
                trace_id=right_result.trace_id or left_result.trace_id or trace_id,
                errors=[*left_result.errors, *right_result.errors],
            )

    return _BatchResult(
        trace_id=trace_id,
        errors=_batch_failure_errors(label, batch, result),
    )


def _persist_units(
    db_path: Path,
    *,
    source_id: int,
    pending_units: list[_PendingKnowledgeUnit],
) -> list[str]:
    all_span_ids: list[str] = []
    for pending in pending_units:
        all_span_ids.extend(str(span_id) for span_id in pending.unit.source_span_ids)
    unique_span_ids = list(dict.fromkeys(all_span_ids))
    span_rows = {
        str(row["id"]): row
        for row in db.get_source_spans_by_ids(db_path, unique_span_ids)
    }

    unit_ids: list[str] = []
    with db.connect(db_path) as conn:
        for pending in pending_units:
            unit = pending.unit
            uid = db.upsert_knowledge_unit(
                db_path,
                unit_type=unit.unit_type,
                canonical_name=unit.canonical_name,
                statement=unit.statement,
                source_span_ids=unit.source_span_ids,
                source_id=source_id,
                confidence=unit.confidence,
                truth_status=unit.truth_status,
                prompt_run_id=pending.prompt_run_id,
                conn=conn,
            )
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
                    conn=conn,
                )
            unit_ids.append(uid)
    return unit_ids


def extract_knowledge_units(
    db_path: Path,
    client: Any,
    *,
    source_id: int,
    source_title: str,
    spans: list[dict],
    curate_spec_hash: str = "",
    on_progress: Callable[[str, dict[str, object]], None] | None = None,
) -> KnowledgeUnitResult:
    """Extract and persist knowledge units from in-memory spans.

    ``spans`` items are dicts with keys ``id``, ``text``, and optional
    ``section_title`` — the just-stored spans carrying their full text (DB stores
    only previews, so the caller passes full text here).

    Extraction is all-or-nothing: staged units from a previous interrupted run
    are discarded first, then units accumulate in memory and are bulk-persisted
    only on full success. An interrupted run therefore re-processes every batch.

    A checkpoint-resume mechanism used to sit here and was removed in v0.52.0
    because it could never run — checkpoints were written only inside the branch
    that required checkpoints to already exist, so the table stayed empty
    forever (verified: 0 rows across 36 sources and 2,799 units). Resumable L2
    is still worth having; see the roadmap. It needs designing rather than
    re-enabling, because the old resume path also returned the staged-unit list,
    which is empty after a successful publish and would have retired the
    source's entire authoritative unit set.
    """
    _discard_unpublished_units(db_path, source_id)

    if not spans:
        return KnowledgeUnitResult(ok=True)

    max_chars = client_optimal_chunk_chars(client)

    from ..ingest_raw import _chunk_text
    refined_spans = []
    for s in spans:
        title = s.get("section_title") or ""
        text = s.get("text") or ""
        span_len = _span_len(s)

        if span_len > max_chars:
            # Subdivide the massive span text
            sub_texts = _chunk_text(text, chunk_size=max_chars - 500, overlap=500)
            for i, sub in enumerate(sub_texts):
                refined_spans.append(
                    {
                        "id": s["id"],
                        "section_title": f"{title} (Part {i+1})",
                        "text": sub,
                    }
                )
        else:
            refined_spans.append(s)

    batches: list[list[dict]] = []
    current_batch: list[dict] = []
    current_chars = 0

    for s in refined_spans:
        span_len = _span_len(s)

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
    last_trace_id = ""
    all_errors: list[str] = []

    # Accumulate in memory, bulk-persist on full success.
    pending_units: list[_PendingKnowledgeUnit] = []
    for index, batch in enumerate(batches, start=1):
        result = _run_batch_with_retry(
            db_path,
            client,
            contract,
            source_id=source_id,
            source_title=source_title,
            batch=batch,
            label=f"batch {index}/{len(batches)}",
            curate_spec_hash=curate_spec_hash,
        )
        if result.trace_id:
            last_trace_id = result.trace_id
        if result.errors:
            all_errors.extend(result.errors)
            break
        pending_units.extend(result.units)

        # One event per LLM call — the heartbeat that makes a slow L2 and a
        # stopped one distinguishable. This loop already knows both numbers; the
        # retry label three lines up is built from the same pair. Before v0.59.0
        # nothing left this function until it had finished, so a job spent the
        # whole extraction reporting a single unchanging row.
        #
        # This is an OBSERVATION, NOT A CHECKPOINT. Extraction is
        # all-or-nothing by design: units accumulate in memory and are
        # bulk-persisted only on full success, so an interrupted run re-does
        # every batch. Do not grow this into a resume point — a checkpoint
        # mechanism lived here and was removed in v0.52.0 because it could never
        # run, and its resume path returned the staged-unit list, which is empty
        # after a successful publish and would retire a source's entire
        # authoritative unit set. Resumable L2 is a separate roadmap item.
        if on_progress is not None:
            try:
                on_progress(
                    "extracted",
                    {
                        "phase": "l2",
                        "batch": index,
                        "batches": len(batches),
                        "units": len(pending_units),
                    },
                )
            except Exception:  # noqa: BLE001 - observation is never fatal
                pass

    if all_errors:
        return KnowledgeUnitResult(
            trace_id=last_trace_id,
            ok=False,
            errors=all_errors,
        )

    all_unit_ids = _persist_units(
        db_path,
        source_id=source_id,
        pending_units=pending_units,
    )

    return KnowledgeUnitResult(
        unit_ids=all_unit_ids,
        trace_id=last_trace_id,
        ok=True,
    )
