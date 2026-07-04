# RELAY — v0.32.1 Release Ready

## Goal

Ship the cross-device sync identity isolation hotfix.

## Current State

- Branch: `hotfix/v0.32.1-sync-device-identity`
- Planning commit: `87fba01`
- Implementation commit: `3628625`
- Version: 0.32.1 / DB schema 11
- Root cause: macOS and Linux shared synchronized
  `.curator/sync_state.json`, reused `device_id=0782dbcf0ff4`, and treated one
  JSONL snapshot as their own.

## Implemented

- Device id, export timestamp, and peer high-water marks now live under
  backend-local `.cache/config/sync_state/<vault-hash>.json`.
- Vault-local sync state is unsupported and never read.
- JSONL transport and row-level LWW contracts are unchanged.
- Concurrent reads and disjoint-source edits remain supported; the user avoids
  editing the same source file concurrently on both devices.

## Validation

- Backend: 1190 passed, 6 skipped, 5 xfailed.
- Plugin: 666 passed.
- Ruff, mypy, TypeScript, production build, version consistency, and targeted
  44-test sync suite passed.
- Fresh `complex_math_backprop` testbed passed autosync, status, add, sync, and
  lint (100/100).

## Production

- Backup: `.cache/migrations/v0.32.1/20260704T042823Z/`.
- macOS backend/plugin 0.32.1 deployed.
- macOS generated distinct snapshot `dev-f6cf2f2ed380.jsonl`.
- Unsupported vault-local sync state was removed after backup.
- Linux Syncthing peer is currently disconnected, so final 32-source round-trip
  verification must occur when it reconnects.

## Immediate Next Action

Review and merge the v0.32.1 PR, then update/reconnect Linux and run autosync.

### Update (2026-07-04, Cross-Device Audit)

- User storage invariant: machine-local state belongs only in repo `.cache/`;
  portable/shared state belongs in vault `.curator/`.
- Reproduced four critical follow-ups: disjoint source loss from numeric id
  collisions, missing source deletion tombstones, stale generation status
  overwrite, and missing importer table allowlist.
- Found machine-local writes still under the vault: `state.sqlite` local tables,
  `runtime/`, `staging/`, `dashboard.md`, PDF page cache, PDF crops, and plugin
  CLI fallback cache.
- Shared singleton writers (`log.md`, `index.md`, `sync-report.json`, generated
  global projections) need an explicit writer/ownership contract even when the
  other device is read-only.
- No follow-up code was added to v0.32.1. Queue one coordinated v0.33.0 integrity
  release after PR #82 and Linux convergence verification.
