# Cross-Agent Relay State

## Goal

Execute Batch 2: Plan B (Math Extraction Distillation) — Evidence Compiler
Integrity release (target v0.8.0).

## Plan Reference

- Master plan: `.agents/plans/B_math_extraction_distillation.md`
- Coding-time evidence ledger: `.agents/plans/B_roadmap_evidence.md`
- Previous plan: Plan D2 (PR #28, v0.7.0) is merged.

## Analysis And Reasoning

- Branch `feature/plan-b-math-distillation` is based on merged Program 1
  `master` (`5a3932c`) plus PM workflow chore commits.
- P0 (Program Setup And Measured Baseline) is COMPLETE: all five Program 1
  failure-atlas suites pass at the rollback anchor (135 passed, 10 xfailed —
  the strict-xfail oracles). Every P0 concern is reproduced, accepted, or
  scheduled in the ledger's failure-boundary table; none disproven. Active
  testbed scenario confirmed as `gaussian_splatting`; testbed DB backed up to
  `.agents/backups/b-pre-implementation-state.sqlite` and restoration
  verified.
- P1 (Docs-First Contract And Migration Specification) is COMPLETE: SCHEMA.md
  §20 (claim_supports, compiler_generations/GEN-, knowledge_units additive
  columns, formula_recovery metadata, audit assertions, v8 migration),
  SYSTEM_BEHAVIOR.md §26 (support/formula/generation/reconciliation/audit
  behavior + migration rehearsal and rollback acceptance criteria),
  SEARCH_ENGINE_SCHEMA.md §10 (generation-aware publish, F10 full-span
  hydration), PLUGIN_SCHEMA.md no-change note, and all four guide pairs
  (EN → KR). Spec titles stay at v0.7.0 until the P10 release bump because
  `tests/test_spec_sync.py` pins titles to the released backend version.
- Full backend CI after P1: 723 passed, 10 xfailed; ruff clean. No code
  behavior change.

## Progress Status

- [x] Fetch the latest `master` and create `feature/plan-b-math-distillation`. (Completed by PM)
- [x] Review the execution phases (P0 to P10) in `.agents/plans/B_math_extraction_distillation.md`.
- [x] P0 — Program Setup And Measured Baseline (commit `5a4ea2c`).
- [x] P1 — Docs-First Contract And Migration Specification (commit `ea244d0`).
- [x] **APPROVED — user cleared the Plan B "Mandatory Stop" (P1 contracts
  approved); application code is now authorized from P3 onward.**
- [x] P2 — Failing gold tests and compiler audit oracles. Added
  `docs/specs/failure_atlas/plan_b_compiler_gold.yml` (deterministic +
  human-labeled gold) and `backend/tests/test_plan_b_compiler.py` (9 gold
  structural PASS + 16 `xfail(strict)` schema/support/formula/audit oracles).
  Full suite 732 passed, 26 xfailed; ruff clean. No application code yet.
- [x] P3 — Additive schema and support lifecycle. `db.py` SCHEMA_VERSION 7→8:
  `claim_supports` (§20.2), `compiler_generations` (§20.3), `knowledge_units`
  §20.1 columns (backfill legacy rows `unchecked`/`not_applicable`), tombstone
  CHECK rebuild, and `db_sync` inclusion of both new canonical tables. Added DB
  lifecycle helpers (support upsert/list, support/formula status, retire,
  eligibility, evidence-hash freshness, generation create/publish/discard).
  The 5 §20.1-§20.3/§20.6 SCHEMA oracles flipped to live `test_v8_*` tests; the
  11 behavior oracles correctly stay xfail (P4-P6). Caught + root-fixed a real
  v7→v8 upgrade bug (index on a column not yet added). D2 holdout db.py drift
  fingerprint re-armed to HEAD (user-approved; metric provably unaffected,
  additive change). Full suite 750 passed, 21 xfailed; ruff src/ clean; 0 new
  mypy errors.
- [~] P4 — Claim extraction, minimal support, and stable reconciliation.
  CORE DONE: `pipeline/claim_support.py` — deterministic structural gate
  (verified|failed|uncertain trichotomy per §26.1), LaTeX token-multiset formula
  check (reorder-tolerant, operator/sign-sensitive), `normalize_claim`/
  `semantic_hash`, `run_compiler_audit` (freshness + unsupported), and
  `reconcile_source` (retire on deleted cited span). Exposed via
  `pipeline/compile.py`. Un-xfailed 5 behavior oracles (minimal-support,
  wrong-real-span F6, edited-span-stale, source-delete-retire, audit-flags-
  unsupported); added `tests/test_plan_b_support.py` (12 unit tests incl. the
  `a^2+b^2` vs `a^2-b^2` multiset proof). Suite 768 passed, 16 xfailed; ruff
  src/ clean; 0 new mypy.
  REMAINING P4: (1) wire `validate_claim_support` into `compile_source_l2`
  (populate `claim_supports` + set support_status on real compiles, passing full
  span text); (2) enforce downstream eligibility (exclude retired/unverified
  from graph/synthesis input) — verify it doesn't starve existing compile/graph
  tests; (3) version the knowledge-unit prompt contract to DECLARE minimal
  support roles + formula centrality; (4) extend reconciliation to changed/split
  (semantic_hash candidate matching), not just delete.

## Verification

- `uv run --directory backend pytest -q` → 768 passed, 16 xfailed (P4 core; 5
  more behavior oracles un-xfailed → passing, +12 new support unit tests; the 6
  remaining Plan B P5/P6 oracles + 10 Program 1 strict-xfail oracles remain
  xfail).
- `uv run --directory backend ruff check src/` → clean. (`ruff check tests/`
  shows 6 PRE-EXISTING errors in test_cli_update/test_migrate/test_plugin_cli/
  test_db_sync imports — outside CI scope and outside Plan B's changes.)
- `uv run --directory backend mypy src/` → 73 pre-existing errors, 0 introduced
  by P3 (verified by stash-compare on db.py/db_sync.py).
- `VAULT_ROOT=$REPO/testbed wiki status` → gaussian_splatting testbed healthy
  (3 sources, L1 done, L2-L4 pending; pre-existing "vault schema v0 → v1"
  warning predates Plan B). Testbed DB migration to v8 happens at P7.

## Critical Context And Blockers

- BLOCKER (by design): user approval required before P2+ implementation.
- Frozen P1 design points the user should review: `claim_supports` roles
  (`primary|contextual|formula`), support statuses
  (`unchecked|verified|failed|stale`), `formula_status` enum,
  `compiler_generations` (`GEN-`) staged-publish table, recovery candidates
  in `source_spans.metadata.formula_recovery` (no new table by default),
  compiler audit surfaced through `wiki lint` (no new CLI command, no plugin
  /MCP schema changes).
- Environment note: stray `backend/.venv` removed and root `.venv` recreated
  (stale shebangs from the old `llm_wiki` repo path were silently falling
  back to Anaconda). Use `uv run --directory backend ...` from the repo root.
- `wiki status` with a relative `VAULT_ROOT` resolves against `backend/` when
  run via `uv run --directory backend`; use an absolute path.

## Immediate Next Action

Executors: P3 (v8 additive schema + lifecycle helpers) committed; suite green.
The P4 support-validation mechanism is SETTLED (SYSTEM_BEHAVIOR §26.1; rationale
in `B_roadmap_evidence.md` "P4 Design Decision"): a deterministic STRUCTURAL
gate (verified|failed|uncertain trichotomy) primary, calibrated model secondary
for `uncertain` only. Formula check = normalized symbol/operator token-MULTISET
equality over inline `$...$` AND display `$$...$$` (tolerates reorder, blocks
operator/sign change, no AST/CAS); text check = salient entity/term intersection
above threshold (zero overlap → `failed`, the F6 gate). Validate on hydrated
FULL span text, never the preview. Do NOT lookup the gold YAML at runtime
(overfitting ban); it is the test-time release oracle only.

Continue P4 — the deterministic validator CORE is done and committed
(`pipeline/claim_support.py`, 5 oracles green). Remaining P4 increments, in
order: (1) wire `validate_claim_support` into `compile_source_l2` after
extraction — pass full span text from `span_inputs`, populate `claim_supports`,
set `support_status`/`formula_status`/`semantic_hash` on each unit; (2) enforce
the §20.1 eligibility rule on downstream stages (graph/synthesis read only
`retired_at IS NULL AND support_status='verified'` units) — FIRST confirm the
fake-LLM compile/graph/synthesis tests still pass (their claims must lexically
support their spans; `test_compile_pipeline`'s do); (3) version the
`curator.knowledge_unit_extract` prompt contract to DECLARE minimal support
roles + formula centrality (the model proposes, the deterministic gate
disposes); (4) extend reconciliation to changed/split via `semantic_hash`
candidate matching. Then P5 (selective formula recovery; the `uncertain`
formula verdicts from P4 are its input queue).