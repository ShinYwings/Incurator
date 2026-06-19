# Domain Analysis: Quick Query Popover Lifecycle
Date: 2026-06-19

## 1. Design Constraints From Codebase

- `QuickQueryPopover` is instantiated once from `plugin/main.ts` and receives
  document-level mouse/key events from the main document and popout documents.
- The class owns raw DOM nodes (`buttonEl`, `popoverEl`) and active selection
  state (`activeDoc`, `anchorRange`).
- Existing tests are a mix of pure function tests and source-contract assertions;
  no browser/Obsidian DOM harness is present for private UI flows.
- Styles live in `plugin/styles.css` under the existing quick-query block.

## 2. Docs/Specs Invariants

- `PLUGIN_SCHEMA.md` §13 is authoritative for Quick Query behavior.
- `PLUGIN_GUIDE.md` and `PLUGIN_GUIDE_KR.md` must stay synchronized.
- Quick Query must remain ephemeral and must not write to chat session history.
- Active provider/model and `LLMClient` remain the execution path.

## 3. Alternatives & Trade-offs

- **ItemView migration**: rejected. It would solve persistence/dragging through
  Obsidian layout primitives, but violates the draft's session-only raw DOM
  constraint and expands scope.
- **Global floating-window manager**: rejected. There is only one popover
  instance and a local class is sufficient.
- **DOM harness for tests**: deferred. Source-contract tests match the current
  repository convention for Obsidian DOM UI and avoid introducing a test runtime.

## 4. Final Decision

Patch `QuickQueryPopover` directly:
- reorder teardown before state mutation;
- make click-away popover dismissal impossible;
- keep scroll tracking for the trigger button only;
- add dynamic title, drag state, and minimize state;
- add CSS for header controls, dragging affordance, minimized state, and stable
  compact layout.

## 5. Implementation Pseudocode

```ts
openForCurrentSelection(doc?) {
  const ownerDoc = ...
  const selection = ownerDoc.getSelection()
  if (!validSelection) notice
  const range = selection.getRangeAt(0)
  const rect = range.getBoundingClientRect()
  this.removeButton()
  this.removePopover() // detaches listeners using old activeDoc
  this.activeDoc = ownerDoc
  this.anchorRange = range.cloneRange()
  this.capturedSelection = ...
  this.openPopover(rect)
}

attachRepositionListeners() {
  handler = () => {
    const rect = this.anchorRange?.getBoundingClientRect()
    if (this.buttonEl) this.applyFloatingPosition(this.buttonEl, rect, BUTTON_SIZE)
    // No popover reposition here.
  }
}

handleDocumentClick(target) {
  const node = target instanceof Node ? target : null
  const el = node instanceof Element ? node : node?.parentElement ?? null
  if (el?.closest(ownUiSelector)) return
  this.removeButton()
  // Never removePopover() here.
}
```
