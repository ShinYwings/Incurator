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
- [x] P4 — Claim extraction, minimal support, and stable reconciliation.
  `pipeline/claim_support.py` implements the deterministic structural gate
  (verified|failed|uncertain trichotomy per §26.1), ordered LaTeX token-sequence
  formula check (direction/binding-preserving, contiguous sub-formula aware),
  `normalize_claim`/
  `semantic_hash`, `run_compiler_audit` (freshness + unsupported), and
  `reconcile_source` (retire on deleted cited span). Exposed via
  `pipeline/compile.py`. Un-xfailed 5 behavior oracles (minimal-support,
  wrong-real-span F6, edited-span-stale, source-delete-retire, audit-flags-
  unsupported); added `tests/test_plan_b_support.py` (12 unit tests incl. the
  direction/binding and sub-formula proofs). Suite 768 passed, 16 xfailed; ruff
  src/ clean; 0 new mypy.
  COMPLETE integration: `compile_source_l2` validates with hydrated full span
  text before downstream use; prompt contract is now
  `curator.knowledge_unit_extract@v2` with proposed support roles/formula
  centrality; proposals persist as unchecked and are replaced by the fresh gate
  verdict; ATM/graph/projection re-emission/knowledge-unit search read only
  verified active units; changed/split reconciliation reuses a prior stable id
  only for a verified semantic-hash candidate with whitespace-normalized exact
  statement equality and retires the temporary candidate.
  REVIEW FIX: semantic hashes now only propose reconciliation candidates;
  stable-id reuse requires whitespace-normalized exact statement equality.
  Formula matching now preserves ordered tokens/grouping and admits only exact
  contiguous sub-formulas, preventing exponent/subtraction/fraction reversal.
  Formula-only parse loss routes to P5 as `uncertain`, escaped `\$` is ignored
  as a delimiter, and formula-bearing spans outrank non-formula spans for
  `primary` support. Legacy NULL-hash fallback was explicitly rejected under
  the no-backward-compatibility-shims invariant. F6 textual support failures now
  preserve `formula_status='preserved_in_text'` when the formula structurally
  matches, preventing false P5 recovery. Multi-span textual verdicts now use
  maximum cited-span prose coverage independently from formula-aware primary
  attribution; formula hash input preserves token/formula boundaries; and the
  tokenizer preserves non-alphabetic LaTeX escapes.
- [x] P5 — Selective formula recovery and downstream preservation.
  `pipeline/formula_recovery.py` adds provider-free measured-loss
  classification (`fragmented|image_only|parser_omitted`), additive
  `source_spans.metadata.formula_recovery` candidates, `0.80` +
  validator-trace + exact-claim-formula acceptance gates, hash-verified full
  raw-span revalidation, linked formula evidence, and page-hash invalidation.
  Raw span text/hash remain immutable. Formula-bearing graph input is never
  destructively truncated. Two P5 strict-xfail oracles are now live green
  tests.

## Verification

- `uv run --directory backend pytest -q` → 790 passed, 14 xfailed (P5 complete;
  the 4 remaining Plan B P6 oracles + 10 Program 1 strict-xfail oracles
  remain xfail).
- `uv run --directory backend ruff check src/` → clean. (`ruff check tests/`
  shows 6 PRE-EXISTING errors in test_cli_update/test_migrate/test_plugin_cli/
  test_db_sync imports — outside CI scope and outside Plan B's changes.)
- `uv run --directory backend mypy src/` → 73 pre-existing errors, 0 introduced
  by P3 (verified by stash-compare on db.py/db_sync.py).
- `VAULT_ROOT=$REPO/testbed wiki status` → gaussian_splatting testbed healthy
  (3 sources, L1 done, L2-L4 pending; pre-existing "vault schema v0 → v1"
  warning predates Plan B). Testbed DB migration to v8 happens at P7.

## Critical Context And Blockers

- No active implementation blocker; the P1 mandatory stop was approved.
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
for `uncertain` only. Formula check = ordered normalized token sequence over
inline `$...$` AND display `$$...$$` (preserves direction/binding; accepts only
contiguous sub-formulas; no AST/CAS); text check = salient entity/term intersection
above threshold (zero overlap → `failed`, the F6 gate). Validate on hydrated
FULL span text, never the preview. Do NOT lookup the gold YAML at runtime
(overfitting ban); it is the test-time release oracle only.

P4 review fixes and P5 selective formula recovery are implemented; full
validation is green. Continue P6: staged atomic compiler generations, publish
gate/failure rollback, and full dependency reconciliation.
