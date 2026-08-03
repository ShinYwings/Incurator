# v0.40.3 Master Implementation Plan — PDF Cross-Reference Resolution Hotfix

Date: 2026-08-03
Status: APPROVED — Arena debate concluded (`hotfix_pdf_crossref_arena/`).
User pre-approved plan+implementation in one pass ("플랜 작성하고 바로 코드 작성해줘").

## 1. Objective

Selecting a pointer like `"From Result A4.1-(p581)"` in the PDF reader and
triggering Ask AI must inject the **actual referenced content** (Result A4.1,
printed page 581 = physical 599 in the reproducing document) into
`<resolved_cross_references>`, and must **never** inject a wrong page as a
resolved-looking reference. Definition of done: the three root causes
(RC1–RC3, `hotfix_pdf_crossref_arena/00_problem.md`) are fixed with failing
tests written first, all plugin tests pass, docs/spec updated, version bumped
to v0.40.3, PR opened.

## 2. Explicit Non-Goals

- NO agentic multi-hop retrieval tools (`fetch_pdf_page` / `search_pdf_anchor`
  LLM tool surface) — Minor scope, deferred; re-enters via USER_REPORT.
- NO backend/DB changes; `source_spans` / FTS are untouched (Rev 1's
  backend-layer approach was invalidated by the code trace).
- NO sidechat conversational-loop changes beyond what the shared resolver
  fixes provide automatically.
- NO OCR / scanned-PDF page-number recovery.

## 3. Strict Quality Conditions & Release Gates

- `npx vitest run -c ./plugin/vitest.config.ts` 100% green.
- `scripts/backend-check pytest|ruff|mypy` green (CI parity; backend untouched).
- New tests reproduce the user's exact failure end-to-end (async resolver with
  windows around physical 276, printed-258 headers, no pageLabels, fetch
  serving physical 599) and assert physical 581 is **never** fetched.
- Version consistency: `backend/pyproject.toml` = `plugin/package.json` =
  `plugin/manifest.json` = `0.40.3`; patch bump ⇒ no spec-title line changes.
- Fail-closed invariant: with no pageLabels, no inferable offset, and no
  probe confirmation, an explicit page locator yields NO injected reference.

## 4. Locked Design Decisions (Arena Consensus)

- **F1 (RC1)**: theorem-family capture `([A-Z]?\d+(?:\.\d+)*)` at
  `crossReferenceResolver.ts:182`; digit still mandatory (no prose capture).
- **F2 (RC2)**: pure `inferPrintedPageOffset(pages)` — header/footer scan
  (first/last 3 non-empty lines; `^\s*(\d{1,4})(?![\d.])` /
  `(?<![\d.])(\d{1,4})\s*$`); modal delta needs ≥2 supporting pages AND strict
  majority of candidate-bearing pages; ties → `undefined`. Wired as
  `ctx.pageOffset` in both `pdfReferenceContext.ts` builders (async recomputes
  from the growing `pageTextMap`). Identity fallback at
  `crossReferenceResolver.ts:417-419` is **deleted** (sync-path no-op
  equivalence proven in `03_defense_lead_architect.md` §1). Async-only
  identity probe: on an unmapped explicit page ref, fetch physical=printed
  once and let re-inference confirm or correct. Async-only mismatch filter:
  drop explicit-page results whose fetched page shows a confidently-extracted
  contradicting printed number; absent/garbled headers keep the resolution.
- **F3 (RC3)**: `CAPTION_LINE_RE` gains
  `results?|corollar(?:y|ies)|propositions?|prop|definitions?|claims?|conjectures?`
  (kind `"theorem"` via existing default). `outlineNumberCandidates(title)`
  gives `"Appendix 4 …"` the additive alias `A4`; used by
  `matchOutlineBySectionNumber`, `resolveObjectOwningSection`, and
  `outlineRangeForNumber`; document-order `find` preserves Chapter-4
  precedence for bare `"4"` lookups.
- Contracts preserved: `ResolveContext`, `ResolvedReference`, block XML shape,
  and all existing resolve methods/confidences are unchanged for currently
  passing cases (except removal of the misleading identity path).

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: agentic tools (deferred, Minor); printed-page range
  locators beyond existing behavior; backend anchors.
- **Stop Conditions**: any existing vitest test that must be *weakened* (not
  extended) to pass → stop and report; the reproducing e2e test cannot be made
  to pass without violating a locked decision → stop and re-enter Arena.

## 6. Evidence Ledger

See `03_pdf_crossref_evidence.md` (rollback anchor, worktree state, pre/post
validation).

## 7. Execution Phases (TDD at each phase)

- **P0 — Baseline**: run plugin vitest on the two touched suites; record green
  baseline in the evidence ledger.
- **P1 — Contract**: update `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`
  (`<resolved_cross_references>` contract: offset inference, identity probe,
  fail-closed rule) and `docs/guides/PLUGIN_GUIDE.md` → `PLUGIN_GUIDE_KR.md`.
  No schema/DB migration (patch).
- **P2 — DB Schema**: N/A (no schema change).
- **P3 — Core Logic (TDD)**: write failing tests in
  `crossReferenceResolver.test.ts` (F1 extraction incl. red-team negatives,
  offset inference consensus/tie rules, fail-closed explicit page, caption
  family, alias order) and `pdfReferenceContext.test.ts` (user's e2e case,
  identity probe confirm/correct/absent, mismatch filter); then implement
  F1–F3 until green.
- **P4 — Integration**: no entry-point changes needed
  (`quickQueryPopover.ts` / `ChatSidebarView.ts` already call the shared
  resolvers); verify via the e2e tests.
- **P5 — Release Gate**: full vitest + backend-check trio; version bump
  0.40.3 + CHANGELOG (`### Fixed` only); ROADMAP/RELAY cleanup; plan deletion;
  `chore(release): v0.40.3`; push + PR.
