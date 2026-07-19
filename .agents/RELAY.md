# RELAY - v0.35.0 Release Publication

## Goal

Publish the completed Claude/Codex model-catalogue refresh from
`release/v0.35.0` without mixing in the deferred PL-1 decomposition.

## Plan Reference

- v0.35 model-refresh plan artifacts are ready for workflow-mandated deletion;
  their implementation and validation evidence is preserved in Git history.
- Deferred next milestone: `.agents/plans/11_pl1_plugin_decomposition.md`.

## Analysis & Reasoning

- PR #86 merged the v0.34.1 Knowledge Sync loop hotfix at `34636fd`; release
  merge commit `7e75b48` carries it into v0.35.0.
- Installed Codex CLI/cache and Claude Code values were used as the executable
  catalogue contract. Public API-only context claims were not substituted for
  CLI behavior.
- Model-specific effort normalization is shared by settings, sidebar,
  dashboard, and load migration. No-effort models omit CLI flags; Claude image
  calls preserve configured effort.
- The pre-existing package-lock edit was preserved and superseded by the merged
  0.34.1 baseline before all manifests were bumped to 0.35.0.

## Progress Status

- [x] v0.34.1 hotfix merged and integrated.
- [x] Docs/spec contract updated in English then Korean.
- [x] Failing backend/plugin regression tests added before implementation.
- [x] Backend and plugin catalogue/effort implementation completed.
- [x] Full backend CI: 1217 passed, 6 skipped, 5 xfailed; Ruff and mypy clean.
- [x] Full plugin CI: 65 files / 678 tests; TypeScript and production build clean.
- [x] Gaussian Splatting testbed status/add/sync/lint and external Reference
  Mode no-copy validation passed.
- [x] v0.35.0 manifest, lockfile, changelog, and four spec-title versions agree.
- [ ] Delete completed v0.35 plan artifacts, create the final release commit,
  push, and open the release PR.

## Critical Context / Blockers

- No blockers.
- PL-1 remains v0.36.0 scope and must not enter this release.
- Temporary testbed external-root config was restored to its original empty
  global values.

## Immediate Next Action

Commit the validation ledger/roadmap state, delete the completed v0.35 plan
artifacts, create `chore(release): v0.35.0`, then push and open the PR.
