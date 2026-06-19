# Evidence Ledger: Purge Legacy QMD References

Date: 2026-06-20

## Rollback Anchor

- Base branch: `master`
- Starting branch: `fix/purge-legacy-qmd-references`
- Pre-work master head: `2e06157 chore(agents): mark persistent popover merged`

## Current Repository Reality

- Active plans: none before this plan.
- `USER_REPORT.md`: empty.
- Roadmap next item: item 4, Purge Legacy QMD References.
- Baseline active match count: 202 matches for case-insensitive `qmd` across
  `backend/src`, `backend/tests`, `plugin`, `scripts`, `docs/guides`,
  `docs/specs`, `AGENTS.md`, `CLAUDE.md`, and the active agent drafts/roadmap.

## Current Dirty Worktree

- Before authoring this plan: clean branch.
- This ledger, arena notes, master plan, roadmap, and relay updates are the only
  intended planning changes.

## Known Risk Areas

- Removing `qmd_*` status fields is a public status payload cleanup. The current
  plugin must be updated in the same branch.
- qmd URI normalization may still protect older vault content. Replace with
  generalized legacy URI stripping instead of dropping normalization outright.
- Query-expander structured output semantics must remain stable.
- Benchmark docs may intentionally discuss historical qmd parity. They should
  not block active functional cleanup unless agent-facing docs still imply qmd is
  installable or supported.

## Validation Targets

- Focused backend tests for status payloads, search-index refresh calls,
  query-expander parser behavior, and no-legacy-reference guard.
- Focused plugin tests/source-contract tests for dashboard/status `search_*`
  usage.
- `scripts/backend-check pytest`
- `scripts/backend-check ruff`
- `scripts/backend-check mypy`
- `npx vitest run -c ./plugin/vitest.config.ts`
- `npx tsc -p plugin/tsconfig.json --noEmit`
- `npm run build` from `plugin/`

