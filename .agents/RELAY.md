# Cross-Agent Relay State

## Status
Persistent Quick Query Popover implemented on
`feature/persistent-quick-query-popover` as v0.15.0. Push + PR next.

## Done This Milestone
- Quick Query popovers are persistent: outside clicks no longer close an open
  popover.
- Popovers detach from selection scroll tracking once spawned; only the trigger
  button tracks the live selection.
- Header drag moves the popover within the owner window and cleans up temporary
  drag listeners.
- Minimize/restore collapses the body without losing answer, input, or follow-up
  state.
- Header title updates to the latest submitted question.
- Teardown order now removes old UI/listeners before switching active document
  in `openForCurrentSelection`.
- Docs synchronized: PLUGIN_SCHEMA §13 plus EN/KR PLUGIN_GUIDE.
- Version and changelog updated for v0.15.0.
- Plan, arena, and draft files deleted from the active workspace; Git history is
  the archive.

## Validation
- `npx vitest run -c ./vitest.config.ts` from `plugin/`: 52 files, 460 tests
  passed.
- `npx tsc -p tsconfig.json --noEmit` from `plugin/`: passed.
- `npm run build` from `plugin/`: passed.
- `scripts/backend-check ruff`: passed.
- `scripts/backend-check mypy`: passed.
- `scripts/backend-check pytest`: 959 passed, 6 skipped, 5 xfailed.
- Version consistency checked locally: backend pyproject, plugin package, and
  plugin manifest are all 0.15.0.

## Immediate Next Action
Push `feature/persistent-quick-query-popover` and open the PR.
