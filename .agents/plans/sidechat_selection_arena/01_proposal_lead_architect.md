# Architecture Proposal: Reuse the LaTeX extractor + add a gated keyboard trigger

Date: 2026-06-11 | Agent Persona: lead_architect (The Proposer)

## 1. Core Logic & Implementation

### A. LaTeX-preserving selection capture (fixes symptom 1)
Add one exported pure helper in `utils/textUtils.ts`, reusing the existing
extractor, and route both popover capture paths through it:

```ts
/** Serialize a Selection to text, preserving MathJax formulas as $...$/$$...$$
 *  LaTeX when present (reads the annotation source, so it works whether the
 *  formula is rendered as SVG or swapped to text). Falls back to the plain
 *  string for non-math selections. */
export function selectionToTextWithLatex(selection: Selection): string {
  if (!selection || selection.rangeCount === 0) return "";
  const frag = selection.getRangeAt(0).cloneContents();
  if (!frag.querySelector("mjx-container, span.math")) {
    return selection.toString();           // unchanged fast path
  }
  return extractTextWithLatex(frag).replace(/\n{3,}/g, "\n\n").trim();
}
```

In `quickQueryPopover.ts`, replace `selection?.toString().trim() ?? ""` in
`handleSelectionChange` AND `openForCurrentSelection` with
`selectionToTextWithLatex(selection).trim()`. No other capture logic changes;
`MAX_SELECTION_LENGTH` slicing and rect/anchor handling stay.

Why this is timing-independent: `mjx-container` keeps
`annotation[encoding="application/x-tex"]` in BOTH the SVG and the swapped-text
states, so reading the DOM annotation never depends on the Live-Preview swap
having completed.

### B. Keyboard-selection trigger (fixes symptom 2)
In `main.ts` `registerQuickQueryDom(doc)`, add a `keyup` listener that fires the
same `handleSelectionChange` when a keyboard selection gesture just happened:

```ts
this.registerDomEvent(doc, "keyup", (e: KeyboardEvent) => {
  // Only react to selection-extending keys; ignore plain typing/navigation.
  const isSelKey = e.shiftKey &&
    (e.key.startsWith("Arrow") || e.key === "Home" || e.key === "End");
  const isSelectAll = (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a";
  if (!isSelKey && !isSelectAll) return;
  (doc.defaultView ?? window).setTimeout(
    () => this.quickQuery.handleSelectionChange(doc), 0);
});
```

`handleSelectionChange` already no-ops on empty selections and ignores its own
UI, so this is safe to call on every qualifying keyup. Registered for the main
document and every popout window, exactly like the existing `mouseup` path.

### C. Symptom 3 (partial LaTeX copy in the editor) — DEFER
The Ask-AI capture (A) already gives the user LaTeX-in-context. A robust
editor-level Cmd+C that preserves LaTeX for a partial selection requires either
the MathJax→KaTeX swap or a transparent-overlay span — both large and previously
reverted. Recommend keeping #3 in the ROADMAP backlog / Icebox, not this batch.

## 2. Pros & Cons
- **Pros**: zero new rendering code; reuses a tested extractor; capture fix is
  timing-independent; keyboard trigger reuses the existing safe handler; small,
  reversible diff; symptom 3's risk avoided.
- **Cons**: `keyup` adds a listener per document (perf — see red-team); the
  cloneContents path runs on every math-containing selection (cheap, already
  done for copy); relies on Obsidian's rendered DOM exposing the MathJax
  annotation in Live Preview (true for reading/preview; source-mode CM selections
  are already plain `$...$` text so the fast path covers them).
