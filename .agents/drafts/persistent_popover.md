# Draft: Persistent Quick Query Popover

## Problem Definition
The user requested the Quick Query Popover (`plugin/src/ui/quickQueryPopover.ts`) to be upgraded from an ephemeral, auto-closing floating element to a persistent, draggable, and minimizable tool window. Currently, the popover closes immediately when the user clicks outside (`handleDocumentClick`), is statically pinned to the text selection anchor, and cannot be collapsed without discarding the LLM exchange.

## "Why" This is Needed
Users analyzing long documents (e.g., PDFs or extensive markdown files) often need to reference an AI answer while simultaneously interacting with the primary document or other Obsidian panels. The ephemeral nature of the current popover forces users to re-run queries or lose the AI's output if they accidentally click away.

## Constraints & Architectural Vectors
1. **Persistence Constraint:** Modifying `handleDocumentClick` to prevent auto-close means the popover lifecycle is now explicitly manual (close button or Escape key). 
2. **Draggability & Scroll Detachment Constraint:** The current implementation uses `computeFloatingPosition` and `attachRepositionListeners` to pin the popover to the live selection rect (`anchorRange`). In complex Obsidian environments (Stacked Tabs, native PDF viewers, or multi-window popouts), tracking the `anchorRange` during a scroll event causes the popover to erratically move along the scroll instead of staying anchored. **Solution:** The popover must completely abandon automatic scroll-repositioning once spawned. It should act as an absolute floating palette within the active `Window` container (respecting `ownerDocument.defaultView`) and stay fixed relative to the viewport, fully ignoring background scroll events.
3. **Minimization Constraint:** Minimization requires state management. The popover DOM must toggle a minimized state where the input row and answer bodies are hidden (`display: none`), leaving only the header visible and accessible for dragging or restoring.
4. **Dynamic Title Constraint:** The header title (currently statically set to "Quick query") must dynamically update to reflect the user's most recent question. When a follow-up question is submitted, the title must immediately update to the new query string, allowing users to identify the context of the popover when minimized or placed alongside other windows.
5. **Session-Only Lifecycle (Future Work Context):** The popover must NOT attempt to persist across Obsidian application restarts. It is strictly an ephemeral session tool. The architectural pivot to a native Obsidian `ItemView` for restart persistence is explicitly deferred to Future Work. The current implementation must remain a raw HTML `<div>`.

## Success Criteria
- **Click-away Immunity:** Clicking anywhere else in the Obsidian workspace does NOT close the popover.
- **Draggable Header:** Clicking and dragging the `.ai-agent-quick-query-header` moves the `.ai-agent-quick-query-popover` freely across the viewport. Dragging detaches the auto-scroll pinning logic.
- **Minimize Toggle:** A new minimize button in the header collapses the popover's body, and clicking it again restores the previous dimensions and visibility.
- **Dynamic Header Title:** The `.ai-agent-quick-query-title` text updates dynamically to match the latest submitted question string.
- **No Side-Effects:** The original Quick Query context injection and Markdown rendering logic remain strictly intact.
