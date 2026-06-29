# Active Relay State

**STATUS: ACTIVE.**

Active branch:
- `fix/mcp-register-source-warnings`

Active goal:
- Continue System Stability Overhaul G08-5 by surfacing MCP
  `curator_register_source` best-effort search-refresh warnings.

Last completed release:
- v0.28.2 merged to `master` on 2026-06-29 via PR #72:
  https://github.com/ShinYwings/Incurator/pull/72

Current repository state:
- Branch: `fix/mcp-register-source-warnings`
- Base: `origin/master` after v0.28.2 relay cleanup
- Draft PR: https://github.com/ShinYwings/Incurator/pull/73
- `.agents/USER_REPORT.md`: empty
- Roadmap queue: no urgent hotfixes; continue the System Stability Overhaul
  before lower-priority roadmap items.

Progress:
- Implemented MCP `curator_register_source` warning visibility for skipped
  non-fatal search-index refreshes.
- Added focused MCP regression tests for expected `SearchBackendError`
  warnings and unexpected `RuntimeError` propagation.
- Updated MCP user guides, SYSTEM_BEHAVIOR, changelog, and release manifests
  for v0.28.3.

Validation:
- `scripts/backend-check ruff`
- `scripts/backend-check mypy`
- `scripts/backend-check pytest backend/tests/test_error_handling_mcp_server.py backend/tests/test_error_handling_plugin_api.py backend/tests/test_register_build_split.py backend/tests/test_spec_sync.py`
- `scripts/backend-check pytest` (`1136 passed, 6 skipped, 5 xfailed`)
- `npx vitest run -c ./plugin/vitest.config.ts` (`646 passed`)
- `cd plugin && npx tsc --noEmit`
- `VAULT_ROOT=testbed PYTHONPATH=backend/src python -m curator.cli status --json`
- `git diff --check`

Immediate next action:
- Review and merge draft PR #73. After merge, truncate `.agents/RELAY.md` back
  to the minimal IDLE stub on `master`.
