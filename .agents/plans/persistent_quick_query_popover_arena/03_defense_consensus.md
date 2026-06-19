# Defense And Consensus
Date: 2026-06-19 | Agent Persona: system_synthesizer

## 1. Consensus Decisions

- Keep `QuickQueryPopover` as a session-local raw DOM surface. No `ItemView`,
  no persisted session data, and no restart restoration.
- Make lifecycle manual: close button and Escape close the popover; outside
  clicks do not.
- Preserve outside-click removal of the trigger button when no popover is open,
  but make internal UI detection node-safe.
- Detach scroll tracking from the popover. Only the trigger button tracks the
  live selection. A spawned popover stays fixed until dragged or closed.
- Implement drag and minimize inside `quickQueryPopover.ts`; style only the
  existing quick-query CSS block.
- Use source-contract tests plus existing pure tests; do not introduce a DOM
  emulation dependency for this small milestone.

## 2. Implementation Safeguards

- Teardown before active document reassignment in `openForCurrentSelection`.
- `removePopover` must abort in-flight LLM calls and detach drag listeners.
- Drag listeners must be attached only during drag and removed on mouseup.
- Minimize must not clear turns, input value, or answer HTML.
- Dynamic title updates on submit, before the query starts, so a minimized
  popover is identifiable during streaming.
- Docs/specs must be updated before implementation is considered complete.
