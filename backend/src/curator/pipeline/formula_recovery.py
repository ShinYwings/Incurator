"""Selective formula-loss classification and recovery lifecycle (Plan B P5)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import db
from .claim_support import (
    _extract_latex,
    _formula_tokens,
    _is_formula_subsequence,
    validate_claim_support,
)

__all__ = [
    "classify_formula_loss",
    "invalidate_formula_recoveries",
    "recover_formula",
]

LOSS_VERDICTS = frozenset({"fragmented", "image_only", "parser_omitted"})
ACCEPTANCE_CONFIDENCE = 0.80


def _contains_formula(text: str, expected: tuple[str, ...]) -> bool:
    return any(
        _is_formula_subsequence(expected, _formula_tokens(formula))
        for formula in _extract_latex(text)
    )


def classify_formula_loss(
    expected_latex: str,
    *,
    parser_text: str,
    raw_text: str,
    extracted_text: str,
    rendered_formula_present: bool = False,
) -> str | None:
    """Classify a measured formula-loss boundary without a provider call.

    Returns ``None`` when the formula is preserved or evidence is insufficient;
    recovery is never scheduled from an expected formula alone.
    """
    expected = _formula_tokens(expected_latex)
    if not expected:
        return None
    if _contains_formula(extracted_text, expected):
        return None

    extracted_formulas = _extract_latex(extracted_text)
    parser_formulas = _extract_latex(parser_text)
    raw_formulas = _extract_latex(raw_text)
    if extracted_formulas:
        return "fragmented"
    if _contains_formula(raw_text, expected) or _contains_formula(parser_text, expected):
        return "parser_omitted"
    if parser_formulas or raw_formulas:
        return "fragmented"
    if rendered_formula_present:
        return "fragmented" if extracted_text.strip() else "image_only"
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def recover_formula(
    db_path: Path,
    *,
    unit_id: str,
    span_id: str,
    loss_verdict: str,
    locator: dict[str, Any],
    page_hash: str,
    crop_hash: str,
    provider: str,
    model: str,
    confidence: float,
    latex: str,
    validator_trace_id: str | None = None,
    raw_span_texts: dict[str, str] | None = None,
    acceptance_confidence: float = ACCEPTANCE_CONFIDENCE,
) -> dict[str, Any]:
    """Record one additive recovery candidate and revalidate only if reviewed."""
    if loss_verdict not in LOSS_VERDICTS:
        raise ValueError(f"invalid formula loss verdict: {loss_verdict!r}")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("formula recovery confidence must be between 0 and 1")

    with db.connect(db_path) as conn:
        span = conn.execute(
            "SELECT content_hash, text_preview, metadata FROM source_spans WHERE id = ?",
            (span_id,),
        ).fetchone()
        unit = conn.execute(
            "SELECT statement, source_span_ids, formula_status "
            "FROM knowledge_units WHERE id = ?",
            (unit_id,),
        ).fetchone()
    if span is None:
        raise ValueError(f"unknown source span: {span_id}")
    if unit is None:
        raise ValueError(f"unknown knowledge unit: {unit_id}")
    cited_span_ids = json.loads(unit["source_span_ids"] or "[]")
    if span_id not in cited_span_ids:
        raise ValueError(f"knowledge unit {unit_id} does not cite source span {span_id}")
    if unit["formula_status"] != "uncertain":
        raise ValueError(
            f"formula recovery requires formula_status='uncertain': {unit_id}"
        )
    if raw_span_texts is not None:
        cited_spans = db.get_source_spans_by_ids(db_path, cited_span_ids)
        if {row["id"] for row in cited_spans} != set(cited_span_ids):
            raise ValueError(f"knowledge unit {unit_id} cites an unknown source span")
        for cited_span in cited_spans:
            raw_text = raw_span_texts.get(cited_span["id"])
            if raw_text is None:
                raise ValueError(
                    f"missing hydrated source span for revalidation: {cited_span['id']}"
                )
            raw_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:16]
            if raw_hash != cited_span["content_hash"]:
                raise ValueError(
                    f"hydrated source span hash mismatch: {cited_span['id']}"
                )

    claim_formulas = [_formula_tokens(value) for value in _extract_latex(unit["statement"])]
    recovered_tokens = _formula_tokens(latex)
    structurally_matches_claim = recovered_tokens in claim_formulas
    reviewed = (
        confidence >= acceptance_confidence
        and bool(validator_trace_id)
        and structurally_matches_claim
        and raw_span_texts is not None
    )
    status = "reviewed" if reviewed else "candidate"
    candidate = {
        "status": status,
        "loss_verdict": loss_verdict,
        "knowledge_unit_id": unit_id,
        "locator": locator,
        "page_hash": page_hash,
        "crop_hash": crop_hash,
        "provider": provider,
        "model": model,
        "confidence": confidence,
        "latex": latex,
        "validator_trace_id": validator_trace_id,
        "created_at": _now_iso(),
    }

    # Read-modify-write metadata in a single transaction to prevent TOCTOU
    # races where concurrent recovery calls silently overwrite each other's
    # appended candidates.
    with db.connect(db_path) as conn:
        fresh_span = conn.execute(
            "SELECT metadata FROM source_spans WHERE id = ?",
            (span_id,),
        ).fetchone()
        metadata = json.loads(fresh_span["metadata"] or "{}")
        if not isinstance(metadata, dict):
            raise ValueError(f"source span {span_id} has invalid metadata")
        recoveries = metadata.setdefault("formula_recovery", [])
        if not isinstance(recoveries, list):
            raise ValueError(f"source span {span_id} has invalid formula_recovery metadata")
        recoveries.append(candidate)
        conn.execute(
            "UPDATE source_spans SET metadata = ? WHERE id = ?",
            (json.dumps(metadata, ensure_ascii=False, sort_keys=True), span_id),
        )

    if not reviewed:
        db.set_unit_formula_status(db_path, unit_id, "uncertain")
        return candidate

    assert raw_span_texts is not None
    augmented_span_texts = dict(raw_span_texts)
    # Re-validate against the additive recovered evidence of EVERY cited span,
    # not just the one being recovered (SYSTEM_BEHAVIOR §26.2: "every cited span
    # plus additive recovered evidence"). The candidate written above is already
    # persisted as 'reviewed', so this loop also re-hydrates it — a multi-span
    # multi-formula claim whose other formulas were recovered earlier would
    # otherwise fail re-validation purely because their evidence was dropped.
    with db.connect(db_path) as conn:
        for cited_id in cited_span_ids:
            cited_meta_row = conn.execute(
                "SELECT metadata FROM source_spans WHERE id = ?", (cited_id,)
            ).fetchone()
            if cited_meta_row is None:
                continue
            cited_meta = json.loads(cited_meta_row["metadata"] or "{}")
            if not isinstance(cited_meta, dict):
                continue
            for rec in cited_meta.get("formula_recovery", []):
                if (
                    isinstance(rec, dict)
                    and rec.get("status") == "reviewed"
                    and rec.get("latex")
                ):
                    augmented_span_texts[cited_id] = (
                        f"{augmented_span_texts[cited_id]}\n${rec['latex']}$"
                    )
    verdict = validate_claim_support(
        db_path,
        unit_id,
        span_texts=augmented_span_texts,
    )
    candidate["validation_verdict"] = verdict
    if verdict != "verified":
        db.set_unit_formula_status(db_path, unit_id, "uncertain")
        return candidate

    db.upsert_claim_support(
        db_path,
        knowledge_unit_id=unit_id,
        source_span_id=span_id,
        support_role="formula",
        support_status="verified",
        evidence_hash=span["content_hash"],
        validator_trace_id=validator_trace_id,
    )
    db.set_unit_formula_status(db_path, unit_id, "linked_evidence")
    return candidate


def invalidate_formula_recoveries(
    db_path: Path,
    *,
    span_id: str,
    current_page_hash: str,
) -> int:
    """Reject candidates from an older rendered page and stale served evidence."""
    # Read-modify-write metadata in a single transaction to prevent TOCTOU.
    with db.connect(db_path) as conn:
        span = conn.execute(
            "SELECT metadata FROM source_spans WHERE id = ?",
            (span_id,),
        ).fetchone()
        if span is None:
            raise ValueError(f"unknown source span: {span_id}")

        metadata = json.loads(span["metadata"] or "{}")
        if not isinstance(metadata, dict):
            raise ValueError(f"source span {span_id} has invalid metadata")
        recoveries = metadata.get("formula_recovery", [])
        if not isinstance(recoveries, list):
            raise ValueError(f"source span {span_id} has invalid formula_recovery metadata")

        invalidated = 0
        reviewed_units: list[tuple[str, list[dict]]] = []
        for candidate in recoveries:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("status") not in {"candidate", "reviewed"}:
                continue
            if candidate.get("page_hash") == current_page_hash:
                continue
            prior_status = candidate["status"]
            candidate["status"] = "rejected"
            candidate["rejection_reason"] = "stale_page_hash"
            candidate["invalidated_at"] = _now_iso()
            invalidated += 1

            unit_id = candidate.get("knowledge_unit_id")
            if prior_status == "reviewed" and isinstance(unit_id, str):
                formula_supports = [
                    row
                    for row in db.list_claim_supports(db_path, unit_id)
                    if row["source_span_id"] == span_id and row["support_role"] == "formula"
                ]
                if formula_supports:
                    reviewed_units.append((unit_id, formula_supports))

        if invalidated:
            conn.execute(
                "UPDATE source_spans SET metadata = ? WHERE id = ?",
                (json.dumps(metadata, ensure_ascii=False, sort_keys=True), span_id),
            )

    # Update support/formula status outside the metadata transaction (each
    # helper opens its own connection).
    for unit_id, formula_supports in reviewed_units:
        for support in formula_supports:
            db.upsert_claim_support(
                db_path,
                knowledge_unit_id=unit_id,
                source_span_id=span_id,
                support_role="formula",
                support_status="stale",
                evidence_hash=support["evidence_hash"],
                support_reason="formula recovery page hash changed",
                validator_trace_id=support["validator_trace_id"],
            )
        db.set_unit_support_status(
            db_path,
            unit_id,
            "stale",
            "formula recovery page hash changed",
        )
        db.set_unit_formula_status(db_path, unit_id, "uncertain")

    return invalidated
