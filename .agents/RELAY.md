# Cross-Agent Relay State

## Goal
Persistent Quick Query Popover (`v0.15.0`) on
`feature/persistent-quick-query-popover`.

## Plan Reference
- Master plan: `.agents/plans/04_persistent_quick_query_popover.md`
- Evidence ledger: `.agents/plans/04_persistent_quick_query_popover_evidence.md`
- Domain analysis: `.agents/plans/A_quick_query_popover_lifecycle.md`
- Arena: `.agents/plans/persistent_quick_query_popover_arena/`

## Analysis & Reasoning
- Inbox is empty; roadmap item 3 is the next actionable item.
- The current popover implementation closes on outside click, follows the live
  selection while scrolling, mutates active document/range before teardown in
  `openForCurrentSelection`, and lacks title/minimize/drag state.
- Current docs/specs say outside click can close a completed popover, so docs
  must change before the implementation is complete.

## Progress Status
- Branch created from `master`.
- Arena problem/proposal/critique/consensus written.
- Domain analysis, evidence ledger, and master implementation plan written.
- No application code has been changed yet.

## Critical Context / Blockers
- Must stop for user approval before coding per the plan-first workflow.
- Scope explicitly excludes `.agents/drafts/popover_tool_scope.md` and restart
  persistence.

## Immediate Next Action
Await user approval of `.agents/plans/04_persistent_quick_query_popover.md`.
After approval, start P1/P2: docs-first contract update and failing tests.
