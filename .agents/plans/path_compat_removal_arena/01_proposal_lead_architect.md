# Backend Proposal: Current-Contract-Only Path Resolution
Date: 2026-07-04 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

- Delete the `wiki paths` Typer group and `portable_migration.py`.
- Delete `_migrate_v10_portable_sources()` and its call from DB initialization.
- Remove legacy `external.roots` and `external.zotero.roots` defaults and their
  automatic conversion to named roots.
- Retain `path_refs.py`, `zotero_tools.resolve_pdf()`, and
  `source_tools._row_path()` for current rows.
- Normalize the current DB with the existing release before deploying the
  compatibility-free code.

## 2. Pros & Cons

Pros: no maintenance-only command, no hidden schema rewrite during reads, and
one clear persisted contract. Cons: pre-v0.29 DBs are unsupported and must be
rebuilt or normalized before installing v0.32.0.
