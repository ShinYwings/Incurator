# v0.30.0 Evidence Ledger — Cross-Device State Sync

Date: 2026-07-02 | Plan: `06_cross_device_state_sync.md`

## Rollback Anchor
- Git SHA at coding start: `58ee9f533ee7680ba5e167fc70923e78440dfadd`
  (branch `fix/zotero-profile-sync`).
- Live vault DB snapshot copied to scratchpad:
  `state.sqlite.rollback-58ee9f5…` (restore target if migration/`.stignore`
  change misbehaves on `second_brain`).

## Current Repository & Schema Reality (verified)
- `db.SCHEMA_VERSION == 10`; `PRAGMA journal_mode=WAL` set in both `init_db`
  and `connect` (`db/schema.py:1321,1362`).
- All `state.sqlite` access goes through the per-operation `db.connect()`
  context manager (closes each call). No long-lived connection to `state.sqlite`
  exists; MCP server uses `with db.connect(...)` per tool call. Concurrency
  (MCP + CLI/plugin) is the real staleness trigger, not a single leaked handle.
- Live `second_brain` DB: 32 sources, 31 `l1_status='done'`, 1 reference-mode.
  Full column scan across all tables: **zero absolute paths** → DB is portable.
- `.stignore` (vault + `backend/.../templates/stignore.template`) currently
  excludes `.curator/state.sqlite`, `.curator/qmd/index.sqlite`, `*.sqlite-*`,
  `*.db-*`, and the plugin `data.json`.

## Baseline Measurements
- `wiki status --json` on `second_brain`: `sources.total = 32`;
  `layer_counts = {contexts: 65, atoms: 353, concepts: 0, synthesis: 0}`.

## WAL/Syncthing Reproduction (empirical, P0)
Copy-only-main-file (Syncthing semantics), concurrent reader open:
- **idle concurrent reader**: no-truncate → synced copy has **0/100** rows
  (STALE); `wal_checkpoint(TRUNCATE)` after commit → **100/100** (complete).
- **pinned mid-transaction reader**: TRUNCATE returns BUSY → cannot flush
  (best-effort limitation; documented — "don't build on two devices at once").

## Current Dirty Worktree
- Modified: `plugin/package-lock.json`.
- Untracked (unrelated): `.agents/drafts/sidechat_ui_regression_v0.29.0.md`.
- New this task: `.agents/plans/06_*`, `.agents/plans/cross_device_state_sync_arena/`,
  `backend/tests/test_db_sync_safety.py`, RELAY/ROADMAP updates.

## P0 RED Tests (confirmed failing)
`backend/tests/test_db_sync_safety.py`:
1. `test_connect_flushes_wal_so_syncthing_copy_is_current` — FAILS (0/100 rows
   in synced copy). Green after P2 checkpoint-truncate.
2. `test_connect_rejects_newer_ondisk_schema_version` — FAILS (no guard). Green
   after P2 schema-drift guard.

## P1 Pivot Evidence (added 2026-07-02, spec reconciliation)
- SYSTEM_BEHAVIOR §13.1 defines the shipped autosync: one-writer-per-file JSONL
  snapshots, row-level LWW + tombstones; `db_sync.SYNC_TABLES` covers all 26
  knowledge tables incl. `sources`. `state.sqlite` device-local **by design**.
- Live vault forensics:
  - `.curator/sync/dev-0782dbcf0ff4.jsonl` (only file; no macOS peer file) was
    **stale**: 5 sources, exported 2026-06-30T18:54:02Z; DB max LWW ts
    2026-07-01T21:10:00Z; `local_has_unexported_changes() == True`.
  - `sync_state.json`: `peers: {}` — linux never imported any peer.
  - Plugin `data.json`: `incuratorEnabled=false` on linux → `setupAutoSync()`
    early-returns (main.ts:1920) → zero plugin triggers on the primary ingest
    device. `autoSyncEnabled=true` (irrelevant — outer gate wins).
  - Vault `settings.yml`: `auto_sync.enabled: false`; `config.py` default also
    `false`; `_maybe_auto_export` called ONLY from `wiki update` (cli.py:3471)
    though config.py:262 documents add/build/sync/update.
  - Manual `wiki db autosync` (real run, 2026-07-02): exported **32 sources,
    35 source_pages, 20 source_pdf_pages, 1301 source_spans** — mechanism
    healthy; triggers were the only failure. `last_export_ts` now
    2026-07-02T02:10:42Z. Once Syncthing ships this, macOS should converge.
- Conclusion: original Part B (un-ignore `state.sqlite`, WAL checkpoint,
  schema-drift guard) rejected — would fight §13.1. P0 RED tests
  (`test_db_sync_safety.py`) deleted; replaced by P2 trigger-repair RED tests.

## Rollback Requirements
- Before editing `.stignore` on `second_brain`: DB snapshot already taken above.
- `.stignore` change is additive-safe (removing one ignore line); revert = re-add
  the `.curator/state.sqlite` line.
- Checkpoint-truncate is behavior-additive (no schema change); revert = remove
  the `PRAGMA wal_checkpoint(TRUNCATE)` call.
- Schema-drift guard raises on newer on-disk version; revert = remove the guard.
