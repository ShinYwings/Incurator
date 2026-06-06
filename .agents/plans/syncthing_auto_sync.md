# Syncthing Auto-Sync — Master Implementation Plan (통합 명세서)

Date: 2026-06-07
Status: DRAFT — Arena debate concluded (`syncthing_auto_sync_arena/`). Awaiting user
approval before any implementation (Universal Strict Workflow Step 3 / Review Feedback
Loop).

Arena debate: `.agents/plans/syncthing_auto_sync_arena/`
- `00_problem.md` — problem, constraints, postmortem of the reverted attempt
- `01_proposal_db_architect.md` — file topology, structural loop prevention, deltas
- `01_proposal_plugin_expert.md` — triggers, fs.watch, status UI, modals, settings
- `01_proposal_edgecase_auditor.md` — the four hazards + reference mode + security
- `02_critique_synthesis.md` — cross-critique + locked consensus

## Linked user_report Items
- `[기능 제안] Zotero급 로컬 DB 클라우드화 (Syncthing 연동...)` → this plan.
- `[PR 픽스] db import --dry-run 0건 표시 버그` → **already resolved** by revert
  `365ee78` (removed the hash guard that was the root cause). This plan adds the
  regression test that locks it (P2) and the item can be deleted from `user_report.md`.

## Strict quality condition (절대 타협 불가)
- Two devices edited offline then reconnected ⇒ **zero row loss**; LWW + tombstone
  reconciles deterministically (proven by test).
- `wiki db import` / `--dry-run` ALWAYS report and apply the true delta. **No hash guard,
  ever.** Locked by regression test.
- No infinite export↔import loop, achieved structurally (not via content hashing).
- `*.sync-conflict-*` files detected and safely merged, not ignored.
- Large exports never block the Obsidian UI thread.
- **No SQLite schema change** (`SCHEMA_VERSION` stays 7).

## Locked design decisions (Arena 합의)
1. **One-writer-per-file**: `.curator/sync/dev-<device_id>.jsonl`; each device writes only
   its own, imports all peers except own. No shared file ⇒ no write-write conflicts.
2. **Structural loop prevention** (no `sync_meta.json` hash): LWW idempotency with
   preserved source timestamps + import never schedules auto-export + `autosync` exports
   self only when local DB changed since `last_export_ts`.
3. **Device-local state**: `.curator/sync_state.json` (device_id, per-peer
   `last_imported_mtime`/`last_max_ts`, own `last_export_ts`). MUST be in `.stignore`.
4. **Triggers**: backend exports at end of mutating CLI commands when
   `auto_sync.enabled`; plugin runs `wiki db autosync` on-load + via `fs.watch` (desktop)
   + 60 s poll fallback + manual ribbon. **Never** on `vault.on("modify")`.
5. **Reference safety**: `_DEVICE_LOCAL_COLUMNS` column-level exclusion keeps local
   `sources.external_path` when `is_reference=1`.
6. **Edge cases**: conflict → import-as-peer then `_archive/`; race → live watcher + per-
   peer mtime; overwrite → row-level LWW + tombstone; large → subprocess + `--since`.
7. **Security**: data-only import, hard `schema_version` gate, table allowlist (keep, test).

## Contracts preserved
- `export_knowledge` / `import_knowledge` signatures unchanged (new functions wrap them).
- `wiki db export` / `wiki db import` behavior unchanged (manual path intact).
- `db.init_db`, `SCHEMA_VERSION = 7` unchanged.
- Import remains DB-only; no writes to `02_Wiki/`.

## Evidence Ledger (증거 장부)
- **Rollback anchor**: branch off current `release/v0.4.0` HEAD (post-revert, clean).
  Record the exact commit in `<plan>_evidence.md` before P1.
- **Current reality**: `db_sync.py` post-revert = clean LWW + tombstones, no hash guard;
  `wiki db export/import` CLI present; `deleted_records` table present (v7); plugin
  auto-sync wiring removed. `EXCLUDE_TABLES` exists; `_DEVICE_LOCAL_COLUMNS` does not yet.
- **Pre/post validation**: capture `pytest tests/test_db_sync.py` (13 passing now) before
  changes; re-run after each phase. Capture the dry-run/real repro before & after P2.

