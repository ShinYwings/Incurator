# Domain Analysis: v0.39.2 PDF Reference Review Hardening

Date: 2026-08-01

## Design Constraints from the Codebase

- `pdfReferenceContext.ts` owns bounded page refresh and reference serialization.
- `ChatSidebarView.ts` assembles provider context and currently invokes the
  latest-user resolver once per prompt-included PDF tab.
- External PDFs are read through the existing read-only plugin API; provider
  filesystem roots must not be widened.
- The adjacent scan order and cap are `[next1, prev1, next2, prev2]`.
- Existing tab/context source identity must be reused; basenames are ambiguous.

## Documentation and Spec Invariants

- Unresolved pointers must fail closed and must not silently explain the current
  page as the referenced target.
- Automatic latest-user resolution is for a PDF-focused turn.
- Exact label evidence such as `Eq. (10)` can resolve a pointer even when PDF
  extraction omits the rendered equation image.
- English guides are canonical and Korean guides are synchronized translations.

## Alternatives and Trade-offs

1. Increase BM25 thresholds: rejected because generic prose can still score
   highly and the contract requires exact evidence, not a tuned heuristic.
2. Expand the scan farther: rejected because it increases I/O and still cannot
   justify a loose fallback.
3. Disable background PDF prompt context: rejected because background PDF text
   can remain useful; only latest-user pointer claiming must be focus-gated.
4. Gate by filename: rejected because duplicate filenames are valid.
5. Exact-evidence fail-closed plus identity-based focus gating: selected as the
   smallest change that directly enforces both contracts.

## Final Decision

- After the bounded exact-label scan, suppress only unresolved single-number
  equation pointers that entered adjacent expansion; preserve all exact hits.
- Invoke latest-user PDF resolution only for the active PDF or a PDF explicitly
  referenced by user context, using canonical existing identity semantics.
- Do not change schemas, permissions, provider launch, request caps, or explicit
  selected/cropped pointer behavior.

## Implementation Pseudocode

```text
refs = resolve_on_current_page(query)
expanded = refs where kind == equation and one number and exact label absent

for page in bounded_adjacent_pages:
    exact = resolve_exact_labels(page, expanded)
    merge exact into refs
    remove exact targets from expanded
    if expanded empty: break

for ref in expanded:
    ref.method = unresolved

serialize only resolved refs

eligible(pdf, active, explicit_refs):
    return same_document(pdf, active_pdf)
        or any(same_document(pdf, explicit_pdf_ref))
```
