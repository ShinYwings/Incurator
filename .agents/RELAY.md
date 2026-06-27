# Active Relay State

**STATUS: Phase B in progress — G18/G19 docs cleanup + G17 plugin cleanup.**

**Current branch**: `fix/phase-b-plugin-rest-cleanup`

**Last refreshed**: 2026-06-27 by Codex.

---

## Goal

Continue the System Stability Overhaul Phase B work. The Phase A diagnosis is
complete; the S1 queue was verified against the current code/tests/changelog and
is already fixed in the 0.25.4-0.25.8 release chain.

This branch handles the G18 docs-code-parity follow-up:

- Add missing live `PluginSettings` fields to `PLUGIN_SCHEMA §2.1`.
- Add lightweight parity tests so future MCP tools and plugin settings cannot
  silently drift from their docs.
- Add a G19 Failure Atlas directory index that separates live specs from frozen
  test oracles and historical handoff contracts.
- Make `USER_GUIDE` / `USER_GUIDE_KR` the canonical usage reference for
  `curate.yml`, with `WORKFLOW_GUIDE` / `WORKFLOW_GUIDE_KR` linking to it instead
  of re-listing selected fields.
- Make `USER_GUIDE` / `USER_GUIDE_KR` the canonical CLI reference via a stable
  `#cli-reference` anchor, with workflow/plugin guides linking there for exact
  command behavior.
- Fix G17-1 by clearing the settings auth-poll timer when the settings tab
  closes or re-renders.
- Fix G17-5 so the **Check DeepSeek API Key** command checks saved/env key
  configuration instead of invoking the login-help path.
- Fix G17-6 so Zotero note reload uses the note's originating import profile
  instead of always `zoteroProfiles[0]`.
- Fix G17-9 so Zotero `window.open` / Electron `openExternal` fallbacks preserve
  later plugin patches during unload.
- Fix G17-11 so plugin `data.json` settings writes flow through one serialized
  writer.
- Remove/clean G17-2/G17-3/G17-4/G17-8 settings/auth/model/device-registry
  cleanup items.

## Plan Reference

- Master plan: `.agents/plans/01_system_stability_overhaul.md`
- Evidence ledger: `.agents/plans/01_roadmap_evidence.md`
- G18 diagnosis: `.agents/plans/diagnosis/G18-docs-code-parity.md`
- G19 diagnosis: `.agents/plans/diagnosis/G19-docs-redundancy.md`

## Progress Status

Completed in this branch:

- Created `backend/tests/test_docs_surface_parity.py`.
- Confirmed the new test failed first with the expected missing fields:
  `agentEffort`, `ollamaHost`, `autoSyncEnabled`, `autoSyncOnLoad`,
  `autoSyncWatch`, `autoSyncNotify`.
- Updated `docs/specs/plugin_schema/PLUGIN_SCHEMA.md` to document those fields
  and the optional `autoSync*` `!== false` default-on semantics.
- Added `docs/specs/failure_atlas/README.md` explaining which files are live
  contracts versus frozen test oracles.
- Extended `backend/tests/test_docs_surface_parity.py` to require the Failure
  Atlas README to document the load-bearing files.
- Updated `docs/guides/USER_GUIDE.md` and `_KR.md` so their `curate.yml`
  reference shows the structured KRS sections (`goal`, `sources`, `knowledge`,
  `output`, `reasoning`, `verification`, `backprop`, `prompts`) rather than the
  old persona-only example.
- Updated `docs/guides/WORKFLOW_GUIDE.md` and `_KR.md` to link to the canonical
  `USER_GUIDE` reference instead of duplicating selected `curate.yml` fields.
- Added a docs parity guard for that `curate.yml` single-source structure.
- Added a stable `cli-reference` anchor to `USER_GUIDE.md` and
  `USER_GUIDE_KR.md`.
- Updated `WORKFLOW_GUIDE(.md/_KR.md)` and `PLUGIN_GUIDE(.md/_KR.md)` to link to
  that anchor for exact CLI definitions/flags.
- Added a docs parity guard requiring those CLI reference links.
- Renamed the branch from `chore/docs-surface-parity-guards` to
  `fix/phase-b-plugin-rest-cleanup` because plugin runtime code changed.
- Added a G17-1 settings source-contract test, then updated `settings.ts` so
  `authPollTimer` is instance-owned and cleared by `hide()` and at the start of
  `display()`.
- Added a G17-5 main source-contract test, then updated the DeepSeek command to
  call `checkDeepSeekApiKey()` and report either the saved plugin key or
  `DEEPSEEK_API_KEY` path.
- Updated `PLUGIN_GUIDE.md` and `PLUGIN_GUIDE_KR.md` to document that
  **Check DeepSeek API Key** is a key-configuration check, not a browser-login
  flow.
- Added `plugin/src/zotero/profileBinding.ts` and tests. Zotero imports now
  stamp `zotero_profile` into note frontmatter, and the reload command resolves
  that stamped profile before falling back to the first saved profile.
