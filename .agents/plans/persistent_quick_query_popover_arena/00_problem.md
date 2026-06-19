# Problem Briefing: Persistent Quick Query Popover
Date: 2026-06-19

## 1. User Request
Proceed with roadmap item 3: Persistent Quick Query Popover.

The current Quick Query Popover (`plugin/src/ui/quickQueryPopover.ts`) is an
ephemeral selection-anchored surface. It closes on outside click, follows the
selection while the background scrolls, and cannot be minimized or freely moved.
The user wants it to behave as a persistent reference window during document
analysis.

## 2. Source Draft
Primary briefing: `.agents/drafts/persistent_popover.md`.

Mandatory constraints from the draft:
- Click-away immunity: outside clicks must not close an open popover.
- Draggable header: users can move the popover freely across the viewport.
- Scroll detachment: once spawned, the popover stops following the selected
  text while background content scrolls; only the trigger button tracks the
  selection.
- Minimize toggle: collapse to a header-only bar without discarding the answer
  or follow-up state.
- Dynamic title: header title updates to the latest submitted question.
- Session-only lifecycle: do not persist across Obsidian restarts and do not
  convert this to an `ItemView`.

## 3. Review Findings To Preserve
The draft includes five review findings that must be addressed together:
1. `openForCurrentSelection` mutates `activeDoc`/`anchorRange` before teardown,
   so old popout-window listeners can leak.
2. `handleDocumentClick` mishandles raw text-node targets and must stop
   dismissing popovers entirely.
3. `attachRepositionListeners` currently repositions both button and popover;
   it must update only the button.
4. The header title span is not captured, so `runQuery` cannot update it.
5. Drag and minimize state are missing.

## 4. Current Code Reality
- `QuickQueryPopover` is a raw DOM helper created by `plugin/main.ts`.
- Main and popout documents register `mouseup`, selection-relevant `keyup`, and
  capture-phase `mousedown` events.
- `handleSelectionChange` ignores selections while a popover exists.
- `openForCurrentSelection` currently mutates active document/range before
  `openPopover`, and `openPopover` performs cleanup after that mutation.
- The current spec (`PLUGIN_SCHEMA.md` §13.4) says outside click can close the
  popover after an answer completes; this must change.

## 5. Definition Of Done
- Tests pin teardown order, click-away immunity, scroll detachment, dynamic
  title, drag hooks, and minimized CSS/state.
- Docs/specs describe the new manual lifecycle and persistent tool-window
  behavior.
- Plugin tests and TypeScript pass.
- Version and changelog are updated for `v0.15.0`.
