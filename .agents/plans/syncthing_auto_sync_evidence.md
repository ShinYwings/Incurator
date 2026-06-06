# Syncthing Auto-Sync — Evidence Ledger

Date: 2026-06-07 | Plan: `syncthing_auto_sync.md` (+ `syncthing_auto_sync_arena/`)

## Rollback Anchor
- Branch: `release/v0.4.0`
- Anchor commit (pre-implementation): `41d9877226a3ac7846a9b9b12cd01e990e0512a1`
  (`chore(relay): live state — Syncthing auto-sync plan awaiting approval`)
- To roll back this feature: `git revert` the implementation commits back to this anchor,
  or `git reset --hard 41d9877` on a throwaway branch only (never on shared `master`).

## Current Schema / Code Reality (verified)
- `SCHEMA_VERSION = 7`; `deleted_records` tombstone table present. **No schema change in
  this feature.**
- `db_sync.py` (post-revert, clean): `export_knowledge(since=...)`, `import_knowledge`
  (LWW + tombstone), `record_tombstone`, `SYNC_TABLES` (20), `EXCLUDE_TABLES`,
  `_UPDATED_AT_COL`, `_PK_COL`. **No `sync_meta.json` hash guard** (the reverted bug).
- `sources` columns include `external_path TEXT` + `is_reference INTEGER` — these are the
  device-local columns to protect under `_DEVICE_LOCAL_COLUMNS`.
- `.curator/state.sqlite` is ALREADY in the `.stignore` template (per-device DB). The
  JSONL files under `.curator/sync/` ARE synced (not excluded) — they carry knowledge.
  Need to add `.curator/sync_state.json` (device-local high-water marks) to `.stignore`.
- Config: `load_config(paths)` merges global+vault YAML over `DEFAULT_CONFIG`;
  `save_config(paths, cfg)`. Nested dict blocks merge key-wise. Will add `auto_sync` block.
- `cli.py`: `db_app` Typer group with `export`/`import`; mutating commands `add`, `build`,
  `sync`, `update` exist. `_resolve_root_or_die()` → `WikiPaths`.
- Plugin: `IncuratorClient.callBackendJson([...])`, `main.ts` `ObsidianAIAgent`
  (`onload`, `onLayoutReady`, `addRibbonIcon`, `registerEvent`, `registerInterval`).

## Pre-Implementation Validation (baseline)
- `pytest tests/test_db_sync.py` → **13 passed** (anchor state).
- Dry-run repro (anchor): DRY-RUN `inserted=1`, REAL `inserted=1` — bug already fixed by
  revert. P2 adds the locking regression test.

## Post-Phase Validation (filled in as phases complete)
- P1: **PASS** — `auto_sync` config block (opt-in), `read/write_sync_state` +
  `get_device_id` (`.curator/sync_state.json`), `_DEVICE_LOCAL_COLUMNS` (sources.external_path),
  `.stignore` template excludes `sync_state.json` (keeps `sync/` synced).
  `pytest tests/test_db_autosync.py` → 6 passed; `ruff` clean.
- P2: **PASS** — `export_for_device` (full snapshot per device), `import_all_peers`
  (own-file skip + per-peer mtime high-water mark), `detect_conflict_files`,
  `_preserve_device_local` (reference external_path kept on LWW update). **Design
  deviation from plan §1.3**: device file is a FULL snapshot each export (overwrite),
  not an incremental `--since` delta — incremental-by-overwrite would lose earlier rows
  for a late-joining peer. Full snapshot is correct + idempotent (LWW); Syncthing
  block-level transfer + subprocess import mitigate size. Incremental deferred.
  `pytest tests/test_db_autosync.py` → 15 passed; regression `test_db_sync.py` +
  `test_db_schema.py` → 23 passed; `ruff` clean.
- P3: _pending_
- P4: _pending_
- P5: _pending_
