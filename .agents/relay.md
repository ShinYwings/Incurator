# Relay State — v0.4.0 release branch (2026-06-07, Claude Code)

## Current Branch
`release/v0.4.0` — PR #6 OPEN ("v0.4.0: Syncthing Auto-Sync and Cross-Device DB
Bridge"). Not merged to master.

## Live State

### Shipped on this branch (base Knowledge Sync Bridge, v0.4.0)
- `wiki db export` / `wiki db import` — JSONL LWW + `deleted_records` tombstones,
  `SCHEMA_VERSION = 7`. Working, 13 tests green.

### Just done this session
- **Reverted** Antigravity's hash-based loop prevention + plugin auto-sync wiring
  (`365ee78`). Root cause of the `db import --dry-run` 0-changes bug was the
  `sync_meta.json` hash guard; revert fixes it (verified by repro). Working tree clean.
- **New workflow rule**: "Review Feedback Loop (Plan-First, Proactively)" added to
  AGENTS.md + CLAUDE.md (`76f5c27`). Review feedback → user_report item → Arena plan
  BEFORE coding, done without being asked.
- **Arena plan authored** for Syncthing auto-sync: `.agents/plans/syncthing_auto_sync.md`
  + `syncthing_auto_sync_arena/` (`3fcca36`). **Awaiting user approval before any code.**

## Plan Reference
- `.agents/plans/syncthing_auto_sync.md` (master) + `syncthing_auto_sync_arena/` (debate)
- Other skeletons: `roadmap.md`, `minor_quick_wins.md`, `stabilization.md`,
  `pdf_annotation_system.md` (numeric prefixes dropped; ordering lives in roadmap.md).

## Critical Context
- **Never reintroduce** the `sync_meta.json` hash guard or a `vault.on("modify")` export
  trigger (both were the broken approach). Loop prevention is structural (LWW idempotency
  + import-never-exports + export-only-on-local-change). See plan §"Locked decisions".
- No SQLite schema change for auto-sync; `SCHEMA_VERSION` stays 7.

## Immediate Next Action
1. **User**: approve `syncthing_auto_sync.md` (or request changes), and review/merge PR #6.
2. **On approval**: implement P1→P5 of the plan via TDD (do NOT start before approval —
   Universal Strict Workflow Step 3 / Review Feedback Loop).
