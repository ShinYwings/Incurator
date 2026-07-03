# RELAY — v0.32.0 Portable-Path Compatibility Removal

## Goal

Remove the v0.29 portable-path backward-compatibility layer while preserving
the current reference-key runtime contract.

## Plan Reference

- `.agents/plans/07_path_compat_removal.md`
- `.agents/plans/07_roadmap_evidence.md`

## Analysis & Reasoning

- `wiki status` fails because the macOS device-local `state.sqlite` still has
  v9 absolute-path columns and `_migrate_v10_portable_sources()` blocks every
  DB connection until `wiki paths migrate --apply` is run.
- `state.sqlite` is intentionally excluded from Syncthing, so the Linux v0.29
  production migration did not update this device's local DB.
- The three affected rows already carry Zotero attachment keys. The current
  runtime resolver can locate them from `logical_source_id=zotero:<key>`
  without persisted absolute paths.

## Progress Status

- Branch: `release/v0.32.0`
- Investigation complete; planning artifacts are being authored.
- No application code changed yet.

## Critical Context / Blockers

- Preserve the current `second_brain` DB with a timestamped backup before its
  one-time normalization.
- Do not remove general schema evolution. Scope is the retired portable-path
  input formats and their command/config adapters.

## Immediate Next Action

Finish the v0.32.0 plan and evidence ledger, then update docs and failing tests
before removing the compatibility code.
