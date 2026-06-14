"""Plan B (Evidence Compiler Integrity, v0.8.0) gold tests and audit oracles.

Two test kinds, mirroring the Failure Atlas convention
(``test_failure_atlas_repro.py``):

- ``test_gold_*`` validate the frozen deterministic fixture
  (``docs/specs/failure_atlas/plan_b_compiler_gold.yml``) for internal
  consistency and conformance to the SCHEMA.md §20 enums. They PASS today —
  they are the labeled ground truth the compiler will be scored against.
- ``test_oracle_*`` assert the desired v0.8.0 contract (SCHEMA §20,
  SYSTEM_BEHAVIOR §26) and are ``xfail(strict=True)``. The schema, support,
  formula, generation, and reconciliation behavior they assert does not exist
  at ``SCHEMA_VERSION = 7``; the tests therefore xfail now "for the intended
  reasons". When P3–P6 implement the additive schema and compiler, each oracle
  XPASSes and fails the suite, forcing a deliberate un-xfail + spec/status
  update in the same change — the same red→green gate Plan B uses to retire the
  F6/F7/F10 atlas oracles.

No not-yet-implemented symbol is imported at module top (collection must never
break); new behavior is probed lazily inside each oracle.

Scenario note (P2): there is no ``complex_math_backprop`` pytest to "rewrite" —
that scenario is absent from ``tests/scenarios/`` (Plan B evidence ledger). The
math-specific deterministic cases live in the gold fixture here; the testbed
scenario rewrite against DB-native L1–L4 + Reference Mode is P7 scope.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from curator import config as cfg
from curator import db

REPO_ROOT = Path(__file__).resolve().parents[2]
ATLAS_DIR = REPO_ROOT / "docs" / "specs" / "failure_atlas"
RELPATH = "04_Resources/pb.md"

# Frozen enums — MUST match SCHEMA.md §20 exactly.
SUPPORT_ROLES = {"primary", "contextual", "formula"}
SUPPORT_STATUSES = {"unchecked", "verified", "failed", "stale"}
FORMULA_STATUSES = {
    "not_applicable", "preserved_in_text", "linked_evidence",
    "omitted_incidental", "missing", "uncertain",
}
LOSS_VERDICTS = {"fragmented", "image_only", "parser_omitted"}
RECOVERY_STATUSES = {"candidate", "reviewed", "rejected"}
GENERATION_STATUSES = {"staged", "authoritative", "discarded"}


def _load_gold() -> dict:
    return yaml.safe_load(
        (ATLAS_DIR / "plan_b_compiler_gold.yml").read_text(encoding="utf-8")
    )


GOLD = _load_gold()
SPANS = {s["id"]: s for s in GOLD["spans"]}


@pytest.fixture()
def vault():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        paths = cfg.WikiPaths(root)
        paths.internal.mkdir(parents=True, exist_ok=True)
        db.init_db(paths.state_db)
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES (?, 'h', 'md', 1, datetime('now'))",
                (RELPATH,),
            )
        yield paths


# ===========================================================================
# Gold-fixture structural validation (PASS today — ground-truth integrity).
# ===========================================================================

def test_gold_version_and_spans_well_formed() -> None:
    assert GOLD["version"] >= 1
    assert len(SPANS) == len(GOLD["spans"]), "duplicate span ids"
    for span in GOLD["spans"]:
        assert span["id"].startswith("SPAN-")
        assert span["content"].strip()
        assert isinstance(span["central"], bool)


def test_gold_long_tail_spans_exceed_preview_and_carry_marker() -> None:
    # F10: a long span must exceed the 200-char preview and expose an end marker
    # so the full-span hydration oracle has a deterministic target.
    long_spans = [s for s in GOLD["spans"] if s.get("long_tail")]
    assert long_spans, "fixture must include at least one long-tail span (F10)"
    for span in long_spans:
        assert len(span["content"]) > 200
    markers = {
        c["expected_full_text_marker"]
        for c in GOLD["formula_cases"]
        if "expected_full_text_marker" in c
    }
    for marker in markers:
        assert any(marker in s["content"] for s in GOLD["spans"]), marker


def test_gold_support_cases_resolve_and_use_frozen_enums() -> None:
    seen = set()
    for case in GOLD["support_cases"]:
        assert case["id"] not in seen, "duplicate support case id"
        seen.add(case["id"])
        assert case["expected_support_status"] in SUPPORT_STATUSES
        assert case["declared"], "every claim must declare its citation surface"
        for span_id in case["declared"]:
            assert span_id in SPANS, f"{case['id']} cites unknown span {span_id}"
        minimal_spans = set()
        for support in case["minimal"]:
            assert support["role"] in SUPPORT_ROLES
            assert support["span"] in SPANS
            minimal_spans.add(support["span"])
        # The minimal subset must be drawn from the declared citation surface.
        assert minimal_spans <= set(case["declared"]), case["id"]
        # Exactly one entailing 'primary' role per verified claim.
        primaries = [s for s in case["minimal"] if s["role"] == "primary"]
        assert len(primaries) == 1, f"{case['id']} needs exactly one primary"


def test_gold_wrong_real_span_case_cites_a_real_but_unrelated_span() -> None:
    # SUP03 is the F6 anti-pattern: a REAL span id that does not entail the claim.
    sup03 = next(c for c in GOLD["support_cases"] if c["id"] == "SUP03")
    assert sup03["expected_support_status"] == "failed"
    assert sup03["declared"] == [SPANS["SPAN-pb000010"]["id"]]
    assert "coral" in SPANS["SPAN-pb000010"]["content"].lower()
    assert "expected_reason_contains" in sup03


def test_gold_contradiction_case_links_a_conflicting_span() -> None:
    sup04 = next(c for c in GOLD["support_cases"] if c["id"] == "SUP04")
    assert sup04.get("expected_contradiction") is True
    assert sup04["contradicts_span"] in SPANS


def test_gold_formula_cases_use_frozen_enums() -> None:
    seen = set()
    for case in GOLD["formula_cases"]:
        assert case["id"] not in seen
        seen.add(case["id"])
        assert case["span"] in SPANS
        if "expected_formula_status" in case:
            assert case["expected_formula_status"] in FORMULA_STATUSES
        if "loss_verdict" in case:
            assert case["loss_verdict"] in LOSS_VERDICTS
        if "recovery" in case:
            assert case["recovery"]["status"] in RECOVERY_STATUSES
            assert 0.0 <= float(case["recovery"]["confidence"]) <= 1.0
        if case.get("expected_formula_status") == "omitted_incidental":
            assert case["expected_reason_code"].startswith("incidental_omission:")


def test_gold_formula_cases_cover_every_loss_verdict() -> None:
    verdicts = {c["loss_verdict"] for c in GOLD["formula_cases"] if "loss_verdict" in c}
    assert verdicts == LOSS_VERDICTS, "fixture must exercise all three loss classes"


def test_gold_reconciliation_and_compile_failure_cases_well_formed() -> None:
    declared_claim_ids = {c["id"] for c in GOLD["support_cases"]}
    for case in GOLD["reconciliation_cases"]:
        assert case["mutation"] in {"none", "edit", "delete", "split"}
        for claim_id in case["claims"]:
            assert claim_id in declared_claim_ids, f"{case['id']} → unknown {claim_id}"
        for closure_id in case.get("expected_changed_closure", []):
            assert closure_id in declared_claim_ids
        for retired_id in case.get("expected_retired", []):
            assert retired_id in declared_claim_ids
    for case in GOLD["compile_failure_cases"]:
        assert case["expected_generation_status"] in GENERATION_STATUSES
        assert case["expected_partial_publish"] is False


def test_gold_unchanged_rebuild_case_expects_zero_regeneration() -> None:
    rec01 = next(c for c in GOLD["reconciliation_cases"] if c["id"] == "REC01")
    assert rec01["mutation"] == "none"
    assert rec01["expected_changed_closure"] == []


# ===========================================================================
# v8 schema regression (the additive migration shipped at P3 — these flipped
# from xfail oracles to live green tests, SCHEMA §20.1-§20.3 / §20.6). Names are
# frozen by SCHEMA §20.
# ===========================================================================

def test_schema_version_is_stamped(vault) -> None:
    # The connect/init path stamps the current SCHEMA_VERSION (bumped 8 -> 9 by
    # Plan C's additive migration; asserting the code constant keeps this robust
    # across future additive bumps).
    with db.connect(vault.state_db) as conn:
        version = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()[0]
    assert version == db.SCHEMA_VERSION


def test_v8_claim_supports_table_and_columns(vault) -> None:
    with db.connect(vault.state_db) as conn:
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(claim_supports)").fetchall()
        }
    assert {
        "knowledge_unit_id", "source_span_id", "support_role", "support_status",
        "support_reason", "evidence_hash", "validator_trace_id",
        "created_at", "updated_at",
    } <= cols


def test_v8_compiler_generations_table_and_columns(vault) -> None:
    with db.connect(vault.state_db) as conn:
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(compiler_generations)").fetchall()
        }
    assert {
        "id", "source_id", "status", "prompt_contract_version",
        "created_at", "published_at", "discarded_at", "audit_json",
    } <= cols


def test_v8_knowledge_units_has_additive_columns(vault) -> None:
    with db.connect(vault.state_db) as conn:
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(knowledge_units)").fetchall()
        }
    assert {
        "semantic_hash", "support_status", "support_reason",
        "formula_status", "retired_at", "generation_id",
    } <= cols


def test_v8_migration_backfills_units_as_unchecked(vault) -> None:
    # A unit created on a migrated DB must read the conservative backfill state:
    # nothing is silently verified.
    unit_id = db.upsert_knowledge_unit(
        vault.state_db, unit_type="atom", canonical_name="Backprop gradient",
        statement=GOLD["support_cases"][0]["statement"],
        source_span_ids=["SPAN-pb000001"], source_id=1,
    )
    with db.connect(vault.state_db) as conn:
        row = conn.execute(
            "SELECT support_status, formula_status, retired_at, generation_id "
            "FROM knowledge_units WHERE id = ?",
            (unit_id,),
        ).fetchone()
    assert row["support_status"] == "unchecked"
    assert row["formula_status"] == "not_applicable"
    assert row["retired_at"] is None
    assert row["generation_id"] is None


# ===========================================================================
# Behavior oracles (xfail strict). These assert observable DB / audit outcomes
# of the SUP/FRM/REC/CMP gold cases through whatever Plan B API P3–P6 lands;
# the helper resolves the first present candidate name so the oracle can XPASS
# without this file pre-guessing the exact internal symbol.
# ===========================================================================

def _resolve(*candidates: str):
    """Return the first present Plan B entry point, else None (→ oracle xfails).

    Searched modules are the ones SYSTEM_BEHAVIOR §26 implicates: db and the
    compile pipeline. P3–P6 must point the matching oracle at the real symbol
    when turning it green.
    """
    from curator.pipeline import compile as compile_mod
    for name in candidates:
        for module in (db, compile_mod):
            fn = getattr(module, name, None)
            if fn is not None:
                return fn
    return None


def _seed_gold_claim(paths: cfg.WikiPaths, case_id: str) -> tuple[str, dict]:
    """Store a gold support case's declared spans + unit, returning its id."""
    case = next(c for c in GOLD["support_cases"] if c["id"] == case_id)
    for span_id in case["declared"]:
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO source_spans "
                "(id, source_id, relpath, span_type, content_hash, text_preview, "
                " created_at) VALUES (?, 1, ?, ?, ?, ?, datetime('now'))",
                (span_id, RELPATH, SPANS[span_id]["span_type"], span_id,
                 SPANS[span_id]["content"][:200]),
            )
    unit_id = db.upsert_knowledge_unit(
        paths.state_db, unit_type="atom", canonical_name=case_id,
        statement=case["statement"], source_span_ids=list(case["declared"]),
        source_id=1,
    )
    return unit_id, case


