# Independent adversarial proposal — PDF bibliography hotfix

## Scope and certainty

This is a read-only code investigation, not a reproduction of the user's actual
incident. The transcript establishes visible page 7, missing bibliography page
11, and a fabricated truncation explanation. It does not establish which PDF
viewer, provider, or exact bibliography format was used. Prior assistant claims
that the native viewer definitely caused this incident exceed available proof.

## Concrete failure paths

1. `plugin/src/context/pdfCapture.ts:getPdfContext` returns page/window content
   but no file identity. `plugin/main.ts:updateActiveContext` native-PDF branch
   stores that object unchanged, while filePath/absolutePath live one level above.
   `quickQueryPopover.ts:runQuery` builds `documentKey` only from pdfPage identity.
   Native viewer has no ExternalPdfView document ID either. Consequently
   `resolveSelectionContextAsync` supplies no CitationSource and bibliography
   retrieval returns before any page is fetched.
2. Fixing only documentKey is insufficient: `fetchActivePdfPage` reads identity
   from the current `activeContext.pdfPage`; native capture has none. Backend
   requests cannot reliably identify the PDF, and the viewer fallback supports
   only ExternalPdfView. Bind an absolute native file identity into the captured
   request, not merely the bibliography cache key.
3. Native `countPdfPages` infers total pages from the largest rendered DOM page
   number. In a lazy/partial DOM this may report 7 for an 11-page paper. A tail
   scan then never requests page 11. Obtain authoritative backend/PDF.js page
   count before scanning; do not call DOM maximum a complete document length.
4. `citationContext.ts:scanForBibliography` converts both fetch throws and
   undefined into empty strings. `loadBibliography` permanently caches the empty
   result. A temporarily unavailable backend, or a tab switch that correctly
   refuses a page, poisons follow-up retrieval until reload/explicit invalidation.
   Partial successful scans also become permanent partial bibliography caches.
5. Followups are individually re-resolved from captured selection + current
   question only. After asking for References, a question like "저자 전체 이름은?"
   triggers neither bracket nor bibliography detection. Cached bibliography is
   never consulted on that path, and followup history contains model answers,
   not previously retrieved source entries. This reproduces the conditions for
   unsupported continuation even after initial lookup succeeds.
6. `fetchActivePdfPage` accepts only optional ExternalPdfView document ID. Native
   undefined ID disables the guard. Each sequential request re-reads mutable
   `activeContext`, so switching native documents mid-resolution can read B and
   cache it as A. Even external capture can disagree with workspace active view:
   `refreshActiveContext` uses lastContentLeaf, ID/index lookup uses active view.
7. Bibliography parsing supports heading-anchored numbered `[N]` entries only.
   Author-year or `1.` entries are not resolved. Whole-list requests return the
   first 40 entries without revealing that selection; tail scan covers at most
   6–40 pages, continuation at most 5–20. No guarantee that "entire document was
   checked" is justified. Exact target entries beyond40 must remain findable.
8. Background formatting truncates per-page text and then the whole combined
   block, potentially cutting closing page tags. `fitTurnBudget` can separately
   truncate resolved-reference text. Existing citations carry no source page and
   provenance is UI-only. A model seeing `[...truncated]` lacks a robust statement
   of which source/page that marker belongs to. Prompt wording alone cannot
   guarantee no hallucinations.

## Smallest reliable fix

Capture an immutable PDF read handle from the same content leaf as selection:
document identity, authoritative total-page metadata or unknown, and a page
fetch closure bound to that exact document. For native PDFs, use the known
absolute path with existing backend context endpoint; fetch metadata first if
needed. For external PDFs, retain existing hash/attachment identity and a pinned
viewer fallback; verify viewer identity after async completion as well. A tab
switch must either keep reading A using its immutable backend args or report A
unavailable; it must never read B.

Use that handle for all reference and citation retrieval in a turn. Preserve
existing numbering disambiguation; for an explicit bibliography request provide
the actually retrieved bibliography section/page excerpts even if the numbered
parser cannot understand its style. Inspect known outline headings first, then
bounded tail scan; if unsuccessful but backend supports document search, use it
to locate References. Do not hide an arbitrary bounded scan as complete search.

Represent bibliography loading as successful pages + failed/unavailable pages +
matched entries (with originating page spans). Cache successful content per
document revision; retry failed pages on later turns. Cache a negative parse only
after the intended search range was successfully read. A missed continuation
must not permanently finalize a partial bibliography.

Keep the last retrieved bibliography evidence scoped to the current popover and
document identity, and reinject/re-resolve it on relevant followups. For short
ambiguous continuation the source evidence from the immediately preceding turn
is a better input than the prior model answer. Switching document resets that
source binding; it must not silently mix A's selection and B's evidence.

Emit truthful per-page/source coverage and per-entry truncation as part of source
blocks. Preserve attribution when fitting the turn budget (whole entries or
bounded excerpts with source labels). Tell the model previous assistant text is
not evidence that a page was read, and missing page data must not be attributed
to truncation of a different page. Acceptance is actual retrieval plus honest
coverage, not merely a refusal phrase.

## Behavioral regressions to write first

- Native viewer shows p7; backend p11 contains References with a distinctive
  author token. Ask bibliography question with no citation in selection. Assert
  p11 fetched using the captured native PDF absolute identity and token reaches
  final provider prompt.
- DOM contains only p7 while backend reports11 pages. The same request reaches
  p11; DOM maximum cannot bound document search.
- First request throws/returns undefined; second request succeeds. Same document
  now produces bibliography. Also fail one continuation page then retry it.
- Initial References question retrieves author token; followup "저자 전체 이름은?"
  retains real source evidence and does not rely solely on earlier model answer.
- During first async fetch switch PDF A to B; later fetches stay A or refuse;
  no B sentinel in A's prompt/cache/index. Cover native and external documents
  and content leaf versus chat-focused workspace view.
- Bibliography heading p11 with author-year entries reaches explicit bibliography
  request despite zero numbered matches. Requested numbered entry80 reaches
  prompt despite first40 wholesale list bound.
- Put `[...truncated]` only in page7 background; preserve successful page11
  bibliography and identify truncation as p7. Assert deterministic prompt
  attribution, not a mocked model claiming it will never hallucinate.
- Nonbibliography selection/code `arr[8]` avoids expensive scan; existing citation
  collision and bibliography continuation tests stay green.

## Release boundaries

No production `.venv`, MCP configuration, vault, DB migration or setup command is
required for this plugin hotfix. Implement in a master-based hotfix worktree,
include paired English/Korean docs and patch bump. Native backend page API can
be exercised with private fixture data. Do not deploy unfinished schema15 code
through editable runtime while fixing this UI path.
