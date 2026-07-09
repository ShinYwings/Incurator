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
- [x] Pushed `release/v0.34.0` and opened draft PR #85.
- [x] Captured and implemented PR #85 review follow-up hardening.

## Validation

- `scripts/backend-check pytest` passed: 1208 passed, 6 skipped, 5 xfailed.
- `scripts/backend-check pytest` after PR #85 follow-up passed: 1212 passed,
  6 skipped, 5 xfailed.
- `scripts/backend-check pytest backend/tests/test_pr85_review_followup.py
  backend/tests/test_plugin_pdf_transcribe.py backend/tests/test_plugin_cli.py
  backend/tests/test_cli_commands.py backend/tests/test_model_setup.py
  backend/tests/test_persona_wizard.py backend/tests/test_plugin_models_ollama.py
  -q` passed: 54 passed.
- `scripts/backend-check pytest backend/tests -k
  test_plugin_models_ollama_lists_with_install_and_ram_flags -vv` passed.
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
- Draft PR: https://github.com/ShinYwings/Incurator/pull/85
- Do not recreate `.agents/plans/10_cm1_god_file_decomposition.md` unless a
  new review finding re-enters the plan-first workflow.
- PR #85 review follow-up plan `11_pr85_review_followup.md` is archived in Git
  history and removed from the active workspace.

## Immediate Next Action

Wait for CI/review on PR #85 and merge when accepted.
