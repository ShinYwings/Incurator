# RELAY - Active Milestone: v0.34.0 (CM-1 Command Module God-File Decomposition)

## Goal

Decompose the backend command-module god-files into modular package structures
with zero regression in CLI commands, MCP tools, or plugin API endpoints.

## Plan Reference

- Parent Master Plan: `.agents/plans/01_system_stability_overhaul.md`
- PM Draft Briefing: `.agents/drafts/10_cm1_god_file_decomposition.md`
- CM-1 plan, domain analyses, Arena notes, and evidence ledger were committed
  in `0d9c746` and then removed from the active workspace per release cleanup.

## Analysis & Reasoning

- Current branch: `release/v0.34.0`.
- Implementation split completed:
  - `curator.cli` is now a root facade that wires isolated command-module
    Typer apps top-down.
  - `curator.commands.*` owns the extracted CLI command groups and shared
    command helpers.
  - `curator.mcp.server` owns the MCP server implementation, with
    `curator.mcp_server` preserved as a compatibility facade.
  - `curator.plugin_api` is now a package with endpoint/domain modules and
    compatibility exports.
- Reviewer plan corrections were honored:
  - No centralized Typer app registry or subcommand module import cycle.
  - No module-level MCP tool decorators outside the dynamic `build_server()`
    server instance path.
  - Extracted plugin API modules use parent-relative imports where needed.
- Version metadata and specs were synchronized to `0.34.0`.

## Progress Status

- [x] Post-merge IDLE reset on `master` completed.
- [x] Created `release/v0.34.0` branch.
- [x] Authored and committed the CM-1 Arena plan artifacts.
- [x] Human approval received to proceed with implementation.
- [x] Added characterization coverage before moving code.
- [x] Implemented CM-1 decomposition with behavior-preserving exports and
  registrations.
- [x] Updated relevant specs and changelog/version metadata.
- [x] Ran backend checks, plugin tests, and testbed validation.
- [x] Removed active CM-1 plan artifacts after committing them to Git history.
- [ ] Push `release/v0.34.0` and open the PR.

## Validation

- `scripts/backend-check pytest` passed: 1208 passed, 6 skipped, 5 xfailed.
- `scripts/backend-check pytest backend/tests/test_spec_sync.py` passed: 10
  passed.
- `scripts/backend-check ruff` passed.
- `scripts/backend-check mypy` passed.
- `npx vitest run -c ./plugin/vitest.config.ts` passed: 669 tests.
- `git diff --check` passed.
- Testbed (`VAULT_ROOT=testbed`, Gaussian Splatting scenario) passed:
  `wiki status`, `wiki migrate`, `wiki add`, `wiki sync`, `wiki lint`, and
  `wiki reindex`.
- `wiki query "Summarize the core concepts in this vault."` exited
  successfully, but the captured terminal output did not include a rendered
  answer before returning to the prompt.

## Critical Context / Blockers

- No active implementation blocker remains.
- Do not recreate `.agents/plans/10_cm1_god_file_decomposition.md` unless a
  new review finding re-enters the plan-first workflow.

## Immediate Next Action

Push the release branch and open the v0.34.0 PR.
