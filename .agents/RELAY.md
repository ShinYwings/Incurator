# Active Relay State

**STATUS: ACTIVE.**

Active branch:
- `fix/backend-exception-narrowing`

Active goal:
- Continue the System Stability Overhaul with a focused XC-1 robustness patch
  for CLI best-effort failure visibility in backend command surfaces.

Last completed release:
- v0.28.0 merged to `master` on 2026-06-29.

Current repository state:
- Branch: `fix/backend-exception-narrowing`
- Base: `origin/master` at v0.28.0
- `.agents/USER_REPORT.md`: empty
- Roadmap queue: no urgent hotfixes; continuing the active System Stability
  Overhaul before lower-priority roadmap items.

Plan reference:
- Parent: `.agents/plans/01_system_stability_overhaul.md`
- Slice: `.agents/plans/03_robustness_slice2.md`
- Domain analysis: `.agents/plans/B_plugin_logging_and_timers.md`

Progress status:
- Implemented G07-12 sub-slice: `_sync_mcp_configs` now warns on expected
  file/JSON failures instead of silently skipping targets.
- Implemented runtime snapshot warning visibility for `wiki config provider` and
  project-scoped `wiki config set --local`.
- Fixed `plugin/vitest.config.ts` so the repo-root validation command discovers
  plugin tests.
- Version bumped to v0.28.1; changelog, specs, and EN/KR guides updated.
- Validation completed: `ruff`, `mypy`, full backend `pytest`, root-level
  `vitest`, plugin `tsc`, `git diff --check`, spec-sync tests, and testbed
  `VAULT_ROOT=testbed ... status --json` smoke.
- Draft PR opened: https://github.com/ShinYwings/Incurator/pull/71
- Review feedback addressed on PR #71:
  - wrong-shaped `mcpServers` values now warn-and-skip instead of raising
    `TypeError`;
  - runtime snapshot refresh now warns on expected `sqlite3.Error` failures for
    `config set --local` and `config provider`;
  - `config set --local` refresh also warns on expected YAML parse failures.
- Review-fix validation completed: `scripts/backend-check ruff`,
  `scripts/backend-check mypy`, `scripts/backend-check pytest
  backend/tests/test_error_handling_cli.py`, and targeted config/spec tests.

Immediate next action:
- Review and merge PR #71. After merge, continue remaining S2
  broad-except/god-file cleanup.
