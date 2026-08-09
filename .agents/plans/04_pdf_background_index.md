# v0.54.0 Master Implementation Plan — Whole-Document PDF Search

Date: 2026-08-09
Status: **AWAITING USER APPROVAL** — Arena debate concluded (1 proposal, 1
red-team critique, 2 convener verifications). No code written yet.
Arena record: `.agents/plans/pdf_background_index_arena/`

## 1. Objective

Make `search_pdf_anchor` cover **every page of the open PDF**, so a question
about a target the user has not scrolled to — "the derivation in Supplementary
B" — locates its page and answers, instead of silently searching only the pages
already rendered.

**Definition of done**: on the user's real 673-page Multiple View Geometry PDF,
opened at page 1, a question about a target in a late chapter returns a citation
to the correct page; Obsidian stays responsive throughout; and every
`search_pdf_anchor` result states how much of the document it actually searched.

## 2. Explicit Non-Goals

- **Not** persisting the index. It stays in memory, per open document, and dies
  with the tab. The backend owns durable knowledge; this must not become a
  second source of truth.
- **Not** routing to the backend instead. Measured and rejected: only 4 PDFs are
  ingested at all (the MVG book is not one), and `source_spans.page_number` is a
  **section index, not a physical page** (max 23 on a 27-page PDF), so
  `curator_get_pdf_context` cannot answer "what is on viewer page N".
- **Not** changing PDF ingest, `source_spans`, or any backend schema.
- **Not** making `BACKGROUND_INDEX_PAGE_CAP` a user setting.
- **Not** OCR. A page with no text layer stays unsearchable; §26.2b already
  governs how that is reported.

## 3. Strict Quality Conditions & Release Gates

- `upsertPage` is **O(1) in document size**. Guarded by a test that upserts ~700
  pages and asserts near-linear wall time. Today this is quadratic — measured
  **226,801 tokenize calls for 673 pages (337x linear)**.
- Indexing 673 pages never blocks the renderer: no synchronous span over ~16 ms.
- **Zero** `notifyContextChanged()` dispatches originate from the background walk.
- Every `search_pdf_anchor` result carries coverage, and the three states —
  complete / still-running / disabled — are textually distinct.
- `plugin/src/context/pdfCapture.ts`'s `[Related PDF snippets]` block discloses
  partial coverage, or is gated.
- Gates: `npx vitest run -c ./plugin/vitest.config.ts`, `tsc --noEmit`,
  `scripts/backend-check ruff|mypy|pytest` all green.
- Every new behavior has a test **verified to fail without its fix**.

## 4. Locked Design Decisions (Arena Consensus)

1. **`upsertPage` becomes incremental.** Delta `documentFrequency` on replace;
   keep a running `totalLength` so `avgPageLength` is O(1). `upsertDocument`
   (bulk, O(n), called once) is untouched. This is a prerequisite, not an
   optimization — a naive walk is 337x linear on the book.
2. **Idle-time backfill**, started fire-and-forget after the neighbour render in
   `renderPdf()`, yielding via `requestIdleCallback` on
   `containerEl.win || window` (popout-safe, mirroring the existing DPR pattern).
3. **Budget by count, bound by `numPages`.** The red team's generator, not the
   proposal's — verified that the original visits **0 pages forward** of a reader
   at page 3000 in a 5,000-page document.
4. **The walk emits no `notifyContextChanged()`.** Verified cascade:
   `notifyContextChanged → EXTERNAL_PDF_CONTEXT_EVENT → renderContextChips →
   refreshActiveContext → PdfCaptureService.capture → unconditional BM25 search`.
   Progress telemetry is not worth ~27 main-thread search+rebuild cycles.
5. **Coverage is reported on three distinct states**, branching on whether the
   walk is *eligible to progress* (`setting && indexedPages < min(total, CAP)`),
   never inferred from `indexedPages < totalPages`.
6. **The outline gate is dropped**: `canSearch(ctx) = canFetch(ctx)`. An outline
   gives titles, not body text. `outlineState` survives as a *hint* in the tool
   description.
7. **`search_anchor` gets a retry budget** alongside `LOCAL_PDF_FETCH_BUDGET`.
8. **The spiral starts at `d = 1`**, skipping the seed page the awaited render
   already extracted.
9. **The setting is rechecked inside the loop**, so disabling it stops the walk.
10. **`PdfCaptureService`'s passive snippet injection is brought under the same
    honesty rule** — this path feeds the model with no toggle and no disclosure.

## 5. Scope Exclusions & Stop Conditions

