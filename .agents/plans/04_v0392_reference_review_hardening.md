# v0.39.2 Review Hardening Master Implementation Plan

Date: 2026-08-01
Status: APPROVED — Arena debate concluded; specs are authored, tests are spec-first.

## 1. Objective

Make PR #103 safe to merge by ensuring single-number equation references fail
closed when the bounded scan finds no exact label and by preventing background
PDF tabs from claiming references during non-PDF-focused turns. Definition of
done: both regressions have behavior tests, the real page-6 fixture still
passes, docs/specs are synchronized, all local plugin/backend gates pass, and
the corrected branch is pushed to the same draft PR.

## 2. Explicit Non-Goals

- No new reference syntax, provider capability, filesystem permission, scan
  depth, database schema, migration, or public API.
- No changes to selected/cropped PDF reference behavior.
- No refactor of unrelated `ChatSidebarView` context assembly.
- No repeat of the live external-provider replay.

## 3. Strict Quality Conditions & Release Gates

- A loose current-page BM25 hit never survives after an exact-label adjacent
  scan is exhausted for a single-number equation pointer.
- A Markdown-focused turn with only background prompt-included PDFs performs no
  latest-user PDF reference resolution.
- The active PDF and an explicitly referenced PDF remain eligible.
- Adjacent fetch order/cap stays `[next1, prev1, next2, prev2]`.
- The existing real page-6 fixture and selected/cropped paths remain green.
- English and Korean guides plus the system behavior spec agree.
- Focused tests, full Vitest, TypeScript, build, backend pytest, Ruff, and MyPy
  pass before push.

## 4. Locked Design Decisions (Arena Consensus)

- Exact evidence is a state transition, not a score threshold. Only expanded
  single-number equation pointers without exact-label evidence are failed
  closed after scan exhaustion.
- Latest-user resolution is gated by canonical document identity: active PDF or
  explicit matching user PDF context. Visibility/prompt inclusion alone is not
  focus; basename-only matching is forbidden.
- Existing generic PDF context remains available to the provider even when the
  latest-user pointer resolver is skipped.
- No schema/migration or version increment beyond the already prepared v0.39.2
  release is needed; these are pre-merge corrections to the same hotfix.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: multi-number equation heuristics, wider page search, OCR,
  cross-document semantic resolution, and stability-audit work.
- **Stop Conditions**: stop and request direction if canonical document identity
  cannot distinguish explicit references, the fix requires a schema/public
  contract change, or the real fixture loses its exact page-6 result.

## 6. Evidence Ledger

- **Current Repository & Schema Reality**: Draft PR #103 at `e02859b`; CI is
  green. No database/schema surface participates in the affected path.
- **Current Dirty Worktree**: clean before these planning artifacts; only plan,
  roadmap, and relay files may change before approval.
- **Confirmed Reproduction**: generic current-page equation/number prose plus
  adjacent pages without `Eq. (10)` fetched `[6, 4, 7, 3]` yet returned
  `bm25-object`, page 5, confidence `0.85`.
- **Control Evidence**: the real external PDF fixture still resolved page 6 by
  `caption-index` with only page 6 fetched.
- **Rollback Requirements**: changes remain on the hotfix branch; use additive
  `git revert` for any follow-up commit. No data backup or migration is needed.

## 7. Execution Phases (Follow TDD and CI at each phase)

- **P0 — Research & Measured Baseline**: preserve the confirmed failure and
  successful real-fixture evidence in deterministic tests. Verify focused tests
  fail only for the two reported gaps.
- **P1 — Contract Specification**: update system behavior and English guide,
  then faithfully synchronize the Korean guide. Verify terminology and
  fail-closed/focus rules agree.
- **P2 — Regression Tests**: add runtime tests for scan exhaustion, active PDF,
  explicit PDF reference, Markdown/background PDF, and multiple background
  PDFs. Verify focused Vitest fails before application logic changes.
- **P3 — Core Logic**: implement exact-evidence scan exhaustion handling in
  `pdfReferenceContext.ts`. Verify focused reference tests and request bounds.
- **P4 — Integration**: implement canonical PDF-focus eligibility and gate the
  latest-user call in provider-context assembly. Verify behavior tests,
  selected/cropped regressions, TypeScript, and build.
- **P5 — Full Validation and Delivery**: run full Vitest and required backend
  checks, update changelog only if wording needs clarification, remove completed
  plan artifacts per workflow, commit incrementally, push to PR #103, and report
  exact results. Do not run a live provider replay.
