# Relay State — v0.4.0 release branch (2026-06-07, Claude Code)

## Current Branch
`release/v0.4.0` — PR #6 OPEN. Not merged to master.

## Live State

Syncthing auto-sync (Zotero-grade) **implemented end-to-end** on top of the base
Knowledge Sync Bridge. Plan-first per the Review Feedback Loop rule.

- Plan: `.agents/plans/syncthing_auto_sync.md` (+ `_arena/`, `_evidence.md`) — all 5
  phases PASS (see evidence ledger).
- Backend: `db_sync.py` `export_for_device` / `import_all_peers` / `detect_conflict_files`
  / `autosync` (one-writer-per-file, structural loop prevention, no hash guard);
  `wiki db autosync` CLI; `auto_sync` config; `.curator/sync_state.json` (in `.stignore`).
- Plugin: `IncuratorClient.dbAutosync`, `SyncScheduler`, `main.ts setupAutoSync`
  (on-load + fs.watch + 60s poll + ribbon + status bar + notices), 4 settings toggles.
- Docs/specs (EN+KR) + CHANGELOG updated; stale reverted-approach spec text replaced.
- Tests: backend 485 passed, plugin 282 passed; ruff clean; `tsc`/build ok.

## Critical Context
- **Never reintroduce** the `sync_meta.json` content-hash loop guard or a
  `vault.on("modify")` export trigger (both were the reverted broken approach and the
  cause of the dry-run/import 0-changes bug).
- Loop prevention is structural: own file never imported + import≠mutation +
  export-only-when-changed. No `SCHEMA_VERSION` bump (still 7).
- `.curator/sync/` IS synced (transport); `state.sqlite` + `sync_state.json` are local.

## Immediate Next Action
1. **User**: review & merge PR #6 (`release/v0.4.0` → `master`).
2. **On merge**: delete `syncthing_auto_sync*.md` plan files; remove the completed item
   from `user_report.md`; truncate this relay to an IDLE stub.
3. **Next**: `minor_quick_wins.md` (web search, wikilink, DiffViewer UX) or
   `stabilization.md` (RAG) — user decides priority.
