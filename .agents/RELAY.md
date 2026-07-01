# RELAY — Portable Path Storage

## Goal

Enforce the user contract that every persisted path under `.curator/` and in
plugin-owned storage is portable. Vault paths are vault-relative; external
paths are represented by portable identity. Zotero persists only its effective
attachment key and resolves through the current device's Zotero DB; generic
external files use a configured root-variable reference plus a relative path.
Only the backend's repo-local ignored `.cache/config/` may contain per-device
absolute roots.

## Plan Reference

- Branch: `release/v0.29.0`
- Roadmap: urgent v0.29.0 portable-path storage item
- Plan: `.agents/plans/06_portable_path_storage.md` (approved 2026-07-01)

## Analysis & Reasoning

- v0.28.5 sanitized runtime snapshot payloads but did not change the DB contract.
- Current `sources.external_path` and `sources.import_origin` persist absolute
  external paths; `db_sync._preserve_device_local` protects the former.
- Current specs explicitly describe this absolute-path design, so this is a
  minor schema/contract change with a migration, not a small hotfix.
- Stable identity remains `logical_source_id` plus content hash. Runtime absolute
  paths must be reconstructed from repo-local `.cache/config/` root mappings.
- Zotero is a stronger special case: the backend already resolves attachment or
  parent item keys through Zotero DB. Persist the effective attachment key only;
  do not persist the resulting path in DB, localStorage, or Obsidian view state.

## Progress Status

- Read RELAY, USER_REPORT, ROADMAP, PLAN_TEMPLATE.
- Created `release/v0.29.0`.
- Triaged the user report into the urgent roadmap queue.
- Repository/schema/plugin persistence audit and Arena plan are complete.
- User approved implementation; active scenario is `gaussian_splatting`.

## Critical Context / Blockers

- Existing production DB values must be inventoried read-only before migration
  design is locked.
- Testbed validation uses `tests/scenarios/gaussian_splatting`.

## Immediate Next Action

Commit the approved planning artifacts, then execute docs-first contract,
failing tests, schema v10 migration, and plugin persistence phases.
