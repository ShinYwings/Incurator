# Active Relay State

**STATUS: ACTIVE.**

Active branch:
- `fix/plugin-api-best-effort-warnings`

Active goal:
- Continue System Stability Overhaul G08-5 by surfacing plugin API best-effort
  maintenance warnings instead of hiding them.

Last completed release:
- v0.28.1 merged to `master` on 2026-06-29 via PR #71:
  https://github.com/ShinYwings/Incurator/pull/71

Current repository state:
- Branch: `fix/plugin-api-best-effort-warnings`
- Base: `origin/master` after v0.28.1 relay cleanup
- `.agents/USER_REPORT.md`: empty
- Roadmap queue: no urgent hotfixes; continue the System Stability Overhaul
  before lower-priority roadmap items.

Immediate next action:
- Validate and ship v0.28.2: `plugin_api.register_source` now returns success
  warnings for skipped non-fatal search-index refreshes and no longer swallows
  unexpected refresh errors.

Progress status:
- Implemented `plugin_api.register_source` `warnings: list[str]` success payload
  for skipped non-fatal search-index refresh failures.
- Narrowed the catch to expected `OSError`, `sqlite3.Error`, and
  `SearchBackendError`; unexpected errors propagate to the CLI wrapper.
- Added `backend/tests/test_error_handling_plugin_api.py`.
- Updated `PLUGIN_SCHEMA`, EN/KR plugin guide, changelog, roadmap, and version
  manifests to v0.28.2.
- Validation completed: `ruff`, `mypy`, focused backend tests, full backend
  `pytest`, root-level `vitest`, plugin `tsc`, `git diff --check`, spec-sync,
  and `VAULT_ROOT=testbed ... status --json` smoke.
- Draft PR opened: https://github.com/ShinYwings/Incurator/pull/72
- Review feedback addressed on PR #72: converted the plugin API test setup
  helper into a pytest fixture. Validation rerun: focused test file, `ruff`,
  and `mypy`.
