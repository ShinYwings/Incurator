"""LLM knowledge-unit extraction (L2).

Refines source spans into typed ``knowledge_units`` via the registered
``curator.knowledge_unit_extract`` contract. Every unit must cite real source
span ids (the prompt validator rejects invented ids).

Each batch's units are persisted as it validates, with ``generation_id`` left
NULL so they are stored but not authoritative; ``compile.py`` stamps the staged
generation onto the returned ids before the publish gate. An interrupted run
therefore keeps its completed batches, and a re-run adopts them instead of
re-paying the provider (SYSTEM_BEHAVIOR L2 item 4).
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import db, prompting
from .chunking import client_optimal_chunk_chars

_log = logging.getLogger(__name__)

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
    # Ids of units adopted from a previous run's identical batch. Already
    # persisted, so the loop must NOT pass them through `_persist_units`.
    adopted_ids: list[str] = field(default_factory=list)


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


def _adoptable_unit_ids(
    db_path: Path, source_id: int, *, curate_spec_hash: str
) -> set[str]:
    """Unpublished units a resumed run may still adopt (SYSTEM_BEHAVIOR L2 §4).

    A unit qualifies when its prompt run matches the ACTIVE contract and curate
    spec, that run validated (``ok`` or ``repaired`` — a JSON-repair retry still
    produced validated output), and every span it cites still exists. Anything
    else is leftover from a configuration or a source that no longer applies.
    """
    from .compile import PROMPT_CONTRACT_VERSION

    with db.connect(db_path) as c:
        rows = c.execute(
            """
            SELECT ku.id AS id, ku.source_span_ids AS spans
              FROM knowledge_units ku
              JOIN prompt_runs pr ON pr.trace_id = ku.prompt_run_id
             WHERE ku.source_id = ?
               AND ku.generation_id IS NULL
               AND ku.retired_at IS NULL
               AND pr.prompt_id || '@' || pr.prompt_version = ?
               AND COALESCE(pr.curate_spec_hash, '') = ?
               AND pr.validator_status IN ('ok', 'repaired')
            """,
            (source_id, PROMPT_CONTRACT_VERSION, curate_spec_hash or ""),
        ).fetchall()
        live = {
            str(r[0]) for r in c.execute(
                "SELECT id FROM source_spans WHERE source_id = ?", (source_id,)
            ).fetchall()
        }
    keep: set[str] = set()
    for row in rows:
        cited = [str(s) for s in json.loads(row["spans"] or "[]")]
        if cited and all(sid in live for sid in cited):
            keep.add(str(row["id"]))
    return keep


def _discard_unpublished_units(
    db_path: Path, source_id: int, *, keep: set[str] | None = None
) -> None:
    """Remove source-local units from runs that never reached a generation.

    ``keep`` holds the ids a resume may still adopt; everything else generation-
    less goes, because it was never authoritative and must not reach the publish
    gate. Claim supports are deleted before their units so nothing is left
    dangling — `dangling_supports` is publish-blocking.
    """
    from ..db_sync import delete_rows_with_tombstones_on_connection

    keep = keep or set()

    with db.connect(db_path) as conn:
        # The kept ids go through a TEMP TABLE, not `id NOT IN (?,?,…)`.
        # SYSTEM_BEHAVIOR requires queries to stay under 900 bind parameters
        # ("remaining below SQLite's common 999-variable limit") and
        # `compile.py:_SQL_VAR_CHUNK` implements that elsewhere. A resumable
        # source blows straight past it: source 45 alone has 5,358 adoptable
        # units, and this is the FIRST statement every resumed extraction runs,
        # so an id list would fail the whole ingest on any conforming build.
        # `executemany` binds one row at a time and has no such ceiling.
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS _ku_keep (id TEXT PRIMARY KEY)")
        conn.execute("DELETE FROM _ku_keep")
        if keep:
            conn.executemany(
                "INSERT OR IGNORE INTO _ku_keep (id) VALUES (?)",
                [(uid,) for uid in sorted(keep)],
            )
        doomed = (
            "SELECT id FROM knowledge_units WHERE source_id = ? "
            "AND generation_id IS NULL AND retired_at IS NULL "
            "AND id NOT IN (SELECT id FROM _ku_keep)"
        )
        delete_rows_with_tombstones_on_connection(
            conn,
            "claim_supports",
            f"knowledge_unit_id IN ({doomed})",
            (source_id,),
        )
        conn.execute(f"DELETE FROM knowledge_units WHERE id IN ({doomed})", (source_id,))
        conn.execute("DROP TABLE IF EXISTS _ku_keep")


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
    adoptable: set[str] | None = None,
    depth: int = 0,
) -> _BatchResult:
    valid_ids = _unique_span_ids(batch)
    input_obj = contract.input_model(
        source_title=source_title,
        spans_block=_spans_block(batch),
        valid_span_ids_block="\n".join(valid_ids),
    )

    # Resume: has this EXACT batch already been extracted and kept?
    #
    # The check sits here rather than in the batch loop on purpose. A batch that
    # failed validation is split and re-run as sub-batches (below), each its own
    # prompt run; checking only at the top level would re-pay every batch that
    # previously succeeded only in halves. `_split_batch_for_retry` is
    # deterministic, so a child's rendered prompt — and therefore its hash —
    # reproduces exactly like its parent's.
    if adoptable:
        adopted = _adopt_existing_batch(
            db_path,
            contract,
            input_obj,
            source_id=source_id,
            curate_spec_hash=curate_spec_hash,
            adoptable=adoptable,
        )
        if adopted is not None:
            trace_id, unit_ids = adopted
            _log.debug("L2 %s adopted from prompt run %s", label, trace_id)
            return _BatchResult(trace_id=trace_id, adopted_ids=unit_ids)

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
                adoptable=adoptable,
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
                adoptable=adoptable,
                depth=depth + 1,
            )
            return _BatchResult(
                units=[*left_result.units, *right_result.units],
                trace_id=right_result.trace_id or left_result.trace_id or trace_id,
                errors=[*left_result.errors, *right_result.errors],
                adopted_ids=[*left_result.adopted_ids, *right_result.adopted_ids],
            )

    return _BatchResult(
        trace_id=trace_id,
        errors=_batch_failure_errors(label, batch, result),
    )


def _adopt_existing_batch(
    db_path: Path,
    contract: Any,
    input_obj: Any,
    *,
    source_id: int,
    curate_spec_hash: str,
    adoptable: set[str],
) -> tuple[str, list[str]] | None:
    """Find a completed run of this exact batch, and return its kept unit ids.

    Batch identity is ``prompt_runs.input_hash`` — the digest of the fully
    rendered system+user messages. It covers the batch text, the span ids cited
    in it, AND the prompt template, so a template edit invalidates every batch by
    construction and no separate configuration key has to be defined or kept in
    sync. Rendering here duplicates the render `run_prompt` does internally; that
    is pure string formatting against a provider round-trip measured at a 18.6 s
    median, so it is not worth restructuring the runner to share.

    Returns ``None`` when nothing matches, which is also what a run whose units
    were dropped by the caller's conditional discard gets — ``adoptable`` is the
    authority on which rows survived, and a run whose units are all gone must be
    re-done rather than adopted as an empty batch.
    """
    rendered = prompting.render_prompt(contract, input_obj)
    with db.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT ku.id AS id, ku.prompt_run_id AS trace_id
              FROM knowledge_units ku
              JOIN prompt_runs pr ON pr.trace_id = ku.prompt_run_id
             WHERE ku.source_id = ?
               AND ku.generation_id IS NULL
               AND ku.retired_at IS NULL
               AND pr.input_hash = ?
               AND pr.prompt_id = ?
               AND pr.prompt_version = ?
               AND COALESCE(pr.curate_spec_hash, '') = ?
               AND pr.validator_status IN ('ok', 'repaired')
             ORDER BY ku.created_at
            """,
            (
                source_id,
                rendered.input_hash,
                contract.prompt_id,
                contract.version,
                curate_spec_hash or "",
            ),
        ).fetchall()

    # Adopt the units of exactly ONE prompt run. `input_hash` is stable across
    # attempts by design — the same batch re-run months later hashes the same —
    # so this query can legitimately match rows written by two different runs.
    # Taking all of them would attribute one batch's output twice.
    #
    # An earlier draft guarded with `len(unit_ids) != len(rows)` and a comment
    # claiming it caught partly-surviving batches. It could never fire: the
    # caller's conditional discard has already deleted every non-adoptable row,
    # so `rows` is a subset of `adoptable` by construction.
    by_trace: dict[str, list[str]] = {}
    for row in rows:
        if str(row["id"]) in adoptable:
            by_trace.setdefault(str(row["trace_id"]), []).append(str(row["id"]))
    if len(by_trace) != 1:
        return None
    trace_id, unit_ids = next(iter(by_trace.items()))
    return trace_id, unit_ids


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

    Publication is all-or-nothing; persistence is not. Each batch's units are
    written as it validates, with ``generation_id`` NULL, so an interrupted run
    keeps its completed work and a re-run adopts it instead of re-paying the
    provider. Batch identity is ``prompt_runs.input_hash``, which covers the
    rendered prompt including the template — see ``_adopt_existing_batch``.

    Generation-less rows from runs that no longer apply are discarded first:
    a changed contract or curate spec, or spans that no longer exist. Those were
    never authoritative and must not reach the publish gate.

    A checkpoint-resume mechanism was removed in v0.52.0 because it could never
    run — checkpoints were written only inside the branch that required
    checkpoints to already exist, so the table stayed empty forever (verified:
    0 rows across 36 sources and 2,799 units). It is NOT what this is. Its other
    defect was returning the staged-unit list as the result, which is empty after
    a successful publish and would have retired the source's entire authoritative
    unit set; the loop below accumulates ids instead and cannot reproduce that.
    """
    adoptable = _adoptable_unit_ids(
        db_path, source_id, curate_spec_hash=curate_spec_hash
    )
    _discard_unpublished_units(db_path, source_id, keep=adoptable)

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

    # Persist per batch; publication stays atomic (SYSTEM_BEHAVIOR L2 items 3-4).
    all_unit_ids: list[str] = []
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
            adoptable=adoptable,
        )
        if result.trace_id:
            last_trace_id = result.trace_id
        if result.errors:
            all_errors.extend(result.errors)
            # A batch that failed validation is split and re-run as halves, and
            # one half can validate while the other does not. Persist the half
            # that did. Its prompt run is already recorded `ok`, so without the
            # rows `_adopt_existing_batch` finds nothing for that hash and the
            # next run re-splits the parent and re-pays BOTH halves — for every
            # retry, indefinitely. The ids are deliberately NOT added to
            # `all_unit_ids`: this run returns ok=False and must attribute
            # nothing, and the rows stay `generation_id IS NULL` for a resume.
            if result.units:
                _persist_units(db_path, source_id=source_id, pending_units=result.units)
            break
        # Adopted units are already stored; only fresh ones are written. Both
        # accumulate HERE, in the loop. A resumed run must never derive its
        # result by querying the source's staged units: that set filters
        # `generation_id IS NULL` and is empty after a successful publish, so
        # the run would attribute zero units to a fresh generation and retire
        # the source's entire authoritative set (§26.3). That is the exact
        # defect that made the v0.51.1 resume path unusable.
        all_unit_ids.extend(result.adopted_ids)
        if result.units:
            all_unit_ids.extend(
                _persist_units(db_path, source_id=source_id, pending_units=result.units)
            )

        # One event per BATCH — the heartbeat that makes a slow L2 and a
        # stopped one distinguishable. Not per LLM call: `_run_batch_with_retry`
        # splits a batch that fails validation and recurses, so a single
        # iteration can cost several calls and go quiet between events. This
        # loop already knows both numbers; the retry label above is built from
        # the same pair. Before v0.59.0 nothing left this function until it had
        # finished, so a job spent the whole extraction reporting one
        # unchanging row.
        #
        # This is an OBSERVATION, not the resume mechanism. Resume keys on
        # `prompt_runs.input_hash` (see `_adopt_existing_batch`), never on this
        # index: `optimal_chunk_chars` changes the batch count with the provider
        # — measured 12 / 23 / 46 / 93 for the same source at 60k / 32k / 16k /
        # 8k — so an index identifies nothing across a configuration change.
        if on_progress is not None:
            try:
                on_progress(
                    "extracted",
                    {
                        "phase": "l2",
                        "batch": index,
                        "batches": len(batches),
                        "units": len(all_unit_ids),
                    },
                )
            except Exception:  # noqa: BLE001 - observation is never fatal
                # Logged, not silent: XC-1 established that best-effort swallows
                # in this codebase still leave a debug trace, and this is the
                # highest-frequency event the sink emits — a bug in the caller's
                # sink would otherwise be invisible exactly where it matters.
                _log.debug("progress sink raised (non-fatal)", exc_info=True)

    if all_errors:
        return KnowledgeUnitResult(
            trace_id=last_trace_id,
            ok=False,
            errors=all_errors,
        )

    return KnowledgeUnitResult(
        unit_ids=all_unit_ids,
        trace_id=last_trace_id,
        ok=True,
    )
