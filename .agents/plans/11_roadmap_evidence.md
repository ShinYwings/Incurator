# v0.36.0 PL-1 Evidence Ledger

Date: 2026-07-09

> Deferred on 2026-07-19. Re-capture rollback anchors, file sizes, and test
> baselines after v0.35.0 ships; the evidence below remains the original
> planning snapshot only.

## Rollback Anchor

- Branch: `release/v0.35.0`
- Current head before PL-1 planning: `61c585423556cf5e26f98ecd634fb43e7e6d65e8`
- Merge base with `master`: `bcc4ac2d66d457670f1ed675c79d231b697af76e`
- PR #85 merged at `3fd9abfae290a1a74403e24cc9331aaf4f31776f`.

## Current Worktree Reality

- One untracked briefing exists: `.agents/drafts/11_pl1_plugin_decomposition.md`.
- No implementation files are modified at planning start.

## Target File Sizes

```text
  2224 plugin/main.ts
  4895 plugin/src/ui/chatSidebar.ts
  2382 plugin/src/agent/llmClient.ts
  1909 plugin/src/ui/externalPdfView.ts
 11410 total
```

## Current Test Reality

- `npx vitest run -c ./plugin/vitest.config.ts` passed:
  65 test files, 669 tests.

## Contract Constraints

- `PLUGIN_SCHEMA.md` says plugin UI owns transient chat/rendering state, while
  backend commands own durable DAG/source writes.
- Old public import paths are active:
  - `./src/agent/llmClient`
  - `./src/ui/chatSidebar`
  - `./src/ui/externalPdfView`
- Source-contract tests currently inspect the old source files directly and must
  move with the code they assert.
