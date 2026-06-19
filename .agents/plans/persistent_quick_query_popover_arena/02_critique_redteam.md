# Critique on Frontend Proposal
Date: 2026-06-19 | Agent Persona: red_teamer

## 1. Vulnerabilities & Flaws

1. Drag listeners can leak if the popover is closed mid-drag unless
   `removePopover` explicitly tears them down.
2. Header drag can accidentally start when the user clicks minimize/close or
   selects title text unless controls are excluded and the header is
   `user-select: none`.
3. Minimized state can hide the input while a query is running, but the stream
   still updates a hidden answer element. This is acceptable only if restoring
   reveals the live/current content and closing still aborts.
4. If `handleDocumentClick` keeps removing the trigger button while a popover is
   open, the capture handler must not remove the popover's own button/control
   clicks. The internal UI detection must handle text nodes and child SVGs.
5. The existing spec says outside clicks close completed popovers. Failing to
   update `PLUGIN_SCHEMA.md` and EN/KR guides will leave the contract
   contradictory.
6. Converting to minor version `v0.15.0` requires synchronized version files and
   changelog even though the code change is plugin-only.

## 2. Suggested Alternatives

- Add `detachDragListeners()` and call it from `removePopover` before DOM
  removal.
- Use class-based control detection:
  `.ai-agent-quick-query-minimize, .ai-agent-quick-query-close`.
- Pin tests with focused source-contract assertions for:
  `detachDragListeners`, capture-safe `Node` target handling, absence of
  popover repositioning in `attachRepositionListeners`, title capture, minimize
  class, and version/docs text.
- Keep no-restart-persistence explicit in docs to avoid future scope creep.