- Updated `PLUGIN_SCHEMA.md`, `PLUGIN_GUIDE.md`, and `PLUGIN_GUIDE_KR.md` to
  document Zotero refresh profile binding.
- Added a G17-9 main source-contract test, then updated Zotero opener fallback
  teardown so `window.open` and Electron `openExternal` restore only when
  Incurator still owns the patched function.
- Updated `PLUGIN_GUIDE.md` and `PLUGIN_GUIDE_KR.md` to document the Zotero
  opener fallback unload behavior.
- Added a G17-11 main source-contract test, then routed `onunload`, scroll
  debounces, settings migrations, `updateSettings`, `saveSettings`, and LLM
  usage accounting through serialized `persistSettings()`.
- Updated `PLUGIN_SCHEMA.md` to document the plugin settings single-writer
  invariant.
- Removed dead `settings.ts` `startProviderLogin` / `providerLabel` helpers and
  dead `cliAuth.ts` `normalizeExpiry`, with source guards.
- Removed the hardcoded stale-model denylist from
  `migrateUnavailableModelDefaults`; migration now uses the bundled catalogue
  check directly, with a source guard.
- Replaced duplicated inline device-registry writes in `cacheBackendCommand` and
  `syncDeviceRegistryFromSyncthing` with async `writeDeviceRegistry()`, with a
  source guard.
- Bumped versions to `0.27.3` in `backend/pyproject.toml`,
  `plugin/package.json`, `plugin/package-lock.json`, and `plugin/manifest.json`.
- Added `CHANGELOG.md` notes for v0.27.3.
- Re-ran the new parity test successfully.
- Updated `.agents/ROADMAP.md` and `.agents/plans/01_roadmap_evidence.md` so
  they no longer say Phase B is waiting on S1 triage.

Validation so far:

- `scripts/backend-check pytest backend/tests/test_docs_surface_parity.py`: passed
  with 5 tests after the Failure Atlas README, `curate.yml` single-source, and
  CLI-reference guards were added.
- `npx vitest run -c ./vitest.config.ts src/settings.test.ts`: passed with 6
  tests after G17-1.
- `npx vitest run -c ./vitest.config.ts src/mainSecurity.test.ts`: failed first
  with the new G17-5 guard before implementation.
- `npx vitest run -c ./vitest.config.ts src/mainSecurity.test.ts`: passed with
  the G17-5/G17-6/G17-9 source guards after implementation.
- `npx vitest run -c ./vitest.config.ts src/zotero/profileBinding.test.ts`:
  failed first because `profileBinding` did not exist, then passed with 4 tests.
- `npx vitest run -c ./vitest.config.ts src/zotero/profileBinding.test.ts src/ui/zoteroWizardModal.test.ts src/mainSecurity.test.ts`:
  passed with 17 tests after G17-6.
- `npx vitest run -c ./vitest.config.ts src/settings.test.ts` and
  `src/auth/cliAuth.test.ts`: failed first with G17-2/G17-3 dead helpers, then
  passed after removal.
- `npx vitest run -c ./vitest.config.ts src/mainSecurity.test.ts`: failed first
  with the new G17-11 single-writer guard, then passed after implementation.
- `npx vitest run -c ./vitest.config.ts src/mainSecurity.test.ts`: failed first
  with the new G17-4 stale-denylist guard, then passed after implementation.
- `npx vitest run -c ./vitest.config.ts src/mainSecurity.test.ts`: failed first
  with the new G17-8 async device-registry writer guard, then passed after
  implementation.
- `npx tsc --noEmit`: passed after the final plugin changes.
- `scripts/backend-check ruff`: passed.
- `scripts/backend-check mypy`: passed.
- `scripts/backend-check pytest backend/tests/test_docs_surface_parity.py backend/tests/test_spec_sync.py`: passed with 15 tests.
- `npx vitest run -c ./vitest.config.ts`: passed, 61 files / 611 tests.
- `git diff --check`: passed.
- `scripts/backend-check pytest`: passed, 1090 passed / 6 skipped / 5 xfailed.

## Critical Context

- Current changes now include plugin runtime code, so v0.27.3 has been applied.
- Pre-existing uncommitted Phase A diagnosis artifacts are still present in the
  working tree and should not be discarded:
  - `.agents/plans/diagnosis/G17-plugin-rest.md`
  - `.agents/plans/diagnosis/G18-docs-code-parity.md`
  - `.agents/plans/diagnosis/G19-docs-redundancy.md`
  - `.agents/plans/diagnosis/INDEX.md`

## Immediate Next Action

Continue remaining Phase B work. Good next candidates are:

- G17 S3 cleanup (citekey resolution, legacy `imageFolder` migration).
- Larger architectural S2s: XC-1 broad-except narrowing and CM-1/PL-1/DB-2
  god-file decomposition.
