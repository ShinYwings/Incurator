# Active Relay State

**STATUS: Phase B — G17 S3 cleanup in progress.**

**Current branch**: `fix/g17-s3-cleanup`

**Last refreshed**: 2026-06-27 by Claude Code.

---

## Goal

Continue the System Stability Overhaul Phase B with the remaining G17 S3
plugin cleanups (the S2 items shipped in v0.27.3 / PR #62). This batch:

- **G17-7**: Zotero "Refresh Zotero Item" silently passed a citekey as a Zotero
  item key when `zotero_app_url` was absent; the backend's
  `get_zotero_item_metadata` queries `items.key`, so a citekey returns `{}` and
  the note was rewritten with empty metadata (silent corruption). Fix: guard the
  empty-metadata result and abort with a clear error before modifying the note.
  (Full citekey→item-key resolution needs new backend work — deferred to a
  Minor; see Icebox candidate below.)
- **G17-12**: `imageFolder` is `@deprecated` but still lived in stored profiles.
  Add a one-time load-time migration that normalizes `imageFolder` →
  `assetFolder`/`assetSubfolder` and deletes `imageFolder`, so the field is
  retired from persisted data. Runtime fallback in `resolveProfileAssetSpec` is
  kept (the migration reuses it).

Classification: Patch (`0.27.3 → 0.27.4`) — bug fix + internal data migration,
no new user-facing capability, no schema/contract change.

## Plan Reference

- Master plan: `.agents/plans/01_system_stability_overhaul.md`
- G17 diagnosis: `.agents/plans/diagnosis/G17-plugin-rest.md`

## Progress Status

- Branch created from `master` (post-#62 merge).
- G17-7: added empty-metadata guard in the Zotero reload command — aborts with a
  clear error before `renderTemplate`/`modify` when the item can't be resolved.
- G17-12: added `migrateZoteroProfileAssetFolders()` in `assetLocalization.ts`,
  wired into `loadSettings`, normalizing `imageFolder` → `assetFolder`/
  `assetSubfolder` and deleting the deprecated field (persists on change).
- Docs: PLUGIN_GUIDE(.md/_KR) reload section + PLUGIN_SCHEMA contract updated.
- Version bumped to 0.27.4 (Patch); CHANGELOG entry added.
- Validation: vitest 621 passed; `tsc --noEmit` clean; `scripts/backend-check`
  ruff/mypy clean; spec-sync + docs-parity pass at 0.27.4; `git diff --check`
  clean.

## Deferred / Icebox candidate

- **G17-7 full fix**: citekey → Zotero item-key resolution requires a backend
  resolver (citekeys are derived, not stored in `items.key`). Treat as a Minor
  with its own plan if multi-profile users need refresh of notes that lack
  `zotero_app_url`.
- **G17-10**: Zotero passthrough consistency — low priority, only when a wrapper
  cleanup PR is already touching those methods.

## Immediate Next Action

- Shipped as **v0.27.4** in PR #63 (https://github.com/ShinYwings/Incurator/pull/63) — awaiting human review/merge.
- After merge, remaining Phase B work is the larger S2 architectural items
  (XC-1 broad-except narrowing; CM-1/PL-1/DB-2 god-file decomposition), each
  warranting its own Arena plan + Minor version. Start on a fresh branch.
