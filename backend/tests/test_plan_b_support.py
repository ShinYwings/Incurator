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


def test_formula_tokens_preserve_non_alphabetic_escapes() -> None:
    assert _formula_tokens(r"\{x\}") == (r"\{", "x", r"\}")
    assert _formula_tokens(r"\{x\}") != _formula_tokens(r"{x}")
    assert r"\\" in _formula_tokens(r"a\\b")


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
    assert semantic_hash(r"$\alpha b$") != semantic_hash(r"$\alphab$")
    assert semantic_hash(r"$a$ $b$") != semantic_hash(r"$a b$")
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


def test_textual_failure_preserves_matching_formula_status(vault) -> None:
    span_id = "SPAN-formula-only-support"
    span_text = r"The equation is $x^2$."
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type, "
            "content_hash, text_preview, created_at) "
            "VALUES (?, 1, ?, 'paragraph', 'formula-support-hash', ?, "
            "'2026-01-01T00:00:00Z')",
            (span_id, RELPATH, span_text),
        )
    unit_id = db.upsert_knowledge_unit(
        vault.state_db, unit_type="atom", canonical_name="Hallucinated prose",
        statement=r"Coral bleaching proves symbiotic algae vanish via $x^2$.",
        source_span_ids=[span_id], source_id=1,
    )

    assert validate_claim_support(vault.state_db, unit_id) == "failed"
    with db.connect(vault.state_db) as conn:
        row = conn.execute(
            "SELECT support_status, formula_status FROM knowledge_units WHERE id = ?",
            (unit_id,),
        ).fetchone()
    assert row["support_status"] == "failed"
    assert row["formula_status"] == "preserved_in_text"


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


def test_formula_only_multi_span_assigns_correct_primary(vault) -> None:
    span1 = "SPAN-empty"
    span2 = "SPAN-formula"
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type, "
            "content_hash, text_preview, created_at) "
            "VALUES (?, 1, ?, 'paragraph', 'h1', 'just text', "
            "'2026-01-01T00:00:00Z')",
            (span1, RELPATH),
        )
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type, "
            "content_hash, text_preview, created_at) "
            "VALUES (?, 1, ?, 'paragraph', 'h2', 'here is $x^2$', "
            "'2026-01-01T00:00:00Z')",
            (span2, RELPATH),
        )
    unit_id = db.upsert_knowledge_unit(
        vault.state_db, unit_type="atom", canonical_name="Math",
        statement="$x^2$", source_span_ids=[span1, span2], source_id=1,
    )

    assert validate_claim_support(vault.state_db, unit_id) == "verified"
    rows = {r["support_role"]: r for r in db.list_claim_supports(vault.state_db, unit_id)}
    assert rows["primary"]["source_span_id"] == span2
    assert rows["contextual"]["source_span_id"] == span1


def test_multi_span_text_coverage_is_independent_of_formula_primary(vault) -> None:
    text_span = "SPAN-text-support"
    formula_span = "SPAN-equation-support"
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type, "
            "content_hash, text_preview, created_at) "
            "VALUES (?, 1, ?, 'paragraph', 'text-hash', ?, "
            "'2026-01-01T00:00:00Z')",
            (
                text_span,
                RELPATH,
                "Residual connections ease optimization in deep networks.",
            ),
        )
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type, "
            "content_hash, text_preview, created_at) "
            "VALUES (?, 1, ?, 'equation', 'formula-hash', 'Equation block: $x^2$.', "
            "'2026-01-01T00:00:00Z')",
            (formula_span, RELPATH),
        )
    unit_id = db.upsert_knowledge_unit(
        vault.state_db,
        unit_type="atom",
        canonical_name="Residual optimization",
        statement="Residual connections ease optimization in deep networks with $x^2$.",
        source_span_ids=[text_span, formula_span],
        source_id=1,
    )

    assert validate_claim_support(vault.state_db, unit_id) == "verified"
    rows = {r["support_role"]: r for r in db.list_claim_supports(vault.state_db, unit_id)}
    assert rows["primary"]["source_span_id"] == formula_span
    assert rows["contextual"]["source_span_id"] == text_span


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


