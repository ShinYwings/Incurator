# Agent Relay State

## Status: AWAITING MERGE — Program 1 / Plan D1 shipped as v0.6.0

- **Goal**: ROADMAP To-Do #1 Batch 1, first release: Plan D1 Failure Atlas
  diagnostic baseline. User approved via `/goal 다음 마일스톤 진행해`
  (2026-06-12).
- **Branch**: `release/v0.6.0` (from `master` @ `8458f65`). PR open — the
  human's only action is to review and merge it on GitHub.
- **Plan**: `.agents/plans/D_current_system_failure_atlas.md` phases P0–P4
  complete. The D1 evidence ledger was deleted in the release commit per the
  Universal Strict Workflow (full content in Git history of this branch).

## What shipped (diagnostics only — zero runtime behavior change)

- `docs/specs/failure_atlas/` — FAILURE_ATLAS.md contract, cases F01–F13
  (all `reproduced` → `assigned`), EVALUATION_BASELINE.md,
  fixture_corpus.yml, qrels.yml.
- `backend/tests/test_failure_atlas_{contract,repro,experiments,eval}.py` —
  13 passing baselines + 13 strict-xfail oracles + experiments + frozen
  lexical baseline. Local CI: backend 643 passed / 13 xfailed; vitest 361
  passed; ruff clean; spec titles + ACTIVE_VERSION + 3 manifests at 0.6.0.
- Known pre-existing (not D1): `mypy src/` has 73 errors on master (CI does
  not gate mypy); `ruff check tests/` has 6 findings in old test files.

## Immediate Next Action (after this PR merges)

Per the Intermission Gate in the D plan: start **Plan E**
(`.agents/plans/E_external_research_design_matrix.md`) on a fresh branch from
post-merge `master`. Plan E benchmarks external technique candidates against
the reproduced atlas failures (by case id) and produces the ADR decision
package. D2 resumes only after E merges. Do NOT start Program 2/3 work.
