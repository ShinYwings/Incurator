# Frontend/Plugin Proposal: Idle-Time Whole-Document BM25 Backfill
Date: 2026-08-09 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

### 1.0 The load-bearing finding this design turns on

`PdfDocumentIndexService.upsertPage()` (`plugin/src/context/pdfDocumentIndex.ts:82-104`)
does not update the index incrementally. It takes the existing pages out of the
map, appends the new one, and calls `buildIndex()` — which re-tokenizes **every
page in the document**, on every call. Today that is invisible: every caller
(`renderPageCanvas`'s per-page `extractPageTextFromPdfJs` at
`ExternalPdfView.ts:1108`, and `pdfReferenceContext.ts`'s bounded `fetchPages`
at 308-327, capped by `DIRECT_FETCH_ROUND_LIMIT=3`) calls it a handful of times
per interaction.

A background walk of all 673 pages of the Hartley book turns this into
`Σ(m=1..673) m ≈ 226,700` page-tokenizations.

**CONVENER VERIFICATION (2026-08-09).** Simulated against the real control flow:

```
  27 pages ->     378 tokenize() calls (linear would be 27; ratio  14.0x)
 100 pages ->    5050 tokenize() calls (linear would be 100; ratio  50.5x)
 673 pages ->  226801 tokenize() calls (linear would be 673; ratio 337.0x)
```

The architect's estimate was right to within 100 calls. The briefing's 7.9 s
figure measured *pdf.js extraction only*; indexing that output through the
current `upsertPage` adds a 337x multiplier on top for the book case. Per
"Root Cause Over Workarounds", the fix is not throttling around this — it is
making `upsertPage` genuinely incremental (delta the document-frequency counts
instead of recomputing), a self-contained rewrite of one function that improves
every existing caller too.

```typescript
interface PdfIndex {
  documentId: string;
  pages: Map<number, IndexedPage>;
  documentFrequency: Map<string, number>;
  avgPageLength: number;
  totalLength: number; // NEW: running total keeps avgPageLength O(1)
}

upsertPage(documentId: string, page: PdfWindowPage, outline: PdfOutlineItem[] = []): void {
  let index = this.indexes.get(documentId);
  if (!index) {
    index = { documentId, pages: new Map(), documentFrequency: new Map(),
              avgPageLength: 0, totalLength: 0 };
    this.indexes.set(documentId, index);
  }

  const previous = index.pages.get(page.pageNum);
  if (previous) {
    for (const term of new Set(previous.tokens)) {
      const df = index.documentFrequency.get(term) ?? 0;
      if (df <= 1) index.documentFrequency.delete(term);
      else index.documentFrequency.set(term, df - 1);
    }
    index.totalLength -= previous.length;
  }

  const tokens = tokenize(page.text);
  const termFrequency = new Map<string, number>();
  for (const t of tokens) termFrequency.set(t, (termFrequency.get(t) ?? 0) + 1);
  for (const t of new Set(tokens)) {
    index.documentFrequency.set(t, (index.documentFrequency.get(t) ?? 0) + 1);
  }
  index.totalLength += tokens.length;

  index.pages.set(page.pageNum, {
    pageNum: page.pageNum, text: page.text, textQuality: page.textQuality,
    sectionTitle: findSectionTitle(outline, page.pageNum),
    tokens, termFrequency, length: tokens.length,
  });
  index.avgPageLength = index.pages.size > 0 ? index.totalLength / index.pages.size : 0;
}

/** Pages actually indexed so far — denominator for the honesty line. */
pageCount(documentId: string): number {
  return this.indexes.get(documentId)?.pages.size ?? 0;
}
```

`upsertDocument` (bulk, called once on open) is untouched — already O(n).

### 1.1 When is the work paid (Q1): idle-time, started right after critical rendering

`renderPdf()` (`ExternalPdfView.ts:839-992`) already sequences by priority: load
the PDF, render the current page for immediate display (939), then
fire-and-forget the neighbour range (943). A fourth, lowest-priority step goes
at the same point:

```typescript
this.renderPagesInRange(token, savedPage - RENDER_RADIUS, savedPage + RENDER_RADIUS);
void this.runBackgroundIndexing(pdf, this.docId, savedPage);
```

Deferring to first-search was rejected: the first question about a distant
target is exactly when latency matters, and starting cold then pays the full
catch-up synchronously — the opposite of what "background" buys.

