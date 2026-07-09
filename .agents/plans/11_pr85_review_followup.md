# v0.34.0 PR #85 Review Follow-up Plan

Date: 2026-07-09
Status: APPROVED FOR SMALL REVIEW FIXES - Review feedback captured; no public contract or schema change.

## 1. Objective

Address the eight PR #85 review findings without changing CLI command names,
plugin JSON payload contracts, MCP tools, or schema behavior.

## 2. Explicit Non-Goals

- Do not change user-facing command output except for preserving existing JSON
  and error semantics.
- Do not redesign the command package split.
- Do not add schema migrations or new plugin settings.

## 3. Strict Quality Conditions & Release Gates

- Each resource-owning command must close clients on success and failure.
- Retry/add bulk state resets must use one DB connection per batch, not one per
  row.
- The reported `test_plugin_models_ollama_lists_with_install_and_ram_flags`
  must pass locally after the patch.
- Run focused pytest, ruff, mypy, and `git diff --check` before pushing.

## 4. Locked Design Decisions

- Catch `SystemExit` in `models ensure` when vault discovery is optional.
- Use `try/finally` close guards for `_start_client`, workspace wizard clients,
  base plugin PDF clients, and resolved extraction clients.
- Use a single `UPDATE ... WHERE id IN (...)` query for each affected batch.
- Treat the CI failure as unresolved until the named test passes after the
  patch; if it remains local-only green, push and let CI rerun on the new SHA.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: No broad command refactor, no unrelated CI cleanup, no plugin
  frontend changes.
- **Stop Conditions**: Stop if the named CI test fails locally after patching or
  if closing the base/extraction clients would double-close the same object
  without an identity guard.

## 6. Evidence Ledger

- Current branch: `release/v0.34.0`.
- Current worktree before follow-up: clean.
- PR: https://github.com/ShinYwings/Incurator/pull/85
- Local reproduction: `test_plugin_models_ollama_lists_with_install_and_ram_flags`
  passed before patch on current branch, so the follow-up must rerun it and let
  GitHub CI re-evaluate the updated commit.

## 7. Execution Phases

- **P0 - Research**: Inspect inline review threads, target files, and failing
  test.
- **P1 - Tests First**: Add focused tests for optional vault fallback, client
  closure, and bulk update behavior where existing coverage does not lock the
  reviewer scenario.
- **P2 - Implementation**: Patch the five command modules with narrow changes.
- **P3 - Validation**: Run focused pytest, reported test, ruff, mypy, and diff
  whitespace checks.
- **P4 - PR Update**: Commit, push, update relay/roadmap, and let CI rerun.
