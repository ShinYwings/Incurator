# RELAY — v0.32.1 Cross-Device Integrity Active

## Goal

Expand PR #82 so independent macOS/Linux replicas converge safely and all
device-local state lives under the Incurator repository `.cache`.

## Plan Reference

- `.agents/plans/07_cross_device_integrity_hotfix.md`
- `.agents/plans/07_roadmap_evidence.md`
- `.agents/plans/cross_device_integrity_arena/`

## Current State

- Branch: `hotfix/v0.32.1-sync-device-identity`
- Rollback anchor: `23a6d2cf2124689c5313880517c8cd832f3a2e60`
- Package/plugin target: v0.32.1 by explicit user direction
- DB schema target: v12
- PR: #82

## Locked Decisions

- `sources.sync_key` is portable transport identity; integer ids stay local.
- Imported child `source_id` values are remapped to local ids.
- Source deletes use sync-key tombstones.
- Generation/source revisions are monotonic.
- JSONL imports enforce table/column allowlists and snapshots use `export_id`.
- DB/runtime/staging/temp files live in repo `.cache/vaults/<vault-key>/`.
- `.curator` retains portable settings, snapshots, sessions, profiles, and
  Collections projections.
- v11 snapshot compatibility and manual path migration commands are excluded.

## Progress Status

- P0 — Baseline reproduction: DONE (9 regression tests fixed failures).
- P1 — Contract specs/guides: DONE (all specs + EN/KR guides updated for
  schema v12 and storage boundary).
- P2 — DB schema/transport: DONE (sync_key, source remap, tombstones,
  generation revision, allowlist, export_id — 52 targeted tests pass).
- P3 — Storage boundary: DONE (DB/runtime/staging/report/log/PDF cache moved
  to `.cache/vaults/<vault-key>/`; one-time relocation with dual-existence
  abort).
- P4 — Plugin/shared state: DONE (serialized sessions, Zotero profile
  tombstones, plugin temp paths under repo cache, vault fallback removed).
- P5 — Integration CI: DONE (verified 2026-07-06T05:32 KST).
  - pytest: 1195 passed, 4 failed (pre-existing — 3 macOS Zotero sandbox
    permission errors, 1 stale `.pytest_cache` cleaned), 6 skipped, 5 xfailed.
  - mypy: clean (103 source files).
  - ruff: clean.
  - spec sync: 10 passed.
  - vitest: 669 passed (65 files).
- P6 — Testbed/Release: NOT STARTED.

## Critical Context

- User allows concurrent reads and distinct-source writes, not simultaneous
  edits to the same source.
- Existing macOS production backup:
  `.cache/migrations/v0.32.1/20260704T042823Z/`.
- Stop before production migration if both old/new DB locations exist.
- Version strings already at 0.32.1 in all three manifests (pyproject.toml,
  package.json, manifest.json). Spec titles stay at v0.32.0 (patch bump,
  same minor line — no change needed).
- 4 pre-existing pytest failures are NOT caused by v0.32.1 changes:
  `test_asset_identity.py` (3) hit macOS sandbox on real Zotero DB;
  `test_workspace_hygiene.py` (1) found stale `.pytest_cache` at repo root
  (now deleted).

## Immediate Next Action (P6 — Executor)

1. **Expand CHANGELOG.md** — rewrite the v0.32.1 entry to cover the full
   expanded scope: schema v12 `sync_key` transport identity, source-id
   remap, sync-key tombstones, monotonic generation/source revisions,
   JSONL table/column allowlist, `export_id` snapshot identity,
   storage boundary relocation to `.cache/vaults/<vault-key>/`, serialized
   session/profile saves, Zotero profile deletion tombstones, and plugin
   temp path isolation.
2. **Incremental commits** — structure the uncommitted diff (54 files,
   ~1168 ins / ~371 del) into logical Conventional Commits:
   - `feat(schema): add sync_key transport identity and source-id remap (v12)`
   - `feat(sync): add tombstones, generation revision, allowlist, export_id`
   - `feat(paths): relocate device-local state to repo cache`
   - `fix(plugin): serialize session/profile saves and isolate temp paths`
   - `docs: update specs and EN/KR guides for schema v12 and storage boundary`
   - `test: add cross-device integrity regression tests`
3. **Release commit** — `chore(release): v0.32.1`
4. **Push and PR #82 update** — push branch `hotfix/v0.32.1-sync-device-identity`
   and update the PR description with the expanded scope.