def test_ambiguous_text_with_verified_formula_preserves_formula_status(vault) -> None:
    """Regression: the ambiguous-textual-support else branch must set
    formula_status='preserved_in_text' when the formula is structurally verified,
    not unconditional 'not_applicable'."""
    span_id = "SPAN-ambiguous-formula"
    # Span text shares moderate term overlap with the claim (between
    # _SUPPORT_FAIL=0.25 and _SUPPORT_VERIFY=0.5), and contains the exact formula.
    # claim terms: {gradient, descent, regularization, optimization, penalty, deep, architectures, network, training}
    # span terms: {gradient, optimization, configurations, loss, certain}
    # overlap = {gradient, optimization} → 2/9 ≈ 0.22… but we need ≥0.25.
    # Adjusted: add "descent" to span so overlap = {gradient, descent, optimization} → 3/9 ≈ 0.33.
    span_text = "Gradient descent optimization uses $x^2$ in certain loss configurations."
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type, "
            "content_hash, text_preview, created_at) "
            "VALUES (?, 1, ?, 'paragraph', 'ambiguous-hash', ?, "
            "'2026-01-01T00:00:00Z')",
            (span_id, RELPATH, span_text),
        )
    # Statement: formula $x^2$ is present in span, but prose overlap is ambiguous.
    unit_id = db.upsert_knowledge_unit(
        vault.state_db, unit_type="atom", canonical_name="Ambiguous formula",
        statement="Gradient descent regularization applies $x^2$ penalty for deep architectures and network training optimization.",
        source_span_ids=[span_id], source_id=1,
    )

    verdict = validate_claim_support(vault.state_db, unit_id)
    assert verdict == "uncertain"
    with db.connect(vault.state_db) as conn:
        row = conn.execute(
            "SELECT formula_status FROM knowledge_units WHERE id = ?",
            (unit_id,),
        ).fetchone()
    assert row["formula_status"] == "preserved_in_text"


def test_f6_with_absent_formula_fails_and_is_not_routed_to_recovery(vault) -> None:
    """Spec-pin (rejects PM Fix 4): a wrong-real-span citation (low/zero prose
    overlap) MUST be `failed` even when the claim carries a formula that the
    cited span lacks. SYSTEM_BEHAVIOR §26.1 makes the F6 gate release-blocking
    and explicitly forbids routing an F6 textual failure to P5 recovery. The
    formula-uncertain route is reserved for the right-topic case (high prose
    overlap), which is covered by test_altered_formula_on_right_topic_is_uncertain.
    Swapping the verdict branches so formula-uncertain preceded the F6 gate would
    funnel wrong-real-span citations into recovery — the exact defect Plan B
    exists to catch."""
    span_id = "SPAN-wrong-real-span-formula"
    span_text = "The neural network computes weight gradients during backprop."
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type, "
            "content_hash, text_preview, created_at) "
            "VALUES (?, 1, ?, 'paragraph', 'wrong-span-hash', ?, "
            "'2026-01-01T00:00:00Z')",
            (span_id, RELPATH, span_text),
        )
    # Claim is about a different topic (coral) AND carries a formula the span
    # does not contain: both the prose gate and the formula check miss.
    unit_id = db.upsert_knowledge_unit(
        vault.state_db, unit_type="atom", canonical_name="Wrong real span",
        statement=r"Coral bleaching expels symbiotic algae, bounded by $a^2$.",
        source_span_ids=[span_id], source_id=1,
    )

    assert validate_claim_support(vault.state_db, unit_id) == "failed"
    with db.connect(vault.state_db) as conn:
        row = conn.execute(
            "SELECT support_status, formula_status FROM knowledge_units WHERE id = ?",
            (unit_id,),
        ).fetchone()
    assert row["support_status"] == "failed"          # release-blocking, not uncertain
    assert row["formula_status"] == "missing"          # not routed to P5 recovery


def test_revalidation_preserves_formula_support_rows(vault) -> None:
    """Regression: _clear_claim_supports(preserve_formula=True) must retain
    formula-role rows so that recover_formula's evidence links survive
    re-validation via validate_claim_support."""
    span_id = "SPAN-formula-preserve"
    span_text = r"The result is $x^2 + y^2$."
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type, "
            "content_hash, text_preview, created_at) "
            "VALUES (?, 1, ?, 'paragraph', 'formula-preserve-hash', ?, "
            "'2026-01-01T00:00:00Z')",
            (span_id, RELPATH, span_text),
        )
    unit_id = db.upsert_knowledge_unit(
        vault.state_db, unit_type="atom", canonical_name="Formula preserve",
        statement=r"The result is $x^2 + y^2$.",
        source_span_ids=[span_id], source_id=1,
    )

    # First validation creates primary support.
    validate_claim_support(vault.state_db, unit_id)
    # Manually insert a formula-role support to simulate recover_formula's output.
    db.upsert_claim_support(
        vault.state_db,
        knowledge_unit_id=unit_id,
        source_span_id=span_id,
        support_role="formula",
        support_status="verified",
        evidence_hash="formula-preserve-hash",
        validator_trace_id="PTR-test",
    )
    supports_before = db.list_claim_supports(vault.state_db, unit_id)
    assert any(r["support_role"] == "formula" for r in supports_before)

    # Re-validate: formula-role row must survive.
    validate_claim_support(vault.state_db, unit_id)
    supports_after = db.list_claim_supports(vault.state_db, unit_id)
    assert any(
        r["support_role"] == "formula"
        and r["support_status"] == "verified"
        and r["validator_trace_id"] == "PTR-test"
        for r in supports_after
    ), f"formula support lost during revalidation: {supports_after}"



