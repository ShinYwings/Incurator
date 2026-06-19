# Evidence Ledger: Persistent Quick Query Popover
Date: 2026-06-19

## 1. Rollback Anchor

- Branch: `feature/persistent-quick-query-popover`
- Base at branch creation: `e478bd5 chore(agents): mark diff viewer release merged`
- Current worktree before planning edits: clean on `master`, then new branch.

## 2. Current Repository Reality

- `USER_REPORT.md` is empty.
- `RELAY.md` was IDLE and named Persistent Quick Query Popover as next action.
- Roadmap item 3 is the next actionable item.
- `.agents/plans/` did not exist before this milestone and is created for the
  plan artifacts.

## 3. Current Code Reality

- `plugin/src/ui/quickQueryPopover.ts` currently:
  - closes the popover on outside click after processing completes;
  - repositions both trigger button and popover on scroll/resize;
  - mutates `activeDoc` and `anchorRange` in `openForCurrentSelection` before
    `openPopover` cleanup;
  - does not capture the title element;
  - has no drag or minimize state.
- `plugin/main.ts` registers quick-query document handlers for main and popout
  documents.
- `plugin/src/ui/quickQueryPopover.test.ts` already covers message building,
  floating position, thinking stripping, and source-contract checks for LaTeX
  capture/rendering.

## 4. Documentation Reality

- `docs/specs/plugin_schema/PLUGIN_SCHEMA.md` §13.4 currently says outside
  clicks can close the popover after an answer completes.
- EN/KR plugin guides describe the popover as minimal and follow-up capable but
  do not describe persistence, dragging, minimize, or dynamic title.

## 5. Validation Plan

- Focused plugin tests:
  `npx vitest run -c ./vitest.config.ts src/ui/quickQueryPopover.test.ts`
- Full plugin checks:
  `npx vitest run -c ./vitest.config.ts`
  `npx tsc -p tsconfig.json --noEmit`
  `npm run build`
- If implementation stays plugin-only, backend checks are not part of the
  critical path, but version consistency must be checked after the bump.

## 6. Rollback Requirements

- No DB/schema migration is expected.
- Rollback is a normal git revert of the feature branch commits.
- No production vault paths or `.curator/` state should be modified.
