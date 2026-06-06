# v0.4.0 Master Implementation Plan (Syncthing Auto-Sync)

Date: 2026-06-06
Status: APPROVED — implementing in phases. Specs are authored, tests are spec-first.

## Strict quality condition
- Import/Export must NEVER trigger an infinite loop.
- Sync must not crash the Obsidian UI thread.

## Locked design decisions
- Use `sync_meta.json` to store last sync timestamp to prevent infinite loops.
- Obsidian Plugin triggers Export on Save.
- Obsidian Plugin triggers Import on Load.
- Manual Ribbon Button for explicit Sync.

## Multi-Agent Role Reviews
- **schema_guardian**: No DB schema changes needed. Use existing tables.
- **cli_regression_runner**: CLI `wiki db import/export` behavior must remain unaffected.

## Phases (each: implement -> unit tests -> `uv run pytest` + `ruff` green)
- **P1 — [Specs]**: Update `PLUGIN_SCHEMA.md` and `SYSTEM_BEHAVIOR.md`.
- **P2 — [Backend]**: Add anti-loop logic and clock skew warning to Python sync logic.
- **P3 — [Plugin]**: Implement Ribbon button and save/load event hooks in TS.
- **P4 — [Testbed Smoke]**: End-to-end sync simulation.
