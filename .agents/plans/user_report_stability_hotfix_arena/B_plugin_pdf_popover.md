# Domain Analysis: Plugin PDF, Popover, and Source Badge Stability

Date: 2026-06-25
Scope: reports 2, 5, 6, 7, 9, 12, 13, 14.

## Design Constraints From Codebase

- `plugin/src/ui/chatSidebar.ts` owns source badges and sidechat markdown render.
- `plugin/src/ui/quickQueryPopover.ts` renders popover answers and attaches
  `attachLatexCopyHandler`, but does not call `stampMathSourceData` like sidechat.
- `plugin/src/context/crossReferenceResolver.ts` detects `Eq. (19.6)` but not a
  bare parenthesized equation reference like `(19.11)`.
- `plugin/src/ui/externalPdfView.ts::convertSelectionToLatex` sends selected text
  through backend transcription, which can add latency and model prose.
- `plugin/src/ui/quickQueryPopover.ts::openForCurrentSelection` removes the
  existing popover before opening a new selection, so only one quick query can
  stay visible.

## Docs / Specs Invariants

- Source states `l1_ready..l4_ready` render as inert `Added`; `queued` and
  `running` keep their own labels and informational click behavior.
- Passive PDF context must not import/register PDFs.
- Quick query may include resolved references and PDF outline/window context.
- Quick query is ephemeral and not chat history, but multiple popovers may
  coexist if each one owns independent follow-up state.

## Alternatives & Trade-Offs

- Keep `Queued`/`Building...` distinct from `Added`, but never show actionable
  Add Source after successful registration.
- Reuse sidechat `stampMathSourceData` in popover rather than duplicating copy
  logic.
- For Convert-to-LaTeX text selections, keep the LLM-backed dedicated backend
  extractor path. The bug is provider/prompt/output discipline: it must use the
  `plugin pdf transcribe` resolver (`latex_extract_model → vision_model →
  main-if-vision`) and output only faithful LaTeX+text, without explanatory prose.
- For `(19.11)`, add bare-equation detection and use existing local PDF search
  hits first; backend fallback is a later phase if local index is insufficient.
- Profile PDF jank before changing render/capture cadence.
- Preserve existing quick-query popovers by creating an independent popover
  session for each selection.

## Final Decision

Plugin implementation should:

1. Ensure source status writer/reader use the same status key after registration.
2. Prevent registered sources from reverting to actionable Add Source.
3. Stamp quick-query rendered math with source LaTeX before copy handling.
4. Resolve bare parenthesized equation references using the same priority model
   as sidechat: local visible/window PDF context first; backend read-only PDF
   context/search only when local context is insufficient and a tracked/resolvable
   identity exists; never passive auto-ingest.
5. Verify curator wikilink postprocessing applies to popover/sidebar outputs.
6. Profile and patch PDF scroll jank only after measurement.
7. Allow multiple quick-query popovers to coexist without sharing follow-up
   memory or writing to sidebar history.

## Implementation Pseudocode

```text
test_quick_query_render_stamps_math_source
test_extract_bare_parenthesized_equation
test_pdf_reference_uses_rag_hits
test_source_badge_post_ingest_status_key
test_convert_selection_to_latex_dedicated_extractor_output_only
test_open_current_selection_preserves_existing_quick_query_popover
```
