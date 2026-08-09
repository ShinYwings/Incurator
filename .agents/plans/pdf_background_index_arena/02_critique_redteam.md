# Critique on Frontend/Plugin Proposal: Idle-Time Whole-Document BM25 Backfill
Date: 2026-08-09 | Agent Persona: red_teamer
Convener note: findings 1.1 and 1.2 were independently re-verified before being
carried into the Master Plan. Evidence is inlined below each.

## 1. Vulnerabilities & Flaws

### 1.1 [CRITICAL — VERIFIED] `notifyContextChanged()` turns idle work into a main-thread search-and-rebuild storm

The proposal fires `notifyContextChanged()` every 25 pages and once at
completion, treating it as free telemetry. Traced:

```
notifyContextChanged()                       ExternalPdfView.ts:2138
  → dispatch EXTERNAL_PDF_CONTEXT_EVENT      ExternalPdfView.ts:2140
  → ChatSidebarView listener                 ChatSidebarView.ts:318-324
  → renderContextChips()                     ChatSidebarView.ts:4347
  → contextChipsContainer.empty()            ChatSidebarView.ts:4350
  → plugin.refreshActiveContext()            ChatSidebarView.ts:4352
  → updateActiveContext → getActivePdfContext → PdfCaptureService.capture()
  → UNCONDITIONAL searchIndex.search(...)    pdfCaptureService.ts:78
```

**CONVENER VERIFICATION**: every hop confirmed at the cited lines. The search at
`pdfCaptureService.ts:78` is not behind any conditional.

So each 25-page tick performs, synchronously on the renderer thread and outside
any idle budget: a full BM25 scan of a growing index, a DOM text extraction, and
a complete chip-container rebuild. For the 673-page book that is ~27 such
cycles per document open. The briefing's own constraint — "the renderer thread
is the user's editor" — is violated by the very mechanism meant to respect it.

### 1.2 [CRITICAL — VERIFIED] `spiralPageOrder` breaks exactly the over-cap case Q2 requires

`pageCap` is used as an absolute page-number ceiling (`center + d <= pageCap`),
not as a count of pages to visit. Correct only by coincidence when
`numPages <= CAP`.

**CONVENER VERIFICATION** — 5,000-page scan, `CAP = 2000`, reader at page 3000:

```
pageCap = 2000 | center = 3000
pages visited forward of the reader : 0
pages visited backward of the reader: 1999
min visited: 1001   max visited: 3000
=> pages 3001..5000 are NEVER indexed; the whole budget goes to 1001..3000
```

Zero pages forward of the reader. The design's own stated rationale —
"nearest-first, seeded at the page the reader opened to" — is inverted in the
one scenario the briefing named as mandatory.

### 1.3 [HIGH] The honesty line lies when background indexing is off

`indexedPages < totalPages && !truncated` → *"background indexing still
running"*, unconditionally. With the setting **off** and 5 of 673 pages scrolled,
the tool asserts an ongoing process that does not exist. §1.3's claim that the
line "says so" when the setting is off is false on inspection: it cannot
distinguish "off" from "running but behind".

### 1.4 [HIGH] A second, silently-fed consumer of the index is never accounted for

`PdfCaptureService.capture()` bakes `ragHits` into `PdfPageContext.text` via
`composePdfContextText`'s `[Related PDF snippets]` block, and that text reaches
the model on paths independent of any toggle — e.g. injected verbatim as
`<background_reference_only>` for other open PDF tabs
(`ChatSidebarView.ts:2186-2210`). Growing the corpus from "a few scrolled pages"
to 2000 silently reshapes passively-injected chat context **with no coverage
signal at all**, unlike the tool's carefully designed honesty line. The
proposal's Pro that this path "gets the same coverage for free" conflates the
backend-gated `pdfRagEnabled` RAG path with this always-on local one.

### 1.5 [MEDIUM] The seed page races itself on every walk

`renderPageCanvas` calls `extractPageTextFromPdfJs` as a fire-and-forget `.then()`
chain (`ExternalPdfView.ts:1095-1108`) that its caller never awaits. The
background loop's first `pageTextCache.has(center)` check therefore reads `false`
almost always, so it re-fetches and re-extracts the page the user is looking at —
duplicating the worker round-trip and firing `notifyContextChanged()` twice for
the seed page of every document open.

### 1.6 [MEDIUM] No budget on `search_pdf_anchor` once the outline gate is gone

`fetch_pdf_page` is metered against `LOCAL_PDF_FETCH_BUDGET`
(`localPdfTools.ts:30`); `search_anchor` returns `pagesFetched: 0`
unconditionally (`LLMClient.ts:690`). Exposing an honestly-incomplete tool on
every document invites a model that reads "Searched 12 of 673 so far" to retry
each round hoping the idle walk caught up — it usually will not have, since idle
callbacks and tool round-trips run on unrelated cadences. No backoff, no
decrement.

### 1.7 [LOW] The memory bound undercounts by design

Page text is held **twice**: in `pageTextCache` (`ExternalPdfView.ts:169`) and
again in `IndexedPage.text` (`pdfDocumentIndex.ts:8-24`). 1.4 MB of extraction
is ≥2.8 MB retained, before per-page `termFrequency` maps and the document-wide
`documentFrequency`. Retained for the life of the open document — not
"transient", as the justification labelled it.

### 1.8 [LOW] Toggling the setting mid-walk does nothing

`pdfFullDocumentIndex` is read once at entry and never rechecked, so disabling it
has no effect until close or swap.

## 2. Suggested Alternatives

**1.1 + 1.4 together.** Remove `notifyContextChanged()` from the walk entirely —
the chip needs no live progress and the tool reports coverage on demand. If a
signal is wanted, use a separate event `renderContextChips` does not subscribe
to, or debounce the dispatch. Separately, `PdfCaptureService.capture()`'s local
search must come under the same honesty discipline: gate it, or thread
`indexedPages`/`totalPages` into the `[Related PDF snippets]` header so a
partially-indexed corpus cannot silently reshape injected context.

**1.2.** Separate "how far to walk" from "which page numbers are legal" — budget
by count, bound by `numPages`:

```ts
function* spiralPageOrder(center: number, numPages: number, budget: number) {
  yield center;
  let visited = 1;
  for (let d = 1; visited < budget && d < numPages; d++) {
    if (visited < budget && center + d <= numPages) { yield center + d; visited++; }
    if (visited < budget && center - d >= 1)        { yield center - d; visited++; }
  }
}
```

Test with `numPages > CAP` and `center` beyond the cap — the exact failing case.

**1.3.** Branch on whether the walk is *eligible to progress*, not on whether the
numbers differ: `stillRunning = setting && indexedPages < min(totalPages, CAP)`.
When off, say so: *"Searched 5 of 673 pages (background indexing is off; scroll
or fetch more pages to search them)."*

**1.5.** Start the spiral at `d = 1`, skipping `center` — the awaited render
already kicked it off — and let the next tick's cache check see it populated.

**1.6.** Give `search_anchor` its own small per-request cap tracked alongside
`budget` in `runLocalPdfTool`, or return the coverage delta so the model can
reason "asking again will not help".

**1.7 / 1.8.** Measure the real retained figure once double storage is either
measured or eliminated (have `IndexedPage` reference the cache entry rather than
copy `text`), and recheck the setting inside the loop body.
