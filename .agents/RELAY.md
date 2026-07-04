# RELAY — v0.32.1 Sync Identity Hotfix

## Goal

Restore cross-device DB convergence after macOS and Linux reused the same synced
`sync_state.json` device id and overwrote one `dev-*.jsonl` snapshot.

Both backends may run concurrently and one may read while the other writes, but
the same source file is not modified concurrently on both devices. The hotfix
must preserve concurrent reads and disjoint-file work.

## Plan Reference

- `.agents/plans/02_sync_identity_hotfix.md`
- `.agents/plans/02_sync_identity_hotfix_evidence.md`
- `.agents/plans/sync_identity_hotfix_arena/`

## Current State

- Branch: `hotfix/v0.32.1-sync-device-identity`
- Root cause reproduced on production `second_brain`.
- macOS DB: L1-L4 = 28/353/1/1.
- Linux dashboard: L1-L4 = 32/0/0/0.
- Only one synced snapshot exists: `dev-0782dbcf0ff4.jsonl`.
- `.curator/sync_state.json` contains that id and is absent from the production
  `.stignore`, so both devices treat the same snapshot as their own.

## Immediate Next Action

Write failing cache-isolation and two-device convergence tests, then move sync
bookkeeping to backend-local `.cache/config`.