def test_minimal_support_yields_verified_primary_row(vault) -> None:
    unit_id, _ = _seed_gold_claim(vault, "SUP01")
    validate = _resolve("validate_claim_support", "validate_support", "compile_claim_support")
    assert validate is not None, "support validation API not implemented"
    validate(vault.state_db, unit_id)
    with db.connect(vault.state_db) as conn:
        rows = conn.execute(
            "SELECT support_role, support_status FROM claim_supports "
            "WHERE knowledge_unit_id = ?",
            (unit_id,),
        ).fetchall()
        unit_status = conn.execute(
            "SELECT support_status FROM knowledge_units WHERE id = ?", (unit_id,)
        ).fetchone()[0]
    assert any(r["support_role"] == "primary" and r["support_status"] == "verified"
               for r in rows)
    assert unit_status == "verified"


def test_wrong_real_span_marked_failed(vault) -> None:
    unit_id, case = _seed_gold_claim(vault, "SUP03")
    validate = _resolve("validate_claim_support", "validate_support", "compile_claim_support")
    assert validate is not None, "support validation API not implemented"
    validate(vault.state_db, unit_id)
    with db.connect(vault.state_db) as conn:
        row = conn.execute(
            "SELECT support_status, support_reason FROM knowledge_units WHERE id = ?",
            (unit_id,),
        ).fetchone()
    assert row["support_status"] == "failed"
    assert case["expected_reason_contains"] in (row["support_reason"] or "")


