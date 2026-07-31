# v0.39.2 Master Implementation Plan

Date: 2026-07-31
Status: APPROVED — user deferred execution until the next session because provider
quota is low; begin directly at P1/P2 without repeating diagnosis or approval.

## 1. Objective

Make latest-user text queries such as `수식 (10)` deterministically receive the
referenced PDF page text, so the final provider answers from supplied evidence and
does not attempt a denied native file read.

## 2. Explicit Non-Goals

- Do not grant blanket tool approval or add `command` permission.
- Do not broaden Antigravity's filesystem roots to arbitrary external paths.
- Do not change PDF ingestion, database schema, or durable source registration.
- Do not redesign general RAG ranking.

## 3. Strict Quality Conditions & Release Gates

- A test matching the reported current-page-(9)/next-page-(10) scenario fails
  before implementation and passes after it.
- The target page body appears in `<resolved_cross_references>` before the
  generic PDF window.
- No provider-native `read_file` is needed in the live reproduction.
- Plugin tests, TypeScript, production build, backend spec/version checks, and
  the relevant testbed smoke pass.
- v0.39.2 versions agree across backend and plugin manifests; changelog and EN/KR
  docs remain synchronized.

## 4. Locked Design Decisions

- Reuse `resolveSelectionReferencesBlockAsync()` and the existing read-only PDF
  context API.
- Resolve the latest user request, not only selected/cropped context text.
- Bound adjacent-page expansion and stop at the first exact equation-label hit.
- Keep Antigravity's current narrow `$read_file$()` compatibility rule unchanged;
  this hotfix removes the unnecessary native read rather than widening it.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: arbitrary full-document scans, new provider flags, Zotero path
  persistence, and backend schema work.
- **Stop Conditions**: stop and re-plan if the target page cannot be fetched via
  the current read-only PDF API or if the fix requires a public contract/schema
  change.

## 6. Evidence Ledger

- Current repository anchor and observed runtime evidence are recorded in
  `.agents/plans/03_v0392_equation_reference_evidence.md`.
- Worktree was clean at branch creation; production vault files are not edited.
- Rollback is branch deletion back to `bc61fab`; no migration is involved.

## 7. Execution Phases

- **P0 — Baseline**: preserve the live command/settings/session evidence and add
  the exact failing fixture.
- **P1 — Contract Specification**: update plugin/system specs and English guide,
  then faithfully update the Korean guide.
- **P2 — TDD**: add latest-user bare-equation adjacent-page tests and ordering/
  fetch-bound assertions.
- **P3 — Core Logic**: integrate the async resolver into sidechat PDF context
  assembly and make the tests pass.
- **P4 — Integration**: run the reported query against the live external PDF and
  verify the provider answers without native tool denial.
- **P5 — Release**: run full checks, bump v0.39.2, update changelog, remove plan
  artifacts, commit, push, and open the hotfix PR.