## Execution Phases (각 단계: TDD + `ruff` + CI 통과 후 다음 단계)

### P1 — Config + state + .stignore (no behavior yet)
- `config.py`: add `auto_sync` block (`enabled`, `dir=.curator/sync`, `device_id`,
  `debounce_ms`, `poll_ms`) with safe defaults.
- `db_sync.py`: `sync_state.py` helpers (read/write `.curator/sync_state.json`),
  `_DEVICE_LOCAL_COLUMNS` map.
- Ensure `.curator/sync_state.json` is in the vault `.stignore` template.
- **Verify**: `pytest` for config load + state round-trip; a test asserting
  `sync_state.json` is matched by `.stignore`. `ruff check src/`.

### P2 — Backend autosync core + dry-run regression lock
- `db_sync.py`: `export_for_device`, `import_all_peers`, `detect_conflict_files`;
  `suppress_auto_export` guard; reference-mode column exclusion in `_lw_upsert`.
- **TDD first**: tests for (a) dry-run==real delta (locks the `[PR 픽스]`), (b) offline
  edit/delete tie-breaks both orderings, (c) reference `external_path` preserved,
  (d) conflict file imported-as-peer, (e) no self-import, (f) incremental `--since` window.
- **Verify**: `pytest tests/test_db_sync.py tests/test_db_autosync.py -v`; `ruff`.

### P3 — CLI + mutating-command hook
- `cli.py`: `wiki db autosync [--dry-run] [--json] [--full]` (import peers → maybe export
  self). Fire `export_for_device` at end of `add/build/sync/update` when
  `auto_sync.enabled` and not under import suppression.
- **Verify**: `pytest tests/test_cli_db_autosync.py`; testbed smoke
  (`VAULT_ROOT=testbed wiki db autosync --dry-run --json`).

### P4 — Plugin integration
- `incuratorClient.ts`: `dbAutosync()`, `resolveSyncDir()`, `isOwnDeviceFile()`.
- `main.ts`: restore ribbon (calls `dbAutosync`), on-load autosync, `fs.watch` (desktop,
  feature-detected) + 60 s poll fallback + coalescing scheduler, status-bar indicator,
  conflict + mismatch modals, new settings (all default-safe).
- **TDD**: `.test.ts` for scheduler coalescing, own-file ignore, mobile fallback path.
- **Verify**: `npx tsc --noEmit`, `npx vitest run`.

### P5 — Docs/specs + testbed E2E
- `docs/guides/USER_GUIDE.md` + `_KR.md`, `WORKFLOW_GUIDE.md` + `_KR.md`,
  `PLUGIN_GUIDE.md` + `_KR.md`: auto-sync setup, Syncthing folder note, conflict UX.
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`: autosync flow, loop-prevention
  rationale. `docs/specs/curator_schema/SCHEMA.md`: `_DEVICE_LOCAL_COLUMNS` contract.
- `docs/guides/SYNC_IGNORE_GUIDE.md` + `_KR.md`: `sync_state.json` exclusion.
- **Verify**: two-vault E2E (copy `dev-A.jsonl` into vault B's `.curator/sync/`, run
  autosync, confirm merge); full `pytest -q` + `ruff` + `mypy` + plugin `vitest`.

## Multi-Agent Role Reviews
- **schema_guardian**: confirm no `SCHEMA_VERSION` bump; `_DEVICE_LOCAL_COLUMNS` documented
  in SCHEMA.md; prefixes/layers untouched.
- **source_pair_analyst**: reference-mode `external_path` exclusion verified against Zotero
  sources; `logical_source_id` dedup unaffected by per-device import.
- **qa_runner**: offline-edit tie-break matrix, dry-run==real lock, mobile fallback,
  fs.watch poll fallback all covered.
- **legacy_sweeper**: ensure no `sync_meta.json` / hash-guard code is reintroduced; no
  `vault.on("modify")` export trigger; reverted symbols not resurrected.

## Out of scope (deferred)
- Retired-device file pruning (`wiki db sync prune`) and `_archive/` cleanup.
- Real-time mobile sync (no Node `fs`); mobile = on-load + manual only.