def test_edited_span_marks_support_stale(vault) -> None:
    unit_id, _ = _seed_gold_claim(vault, "SUP01")
    validate = _resolve("validate_claim_support", "validate_support", "compile_claim_support")
    audit = _resolve("compiler_audit", "run_compiler_audit", "audit_claim_supports")
    assert validate is not None and audit is not None, "support/audit API not implemented"
    validate(vault.state_db, unit_id)
    # Mutate the cited span's content hash → freshness re-check must mark stale.
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "UPDATE source_spans SET content_hash = 'edited-hash' WHERE id = ?",
            ("SPAN-pb000001",),
        )
    audit(vault.state_db)
    with db.connect(vault.state_db) as conn:
        status = conn.execute(
            "SELECT support_status FROM knowledge_units WHERE id = ?", (unit_id,)
        ).fetchone()[0]
    assert status == "stale"


def test_oracle_central_formula_preserved_in_text(vault) -> None:
    frm01 = next(c for c in GOLD["formula_cases"] if c["id"] == "FRM01")
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type, "
            "content_hash, text_preview, created_at) "
            "VALUES (?, 1, ?, 'equation', ?, ?, datetime('now'))",
            (frm01["span"], RELPATH, frm01["span"], SPANS[frm01["span"]]["content"][:200]),
        )
    unit_id = db.upsert_knowledge_unit(
        vault.state_db, unit_type="atom", canonical_name="FRM01",
        statement=frm01["statement"], source_span_ids=[frm01["span"]], source_id=1,
    )
    validate = _resolve("validate_claim_support", "validate_support", "compile_claim_support")
    assert validate is not None, "support validation API not implemented"
    validate(vault.state_db, unit_id)
    with db.connect(vault.state_db) as conn:
        status = conn.execute(
            "SELECT formula_status FROM knowledge_units WHERE id = ?", (unit_id,)
        ).fetchone()[0]
    assert status == frm01["expected_formula_status"]  # preserved_in_text