```typescript
const BACKGROUND_INDEX_PAGE_CAP = 2000;
const IDLE_CALLBACK_TIMEOUT_MS = 1000;

function idleYield(win: Window & typeof globalThis): Promise<IdleDeadline> {
  return new Promise((resolve) => {
    if (typeof win.requestIdleCallback === "function") {
      win.requestIdleCallback((d) => resolve(d), { timeout: IDLE_CALLBACK_TIMEOUT_MS });
    } else {
      // Electron build without requestIdleCallback: a macrotask boundary still
      // unblocks scroll/keyboard handling, though it is not true idle semantics.
      setTimeout(() => resolve({ timeRemaining: () => 0, didTimeout: true } as IdleDeadline), 0);
    }
  });
}

/** Nearest-first, seeded at the page the reader opened to, so idle time buys the
 *  neighbourhood most likely to be asked about before the far end of a book. */
function* spiralPageOrder(center: number, pageCap: number): Generator<number> {
  yield center;
  for (let d = 1; d < pageCap; d++) {
    if (center + d <= pageCap) yield center + d;
    if (center - d >= 1) yield center - d;
  }
}

private async runBackgroundIndexing(pdf: PdfDocument, docId: string, centerPage: number): Promise<void> {
  if (!this.plugin.settings?.pdfFullDocumentIndex) return;
  const idxToken = this.indexBuildToken;
  const win = (this.containerEl.win || window) as Window & typeof globalThis;
  const pageCap = Math.min(pdf.numPages, BACKGROUND_INDEX_PAGE_CAP);
  const alive = () => idxToken === this.indexBuildToken && this.docId === docId;

  let visited = 0;
  for (const pageNum of spiralPageOrder(centerPage, pageCap)) {
    if (!alive()) return;
    if (this.pageTextCache.has(pageNum)) continue;  // already read: skip
    await idleYield(win);
    if (!alive()) return;                            // re-check after yielding
    try {
      const page = await pdf.getPage(pageNum);
      if (!alive()) return;
      await this.extractPageTextFromPdfJs(page, pageNum);
    } catch (err) {
      logger.warn(`Background index: page ${pageNum} extraction failed`, err);
    }
    if (++visited % 25 === 0) this.notifyContextChanged();
  }
  if (alive()) this.notifyContextChanged();
}
```

`this.containerEl.win || window` mirrors the DPR pattern already at
`ExternalPdfView.ts:1063` — required because Obsidian's popout moves the leaf to
a separate Electron `BrowserWindow` with its own event loop; scheduling on the
wrong window's `requestIdleCallback` would silently never fire.

**A gap this closes**: `indexBuildToken` is currently NOT bumped in
`renderPdf()`'s reset block (843-855), only in `reloadFromDisk` (340) and
`onClose` (519). Since the view instance is reused across documents
(`main.ts:1820`), a doc swap today leaves the previous document's loop believing
it is current. Fix: add `this.indexBuildToken++;` beside the existing
`this.documentIndex.removeDocument(this.docId);` at 854.

### 1.2 What bounds it (Q2): a hard page cap, content-agnostic

`BACKGROUND_INDEX_PAGE_CAP = 2000` — ~3x the largest measured real document,
≈24 s of raw extraction spread across idle slices, ≈4 MB transient text, never
persisted. The cap is a **page count**, not a size or time budget: pdf.js pays
`getPage()`/`getTextContent()` per page regardless of text volume, so page count
is the right unit.

At the cap the walk stops. `fetch_pdf_page` stays uncapped and unchanged;
manual scrolling past the cap still indexes via the existing render path. The
search result carries `truncated: true` so the ceiling is stated, not silent.

### 1.3 What the model sees while incomplete (Q3): a coverage line, every time

```typescript
export interface AnchorSearchResult {
  hits: PdfRagHit[];
  indexedPages: number;
  totalPages: number;
  truncated: boolean;
}

export function formatAnchorHits(result: AnchorSearchResult): string {
  const { hits, indexedPages, totalPages, truncated } = result;
  const coverage =
    !truncated && indexedPages >= totalPages
      ? `Searched all ${totalPages} pages.`
      : truncated
        ? `Searched the first ${indexedPages} of ${totalPages} pages (indexing capped; ` +
          `pages beyond that are fetchable by number but not searchable).`
        : `Searched ${indexedPages} of ${totalPages} pages so far (background indexing still running).`;
  if (hits.length === 0) {
    return `${coverage} No matching pages` +
      (indexedPages < totalPages ? " among the pages indexed so far" : "") + ".";
  }
  return `${coverage}\n` + hits.map((h) => `p.${h.pageNum} (score ${h.score}): ${h.snippet}`).join("\n");
}
```

