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
- Completed plan: Git history at commit `b63e672`

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

- Implementation, schema-v10 production migration, documentation, testbed
  validation, full local CI, version bump, build, and second_brain deployment
  are complete.
- Production DB and structured `.curator`/plugin persistence audits report zero
  absolute filesystem locators.
- Installed backend and plugin version: `0.29.0`.

## Critical Context / Blockers

- Obsidian must be reloaded once so the deployed 0.29.0 plugin runs its
  localStorage migration in the live Electron profile.
- Full Zotero PDF parsing in testbed is blocked by the host's missing
  Tesseract `eng.traineddata`; key-based Zotero resolution and generic external
  Reference Mode were validated.

## Immediate Next Action

Push `release/v0.29.0` and open the release PR.
