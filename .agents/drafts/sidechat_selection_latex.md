# Sidechat Selection & LaTeX Robustness Plan

## Context
Triaged from USER_REPORT on 2026-06-11. Consolidates the MathJax selection
timing bug (user-tagged [hotfix]) with the previously-logged low-priority
partial-selection LaTeX-copy problem. Root cause across all of these is that
MathJax renders formulas as SVG, which destroys the browser text selection
across formula boundaries.

## Observed Symptoms (verbatim evidence to preserve)
- **Popover Ask AI drops formulas when dragging over math.** In Obsidian Live
  Preview, clicking/dragging a formula swaps the on-screen MathJax (SVG) widget
  back to markdown text (`$...$`) in real time. On `mouseup` the popover reads
  the selection, but it reads the *previous* state (SVG) right before/while the
  DOM is swapped to text, so the entire formula is lost from the captured text.
- **Keyboard selection doesn't trigger Ask AI.** Dragging shows the Ask AI
  hover, but selecting a region via keyboard (Shift+Arrow) does not surface the
  Ask AI affordance.
- **Partial-selection LaTeX copy impossible** (existing low-pri item): because
  MathJax swaps formulas to SVG, copying only a drag-selected region with LaTeX
  intact doesn't work. Prior attempts — `pointer-events: none` CSS, Cmd+Shift+C,
  right-click menu — all copied the whole message and were reverted.

## Requirements
1. **Defer/normalize selection read on `mouseup`** so the popover captures the
   markdown text (`$...$`), not the stale SVG, after the Live Preview swap
   settles.
2. **Trigger Ask AI on keyboard selection** (Shift+Arrow), not just mouse drag.
3. **Enable partial-selection copy with LaTeX preserved.** Candidate solutions
   (priority low for #3):
   - (a) Replace MathJax with **KaTeX** — KaTeX preserves DOM text nodes, so
     browser selection works across formulas.
   - (b) Overlay a transparent text `<span>` carrying the LaTeX source on top of
     each `mjx-container`.

## Files Likely Involved
- Plugin Ask-AI popover / selection-capture logic
- Quick-query popover, sidechat message rendering
- Math rendering layer (MathJax → potential KaTeX swap)

## Notes
- Plugin-only TS work → needs `.test.ts` coverage.
- #1 and #2 are the urgent (hotfix-class) parts; #3 (KaTeX/overlay) is the
  larger architectural option and lower priority.
