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
