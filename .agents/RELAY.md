# Active Relay State

**STATUS: HOTFIX IN PROGRESS.**

Goal:
- Prevent plugin/backend runtime snapshots from exporting absolute local paths in
  `status.json` / `sources.json` payloads.

Current repository state:
- Branch: `hotfix/v0.28.5-runtime-path-snapshots`
- Version target: `0.28.5`
- Working tree: hotfix changes present, not committed.

Progress status:
- Backend runtime snapshot serialization now clears absolute vault/model/cache
  paths, external source paths, absolute legacy source `relpath` values, and
  absolute device platform fields.
- Machine-local path configuration remains in repo-local `.cache/config/config.yml`.
- Plugin guide and Korean guide updated to document the sanitized runtime
  snapshot contract.
- Version bumped in `backend/pyproject.toml`, `plugin/package.json`,
  `plugin/package-lock.json`, and `plugin/manifest.json`; `CHANGELOG.md` has a
  `0.28.5` entry.

Validation completed:
- `scripts/backend-check pytest backend/tests/test_runtime_state.py backend/tests/test_spec_sync.py`
- `scripts/backend-check ruff backend/src/curator/runtime_state.py backend/tests/test_runtime_state.py`
- `scripts/backend-check mypy`
- `npx tsc --noEmit` from `plugin/`
- `npx vitest run -c ./plugin/vitest.config.ts plugin/src/ui/incuratorDashboardModal.test.ts plugin/src/agent/incuratorClient.test.ts`
- `npm run build` from `plugin/`
- Testbed runtime smoke: `.venv-dev` backend wrote
  `testbed/.curator/runtime/status.json` and `sources.json`; both files were
  parsed and verified to contain no strings beginning with `/`.

Immediate next action:
- Commit and push/open PR if requested; otherwise leave the hotfix branch for
  user review.

### Update (2026-07-01, Codex)

Investigated second_brain Obsidian agent backend discovery after device switch.
Root cause: the plugin `data.json` had `incuratorBackendCommand: "wiki"` with an
empty `incuratorRepoPath`, while this Linux device's PATH resolves bare `wiki` to
the stale Anaconda command `/home/shin/Library/anaconda3/bin/wiki` (`incurator
0.8.0`). The installed Obsidian plugin is `0.28.4`, and the matching backend is
`/home/shin/Workspace/Incurator/.venv/bin/wiki` (`0.28.4`). Updated
`/home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent/data.json`
to use that absolute backend command and set `incuratorRepoPath` to
`/home/shin/Workspace/Incurator`. Also repaired repo-local
`.cache/config/devices.json` local backend hint to the same `.venv/bin/wiki`.
Validated from the second_brain cwd: `plugin version` returns backend `0.28.4`
and `status --json` succeeds with 5 sources.