def test_oracle_below_threshold_recovery_stays_uncertain(vault) -> None:
    frm05 = next(c for c in GOLD["formula_cases"] if c["id"] == "FRM05")
    classify = _resolve("classify_formula_loss", "loss_verdict", "classify_loss")
    recover = _resolve("recover_formula", "run_formula_recovery")
    assert classify is not None and recover is not None, "recovery API not implemented"
    span_id = db.upsert_source_span(
        vault.state_db,
        source_id=1,
        relpath=RELPATH,
        span_type="equation",
        content_hash="frm05-span-hash",
        page_number=3,
        text_preview="Figure 3 contains a Jacobian norm bound.",
    )
    unit_id = db.upsert_knowledge_unit(
        vault.state_db,
        unit_type="equation",
        canonical_name="FRM05",
        statement=r"The bound is $\lVert J \rVert \le L^{d}$.",
        source_span_ids=[span_id],
        source_id=1,
    )
    db.set_unit_formula_status(vault.state_db, unit_id, "uncertain")

    candidate = recover(
        vault.state_db,
        unit_id=unit_id,
        span_id=span_id,
        loss_verdict=frm05["loss_verdict"],
        locator={"source_id": 1, "page": 3, "region": "eq-2"},
        page_hash="page-v1",
        crop_hash="crop-v1",
        provider="mock",
        model="mock-formula-reader",
        confidence=float(frm05["recovery"]["confidence"]),
        latex=frm05["recovery"]["latex"],
    )

    assert candidate["status"] == frm05["expected_recovery_status"]
    with db.connect(vault.state_db) as conn:
        status = conn.execute(
            "SELECT formula_status FROM knowledge_units WHERE id = ?", (unit_id,)
        ).fetchone()[0]
    assert status == frm05["expected_formula_status"]
    assert not any(
        row["support_role"] == "formula"
        for row in db.list_claim_supports(vault.state_db, unit_id)
    )


