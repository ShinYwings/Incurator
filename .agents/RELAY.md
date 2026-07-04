# RELAY — v0.32.0 Release Ready

## Goal

Ship the current-contract-only portable source path release.

## Current State

- Branch: `release/v0.32.0`
- Planning commit: `3ce8a11`
- Implementation commit: `4292e79`
- Release commit: `chore(release): v0.32.0`
- Draft PR: https://github.com/ShinYwings/Incurator/pull/80
- Version: 0.32.0 / DB schema 11
- Local release state is complete and pushed.

## Implemented

- Removed `wiki paths`, `portable_migration.py`, and the pre-v0.29 source-table
  converter from DB initialization.
- Removed legacy external root-array conversion and runtime discovery.
- Absolute non-reference `sources.relpath` values no longer resolve as local
  files.
- Preserved current Zotero attachment-key and named-root reference resolution.

## Production / Testbed

- macOS `second_brain` DB backup:
  `.cache/migrations/v0.29.0/20260703T221125Z/state.sqlite`
- Normalized source ids 1, 27, and 30 to schema-11 Zotero identities; SQLite
  integrity passed and absolute locator count is zero.
- Deployed backend/plugin 0.32.0 with `INCURATOR_SKIP_MODELS=1 ./setup.sh`.
- Fresh `complex_math_backprop` testbed passed status, add, sync, and lint
  (100/100).

## Verification

- Backend: 1187 passed, 6 skipped, 5 xfailed.
- Plugin: 666 passed.
- Ruff, mypy, TypeScript, plugin production build, spec sync, and deployed
  `wiki status` passed.
- `.venv/bin/wiki paths --help` returns `No such command 'paths'`.

## Immediate Next Action

Review and merge draft PR #80.

### Update (2026-07-04, Codex)

- Re-audited cross-device source resolution after removing `wiki paths`.
- Production `state.sqlite` and the synced device JSONL contain no absolute
  source locators; all three reference rows use `zotero:<attachment-key>`.
- The current macOS backend resolved all three keys through the local
  `/Users/shin/Zotero/zotero.sqlite` and local Zotero attachment preferences.
- Generic references resolve `@<root_key>/<relative-path>` against this
  checkout's ignored `.cache/config/config.yml`; Zotero also auto-discovers
  standard OS locations and Zotero `prefs.js`.
- Targeted portable-path, Zotero, machine-local config, and DB sync tests pass:
  47 passed.
