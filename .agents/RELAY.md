# Active Relay State

**STATUS: ACTIVE - System Stability Phase A is in progress. PR #58 (`v0.27.0`)
has review follow-up edits validated locally and ready to commit/push.**

**Branch**: `feature/system-stability-phase-a`

---

## Goal

System Stability Overhaul - make the system solidly stable through exhaustive
whole-codebase diagnosis and targeted follow-up PRs across correctness,
architecture, prompt consistency, RAG/DAG performance, robustness, UI/UX, and
docs-code reconciliation.

This is still Phase A / early fix batches. Broad architectural refactors remain
plan-first and should be shipped as small PRs, not one large diff.

## Plan Reference

- Master Plan: `.agents/plans/01_system_stability_overhaul.md`
- Evidence Ledger: `.agents/plans/01_roadmap_evidence.md`
- Diagnosis Index: `.agents/plans/diagnosis/INDEX.md`
- Briefing: `.agents/plans/system_stability_overhaul_arena/00_problem.md`
- Roadmap: `.agents/ROADMAP.md`

## Analysis & Reasoning

- `.agents/USER_REPORT.md` is empty; urgent hotfix queue is clear.
- Active roadmap item is still System Stability Overhaul.
- `master` is at v0.26.0 after PR #57 merge. Current branch contains v0.27.0
  work for PR #58.
- Diagnosis index is stale as a completion tracker: it still marks G07-G19 as
  `pending`, while several G07/G08/G11/G14/G15 fixes have already shipped or are
  under PR #58 review. Use git history, PR state, and
  `.agents/plans/01_roadmap_evidence.md` together; reconcile the index after the
  current PR settles.
- Root-level `pr_diff.diff` was confirmed as a disposable review artifact by
  the user and deleted on 2026-06-26.

## Progress Status

Already shipped before this handoff:

- PR #57 / v0.26.0: cross-page PDF equation lookup and per-PDF page cache merged
  to `master`.
- PR #58 / v0.27.0 initial batch: S2 correctness fixes for MCP build-client
  leaks, lint field-name output, `wiki lint --save`, deep contradiction
  read-only behavior, model effort persistence, and dashboard Jobs poller cleanup.

Current local uncommitted review follow-up for PR #58:

- `.agents/RELAY.md` rewritten by this handoff.
- `backend/src/curator/lint.py`: `run_lint(..., apply_flags=False)` now threads
  `apply_flags` into `check_contradictions_deep`.
- `backend/src/curator/cli.py`: `wiki lint --fix` passes `apply_flags=fix`, so
  contradiction flag write-back is enabled only for explicit fix runs.
- `backend/tests/test_stability_phase_a_s2b.py`: adds two regression tests for
  `run_lint` apply-flag threading.
- `plugin/src/ui/chatSidebar.ts`: model/effort normalization now persists only on
  explicit model/provider changes, saving model and effort together without an
  unawaited `saveSettings()` from display sync.

Validation completed on 2026-06-26:

- `scripts/backend-check pytest backend/tests/test_stability_phase_a_s2b.py`:
  9 passed.
- `scripts/backend-check ruff`: passed.
- `scripts/backend-check mypy`: passed, 97 source files.
- `npx vitest run -c ./plugin/vitest.config.ts` from repo root: failed because
  the config resolves `src/**/*.test.ts` relative to cwd and found no files.
- `npx vitest run -c ./vitest.config.ts` from `plugin/`: 60 files / 597 tests
  passed.
- `scripts/backend-check pytest`: 1068 passed, 6 skipped, 5 xfailed, 7 warnings.

## Critical Context / Blockers

- Do not revert the uncommitted code changes; they predate this relay update and
  are part of the PR #58 review follow-up.
- Because code changed after the existing `chore(release): v0.27.0` commit,
  preserve the workflow expectation that the final release commit is last before
  opening/updating the PR. Use a deliberate commit strategy rather than leaving a
  code commit after the release commit.
- Continue respecting the docs/test mandate for any new behavior changes. These
  current review fixes are narrow follow-ups inside the already documented
  v0.27.0 behavior.

## Immediate Next Action

1. Commit/push the review follow-up to PR #58 while keeping release-commit order
   compliant.
2. After PR #58 merges, reconcile `.agents/plans/diagnosis/INDEX.md` with the
   shipped Phase A batches, then continue remaining S2 work from G09/G10/G13/G14
   and later groups.