def test_oracle_long_formula_tail_is_fully_retrievable(vault) -> None:
    # F10 (SEARCH_ENGINE §10.2): full span text is hydrated from the registered
    # source file, not the stored 200-char preview. Materialize the source and
    # store the span through the deterministic L1 path so its content_hash is the
    # parse-derived hash hydration verifies against.
    from curator.pipeline import source_spans as l1_spans

    frm08 = next(c for c in GOLD["formula_cases"] if c["id"] == "FRM08")
    content = SPANS[frm08["span"]]["content"]
    src = vault.root / RELPATH
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(content, encoding="utf-8")
    sections = [{"id": "s1", "title": "Proof", "page": None, "text": content}]
    span_ids = l1_spans.store_source_spans(
        vault.state_db, 1, RELPATH, l1_spans.spans_from_sections(sections)
    )
    assert len(span_ids) == 1
    # The stored preview must NOT already contain the tail — proves hydration is real.
    with db.connect(vault.state_db) as conn:
        preview = conn.execute(
            "SELECT text_preview FROM source_spans WHERE id = ?", (span_ids[0],)
        ).fetchone()[0]
    assert frm08["expected_full_text_marker"] not in preview

    hydrate = _resolve("hydrate_span_text", "get_full_span_text", "full_span_text")
    assert hydrate is not None, "full-span hydration API not implemented"
    text = hydrate(vault.state_db, span_ids[0])
    assert frm08["expected_full_text_marker"] in text


def test_hydration_unavailable_raises_and_never_substitutes_preview(vault) -> None:
    # F10 / §10.2: an unreadable source or content-hash drift is surfaced as
    # SpanTextUnavailable, never silently downgraded to the 200-char preview.
    from curator.pipeline import compile as compile_mod
    from curator.pipeline import source_spans as l1_spans

    content = SPANS["SPAN-pb000009"]["content"]
    src = vault.root / RELPATH
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(content, encoding="utf-8")
    span_ids = l1_spans.store_source_spans(
        vault.state_db, 1, RELPATH,
        l1_spans.spans_from_sections([{"id": "s1", "title": "P", "page": None, "text": content}]),
    )
    # 1) content-hash drift: source edited so no current span matches the stored hash.
    src.write_text("A completely different paragraph with no overlap whatsoever.", "utf-8")
    with pytest.raises(compile_mod.SpanTextUnavailable):
        compile_mod.hydrate_span_text(vault.state_db, span_ids[0])
    # 2) unreadable source: file removed entirely.
    src.unlink()
    with pytest.raises(compile_mod.SpanTextUnavailable):
        compile_mod.hydrate_span_text(vault.state_db, span_ids[0])
    # Batch hydration omits unavailable spans (caller flags them stale).
    assert compile_mod.hydrate_spans(vault.state_db, span_ids) == {}


