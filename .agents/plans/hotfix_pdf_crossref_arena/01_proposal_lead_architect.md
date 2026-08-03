# [Resolver] Proposal: Deterministic Cross-Reference Hotfix (F1–F3)

Date: 2026-08-03 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

### F1 — Theorem-family letter-prefixed numbers (RC1)
`crossReferenceResolver.ts:182` capture becomes `([A-Z]?\d+(?:\.\d+)*)`,
mirroring the section/appendix patterns. `objectNumber` flows through existing
uppercase normalization in `findCaptionEntry` / `sectionComponents`.
Consequence: `resolveWithNearbyPageHints` begins to fire for
`"Result A4.1-(p581)"`, transferring the (now correct, see F2) page target
onto the theorem reference.

### F2 — Printed→physical offset inference + fail-closed explicit pages (RC2)
1. New pure helper in `crossReferenceResolver.ts`:

```ts
export function inferPrintedPageOffset(
  pages: { pageNum: number; text: string }[]
): number | undefined
```

   Per page: scan the first 3 and last 3 non-empty lines for a standalone
   page-number token — `^\s*(\d{1,4})(?![\d.])` or `(?<![\d.])(\d{1,4})\s*$`
   (negative lookarounds reject `9.6`-style section heads). Candidate printed
   numbers give per-page deltas `physical − printed`. Return the modal delta
   iff it is supported by ≥ 2 distinct pages AND by a strict majority of pages
   that produced any candidate; else `undefined` (fail closed).
2. Wire `pageOffset: inferPrintedPageOffset(...)` into both `ResolveContext`
   builders in `pdfReferenceContext.ts` (sync: window pages; async: the
   growing `pageTextMap`, so fetched pages strengthen/repair the consensus).
3. **Delete the identity fallback** in `explicitPageTarget`
   (`crossReferenceResolver.ts:417-419`). Precedence stays
   `printedToPdf → pageOffset → unresolved`.
4. **Identity probe (async only)**: when a page ref stays unresolved because
   neither labels nor offset exist, fetch physical = printed (bounded by
   `pageCount`) once. Re-resolution recomputes the offset from the fetched
   page's own header: header confirms identity → resolves at offset 0; header
   reveals the true delta → next round fetches the right page; no header →
   stays unresolved. This preserves today's correct behavior for
   no-front-matter PDFs without ever trusting identity blindly.
5. **Post-fetch mismatch filter (async only)**: for `explicit-page` results,
   if a printed number is extractable from the fetched target page and it
   contradicts `ref.printedPage` (after mapping), demote to `unresolved`.

### F3 — Caption index covers the full theorem family + appendix alias (RC3)
1. `CAPTION_LINE_RE` gains
   `results?|corollar(?:y|ies)|propositions?|prop|definitions?|claims?|conjectures?`
   (all map to kind `"theorem"` via the existing `captionKind` default).
2. New helper `outlineNumberCandidates(title)`: `"Appendix 4 …"` yields
   `["4", "A4"]` (additive alias); non-appendix titles unchanged. Used by
   `matchOutlineBySectionNumber`, `resolveObjectOwningSection`, and
   `outlineRangeForNumber` (pdfReferenceContext) so `Result A4.1`-style
   anchors can locate their owning appendix range for outline expansion.

## 2. Pros & Cons

- **Pros**: every change is deterministic and unit-testable; the user's exact
  case is solved twice over (explicit-page path via F2, caption-index path via
  F1+F3 once page 599 enters the index); fail-closed everywhere replaces the
  one code path that violated the module's own "never inject misleading
  content" contract.
- **Cons / limits**: offset inference depends on printed headers/footers
  existing in the text layer (scanned PDFs without OCR page numbers stay
  unresolved — acceptable, fail-closed); the identity probe costs one extra
  page fetch in the rare no-mapping case; prose lines like "Results 3 and 4
  show…" can enter the caption index (pre-existing risk class, bounded by
  nearest-page selection).
