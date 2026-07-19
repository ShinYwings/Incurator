# v0.36.0 PL-1 Evidence Ledger

Date: 2026-07-09

> Refreshed on 2026-07-19 after v0.35.0 shipped. This is the active P0 baseline
> for implementation on `release/v0.36.0`.

## Rollback Anchor

- Branch: `release/v0.36.0`
- Current head before PL-1 implementation:
  `9129908a0d305f726b30dc305ef927dc2cb20202`
- Merge base with `master`:
  `9129908a0d305f726b30dc305ef927dc2cb20202`
- PR #87 merged at the same commit on 2026-07-19.

## Current Worktree Reality

- Only relay/roadmap/plan activation metadata is modified at P0 start.
- No implementation, test, spec, guide, manifest, or lockfile is modified.

## Target File Sizes

```text
  2253 plugin/main.ts
  4889 plugin/src/ui/chatSidebar.ts
  2387 plugin/src/agent/llmClient.ts
  1909 plugin/src/ui/externalPdfView.ts
 11438 total
```

## Current Test Reality

- `npx vitest run -c ./plugin/vitest.config.ts`: 65 files, 678 tests passed.
- `npx tsc --noEmit -p plugin/tsconfig.json`: passed.
- `npm run build --prefix plugin`: passed at plugin v0.35.0.

## Code/Documentation Divergence Found at P0

- `PLUGIN_GUIDE_KR.md` still claims a dragged `ExternalPdfView` can restore
  after restart only from a captured absolute `doc.path` and must be re-dragged
  after moves. The active v0.29+ code/spec instead persists only
  `zoteroAttachmentKey` or portable `externalRef` and resolves the local path at
  runtime. The English guide has no matching stale section, so the EN/KR pair is
  also structurally divergent. P1 must add the correct English source section
  first, then replace the Korean text faithfully.

## Contract Constraints

- `PLUGIN_SCHEMA.md` says plugin UI owns transient chat/rendering state, while
  backend commands own durable DAG/source writes.
- Old public import paths are active:
  - `./src/agent/llmClient`
  - `./src/ui/chatSidebar`
  - `./src/ui/externalPdfView`
- Source-contract tests currently inspect the old source files directly and must
  move with the code they assert.
