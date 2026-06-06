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
- P3: **PASS** — `db_sync.autosync` (import peers + merge/archive conflict files +
  export-if-changed), `wiki db autosync [--dry-run] [--json] [--skip-reindex]`,
  `_maybe_auto_export` hook on `wiki update` (gated by `auto_sync.enabled`).
  **Scope note**: hook wired into `update` only (single clean exit), not threaded into
  the 500-line `sync`/`add`/`build` exit mazes — `wiki db autosync` (explicit, used by
  the plugin) covers the standalone path. **Bug fixed**: `--json` used
  `console.print(json.dumps(...))` which rich wrapped mid-token at width 80 (would break
  the plugin's JSON parse); switched export/import/autosync `--json` to `_print_json`
  (valid JSON). Also fixed pre-existing mypy error on `_PK_COL` annotation.
  Full suite: **482 passed**; `ruff` + `mypy src/curator/db_sync.py` clean.
- P4: **PASS** — `IncuratorClient.dbAutosync()` (calls `wiki db autosync --json
  --skip-reindex`, maps stats); `SyncScheduler` (debounce + non-overlap coalescing, in
  its own testable module); `main.ts` wiring: `setupAutoSync` (ribbon "Sync Knowledge
  DB", on-load runNow, `fs.watch` on `.curator/sync` via `window.require("fs")` with
  mobile/feature-detect fallback, 60 s poll fallback, status-bar `⟳/✓` indicator,
  change + conflict Notices). Settings UI: 4 toggles (enabled/on-load/watch/notify),
  optional in PluginSettings (read with `!== false`). `tsc` clean, `npm run build` ok,
  `vitest` → **282 passed** (incl. new SyncScheduler + dbAutosync tests).
- P5: **PASS** — Docs (EN+KR): USER_GUIDE `wiki db autosync`, PLUGIN_GUIDE auto-sync
  settings/triggers, SYNC_IGNORE_GUIDE `sync_state.json` exclusion. Specs: SYSTEM_BEHAVIOR
  §13.1 rewritten (removed the stale reverted `sync_meta.json` hash design) + §13.3;
  SCHEMA `_DEVICE_LOCAL_COLUMNS`. CHANGELOG: replaced stale reverted-approach entry, added
  Fixed note for the dry-run/import bug. **E2E**: `TestTwoDeviceE2E` — bidirectional merge
  (no loss), concurrent-edit-newer-wins, stable re-import no-op. Full CI: backend
  **485 passed**, `ruff` clean (mypy db_sync clean; config.py note is pre-existing
  missing `types-PyYAML` stub, and CI runs ruff+pytest only); plugin **282 passed**, `tsc`
  clean, `npm run build` ok. No `SCHEMA_VERSION` bump (still 7).