def test_oracle_unchanged_rebuild_is_idempotent(vault) -> None:
    unit_id, _ = _seed_gold_claim(vault, "SUP01")
    recompile = _resolve("recompile_source", "compile_source_generation", "rebuild_source")
    assert recompile is not None, "generation-aware recompile API not implemented"
    before = recompile(vault.state_db, source_id=1)
    after = recompile(vault.state_db, source_id=1)
    # Unchanged source + same prompt contract → identical authoritative ids/counts.
    assert before == after
    with db.connect(vault.state_db) as conn:
        unit_count = conn.execute(
            "SELECT COUNT(*) FROM knowledge_units WHERE source_id = 1"
        ).fetchone()[0]
    assert unit_count == 1  # no duplicate accumulation / count amplification


def test_oracle_failed_compile_leaves_no_partial_publish(vault) -> None:
    compile_gen = _resolve("compile_source_generation", "recompile_source")
    assert compile_gen is not None, "staged-generation compile API not implemented"
    with pytest.raises(Exception):
        compile_gen(vault.state_db, source_id=1, _inject_failure="extraction_provider_error")
    with db.connect(vault.state_db) as conn:
        authoritative = conn.execute(
            "SELECT COUNT(*) FROM compiler_generations WHERE status = 'authoritative'"
        ).fetchone()[0]
    assert authoritative == 0  # nothing published


def test_source_delete_retires_dependent_claim(vault) -> None:
    rec03 = next(c for c in GOLD["reconciliation_cases"] if c["id"] == "REC03")
    unit_id, _ = _seed_gold_claim(vault, rec03["claims"][0])
    reconcile = _resolve("reconcile_source", "reconcile_source_change", "invalidate_closure")
    assert reconcile is not None, "reconciliation API not implemented"
    with db.connect(vault.state_db) as conn:
        conn.execute("DELETE FROM source_spans WHERE id = ?", (rec03["deleted_span"],))
    reconcile(vault.state_db, source_id=1)
    with db.connect(vault.state_db) as conn:
        retired_at = conn.execute(
            "SELECT retired_at FROM knowledge_units WHERE id = ?", (unit_id,)
        ).fetchone()[0]
    assert retired_at is not None  # retired, never silently deleted


# ===========================================================================
# Compiler-audit oracle — the read-only traversal of active L2–L4 claims to
# exact support (SCHEMA §20.5, SYSTEM_BEHAVIOR §26.5). This is the central P2
# "failing compiler-audit test": it must report the planted wrong-real-span
# claim (SUP03) as an unsupported finding.
# ===========================================================================

def test_compiler_audit_flags_unsupported_active_claim(vault) -> None:
    # Plant the F6 anti-pattern: an active claim citing a real-but-unrelated span.
    unit_id, _ = _seed_gold_claim(vault, "SUP03")
    audit = _resolve("compiler_audit", "run_compiler_audit", "audit_compiler_integrity")
    assert audit is not None, "compiler audit API not implemented"
    report = audit(vault.state_db)
    # The audit surfaces unsupported/failed claims by id; SUP03 must appear.
    flagged = getattr(report, "unsupported_claims", None)
    if flagged is None and isinstance(report, dict):
        flagged = report.get("unsupported_claims")
    assert flagged, "audit reported no unsupported claims"
    assert unit_id in set(flagged)


def test_oracle_wiki_lint_has_compiler_integrity_section(vault) -> None:
    from curator import lint as lint_mod
    report_fn = _resolve("compiler_integrity_report", "audit_compiler_integrity")
    has_section = hasattr(lint_mod, "compiler_integrity") or report_fn is not None
    assert has_section, "wiki lint Compiler Integrity surface not implemented"
