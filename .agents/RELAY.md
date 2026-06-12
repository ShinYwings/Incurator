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
- [ ] **STOPPED — awaiting user approval of the P1 contracts before any
  application code (Plan B "Mandatory Stop").**
- [ ] P2 — Failing gold tests and compiler audit oracles (after approval).

## Verification

- `uv run --directory backend pytest -q` → 723 passed, 10 xfailed.
- `uv run --directory backend ruff check src/` → clean.
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

USER: review and approve the P1 contracts (SCHEMA.md §20, SYSTEM_BEHAVIOR.md
§26, SEARCH_ENGINE_SCHEMA.md §10) so implementation can start.
Executors: after approval, begin P2 (failing gold tests + compiler audit
oracles) per the master plan; do NOT write application code before then.
