# Critique on the Citation-Chase / Fetch-Ladder Proposal
Date: 2026-08-09 | Agent Persona: red_teamer
Convener note: the four decisive claims were independently re-verified. Evidence inline.

## 1. Vulnerabilities & Flaws (verified subset)

### 1.1 [CONFIRMED] The tool budget cannot hold the ladder
`LLMClient.ts:945` — `const MAX_RECURSION = 5`, shared across every tool family,
with the final round stripping tools to force an answer. A 4-rung ladder costs up
to 4 rounds to land content *once*; depth-2 chaining repeats it. The proposal's
own budget (4 external lookups, depth 2) cannot fit.

### 1.2 [CONFIRMED — the decisive one] `isScannedLike` is blind to the actual case
`pdfTextLayout.ts:193-199`:
```
isScannedLike = source === "none" || charCount < 20 || wordCount < 4
             || alphaNumRatio < 0.10 || brokenCharRatio > 0.35 || score < 0.10
```
All page-level aggregates. Measured on the real target — page 11 of the paper,
the page whose equation (29) IS a picture:
```
charCount: 3354   wordCount: 855   -> isScannedLike = false
```
A text-dense page with one rasterized equation scores healthy and never
escalates. **The signal is structurally incapable of detecting the failure this
feature exists to fix.**

### 1.3 [CONFIRMED] Popover is zero-MCP, so most rungs are unreachable there
`messageUtils.ts` `shouldInjectMcpTools` returns false for `"local-only"`. The
popover — the surface the user named FIRST — cannot reach `search_curator`,
Zotero tools, or any MCP rung.

### 1.4 [CONFIRMED] The wikilink provenance chip would always fire on the popover
`quickQueryContext.ts` contains **zero** occurrences of `[[`. The popover model
is never told wikilinks exist, so a render-time "no citation found" check is a
constant false negative on that surface.

### 1.5 `[8]` extraction is syntax-overloaded and the bibliography is not loaded
No existing pattern reuses a bare `[...]` delimiter. Footnote markers (`[^8]`),
markdown reference links (`[text][8]`), and array indices in CS papers all
collide. Worse, `resolveOne` resolves via an outline or a caption index built
from **already-fetched pages** — and the References section is back-matter the
reader is never near when a mid-document `[8]` is clicked.

### 1.6 Deleting the general-knowledge mandate removes the popover's only fallback
That string exists exactly once, scoped to `"local-only"`. Given 1.3, popover
resolution will fail often; deleting the fallback with nothing in its place is a
regression dressed as a prompt diet.

### 1.7 Vault-wide BM25 would copy a quadratic pattern
`pdfDocumentIndex.ts` `upsertPage` rebuilds the whole index per call (measured
elsewhere at 331x linear for 673 items). Applying that shape to 137+ vault files
is a different cost class than the per-PDF index it is modelled on.

## 2. Suggested Alternatives
- Split the ladder by surface; do not promise the popover what its tool policy forbids.
- Decide text-vs-pixel **per region**, not per page, using layout data.
- Design the round budget for the ladder's shape deliberately; do not ship against an unexamined constant.
- Track provenance from the tool results actually fetched, not by regexing output syntax one surface was never taught.
- Keep an honest fallback wherever the ladder is least reliable.
- Route vault-wide retrieval through the DB-native search the backend already maintains rather than a second, weaker in-memory BM25.
