"""Plan B (v0.8.0) P4 — deterministic claim-support validator, audit, reconcile.

Exercises the SYSTEM_BEHAVIOR §26.1 structural gate directly (the gold fixtures
in plan_b_compiler.py are the release oracle; this is the fine-grained unit
coverage), including ordered formula-token matching that preserves operation
direction and binding.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from curator import config as cfg
from curator import db
from curator.pipeline.claim_support import (
    _content_terms,
    _extract_latex,
    _formula_tokens,
    _is_formula_subsequence,
    normalize_claim,
    reconcile_source,
    run_compiler_audit,
    semantic_hash,
    validate_claim_support,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ATLAS_DIR = REPO_ROOT / "docs" / "specs" / "failure_atlas"
RELPATH = "04_Resources/pb.md"

GOLD = yaml.safe_load((ATLAS_DIR / "plan_b_compiler_gold.yml").read_text(encoding="utf-8"))
SPANS = {s["id"]: s for s in GOLD["spans"]}


@pytest.fixture()
def vault():
    with tempfile.TemporaryDirectory() as t:
        paths = cfg.WikiPaths(Path(t))
        paths.internal.mkdir(parents=True, exist_ok=True)
        db.init_db(paths.state_db)
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES (?, 'h', 'md', 1, '2026-01-01T00:00:00Z')",
                (RELPATH,),
            )
        yield paths


def _seed(paths: cfg.WikiPaths, span_ids: list[str], statement: str) -> str:
    """Insert the named gold spans (full content as both preview and hash) and a
    unit citing them. Returns the unit id."""
    for sid in span_ids:
        content = SPANS[sid]["content"]
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO source_spans (id, source_id, relpath, span_type, "
                "content_hash, text_preview, created_at) "
                "VALUES (?, 1, ?, ?, ?, ?, '2026-01-01T00:00:00Z')",
                (sid, RELPATH, SPANS[sid]["span_type"], f"hash-{sid}", content),
            )
    return db.upsert_knowledge_unit(
        paths.state_db, unit_type="atom", canonical_name="C", statement=statement,
        source_span_ids=span_ids, source_id=1,
    )


# ---------------------------------------------------------------------------
# Ordered formula tokens (the math-integrity core).
# ---------------------------------------------------------------------------

def test_formula_tokens_preserve_operation_direction_and_binding() -> None:
    assert _formula_tokens("a^b") != _formula_tokens("b^a")
    assert _formula_tokens("a - b") != _formula_tokens("b - a")
    assert _formula_tokens(r"\frac{a}{b}") != _formula_tokens(r"\frac{b}{a}")
    assert _formula_tokens("a^2 + b^2 = c^2") != \
        _formula_tokens("c^2 = a^2 + b^2")


def test_formula_tokens_normalize_spacing_but_preserve_grouping() -> None:
    assert _formula_tokens(r"\nabla_W L = \delta\, x^{T}") == \
        _formula_tokens(r"\nabla_W  L=\delta x^{T}")
    assert _formula_tokens(r"x^{ab}") != _formula_tokens(r"x^a b")


def test_formula_subsequence_requires_contiguous_ordered_tokens() -> None:
    span = _formula_tokens(r"M = \int \rho dV")
    assert _is_formula_subsequence(_formula_tokens("M"), span)
    assert not _is_formula_subsequence(_formula_tokens(r"\rho M"), span)


def test_extract_latex_ignores_escaped_dollars() -> None:
    assert _extract_latex(r"Price is \$10 only.") == []
    assert _extract_latex(r"Price is \$10, and $x=5$.") == ["x=5"]


def test_content_terms_strip_latex_and_stopwords() -> None:
    terms = _content_terms(r"The gradient $\nabla_W L = \delta x^T$ descends quickly.")
    assert "gradient" in terms and "descends" in terms
    assert "the" not in terms          # stopword
    assert "nabla" not in terms        # inside the stripped LaTeX region


def test_semantic_hash_is_deterministic_and_discriminating() -> None:
    a = "Backpropagation computes the weight gradient."
    assert semantic_hash(a) == semantic_hash(a)
    assert semantic_hash(a) == semantic_hash("backpropagation   computes the WEIGHT gradient.")
    assert semantic_hash(a) != semantic_hash("Coral bleaching expels symbiotic algae.")
    assert "terms:" in normalize_claim(a)


# ---------------------------------------------------------------------------
# Structural verdicts on the gold cases.
# ---------------------------------------------------------------------------

def test_verified_single_span_writes_primary_row(vault) -> None:
    sup01 = next(c for c in GOLD["support_cases"] if c["id"] == "SUP01")
    unit_id = _seed(vault, sup01["declared"], sup01["statement"])
    assert validate_claim_support(vault.state_db, unit_id) == "verified"
    rows = db.list_claim_supports(vault.state_db, unit_id)
    assert any(r["support_role"] == "primary" and r["support_status"] == "verified"
               for r in rows)
    with db.connect(vault.state_db) as conn:
        row = conn.execute(
            "SELECT support_status, semantic_hash FROM knowledge_units WHERE id = ?",
            (unit_id,),
        ).fetchone()
    assert row["support_status"] == "verified"
    assert row["semantic_hash"]  # set during validation


def test_failed_wrong_real_span(vault) -> None:
    sup03 = next(c for c in GOLD["support_cases"] if c["id"] == "SUP03")
    unit_id = _seed(vault, sup03["declared"], sup03["statement"])
    assert validate_claim_support(vault.state_db, unit_id) == "failed"
    with db.connect(vault.state_db) as conn:
        row = conn.execute(
            "SELECT support_status, support_reason FROM knowledge_units WHERE id = ?",
            (unit_id,),
        ).fetchone()
    assert row["support_status"] == "failed"
    assert "does not minimally support" in row["support_reason"]


def test_revalidation_replaces_previous_support_rows(vault) -> None:
    sup01 = next(c for c in GOLD["support_cases"] if c["id"] == "SUP01")
    unit_id = _seed(vault, sup01["declared"], sup01["statement"])
    validate_claim_support(vault.state_db, unit_id)

    with db.connect(vault.state_db) as conn:
        conn.execute(
            "UPDATE knowledge_units SET statement = ? WHERE id = ?",
            ("Coral bleaching expels symbiotic algae.", unit_id),
        )
    assert validate_claim_support(vault.state_db, unit_id) == "failed"
    rows = db.list_claim_supports(vault.state_db, unit_id)
    assert rows
    assert all(row["support_status"] == "failed" for row in rows)


def test_multi_span_primary_on_best_supporting_span(vault) -> None:
    sup02 = next(c for c in GOLD["support_cases"] if c["id"] == "SUP02")
    unit_id = _seed(vault, sup02["declared"], sup02["statement"])
    assert validate_claim_support(vault.state_db, unit_id) == "verified"
    rows = {r["support_role"]: r for r in db.list_claim_supports(vault.state_db, unit_id)}
    # The update-rule span (SPAN-pb000002) is the primary; the chain-rule span is contextual.
    assert rows["primary"]["source_span_id"] == "SPAN-pb000002"
    assert rows["contextual"]["source_span_id"] == "SPAN-pb000001"


def test_formula_preserved_in_text_verified(vault) -> None:
    frm01 = next(c for c in GOLD["formula_cases"] if c["id"] == "FRM01")
    unit_id = _seed(vault, [frm01["span"]], frm01["statement"])
    assert validate_claim_support(vault.state_db, unit_id) == "verified"
    with db.connect(vault.state_db) as conn:
        fstatus = conn.execute(
            "SELECT formula_status FROM knowledge_units WHERE id = ?", (unit_id,)
        ).fetchone()[0]
    assert fstatus == "preserved_in_text"


def test_altered_formula_on_right_topic_is_uncertain(vault) -> None:
    # Right topic (term overlap high) but the cited span's formula differs from
    # the claim's: route to P5, never a silent verify (and never a wrong verify).
    unit_id = _seed(
        vault, ["SPAN-pb000001"],
        r"The weight gradient is $\nabla_W L = \delta\, y^{T}$.",  # y, not x
    )
    assert validate_claim_support(vault.state_db, unit_id) == "uncertain"
    with db.connect(vault.state_db) as conn:
        row = conn.execute(
            "SELECT support_status, formula_status FROM knowledge_units WHERE id = ?",
            (unit_id,),
        ).fetchone()
    assert row["support_status"] == "unchecked"   # not promoted
    assert row["formula_status"] == "uncertain"   # routed to P5 recovery


def test_valid_subformula_on_right_topic_is_verified(vault) -> None:
    span_id = "SPAN-subformula"
    span_text = r"The mass is $M = \int \rho dV$."
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type, "
            "content_hash, text_preview, created_at) "
            "VALUES (?, 1, ?, 'paragraph', 'subformula-hash', ?, '2026-01-01T00:00:00Z')",
            (span_id, RELPATH, span_text),
        )
    unit_id = db.upsert_knowledge_unit(
        vault.state_db, unit_type="atom", canonical_name="Mass",
        statement="$M$", source_span_ids=[span_id], source_id=1,
    )
    assert validate_claim_support(vault.state_db, unit_id) == "verified"


def test_formula_only_parse_loss_routes_to_uncertain(vault) -> None:
    span_id = "SPAN-formula-loss"
    span_text = "The PDF parser omitted the equation from this region."
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type, "
            "content_hash, text_preview, created_at) "
            "VALUES (?, 1, ?, 'paragraph', 'formula-loss-hash', ?, '2026-01-01T00:00:00Z')",
            (span_id, RELPATH, span_text),
        )
    unit_id = db.upsert_knowledge_unit(
        vault.state_db, unit_type="equation", canonical_name="Lost formula",
        statement=r"$\lVert J \rVert \le L^{d}$", source_span_ids=[span_id],
        source_id=1,
    )

    assert validate_claim_support(vault.state_db, unit_id) == "uncertain"
    with db.connect(vault.state_db) as conn:
        row = conn.execute(
            "SELECT support_status, formula_status FROM knowledge_units WHERE id = ?",
            (unit_id,),
        ).fetchone()
    assert row["support_status"] == "unchecked"
    assert row["formula_status"] == "uncertain"


def test_claim_without_salient_text_or_formula_fails(vault) -> None:
    span_id = "SPAN-garbage"
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type, "
            "content_hash, text_preview, created_at) "
            "VALUES (?, 1, ?, 'paragraph', 'garbage-hash', 'source text', "
            "'2026-01-01T00:00:00Z')",
            (span_id, RELPATH),
        )
    unit_id = db.upsert_knowledge_unit(
        vault.state_db, unit_type="atom", canonical_name="Garbage",
        statement="the and of", source_span_ids=[span_id], source_id=1,
    )

    assert validate_claim_support(vault.state_db, unit_id) == "failed"


# ---------------------------------------------------------------------------
# Audit + reconciliation.
# ---------------------------------------------------------------------------

def test_audit_flags_unverified_and_clears_when_verified(vault) -> None:
    sup01 = next(c for c in GOLD["support_cases"] if c["id"] == "SUP01")
    unit_id = _seed(vault, sup01["declared"], sup01["statement"])
    # Unvalidated unit is unchecked → flagged unsupported.
    report = run_compiler_audit(vault.state_db)
    assert unit_id in report.unsupported_claims
    assert not report.ok
    # After validation it verifies → no longer flagged.
    validate_claim_support(vault.state_db, unit_id)
    report2 = run_compiler_audit(vault.state_db)
    assert unit_id not in report2.unsupported_claims


def test_audit_marks_stale_on_evidence_hash_drift(vault) -> None:
    sup01 = next(c for c in GOLD["support_cases"] if c["id"] == "SUP01")
    unit_id = _seed(vault, sup01["declared"], sup01["statement"])
    validate_claim_support(vault.state_db, unit_id)
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "UPDATE source_spans SET content_hash = 'drifted' WHERE id = ?",
            (sup01["declared"][0],),
        )
    report = run_compiler_audit(vault.state_db)
    assert unit_id in report.stale_claims
    with db.connect(vault.state_db) as conn:
        assert conn.execute(
            "SELECT support_status FROM knowledge_units WHERE id = ?", (unit_id,)
        ).fetchone()[0] == "stale"


def test_reconcile_retires_on_deleted_span_only(vault) -> None:
    sup02 = next(c for c in GOLD["support_cases"] if c["id"] == "SUP02")
    multi = _seed(vault, sup02["declared"], sup02["statement"])     # cites 001 + 002
    sup01 = next(c for c in GOLD["support_cases"] if c["id"] == "SUP01")
    single = _seed(vault, sup01["declared"], sup01["statement"])    # cites 001 only

    with db.connect(vault.state_db) as conn:
        conn.execute("DELETE FROM source_spans WHERE id = 'SPAN-pb000002'")
    retired = reconcile_source(vault.state_db, source_id=1)

    assert multi in retired           # lost a cited span → retired
    assert single not in retired      # its only span (001) survives → untouched
    with db.connect(vault.state_db) as conn:
        assert conn.execute(
            "SELECT retired_at FROM knowledge_units WHERE id = ?", (multi,)
        ).fetchone()[0] is not None
        assert conn.execute(
            "SELECT retired_at FROM knowledge_units WHERE id = ?", (single,)
        ).fetchone()[0] is None


def test_reconcile_noop_when_unchanged(vault) -> None:
    sup01 = next(c for c in GOLD["support_cases"] if c["id"] == "SUP01")
    unit_id = _seed(vault, sup01["declared"], sup01["statement"])
    assert reconcile_source(vault.state_db, source_id=1) == []
    with db.connect(vault.state_db) as conn:
        assert conn.execute(
            "SELECT retired_at FROM knowledge_units WHERE id = ?", (unit_id,)
        ).fetchone()[0] is None


def test_reconcile_split_reuses_semantically_identical_verified_claim(vault) -> None:
    statement = "Backpropagation computes the weight gradient."
    candidate_statement = "Backpropagation   computes the weight gradient."
    old_id = _seed(vault, ["SPAN-pb000001"], statement)
    validate_claim_support(vault.state_db, old_id)

    new_span = "SPAN-split0001"
    content = SPANS["SPAN-pb000001"]["content"]
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type, "
            "content_hash, text_preview, created_at) "
            "VALUES (?, 1, ?, 'paragraph', 'split-hash', ?, '2026-01-02T00:00:00Z')",
            (new_span, RELPATH, content),
        )
    candidate_id = db.upsert_knowledge_unit(
        vault.state_db, unit_type="atom", canonical_name="C2",
        statement=candidate_statement,
        source_span_ids=[new_span], source_id=1,
    )
    validate_claim_support(
        vault.state_db, candidate_id, span_texts={new_span: content}
    )

    retired = reconcile_source(
        vault.state_db,
        source_id=1,
        current_span_ids=[new_span],
        candidate_unit_ids=[candidate_id],
    )

    assert candidate_id in retired
    with db.connect(vault.state_db) as conn:
        old = conn.execute(
            "SELECT source_span_ids, support_status, retired_at "
            "FROM knowledge_units WHERE id = ?",
            (old_id,),
        ).fetchone()
        candidate_retired = conn.execute(
            "SELECT retired_at FROM knowledge_units WHERE id = ?",
            (candidate_id,),
        ).fetchone()[0]
    assert old["source_span_ids"] == f'["{new_span}"]'
    assert old["support_status"] == "verified"
    assert old["retired_at"] is None
    assert candidate_retired is not None
    assert any(
        row["source_span_id"] == new_span and row["support_status"] == "verified"
        for row in db.list_claim_supports(vault.state_db, old_id)
    )


def test_reconcile_does_not_reuse_id_for_reversed_directionality(vault) -> None:
    old_statement = "Alpha causes beta."
    candidate_statement = "Beta causes alpha."
    old_id = _seed(vault, ["SPAN-pb000001"], old_statement)

    new_span = "SPAN-direction"
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type, "
            "content_hash, text_preview, created_at) "
            "VALUES (?, 1, ?, 'paragraph', 'direction-hash', ?, '2026-01-02T00:00:00Z')",
            (new_span, RELPATH, candidate_statement),
        )
    candidate_id = db.upsert_knowledge_unit(
        vault.state_db, unit_type="atom", canonical_name="Direction",
        statement=candidate_statement, source_span_ids=[new_span], source_id=1,
    )
    validate_claim_support(
        vault.state_db, candidate_id, span_texts={new_span: candidate_statement}
    )

    assert semantic_hash(old_statement) == semantic_hash(candidate_statement)
    retired = reconcile_source(
        vault.state_db, source_id=1, current_span_ids=[new_span],
        candidate_unit_ids=[candidate_id],
    )

    assert old_id in retired
    assert candidate_id not in retired
    with db.connect(vault.state_db) as conn:
        assert conn.execute(
            "SELECT retired_at FROM knowledge_units WHERE id = ?", (old_id,)
        ).fetchone()[0] is not None
        assert conn.execute(
            "SELECT retired_at FROM knowledge_units WHERE id = ?", (candidate_id,)
        ).fetchone()[0] is None