# ---------------------------------------------------------------------------
# P6 — compiler-audit §20.5 assertions (dangling, formula consistency,
# generation invariant) + broad-fallback Plan-C recording, and F7 stale-span
# reconciliation.
# ---------------------------------------------------------------------------

def test_audit_flags_dangling_support_on_missing_span(vault) -> None:
    sup01 = next(c for c in GOLD["support_cases"] if c["id"] == "SUP01")
    unit_id = _seed(vault, sup01["declared"], sup01["statement"])
    validate_claim_support(vault.state_db, unit_id)
    # Remove the cited span out from under the support row (referential break).
    with db.connect(vault.state_db) as conn:
        conn.execute("DELETE FROM source_spans WHERE id = ?", (sup01["declared"][0],))
    report = run_compiler_audit(vault.state_db)
    assert unit_id in report.dangling_supports
    assert unit_id in report.release_blocking
    assert not report.ok


def test_audit_flags_formula_status_inconsistency(vault) -> None:
    # linked_evidence WITHOUT a verified formula support row is inconsistent (§20.5 #5).
    unit_id = _seed(vault, ["SPAN-pb000001"], "Backprop computes the gradient.")
    db.set_unit_formula_status(vault.state_db, unit_id, "linked_evidence")
    report = run_compiler_audit(vault.state_db)
    assert unit_id in report.formula_inconsistencies
    assert unit_id in report.release_blocking


def test_audit_flags_multiple_authoritative_generations(vault) -> None:
    # §20.5 #4: at most one authoritative generation per source scope.
    now = "2026-01-01T00:00:00Z"
    with db.connect(vault.state_db) as conn:
        for gid in ("GEN-aaaa1111", "GEN-bbbb2222"):
            conn.execute(
                "INSERT INTO compiler_generations (id, source_id, status, "
                "prompt_contract_version, created_at, audit_json) "
                "VALUES (?, 1, 'authoritative', 'v2', ?, '{}')",
                (gid, now),
            )
    report = run_compiler_audit(vault.state_db)
    assert "source:1" in report.staged_leftovers
    assert not report.ok


def test_audit_records_synthesis_broad_fallback_for_plan_c(vault) -> None:
    # The synthesis.py:110 broad fallback (community-report-derived) is RECORDED
    # and assigned to Plan C, never removed by Plan B (§20.5 #2; user direction).
    spans = ["SPAN-pb000001", "SPAN-pb000002", "SPAN-pb000003"]
    for sid in spans:
        with db.connect(vault.state_db) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO source_spans (id, source_id, relpath, span_type, "
                "content_hash, text_preview, created_at) VALUES (?, 1, ?, 'paragraph', ?, ?, ?)",
                (sid, RELPATH, sid, SPANS[sid]["content"][:50], "2026-01-01T00:00:00Z"),
            )
    rep_id = db.upsert_community_report(
        vault.state_db, community_key="c1", title="C1", summary="s",
        full_content="s", dependency_hash="d", entity_ids=[],
        source_span_ids=spans, rank=0.5,
    )
    # Synthesis node grounding to the FULL union of its report's spans = the fallback.
    db.upsert_synthesis_node(
        vault.state_db, title="Broad", statement="Everything",
        community_report_ids=[rep_id], source_span_ids=spans,
        dependency_hash="d", confidence=0.5,
    )
    report = run_compiler_audit(vault.state_db)
    flagged = {f["id"]: f for f in report.broad_fallback_plan_c}
    syn_findings = [f for f in report.broad_fallback_plan_c if f["type"] == "synthesis_node"]
    assert syn_findings and all(f["owner"] == "plan_c" for f in syn_findings)
    # Plan-C-assigned findings are NOT release-blocking for Plan B.
    assert not any(fid in report.release_blocking for fid in flagged)


def test_reconcile_removes_stale_spans_of_edited_source(vault) -> None:
    # F7 (§26.4): reconciliation removes the source's stale spans + their
    # derived support/dependency rows, leaving only the current set.
    old_unit = _seed(vault, ["SPAN-pb000001"], "Backprop computes the gradient.")
    validate_claim_support(vault.state_db, old_unit)
    new_span = "SPAN-edited01"
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type, "
            "content_hash, text_preview, created_at) "
            "VALUES (?, 1, ?, 'paragraph', 'edited-hash', 'edited', '2026-01-02T00:00:00Z')",
            (new_span, RELPATH),
        )
    reconcile_source(vault.state_db, source_id=1, current_span_ids=[new_span])
    with db.connect(vault.state_db) as conn:
        remaining = {r[0] for r in conn.execute(
            "SELECT id FROM source_spans WHERE source_id = 1"
        ).fetchall()}
        orphan_supports = conn.execute(
            "SELECT COUNT(*) FROM claim_supports WHERE source_span_id = 'SPAN-pb000001'"
        ).fetchone()[0]
    assert remaining == {new_span}
    assert orphan_supports == 0
