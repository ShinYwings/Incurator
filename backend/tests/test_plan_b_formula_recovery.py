"""Plan B P5 provider-free formula-loss classification and recovery lifecycle."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db
from curator.pipeline.formula_recovery import (
    classify_formula_loss,
    invalidate_formula_recoveries,
    recover_formula,
)

RELPATH = "04_Resources/formula-recovery.pdf"
RAW_SPAN_TEXT = "Figure 3 contains a Jacobian norm bound."
RAW_SPAN_HASH = hashlib.sha256(RAW_SPAN_TEXT.encode("utf-8")).hexdigest()[:16]


@pytest.fixture()
def vault():
    with tempfile.TemporaryDirectory() as t:
        paths = cfg.WikiPaths(Path(t))
        paths.internal.mkdir(parents=True, exist_ok=True)
        db.init_db(paths.state_db)
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES (?, 'source-hash', 'pdf', 1, '2026-01-01T00:00:00Z')",
                (RELPATH,),
            )
        yield paths


def _seed_uncertain_claim(vault: cfg.WikiPaths) -> tuple[str, str]:
    span_id = db.upsert_source_span(
        vault.state_db,
        source_id=1,
        relpath=RELPATH,
        span_type="equation",
        content_hash=RAW_SPAN_HASH,
        page_number=3,
        text_preview=RAW_SPAN_TEXT,
        metadata={"region": [120, 410, 580, 470]},
    )
    unit_id = db.upsert_knowledge_unit(
        vault.state_db,
        unit_type="equation",
        canonical_name="Jacobian norm bound",
        statement=r"The bound is $\lVert J \rVert \le L^{d}$.",
        source_span_ids=[span_id],
        source_id=1,
    )
    db.set_unit_formula_status(vault.state_db, unit_id, "uncertain")
    return span_id, unit_id


def test_provider_free_classifier_requires_measured_loss_evidence() -> None:
    expected = r"\nabla_W L = \delta x^T"

    assert classify_formula_loss(
        expected,
        parser_text=r"$\nabla_W L = \delta x^T$",
        raw_text=r"$\nabla_W L = \delta x^T$",
        extracted_text=r"$\nabla_W L = \delta x^T$",
    ) is None
    assert classify_formula_loss(
        expected,
        parser_text=r"$W L = \delta x$",
        raw_text=r"$W L = \delta x$",
        extracted_text=r"$W L = \delta x$",
    ) == "fragmented"
    assert classify_formula_loss(
        expected,
        parser_text="",
        raw_text=r"$\nabla_W L = \delta x^T$",
        extracted_text="",
    ) == "parser_omitted"
    assert classify_formula_loss(
        expected,
        parser_text="",
        raw_text="",
        extracted_text="",
        rendered_formula_present=True,
    ) == "image_only"
    assert classify_formula_loss(
        expected,
        parser_text="",
        raw_text="",
        extracted_text="",
    ) is None


def test_below_threshold_recovery_is_additive_and_stays_uncertain(vault) -> None:
    span_id, unit_id = _seed_uncertain_claim(vault)

    result = recover_formula(
        vault.state_db,
        unit_id=unit_id,
        span_id=span_id,
        loss_verdict="image_only",
        locator={"source_id": 1, "page": 3, "region": [120, 410, 580, 470]},
        page_hash="page-v1",
        crop_hash="crop-v1",
        provider="mock",
        model="mock-formula-reader",
        confidence=0.42,
        latex=r"\lVert J \rVert \le L^{d}",
    )

    assert result["status"] == "candidate"
    with db.connect(vault.state_db) as conn:
        span = conn.execute(
            "SELECT content_hash, text_preview, metadata FROM source_spans WHERE id = ?",
            (span_id,),
        ).fetchone()
        unit = conn.execute(
            "SELECT support_status, formula_status FROM knowledge_units WHERE id = ?",
            (unit_id,),
        ).fetchone()
    assert span["content_hash"] == RAW_SPAN_HASH
    assert span["text_preview"] == RAW_SPAN_TEXT
    assert '"formula_recovery"' in span["metadata"]
    assert unit["support_status"] == "unchecked"
    assert unit["formula_status"] == "uncertain"
    assert db.list_claim_supports(vault.state_db, unit_id) == []


def test_reviewed_recovery_revalidates_without_overwriting_raw_span(vault) -> None:
    span_id, unit_id = _seed_uncertain_claim(vault)

    result = recover_formula(
        vault.state_db,
        unit_id=unit_id,
        span_id=span_id,
        loss_verdict="image_only",
        locator={"source_id": 1, "page": 3, "region": [120, 410, 580, 470]},
        page_hash="page-v1",
        crop_hash="crop-v1",
        provider="mock",
        model="mock-formula-reader",
        confidence=0.96,
        latex=r"\lVert J \rVert \le L^{d}",
        validator_trace_id="PTR-reviewed",
        raw_span_texts={span_id: RAW_SPAN_TEXT},
    )

    assert result["status"] == "reviewed"
    with db.connect(vault.state_db) as conn:
        span = conn.execute(
            "SELECT content_hash, text_preview FROM source_spans WHERE id = ?",
            (span_id,),
        ).fetchone()
        unit = conn.execute(
            "SELECT support_status, formula_status FROM knowledge_units WHERE id = ?",
            (unit_id,),
        ).fetchone()
    assert span["content_hash"] == RAW_SPAN_HASH
    assert span["text_preview"] == RAW_SPAN_TEXT
    assert unit["support_status"] == "verified"
    assert unit["formula_status"] == "linked_evidence"
    supports = db.list_claim_supports(vault.state_db, unit_id)
    assert any(
        row["support_role"] == "formula"
        and row["validator_trace_id"] == "PTR-reviewed"
        for row in supports
    )


def test_recovery_rejects_unmeasured_loss_class(vault) -> None:
    span_id, unit_id = _seed_uncertain_claim(vault)

    with pytest.raises(ValueError, match="invalid formula loss verdict"):
        recover_formula(
            vault.state_db,
            unit_id=unit_id,
            span_id=span_id,
            loss_verdict="unknown",
            locator={"source_id": 1, "page": 3},
            page_hash="page-v1",
            crop_hash="crop-v1",
            provider="mock",
            model="mock-formula-reader",
            confidence=0.96,
            latex=r"\lVert J \rVert \le L^{d}",
            validator_trace_id="PTR-reviewed",
        )

    candidate = recover_formula(
        vault.state_db,
        unit_id=unit_id,
        span_id=span_id,
        loss_verdict="image_only",
        locator={"source_id": 1, "page": 3},
        page_hash="page-v1",
        crop_hash="crop-v1",
        provider="mock",
        model="mock-formula-reader",
        confidence=0.96,
        latex=r"\lVert J \rVert \le L^{d}",
        validator_trace_id="PTR-reviewed",
    )
    assert candidate["status"] == "candidate"

    with pytest.raises(ValueError, match="hydrated source span hash mismatch"):
        recover_formula(
            vault.state_db,
            unit_id=unit_id,
            span_id=span_id,
            loss_verdict="image_only",
            locator={"source_id": 1, "page": 3},
            page_hash="page-v1",
            crop_hash="crop-v1",
            provider="mock",
            model="mock-formula-reader",
            confidence=0.96,
            latex=r"\lVert J \rVert \le L^{d}",
            validator_trace_id="PTR-reviewed",
            raw_span_texts={span_id: "not the cited span"},
        )

    db.set_unit_formula_status(vault.state_db, unit_id, "preserved_in_text")
    with pytest.raises(ValueError, match="requires formula_status='uncertain'"):
        recover_formula(
            vault.state_db,
            unit_id=unit_id,
            span_id=span_id,
            loss_verdict="image_only",
            locator={"source_id": 1, "page": 3},
            page_hash="page-v1",
            crop_hash="crop-v1",
            provider="mock",
            model="mock-formula-reader",
            confidence=0.96,
            latex=r"\lVert J \rVert \le L^{d}",
            validator_trace_id="PTR-reviewed",
        )


def test_page_hash_change_invalidates_only_stale_recovery(vault) -> None:
    span_id, unit_id = _seed_uncertain_claim(vault)
    recover_formula(
        vault.state_db,
        unit_id=unit_id,
        span_id=span_id,
        loss_verdict="image_only",
        locator={"source_id": 1, "page": 3, "region": [120, 410, 580, 470]},
        page_hash="page-v1",
        crop_hash="crop-v1",
        provider="mock",
        model="mock-formula-reader",
        confidence=0.96,
        latex=r"\lVert J \rVert \le L^{d}",
        validator_trace_id="PTR-reviewed",
        raw_span_texts={span_id: RAW_SPAN_TEXT},
    )

    assert invalidate_formula_recoveries(
        vault.state_db, span_id=span_id, current_page_hash="page-v1"
    ) == 0
    assert invalidate_formula_recoveries(
        vault.state_db, span_id=span_id, current_page_hash="page-v2"
    ) == 1

    span = db.get_source_spans_by_ids(vault.state_db, [span_id])[0]
    recovery = span["metadata"]["formula_recovery"][0]
    assert recovery["status"] == "rejected"
    assert recovery["rejection_reason"] == "stale_page_hash"
    with db.connect(vault.state_db) as conn:
        unit = conn.execute(
            "SELECT support_status, formula_status FROM knowledge_units WHERE id = ?",
            (unit_id,),
        ).fetchone()
    assert unit["support_status"] == "stale"
    assert unit["formula_status"] == "uncertain"
    assert any(
        row["support_role"] == "formula" and row["support_status"] == "stale"
        for row in db.list_claim_supports(vault.state_db, unit_id)
    )
