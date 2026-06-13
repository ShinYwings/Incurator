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
- [ ] P3 — Additive schema and support lifecycle (v8 migration: `claim_supports`,
  `compiler_generations`, `knowledge_units` additive columns; backfill legacy
  rows `unchecked`). Turns the §20.1-§20.3/§20.6 schema oracles green first.

## Verification

- `uv run --directory backend pytest -q` → 732 passed, 26 xfailed (P2; baseline
  723/10 + 9 gold passes + 16 new Plan B oracles; all 10 Program 1 strict-xfail
  oracles preserved).
- `uv run --directory backend ruff check src/ tests/test_plan_b_compiler.py` → clean.
- `VAULT_ROOT=$REPO/testbed wiki status` → gaussian_splatting testbed healthy
  (3 sources, L1 done, L2-L4 pending; pre-existing "vault schema v0 → v1"
  warning predates Plan B).

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

Executors: P1 approved and P2 (red TDD state) committed. Begin P3 — implement
the v8 additive migration in `db.py` (`claim_supports`, `compiler_generations`,
`knowledge_units` additive columns; `deleted_records` tombstone CHECK + export
extension), backfilling every legacy `knowledge_units` row as
`support_status='unchecked'`, `formula_status='not_applicable'`,
`generation_id=NULL`. Drive the §20.1-§20.3/§20.6 schema oracles in
`tests/test_plan_b_compiler.py` green (un-xfail them in the same change) and
rehearse the migration on `.agents/backups/b-pre-implementation-state.sqlite`
per SYSTEM_BEHAVIOR §26.6 before touching the live testbed DB.
