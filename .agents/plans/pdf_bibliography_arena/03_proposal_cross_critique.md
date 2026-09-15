# Cross-critique of adversarial proposal

I read `/tmp/pdf_hotfix_adversary.md` after completing independent proposal01.
The independently identified native identity loss, mutable active-view reads,
negative-cache poisoning, numbered-only parsing, and reference-count truncation
agree with my findings. Two additions materially improve the synthesis:

1. Native DOM-derived page count is not authoritative. `pdfCapture.ts:428`
   derives the maximum page DOM attribute, so the captured count cannot safely
   define the search boundary when page11 has not been rendered. Fetch existing
   backend context metadata using the captured absolute native path before
   selecting tail pages. Without this, fixing path propagation alone still
   permits a page7-only lookup. This is essential, not optional polish.
2. Followup evidence must be retained. `quickQueryPopover.ts:535–614` resolves
   only captured selection and this question, while
   `quickQueryContext.ts:166–178` carries previous assistant prose. A question
   like “저자 전체 이름은?” following a References lookup can otherwise lose its
   source. Keep the immediately relevant successful bibliography evidence on the
   popover, bound to the same document; clear on document change. Reuse source
   evidence, not a claim reconstructed from assistant text.

Implementation scope cautions:

- An outline-first locator is reasonable if the existing capture already has
  a References heading. Do not add a new document-search API or ingest step to
  meet this hotfix; the existing context endpoint and bounded heading scan are
  sufficient for the reported 7→11 case. Report coverage honestly where the
  bounded search does not locate a section.
- A comprehensive author-year parser is unnecessary. The bibliography heading
  supplies structural anchoring; deliver exact observed page excerpts for the
  explicit bibliography question, with page and partial-range metadata.
- Scope the negative-cache change to failed reads and incomplete continuation.
  A genuinely fully retrieved negative result may still be cached as promised.
- Do not fix attribution merely by adding generic system instructions while
  retaining anonymous `[...truncated]` output. Keep page labels adjacent to
  actual excerpt clipping and test the final fitted prompt.
- Regression tests must reach the popover/source-capture boundary for native
  file identity and last-content-leaf behavior. Resolver-only fixtures that
  pre-supply correct documentId/pageCount would repeat the historical blind
  spot, even if labelled “end to end.”

With these constraints, the combined plan repairs existing reading capability
without becoming a second retrieval system or a full bibliography parser.
