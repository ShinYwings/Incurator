# PL-1 Domain Analysis A: Chat Sidebar

Date: 2026-07-09

## Design Constraints From Codebase

- `chatSidebar.ts` is 4,895 LOC and exports `CHAT_VIEW_TYPE`,
  `MultiEditProposal`, and `ChatSidebarView`.
- It imports `ExternalPdfView`, backend clients, prompt/context helpers, diff
  viewer, Zotero utilities, file hashing, source-status helpers, and session
  utilities.
- `chatSidebarSource.test.ts` contains many source-string assertions against
  `chatSidebar.ts`; these must move to new owner modules as extraction happens.

## Docs/Specs Invariants

- Chat session persistence and prompt/context behavior described in
  `PLUGIN_GUIDE.md` must not change.
- Plugin authority boundaries in `PLUGIN_SCHEMA.md` remain unchanged: plugin UI
  owns transient chat UI and rendering, backend commands own durable DAG writes.

## Alternatives & Trade-offs

- Big-bang class split: fastest LOC reduction, highest risk of private-state
  leakage and broken tests.
- Helper-first extraction: slower, safer, preserves class lifecycle while moving
  pure rendering/context/session logic.

## Final Decision

Use helper-first extraction. Keep `ChatSidebarView` public and move concerns in
this order: context/status helpers, message/edit rendering, session drawer,
drag/drop, then remaining view orchestration.

## Implementation Pseudocode

```text
create ui/chat/
move pure context/status helpers -> ui/chat/contextRefs.ts
move source-contract tests for those helpers -> ui/chat/contextRefs.test.ts
update chatSidebar.ts imports
run focused + full vitest
repeat for messageRendering, sessionDrawer, dragDrop
```
