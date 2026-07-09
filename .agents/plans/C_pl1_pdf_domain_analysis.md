# PL-1 Domain Analysis C: External PDF View

Date: 2026-07-09

## Design Constraints From Codebase

- `externalPdfView.ts` is 1,909 LOC and exports PDF view constants,
  `ExternalPdfState`, and `ExternalPdfView`.
- It owns Obsidian view lifecycle, PDF.js loading/rendering, ToC, snipping,
  annotation overlays, runtime path state, portable Zotero resolution, and
  context events.
- `externalPdfState.ts`, `externalPdfRegistry.ts`, `incuratorQueryTrace.ts`,
  `chatSidebar.ts`, and `main.ts` import from this file.

## Docs/Specs Invariants

- `ExternalPdfState` must continue to omit non-portable absolute paths from
  persisted state.
- Convert-to-LaTeX must continue to route through backend PDF extraction model,
  not the main chat client.
- Zotero resolution must remain backend-first and cache invalidation rules must
  remain intact.

## Alternatives & Trade-offs

- Move `ExternalPdfView` class to `ui/pdf/ExternalPdfView.ts` and make old file a
  facade: clear ownership, requires updating source tests.
- Keep class in old file and move helpers only: safer first step, less LOC
  reduction.

## Final Decision

Move helper domains first, then move the class into `ui/pdf/ExternalPdfView.ts`
once all dependent tests target the new owner modules. The old
`ui/externalPdfView.ts` remains a facade exporting constants, types, and class.

## Implementation Pseudocode

```text
create ui/pdf/types.ts, toc.ts, toolbar.ts, snipping.ts, rendering.ts
move pure helpers and tests
update imports from externalPdfView.ts to ui/pdf modules where internal
after tests pass, move class to ui/pdf/ExternalPdfView.ts
re-export from ui/externalPdfView.ts
```