**Exclusions**: eliminating the double storage of page text (`pageTextCache` +
`IndexedPage.text`) is measured and reported in P0 but deferred unless P0 shows
it exceeds ~10 MB for the book; `AbortController` through pdf.js (its page API
does not cleanly support it), leaving the accepted one-page-resurrection race.

**Stop conditions — halt and ask:**
- P0 measures the renderer blocking >16 ms per idle slice even at one page per
  slice. The idle-backfill approach is then wrong and needs re-debate.
- Making `PdfCaptureService` honest turns out to change what the model receives
  for *existing* users in a way that is not purely additive.
- Retained memory for the 673-page book exceeds ~50 MB.
- Any change would require persisting the index or touching backend schema.

## 6. Evidence Ledger

**Repository reality (verified 2026-08-09, master `ca52774`, v0.53.0):**
- Working tree clean, no open PRs, only `master` exists locally and remotely.
- `pdfFullDocumentIndex`: **0 consumers** outside `settings.ts`. Sibling settings
  `pdfRagTopK` (4), `pdfWindowRadius` (1), `pdfRagEnabled` (1) are wired.
- `upsertPage` → `buildIndex(ALL pages)`: **quadratic**, simulated at 378 / 5,050
  / 226,801 tokenize calls for 27 / 100 / 673 pages.
- pdf.js 4.10 extraction: **12.9 ms/page** (27p paper, 0.3 s total, 118 KB);
  **11.8 ms/page** (673p book, 7.9 s total, 1.4 MB).
- Backend PDF coverage: 4 sources; `MAX(page_number)` 23 on a 27-page PDF; the
  673-page book has **no source row at all**.
- `canSearch = canFetch(ctx) && outlineState === "absent"` — anchor search is
  withheld from every outlined document today.
- Cascade from `notifyContextChanged` confirmed hop-by-hop to an unconditional
  `searchIndex.search` at `pdfCaptureService.ts:78`.

**Dirty worktree**: none. Four pre-existing unrelated stashes
(`stash@{0}`–`stash@{3}`) must be left alone.

**Rollback**: plugin-TypeScript only. No DB, no schema, no migration, nothing
persisted. Rollback anchor is master at `ca52774`; reverting the branch fully
restores prior behavior.

## 7. Execution Phases (TDD + CI at each phase)

- **P0 — Measured baseline.** Instrument `upsertPage` call counts and wall time
  for the 27p and 673p documents; measure retained memory of `pageTextCache` +
  `PdfIndex` after a full walk. Record in
  `.agents/plans/04_pdf_background_index_evidence.md`. *Verify: numbers recorded;
  stop conditions re-checked against them before P1.*
- **P1 — Contract specification.** PLUGIN_SCHEMA §13.7 gains the whole-document
  contract, the coverage-disclosure rule, and the dropped outline gate;
  PLUGIN_GUIDE + `_KR` document what the setting now does. *Docs-first — stop for
  approval if the contract shifts from what is locked in §4.*
- **P2 — Incremental `upsertPage`.** The prerequisite. *Verify: the ~700-page
  linear-time test fails before and passes after; the stale-term-removal test
  fails before and passes after; existing `pdfDocumentIndex` tests unchanged.*
- **P3 — The backfill walk.** `spiralPageOrder` (count-budgeted), idle yielding,
  cancellation via `indexBuildToken` (including the missing bump in `renderPdf`'s
  reset block), in-loop setting recheck, no `notifyContextChanged`. *Verify:
  generator unit tests including `numPages > CAP` with `center` past the cap;
  source-assertion tests for the call site, popout-safe window, and cap.*
- **P4 — Tool surface.** Drop the outline gate, add the coverage line's three
  states, add the `search_anchor` retry budget. *Verify: the existing "withholds
  search_pdf_anchor when the document has an outline" test is **inverted** — a
  visible contract change; `formatAnchorHits` covers all three states.*
- **P5 — Passive-injection honesty.** `PdfCaptureService` / `composePdfContextText`
  disclose partial coverage. *Verify: a test asserting the snippet block names
  its coverage.*
- **P6 — Manual smoke (the gap automation cannot close).** Open the real
  673-page MVG PDF at page 1, ask about a late-chapter target, confirm the
  citation and that scrolling/typing stay smooth mid-backfill. A unit test cannot
  prove "Obsidian stays responsive"; this is documented as a known gap.

**Version**: Minor → **v0.54.0** (new user-facing capability; a setting that did
nothing begins doing something, and a tool's availability contract changes).
`MAJOR.MINOR` moves 0.53 → 0.54, so all four spec titles must be bumped.
