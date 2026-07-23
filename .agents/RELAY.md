# RELAY — v0.36.6 Purple Pin Zotero Source Registration Hotfix

## Goal

Fix Purple Pin Add source rejecting a valid Zotero PDF with
`root_unregistered` when `external.path_roots` is empty.

## Plan Reference

- Small isolated hotfix; heavy Arena planning is skipped under the ROADMAP
  hotfix exception because there is no public contract, schema, or architecture
  change.
- Branch: `hotfix/v0.36.6-purple-pin-zotero-source`

## Analysis & Reasoning

Purple Pin calls `IncuratorClient.ingestPdf()` with both `--file-path` and
`--zotero-attachment-key`. `plugin_api.import_source()` assigns the portable
`zotero:<effective-key>` logical identity only in its key-only resolution
branch. The dual-input call therefore falls back to generic external-path
encoding and fails when the Zotero PDF is outside configured
`external.path_roots`.

The fix must preserve the supplied path (so existing viewer-resolved linked
attachments remain usable), set the explicit Zotero key as the durable logical
identity, and leave generic external-root rejection unchanged.

## Progress Status

- [x] Reproduced the control-flow cause from the production configuration
  (`external.path_roots: {}`).
- [x] Created the isolated hotfix branch from updated `master`.
- [x] Added backend regression tests for path + Zotero key and generic-path guard.
- [x] Updated EN/KR guide and all three static behavior/schema contracts.
- [x] Implemented the minimal backend identity fix.
- [x] Passed backend 1270 tests, plugin 704 tests, ruff, mypy, production build,
  real-path dry-run, and active testbed lint 100/100.
- [x] Bumped all manifests to v0.36.6 and updated the changelog.
- [ ] Commit, push, and open the hotfix PR.

## Critical Context / Blockers

- No blocker. The active local machine config has no generic external roots,
  matching the user's failure condition. The regression uses a platform-neutral
  temporary directory and therefore exercises the same boundary on Linux CI.

## Immediate Next Action

Create the fix and release commits, push the branch, and open the hotfix PR.
