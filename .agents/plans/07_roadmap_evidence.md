# v0.32.0 Evidence Ledger

Date: 2026-07-04

## Rollback Anchor

- Git base: `1842739` (`master`, merged PR #79).
- Worktree was clean before branch creation.
- Production DB backup is required before normalization; record its generated
  path after apply.

## Current Schema Reality

- Backend and plugin version: `0.31.0`.
- DB schema constant: 11.
- macOS local DB still exposes pre-v10 `external_path` / `import_origin`.
- `wiki paths migrate --json` reports exactly source ids 1, 27, and 30, all
  resolvable to Zotero keys `PZBCB9LJ`, `FTW7QHWY`, and `CA2VD8VR`.
- `.stignore` excludes `.curator/state.sqlite`, explaining device divergence.

## Pre-Validation

- `wiki status`: fails with `portable path migration required`.
- Resolver modules already implement the intended current contract.
- No application code was modified before this ledger.

## Post-Validation

Pending implementation, DB normalization, targeted tests, full CI, and testbed
smoke.
