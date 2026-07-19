# v0.35.0 Model Catalogue Refresh Evidence Ledger

Date: 2026-07-19

## Rollback Anchor

- Working branch: `release/v0.35.0`
- Current branch head before model-refresh planning: `c9f5726`
- Merged hotfix baseline: `34636fd` (PR #86, merged 2026-07-19).

## Current Worktree Reality

- The pre-existing user-owned `plugin/package-lock.json` edit was preserved
  through the master merge. The merged v0.34.1 lockfile superseded its older
  0.34.0 version value, and the release bump then reconciled the lockfile to
  0.35.0 with the other manifests.
- The merged hotfix baseline is present on the release branch at merge commit
  `7e75b48`.

## Runtime Evidence

- `codex-cli 0.139.0`; cache fetched `2026-07-19T07:50:55Z`.
- Visible Codex entries: Sol, Terra, Luna, GPT-5.5. Effective context: 272K.
- Sol/Terra support through `ultra`; Luna through `max`; GPT-5.5 through
  `xhigh`.
- `claude` version `2.1.175`; help accepts efforts
  `low|medium|high|xhigh|max` and current aliases/full IDs such as
  `claude-fable-5`.
- Anthropic official docs confirm effort support for Fable 5, Opus 4.8, and
  Sonnet 4.6; Haiku 4.5 has no effort dimension.

## Code/Document Divergence Baseline

- Backend default and guide examples still select GPT-5.5.
- Codex TypeScript/spec/guide effort unions stop at `xhigh`.
- Plugin schema requires nonexistent `supportsThinking`.
- Model transition behavior differs among settings, sidebar, dashboard, and
  load migration.
- Claude plugin command always emits `--effort`.
- Plugin context clipping uses characters although catalogue context is shown
  as tokens.

## Pre-Implementation Gates

- Update `release/v0.35.0` from merged master without overwriting the user-owned
  lockfile edit.
- Capture a fresh test baseline after that branch update.
- Stop if the installed CLI catalogue changes again before implementation; the
  locked tables must be revalidated rather than guessed.

## Post-Implementation Evidence

- Documentation-first contract: `333d6d7`.
- Failing regression tests before implementation: `a4ea37e`.
- Backend/plugin implementation: `aa7ada5`.
- Backend full suite: `1217 passed, 6 skipped, 5 xfailed`.
- Backend static gates: Ruff clean; mypy clean across 125 source files.
- Plugin full suite: 65 files, 678 tests passed.
- Plugin TypeScript check and production build passed.
- Version/spec consistency: 10 tests passed; backend, package, lockfile, plugin
  manifest, and all four static spec titles declare v0.35.0.
- Model/spec focused rerun after refreshing the editable dev install: 28 tests
  passed; `wiki version` reports 0.35.0.

## Testbed Evidence

- Reinitialized the active `gaussian_splatting` scenario and migrated the
  generated vault to schema v1.
- `wiki status`, `wiki add`, `wiki sync`, and `wiki lint` passed; lint reported
  100/100 with zero errors, warnings, or infos.
- Reference Mode rejected an unregistered external root, then accepted the same
  Zotero PDF after its machine-local named root was explicitly registered.
- The import emitted only
  `04_Resources/References/Zwicker et al. - 2002 - EWA splatting.md`; the
  testbed PDF count remained 3 before and after, proving no hard copy.
- Temporary global `external.path_roots` and `external.zotero.root_keys` values
  were restored to their original `{}` and `[]` values immediately afterward.

## Release Decision

- All P0-P6 gates passed. v0.35.0 is release-ready.
- PL-1 plugin decomposition remains excluded and is the next v0.36.0 milestone.
