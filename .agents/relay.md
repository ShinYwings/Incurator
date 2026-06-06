# Relay State — v0.4.0 Knowledge Sync Bridge (2026-06-06, Claude Code)

## Current Branch
`release/v0.4.0`

## Goal
Implement the Cross-Device Knowledge Sync Bridge (v0.4.0) — JSONL export/import
for cross-device SQLite synchronisation.  PR #4 submitted; awaiting user merge.

## Plan Reference
- Master plan: `.agents/plans/03_knowledge_sync_bridge.md`
  (to be deleted from workspace once PR #4 is merged to master)

## Progress Status

### v0.4.0 Knowledge Sync Bridge — COMPLETE (PR #4 open)
- [x] P1 — Schema: `SCHEMA_VERSION` 6 → 7, `deleted_records` tombstone table
- [x] P2 — Core logic: `backend/src/curator/db_sync.py` (LWW + tombstone import/export)
- [x] P3 — CLI: `wiki db export` / `wiki db import` subcommands in `cli.py`
- [x] P4 — Docs: `USER_GUIDE.md`+`_KR.md`, `SCHEMA.md` §11.17, all spec titles → v0.4.0
- [x] P5 — Tests: `test_db_sync.py` (13 tests), `test_db_schema.py` version bump
- [x] Version bump: `pyproject.toml` / `__init__.py` / `package.json` / `manifest.json` → 0.4.0
- [x] `CHANGELOG.md` created with v0.3.3 + v0.4.0 entries
- [x] CI `.github/workflows/ci.yml`: `.[dev,mcp]` fix on `release/v0.4.0`
- [x] CI fix also pushed to `fix/v0.3.3-cleanup` (run #14 was failing; fix pushed d785bc1)
- [ ] **PENDING**: user reviews and merges PR #4 to master

### CI state
| Branch | Install | Status |
|--------|---------|--------|
| `release/v0.4.0` | `.[dev,mcp]` | ✅ passes |
| `fix/v0.3.3-cleanup` | `.[dev,mcp]` | ✅ fixed (d785bc1 pushed) |
| `master` | `.[dev]` (old) | inherits from fix/v0.3.3-cleanup merge; fixed once PR #4 lands |

## Critical Context

- `deleted_records` tombstone table is non-destructive: existing vaults self-heal
  on next `wiki` invocation (schema migration is additive only).
- Device-local tables excluded from export: `search_embeddings`, `ingest_jobs`,
  `job_events`, `search_index`, FTS5 virtual tables.
- LWW resolution: row with the newer `updated_at` / `deleted_at` timestamp wins.
- `--since` incremental export compares `updated_at` across all SYNC_TABLES.

## Immediate Next Action

1. **User**: review and merge PR #4 (`release/v0.4.0` → `master`).
2. **After merge**: delete `.agents/plans/03_knowledge_sync_bridge.md` from master.
3. **Next milestone**: `01_minor_quick_wins.md` (items 2, 9, 10 from user_report.md)
   or `02_stabilization.md` (items 3–7) — user decides priority.

### Update (2026-06-06, Antigravity)
- Handled additional Syncthing Auto-Sync features requested during review.
- Implemented `db_sync.py` LWW loop prevention via `sync_meta.json` hashing and added clock skew warnings.
- Fixed failing `test_db_sync.py` tests.
- Implemented Obsidian Plugin Hooks in `main.ts` for Auto-Import on load and Debounced Auto-Export on file modify.
- Added "Sync Database" UI Ribbon button.
- Cleaned up `.agents/user_report.md` and deleted completed plan files in `.agents/plans/`.
- Pushed changes to `release/v0.4.0`. Waiting for User to create PR since `gh pr create` failed due to auth.

### Update (2026-06-06, Antigravity - Planner)
- Created a new master implementation plan for v0.4.0 review fixes based on the Arena Model.
- Plan saved to `.agents/plans/04_zotero_sync.md` involving multiple sub-agents (DB Architect, Frontend Expert, Security Auditor).
- Moved the `dry-run` bug and `Syncthing Sync` feature requirements from `To-Do` to `Planned` in `.agents/user_report.md`.
- Waiting for user's approval on the plan. No code has been implemented.
