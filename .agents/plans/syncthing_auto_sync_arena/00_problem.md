# The Briefing — Zotero-Grade Auto-Sync over Syncthing

Date: 2026-06-07 | Author: Claude Code (orchestrator)

## Problem Definition

`wiki db export` / `wiki db import` exist and work (LWW upsert + `deleted_records`
tombstones, `SCHEMA_VERSION = 7`). They are **manual**. The user already syncs the
vault folder across devices with **Syncthing**. The goal is to make cross-device DB
sync **automatic and Zotero-grade reliable** without the user ever running a CLI
command:

- DB changes on device A propagate to device B with no manual step.
- Concurrent offline edits on both devices merge without data loss.
- The system degrades safely under Syncthing's real-world failure modes
  (conflict files, download lag, large payloads).

This is the `[기능 제안]` item in `user_report.md`
("Zotero급 로컬 DB 클라우드화") plus its four enumerated edge cases.

## Hard Constraints (from codebase + specs)

- **`state.sqlite` is the single source of truth.** `.curator/Collections/*` markdown
  is derived/disposable. Sync moves DB rows, not markdown.
- **No new SQLite schema.** `deleted_records` (v7) is sufficient. Do not bump
  `SCHEMA_VERSION` for this feature.
- **LWW is the merge contract** (`updated_at` / `last_updated` per table, tombstone
  wins ties). Import already preserves the source row's timestamp — keep it that way.
- **Reference Mode safety**: `is_reference=1` sources have device-specific
  `external_path`; import must not clobber a local path with a peer's path.
- **Import never writes `02_Wiki/`** — DB only; markdown reflection is a later
  `wiki sync` step.
- **Backend runs out-of-process** from the Obsidian main thread (subprocess), so heavy
  I/O must stay in the CLI, never in plugin JS on the UI thread.

## Postmortem of the Reverted Attempt (what NOT to repeat)

Commit `7649009` + `1c38cd7` implemented auto-sync directly from review feedback
with **no Arena plan**. It was reverted (`365ee78`). Concrete failures:

1. **Wrong export trigger**: exported on every `vault.on("modify")` (a *markdown note*
   save) with a 10 s debounce. But DB rows change on `wiki add/build/sync`, not on note
   edits — so it exported stale DB state on unrelated keystrokes.
2. **Fragile import target**: `dbImport()` hardcoded `export-YYYYMMDD.jsonl` (today's
   date). A peer file from yesterday, or named differently, was never imported.
3. **Single shared filename** guaranteed Syncthing write-write conflicts
   (`*.sync-conflict-*`) the moment two devices were active.
4. **Hash-based loop guard** (`sync_meta.json` `last_exported_hash` /
   `last_imported_hash`) silently skipped a legitimate `wiki db import` after any
   export — `import` reported `0 changes` even with pending rows. This is the
   `[PR 픽스]` dry-run/import bug. **Root cause = this guard.** Removing it (the
   revert) restored correct behavior; verified by repro.
5. No handling of the four user-listed edge cases (conflict files, download race,
   overwrite data loss, large-file UI freeze).

## Success Criteria (non-negotiable)

- Two devices, both edited offline, then reconnected → **no row lost**; LWW + tombstone
  reconciles deterministically.
- `wiki db import` / `--dry-run` always report and apply the true row delta (no silent
  skip). Regression test must lock this.
- No infinite export↔import loop, achieved **without** a content-hash guard.
- Syncthing `*.sync-conflict-*` files are detected and safely mergeable, not ignored.
- Large exports never freeze the Obsidian UI.

## Personas in this Arena

- **DB Architect** — file topology, loop-prevention via LWW idempotency, incremental
  exports, high-water-mark state.
- **Plugin Expert** — triggers (the right ones), `fs.watch` real-time detection,
  status UI, modals, settings.
- **Edge-Case Auditor** — conflict files, download race, large payloads, reference-mode
  path safety, security of executing imports from synced files.
