# PDF bibliography hotfix — independent proposal

## Verified behavior versus incident hypothesis

The user's acceptance condition is substantive: while reading page 7, a
bibliography question must fetch the document's References content on page 11
and include it in the actual outgoing turn. A disclaimer alone does not restore
the feature. The exact incident document, viewer type and outgoing payload have
not been observed; the earlier claim that a native-view identity failure caused
this particular incident is a plausible hypothesis, not established fact.

Verified source defects and existing capabilities:

- `plugin/src/context/citationContext.ts:111` already calls
  `asksAboutBibliography(question)`. Lines 119–124 deliberately bypass the
  numeric-bracket early-out for an explicit bibliography question. Thus “the
  selection had no [N], so no fetch was attempted” is not a sufficient diagnosis.
- Native capture `plugin/src/context/pdfCapture.ts:18–68` returns page content,
  count and window, but no document identity or file path. In
  `plugin/main.ts:2111–2118`, native `pdfCtx` is assigned without enrichment.
  `quickQueryPopover.ts:589–593` obtains its cache key only from `pdfPage`
  fields. The top-level `activeContext.filePath` is available but unused here.
  `pdfReferenceContext.ts:564–580` then passes no citation source, causing
  `citationContext.ts:103` to return before fetching. This is a real native-path
  defect regardless of whether it caused the report.
- Even adding only that cache key is insufficient: `main.ts:1917–1924` sends
  `pdf.filePath/hash/zoteroAttachmentKey` to the backend. Native capture supplies
  none. Its viewer fallback at line 1934 only supports ExternalPdfView.
- ExternalPdfView supplies document ID and path at
  `plugin/src/ui/pdf/ExternalPdfView.ts:588–607`; its ordinary reference path
  should work for numbered entries. However fetch identity and index retrieval
  use the currently focused external view (`main.ts:1909,1943,1949`), whereas
  `refreshActiveContext` reads the last content leaf (`main.ts:1889–1893`). Those
  sources can differ while chat/popover input has focus. A multi-page turn must
  bind metadata, fetch target and index to one captured document.
- `citationContext.ts:176–179` converts a thrown/undefined page fetch into empty
  text. Lines 155–158 cache even an empty scan indefinitely. A transient backend
  outage becomes a lasting negative result until explicit cache eviction.
- The bibliography parser accepts only line-initial `[N]`
  (`citationResolver.ts:104,193`). A `References` page with author-year entries
  or `1.` numbering produces no parsed bibliography. `citationContext.ts:189`
  consequently rejects that heading before reading continuation pages. Raw
  References text is never included as an alternative.
- Whole-list fallback is capped at the first 40 numeric entries
  (`citationContext.ts:132–136`). The generic question “reference 90” does not
  identify 90 through the bracket parser, so its answer can still be absent.
  Existing tests only exercise reference 12 among three entries.
- Existing spec §13.7b (around line 3000) still describes a fixed six-page scan
  and no-bracket early-out; current code uses scaled bounds and explicit
  bibliography intent. Update that stale description as part of the fix.

## Minimal implementation proposal

1. Capture a single document-bound page reader before the first await. It owns
   path/hash/key, document ID, page count, known pages and optional external
   viewer/index. Native capture must expose its own leaf's file path (never
   another active leaf's path), and backend requests must use that same source.
   Extend the existing fetch helper or add a small helper; do not route fetches
   through mutable active context during the loop. Preserve the existing
   backend-first/custom-viewer fallback and wrong-document guards.
2. Keep the existing bounded bibliography scan, but make its result contain
   both parsed entries and observed heading-anchored raw page excerpts plus
   attempted/successful/failed page numbers. Detect the heading independently
   of `[N]` parsing. For explicit bibliography questions, deliver raw excerpts
   when numbering cannot be parsed, so author-year bibliographies remain
   answerable. Do not invent a new author-name matching engine or ingest the
   whole document. Numeric `[N]` selections retain strict collision rejection.
3. Resolve explicitly named reference numbers before applying whole-list caps;
   for free-form bibliographic asks, deliver the bounded raw bibliography
   section instead of silently substituting the first 40 entries. Preserve
   page labels and mark actual clipping at the evidence block that is clipped.
4. Cache successful content; cache a negative result only if every requested
   page was actually retrieved. Never cache undefined/throw as empty success.
   A failed continuation must not freeze an incomplete bibliography for later
   questions. Maintain current per-document reload eviction.
5. Build the outgoing prompt and UI provenance from that retrieval result.
   Explicit questions whose retrieval failed get an actionable failure state
   after the real attempt; prompts must not imply that unobserved pages were
   fetched/truncated. Missing guessed citation numbers in ordinary code still
   disappear silently as the existing contract requires. Do not claim this
   alone guarantees arbitrary model output never hallucinates.

## Regression tests and acceptance evidence

- Through the popover preparation boundary with native capture, visible page
  7, total pages 11, and References only on 11: ask in Korean without selecting
  `[N]`; assert backend receives this PDF's path and page 11 and the final LLM
  message contains the reference author/title, not merely status metadata.
- Repeat for ExternalPdfView with the popover focused and with another PDF
  becoming active between sequential fetches; no foreign content may be
  returned or inserted into the first document's cache/index.
- References on page 11 with author-year text and with `1.` style: outgoing
  turn includes the actual heading-anchored page text without claiming a
  fabricated numeric citation match.
- First lookup throws or returns undefined; second lookup succeeds under the
  same document key. The second must refetch and deliver the bibliography.
  Repeat for failure after a successfully parsed heading page.
- Numbered entry 90 among >40 entries: a typed “reference 90” delivers entry 90.
  Preserve bracket collision/no-bibliography-intent no-fetch tests.
- A genuine fetch failure marks that page unavailable, while any page-7 context
  clipping is scoped to page 7. Never generate “page 11 was truncated” when it
  was never returned. Test final prompt assembly, not only resolver output.

No environment changes, live DB work, full-document ingest or provider call is
needed for these regressions. Actual incident cause remains qualified until a
runtime reproduction or outgoing payload establishes it.
