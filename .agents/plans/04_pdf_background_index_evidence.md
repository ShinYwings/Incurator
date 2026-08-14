# Evidence Ledger — v0.54.0 Whole-Document PDF Search

Date: 2026-08-09 | Phase: **P0 complete** | Branch:
`feature/v0.54.0-pdf-background-index` | Rollback anchor: master `ca52774`

## P0 — Measured baseline

Measured against the **real** `PdfDocumentIndexService` (not a simulation),
driven by page text extracted from the user's own PDFs with pdf.js 4.10 using
the plugin's own options (`disableFontFace: true`).

| | paper27 | book673 |
|---|---|---|
| pages | 27 | 673 |
| raw extracted text | 0.13 MB | 1.71 MB |
| `upsertPage` loop (**current**, per page) | 93 ms | **26,881 ms** |
| `upsertDocument` bulk (one shot) | 8 ms | 81 ms |
| ratio loop / bulk | 11.4x | **331.3x** |
| one `search()` over the full index | 2.5 ms | **59.7 ms** |
| retained by the index | 0.84 MB | 9.14 MB |
| `pageTextCache` duplicate of the text | +0.13 MB | +1.71 MB |

### Finding P0-1 — the quadratic is worse in wall time than in call count

The Arena predicted 337x by counting tokenizer calls. Measured wall time is
**331x**, and in absolute terms **26.9 seconds of pure CPU** to index the book
one page at a time. Confirms the incremental `upsertPage` rewrite (P2) as a hard
prerequisite: without it the walk is not slow, it is unusable.

### Finding P0-2 — NEW, not anticipated by the plan: `search()` costs 59.7 ms on a full book index

This was not measured during the Arena and it changes P5's scope.

A single BM25 `search()` over the 673-page index takes **59.7 ms** — roughly
**4x the 16 ms frame budget**. Two consequences:

1. **The red team's finding 1.1 is worse than stated.** Each background
   `notifyContextChanged()` tick would cost ~60 ms of main-thread search, not an
   unquantified "cycle". The plan's decision #4 (emit nothing from the walk) is
   confirmed as necessary, not merely tidy.
2. **An existing always-on path becomes janky purely as a side effect of a
   fuller index.** `PdfCaptureService.capture()` runs `searchIndex.search()`
   unconditionally (`pdfCaptureService.ts:78`) on **every** context capture —
   chip refresh, tab switch, active-context change. Today that search covers a
   handful of scrolled pages and is ~2 ms. Once the index is whole-document it
   becomes ~60 ms **on the renderer thread, on a path no setting gates**.

   This is a regression the feature would introduce into behavior the user never
   asked to change. P5 was scoped to *disclosure* ("say the coverage"); it must
   now also address *cost*. Options to decide at P5: memoize per
   `(documentId, query, indexedPages)`, move the capture-path search behind
   `pdfRagEnabled`, or cap the pages it scores. **Not decided here** — P5 owns it.

### Finding P0-3 — the 16 ms budget allows exactly one page per idle slice

Post-fix per-page indexing cost is `81 ms / 673 ≈ 0.12 ms`, negligible. The
dominant per-page cost is pdf.js extraction at **~12 ms** (briefing §2).

So one page per idle slice ≈ 12 ms, inside the 16 ms frame budget. **Two pages
per slice ≈ 24 ms would blow it.** Locking in: the walk processes exactly one
page per idle callback and never batches. This is now a design constraint, not
an implementation detail.

### Finding P0-4 — memory is acceptable; the deferral holds

Index 9.14 MB + duplicated text 1.71 MB ≈ **10.9 MB** for the largest real
document. Well under the 50 MB stop condition. The *duplication* specifically is
1.71 MB, under the 10 MB threshold the plan set for pulling that work forward,
so §5's deferral stands.

Worth recording: the index is **5.3x the size of the raw text** it indexes
(9.14 MB from 1.71 MB), driven by per-page token arrays and `termFrequency`
maps. Not a problem at 673 pages; it is the reason the page cap exists.

## Stop-condition re-check (required before P1)

| Condition | Status |
|---|---|
| Renderer blocks >16 ms per idle slice at one page/slice | **PASS** — ~12 ms/page, one page per slice (P0-3) |
| Retained memory >50 MB for the book | **PASS** — 10.9 MB |
| Making `PdfCaptureService` honest changes existing model input non-additively | **OPEN** — P0-2 shows it must change for *cost*, not only disclosure. Flagged to the user; P5 decides |
| Requires persisting the index or backend schema change | **PASS** — neither |

**No stop condition triggered. P1 may proceed.** P0-2 is a scope expansion inside
P5, not a halt — but it is a change from the approved plan and is reported to the
user rather than absorbed silently.

## Repository state at P0

- Branch cut from master `ca52774` (v0.53.0), clean tree.
- Full plugin suite green at P0 exit: **942 passed / 87 files**.
- Temporary measurement harness (`zz_p0_baseline.test.ts`) removed; suite
  re-verified green after removal.
- Four pre-existing unrelated stashes left untouched.