This holds regardless of the setting: with background indexing off,
`indexedPages` simply never grows past what render/fetch touched, and the line
says so. The setting controls whether the index is *filled*, never whether the
tool is *honest* about what is in it.

### 1.4 Does `outlineState === "absent"` survive (Q4): no — the gate is dropped, the signal is not

An outline gives section *titles*, not body text, so an outlined document still
cannot be searched for a phrase today — precisely the MVG-book case. Once the
index is whole-document, anchor search is valuable on every document.

```typescript
function canSearch(ctx: LocalPdfToolContext): boolean {
  return canFetch(ctx);   // outlineState no longer gates availability
}
```

`outlineState` stays in the context but changes role from *gate* to *hint*,
folded into the tool description: with an outline, "prefer the ToC for
section-level navigation, use this to locate wording titles don't capture";
without one, the existing "no embedded outline" wording.

### 1.5 Cancellation and lifecycle (Q5)

| Trigger | Mechanism |
|---|---|
| Tab close | `onClose()` already bumps `indexBuildToken` (519) then `removeDocument` (520). Loop observes the mismatch after its next `await`. |
| Document swap | **New**: `indexBuildToken++` added to `renderPdf()`'s reset block. |
| Popout window | `idleYield` schedules on `containerEl.win \|\| window`. |
| Obsidian quit | Obsidian calls `onClose()` on every open view. |
| `Cmd+Shift+R` | `reloadFromDisk()` already bumps the token (340). |

**Accepted, bounded edge case**: cancellation is cooperative, so a page
extraction already past its last check when `onClose` fires can still land and
resurrect a one-page index entry for a closed document. Bounded to one page,
collected on reopen or plugin unload. Eliminating it needs `AbortController`
threaded through pdf.js's page API, which it does not cleanly support.

### 1.6 What is the test (Q6)

**`pdfDocumentIndex.test.ts`** — `pageCount()` for unknown/known documents; a
term unique to a page's *old* text disappears after `upsertPage` replaces it
(proves delta-removal, not just that a full rebuild happened); and a
~700-page upsert loop asserted to stay under a wall-clock bound — quadratic
today, linear after.

**`localPdfTools.test.ts`** — the existing "withholds search_pdf_anchor when the
document has an outline" test encodes the old contract and must be **inverted**;
same for `outlineState: "unknown"`; `parseLocalPdfToolCall` accepts a search on
an outlined document; `formatAnchorHits` covers complete / in-progress /
truncated, including zero-hits-but-incomplete reading differently from
zero-hits-but-exhaustive.

**`externalPdfViewSource.test.ts`** (source-assertion pattern, since the class
cannot be instantiated outside Obsidian) — the fire-and-forget call site exists
and is not awaited; `indexBuildToken++` is present in `renderPdf`'s reset block
specifically; `containerEl.win || window` is used inside the idle scheduling;
`BACKGROUND_INDEX_PAGE_CAP` bounds the walk.

**Manual smoke** (a unit test structurally cannot prove "Obsidian stays
responsive"): open the 673-page MVG PDF, ask about an appendix target far past
the render window, confirm the citation lands on the right page and that
scrolling/typing stay smooth mid-backfill.

## 2. Pros & Cons

**Pros**
- Fixes a real O(n²) defect at its root; every existing caller benefits.
- Reuses `extractPageTextFromPdfJs`, `PdfDocumentIndexService`, and
  `indexBuildToken` (unused scaffolding until now). No new source of truth.
- A paper finishes before the user finishes the abstract; a book makes steady
  invisible progress.
- The coverage line closes the silent-partial-search failure mode.
- Dropping the outline gate makes the tool available where it was needed most.
- `pdfRagEnabled`'s auto-search path shares the index and gets the same
  coverage for free.
- The cap is content-agnostic, bounding a scanned book as well as a dense one.

**Cons / honest limitations**
- `requestIdleCallback` has no prior use in this codebase; timing is
  nondeterministic by design, and the `setTimeout(0)` fallback approximates it.
- Background extraction shares pdf.js's worker channel with foreground
  rendering; a distant scroll mid-backfill can queue a few ms behind an in-flight
  `getTextContent()`. Minimised by per-page yielding, not eliminated.
- Cooperative cancellation leaves the bounded one-page resurrection case above.
- `BACKGROUND_INDEX_PAGE_CAP` is hardcoded, not user-configurable in this pass.
- `searchAnchor`'s return type changes; every call site must move together.
- Deliberately inverts a currently-passing test — a visible contract change a
  reviewer must see called out, not absorbed silently into a larger diff.
