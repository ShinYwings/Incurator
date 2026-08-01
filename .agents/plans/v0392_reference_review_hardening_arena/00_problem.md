# Briefing: v0.39.2 PDF Reference Review Hardening

Date: 2026-08-01
Source: Code review of draft PR #103

## Problem Statement

The v0.39.2 hotfix correctly resolves the real `수식 (10)` fixture, but review
found two correctness failures that must be fixed before merge:

1. After the bounded adjacent-page scan fails to find an exact equation label,
   `resolveSelectionReferences()` returns its last loose BM25 result. A
   diagnostic using current-page text `The equation system has 10 unknowns,
   but no numbered equation label is present.` and adjacent pages with no exact
   `Eq. (10)` label fetched pages `[6, 4, 7, 3]` and still emitted a
   `bm25-object` reference to page 5 with confidence `0.85`. This violates the
   documented fail-closed contract for unresolved pointers.
2. `buildIncuratorProviderContext()` runs latest-user PDF reference resolution
   for every prompt-included PDF tab. During a Markdown-focused turn, a
   background PDF split can therefore claim the same `수식 (10)` token and
   inject unrelated evidence. Multiple background PDFs can each claim it.

## Required Outcome

- A single-number equation pointer is emitted only when its target has exact
  equation-label evidence after the bounded scan; otherwise it remains
  unresolved and contributes no `<resolved_cross_references>` block.
- Latest-user PDF reference resolution runs only for the PDF document actually
  in focus for the turn: the active PDF tab, or a PDF explicitly referenced by
  user context.
- Existing explicit selected/cropped PDF pointer handling, provider filesystem
  isolation, request bounds, and the successful real page-6 fixture remain
  unchanged.

## Constraints

- No schema, migration, provider permission, or public API change.
- Preserve the existing four-page next-first adjacent scan cap.
- Add regression tests before changing runtime logic.
- Update the English contract first and keep the Korean guide synchronized.
- Do not rerun the live external provider replay; deterministic local tests and
  the existing isolated replay evidence are sufficient.
