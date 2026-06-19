# Cross-Agent Relay State

## Status
Persistent Quick Query Popover implemented on
`feature/persistent-quick-query-popover` as v0.15.0.

PR opened: https://github.com/ShinYwings/Incurator/pull/37

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
- PR #37 follow-up review fixes addressed: trigger scroll listeners detach
  when the persistent popover remains open, Escape handling is scoped to popover
  focus, and active spec headers/tests are synchronized to v0.15.0.

## Validation
- `npx vitest run -c ./vitest.config.ts` from `plugin/`: 52 files, 460 tests
  passed.
- `npx tsc -p tsconfig.json --noEmit` from `plugin/`: passed.
- `npm run build` from `plugin/`: passed.
- `scripts/backend-check ruff`: passed.
- `scripts/backend-check mypy`: passed.
- `scripts/backend-check pytest`: 959 passed, 6 skipped, 5 xfailed.
- PR #37 follow-up validation:
  - `npx vitest run -c ./vitest.config.ts src/ui/quickQueryPopover.test.ts`:
    17 tests passed.
  - `npx vitest run -c ./vitest.config.ts`: 52 files, 462 tests passed.
  - `npx tsc -p tsconfig.json --noEmit && npm run build`: passed.
  - `scripts/backend-check pytest backend/tests/test_spec_sync.py`: 9 passed.
  - `scripts/backend-check pytest`: 959 passed, 6 skipped, 5 xfailed.
  - `scripts/backend-check ruff`: passed.
  - `scripts/backend-check mypy`: passed.
- Version consistency checked locally: backend pyproject, plugin package, and
  plugin manifest are all 0.15.0.

## Immediate Next Action
Wait for GitHub CI on PR #37, then merge if checks pass.
