# 00 — Problem Briefing: Sidechat Selection & LaTeX Robustness

Date: 2026-06-11 | Target: v0.5.1 or v0.6.0 (open) | Branch: `feature/sidechat-selection-latex`
Source: `.agents/drafts/sidechat_selection_latex.md` (ROADMAP To-Do #1)

## User-reported pain (verbatim symptoms preserved)
1. **Ask AI popover drops formulas when dragging over math.** In Obsidian Live
   Preview, dragging a formula swaps the on-screen MathJax (SVG) widget back to
   markdown `$...$` text in real time. On `mouseup` the popover reads the
   selection but catches the SVG state right before/while the swap, so the whole
   formula is lost from the captured text. [user-tagged hotfix]
2. **Keyboard selection doesn't trigger Ask AI.** Mouse-drag shows the Ask AI
   button; selecting via keyboard (Shift+Arrow) does not surface it.
3. **Partial-selection LaTeX copy impossible** (existing low-pri): MathJax→SVG
   means copying only a drag-selected region with LaTeX intact doesn't work.
   Prior attempts (`pointer-events: none`, Cmd+Shift+C, right-click) all copied
   the whole message and were reverted.

## Repository reality (Evidence — verified 2026-06-11 on master @ afe8e60)
- **Capture uses `selection.toString()`** in `ui/quickQueryPopover.ts`
  `handleSelectionChange` (line 141) and `openForCurrentSelection` (line 175).
  `toString()` serializes an SVG-rendered formula to empty/garbled text → LaTeX
  is lost. The `mjx-container` for a formula CONTAINS its LaTeX source in
  `annotation[encoding="application/x-tex"]` regardless of SVG-vs-text state.
- **A LaTeX-aware DOM extractor already exists**: `utils/textUtils.ts`
  `extractTextWithLatex(node)` + `getLatexFromMathEl(el)` walk a node/fragment and
  emit `$...$`/`$$...$$` from `mjx-container` / `span.math` annotations. It is
  already used by `attachLatexCopyHandler` (chat copy) on
  `selection.getRangeAt(0).cloneContents()`. → Reusable for the popover capture.
- **Trigger is `mouseup`-only**: `main.ts` `registerQuickQueryDom` (line 138)
  registers `mouseup` → `setTimeout(0)` → `handleSelectionChange(doc)`, plus a
  `mousedown` capture for dismissal. There is NO `keyup`/`selectionchange`
  listener, so keyboard selections never trigger the button.
- The `setTimeout(0)` defer was added "so the browser finalizes the selection",
  but it does NOT fix symptom 1 because `toString()` on the SVG is still empty —
  the problem is the READ METHOD, not (only) the timing.

## Reframed problem statement
Symptom 1 is a **capture-method** bug, not a timing race: read LaTeX from the
DOM annotation (which is present in both SVG and text states) instead of
`toString()`, and the swap timing becomes irrelevant. Symptom 2 is a missing
event source. Symptom 3 is a separate, larger editor-copy concern the draft
already rates low-priority.

## Out of scope (explicitly)
- Replacing MathJax with KaTeX, or transparent LaTeX overlays (symptom 3's heavy
  options) — disproportionate; revisit only if symptom 1's fix proves insufficient.
- Chat-sidebar copy (`attachLatexCopyHandler`) — already works; untouched.
- PDF selection capture semantics beyond the shared text-extraction change.

## Success criteria
- Dragging a selection that spans a rendered formula and clicking Ask AI sends
  the formula as `$...$`/`$$...$$` LaTeX, not empty/garbled text — independent of
  the Live-Preview swap timing.
- A keyboard (Shift+Arrow) selection surfaces the Ask AI button, with no button
  spam on ordinary cursor movement (debounced, gated on non-empty selection).
- No regression to mouse-drag trigger, popout-window support, or PDF capture.
- `npx vitest` green; new unit tests for the shared selection-text extractor.
