# v0.32.1 Sync Identity Hotfix Evidence Ledger

Date: 2026-07-04

## Rollback Anchor

- Base: `master`
- Anchor: `a8c656278bc54c01c6fc16f2465bf05b30e26fe9`
- Branch: `hotfix/v0.32.1-sync-device-identity`

## Current Schema Reality

- Backend version 0.32.0; DB schema 11.
- User-confirmed operating invariant: macOS and Linux backends may run
  concurrently and one may read while the other writes, but the same source
  file is not modified concurrently on both devices.
- No schema change planned.
- JSONL export includes sources, compiler generations, knowledge units,
  community reports, and synthesis nodes.

## Production Baseline

- macOS: 28 sources, 28 L1, 353 verified authoritative KUs, 1 live report,
  1 synthesis node.
- Linux Dashboard: 32 L1, 0 L2, 0 L3, 0 L4.
- Shared snapshot count: one (`dev-0782dbcf0ff4.jsonl`).
- macOS `sync_state.json`: `device_id=0782dbcf0ff4`, no peers.
- Production `.stignore` omits `sync_state.json`.
- Dry-run: zero imported files, `would_export=false`.
- Snapshot write time and local `last_export_ts` disagree, proving another
  device wrote the same filename.

## Pre-Implementation Validation

- Existing targeted sync/runtime suite:
  `test_db_autosync.py`, `test_cli_db_autosync.py`, `test_runtime_state.py` —
  41 passed.
- Coverage gap: no test starts two backends with one synchronized
  `.curator/sync_state.json` id.

## Post-Implementation Validation

- Cache isolation: passed; vault-local shared ids are ignored and state files
  are namespaced under isolated backend cache roots.
- Two-device convergence: passed; simulated macOS/Linux backends starting with
  the same old id emitted distinct snapshots and retained both devices' rows.
- Targeted sync/CLI/runtime suite: 44 passed; Ruff passed.
- Full backend/plugin CI: pending.
- Production recovery: pending.
