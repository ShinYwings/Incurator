# Frontend Proposal: Session-Local Floating Tool Window
Date: 2026-06-19 | Agent Persona: frontend_architect

## 1. Core Logic & Implementation

Keep `QuickQueryPopover` as a raw DOM helper. Do not introduce an Obsidian
`ItemView`, persisted session record, or cross-window manager.

Implementation outline:

1. Add state fields:
   - `titleEl: HTMLElement | null`
   - `inputRowEl: HTMLElement | null`
   - `answerEl: HTMLElement | null`
   - `isMinimized: boolean`
   - `dragState: { startX; startY; startLeft; startTop; win } | null`
2. Fix teardown order:
   - Add a private `resetSurface()` or call `removeButton()` and
     `removePopover()` before mutating `activeDoc` / `anchorRange` in
     `openForCurrentSelection`.
   - Preserve `handleSelectionChange` behavior for normal selection changes.
3. Detach popover from scroll tracking:
   - `attachRepositionListeners` should only reposition `buttonEl`.
   - Popover placement is computed once in `openPopover`.
   - Dragging writes `style.left/top` directly and keeps `position: fixed`.
4. Replace outside-click dismissal:
   - `handleDocumentClick` should still remove the trigger button for outside
     clicks, but must never remove an open popover.
   - Use `target instanceof Node` and parent fallback so raw text-node clicks
     do not bypass internal UI detection.
5. Header controls:
   - Capture the title element.
   - Add minimize and close buttons as real buttons/spans with fixed class names.
   - Minimize toggles a class such as `is-minimized` on the popover, hides
     input/answer body via CSS, and leaves the header draggable.
6. Dynamic title:
   - On submit, update `titleEl` immediately to the question, shortened only by
     CSS overflow rather than mutating content.
7. Drag behavior:
   - `mousedown` on header starts drag unless the target is a header control.
   - Register `mousemove` and `mouseup` on the owning window only while dragging.
   - Clamp final position inside viewport margins using current window
     dimensions.
   - Remove drag listeners on mouseup and in `removePopover`.

## 2. Pros & Cons

Pros:
- Preserves the existing ephemeral raw-DOM architecture.
- Limits behavioral change to `quickQueryPopover.ts` and styles.
- Avoids global drag listeners except during active drag.
- Works in popout windows by using `activeDoc.defaultView`.

Cons:
- Pure unit testing of private DOM methods is limited under the current Node
  Vitest setup, so some coverage will remain source-contract based unless a
  DOM test harness is added.
- Header controls remain custom DOM rather than a shared component.
