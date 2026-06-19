# v0.16.0 Master Implementation Plan

Date: 2026-06-20
Status: DRAFT - Arena debate concluded. Awaiting implementation approval.

## 1. Objective

Purge active legacy qmd runtime, build, status, plugin, test, and agent-facing
references so DB-native search is the only live implementation path and status
contract.

Definition of done:
- Active source/test/plugin/script/guides/specs/agent-rule files no longer imply
  qmd is installed, called, configured, or a live status field.
- Current plugin and backend status surfaces use `search_*` only.
- CI guards prevent reintroducing the retired token in active functional areas.
- Version and changelog are updated for v0.16.0.

## 2. Explicit Non-Goals

- No search ranking or retrieval algorithm rewrite.
- No DB schema migration.
- No removal of DB-native query expansion semantics (`lex:`, `vec:`, `hyde:`).
- No testbed corpus redesign.
- No broad cleanup of unrelated retired EXH references.

## 3. Strict Quality Conditions & Release Gates

- No active code path may install or invoke an external qmd binary.
- Runtime and MCP status payloads must expose DB-native `search_*` fields without
  `qmd_*` compatibility keys.
- Plugin status/dashboard code must read `search_*` only.
- Backend and plugin focused tests must cover the status contract change.
- Full backend and plugin validation must pass before PR.

## 4. Locked Design Decisions (Arena Consensus)

- Replace compatibility names with DB-native search names in active code.
- Generalize useful legacy behavior without literal qmd naming, such as old URI
  normalization.
- Remove the qmd installer from the build hook.
- Keep historical benchmark evidence only if it is clearly archival and not
  agent-facing active behavior. Agent-facing docs and rules should not contain
  live qmd instructions.
- Treat this as a code behavior cleanup release and bump to v0.16.0.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: RAG quality hardening, UI/UX overhaul, native PDF annotation,
  and wikilink validation.
- **Stop Conditions**: Stop if removing `qmd_*` status keys reveals an
  un-updated plugin consumer that cannot be migrated in this branch, or if a
  testbed requires historical qmd URI support that cannot be generalized.

## 6. Evidence Ledger

- **Current Repository & Schema Reality**: DB-native search schema is current in
  `docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md`; runtime still has stale
  names and compatibility fields.
- **Current Dirty Worktree**: clean before planning; plan artifacts are the only
  intended changes at approval time.
- **Rollback Requirements**: branch is isolated from `master`; rollback is safe
  by abandoning `fix/purge-legacy-qmd-references` before merge or reverting the
  PR after merge.

## 7. Execution Phases (Follow TDD and CI at each phase)

- **P0 - Baseline & Guard Tests**
  - Add focused tests that fail on current qmd references in active functional
    areas.
  - Add/adjust backend status tests to assert only `search_*` fields.
  - Add/adjust plugin tests to assert only `search_*` consumption.

- **P1 - Docs & Contract Specification**
  - Update `docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md`,
    `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`,
    `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`, and relevant guides.
  - Update `AGENTS.md` and `CLAUDE.md` together if agent rules change.

- **P2 - Backend Runtime Cleanup**
  - Rename `_refresh_qmd_index` and update all call sites/tests.
  - Remove `qmd_*` status payload keys.
  - Rewrite MCP/search/query/router comments and docstrings.
  - Remove qmd installation from `scripts/build/hatch_build.py`.
  - Generalize legacy URI stripping.

- **P3 - Plugin Cleanup**
  - Remove `qmd_*` fallbacks.
  - Rename local variables/classes/selectors where they are search-engine UI,
    not qmd UI.
  - Update plugin source-contract tests.

- **P4 - Sweep, Version, Changelog**
  - Run the no-legacy-reference guard.
  - Bump backend/plugin/manifest/package-lock to v0.16.0.
  - Update `CHANGELOG.md`.
  - Delete implemented plan/draft artifacts after validation.

- **P5 - Validation & PR**
  - Run backend `pytest`, `ruff`, and `mypy`.
  - Run plugin Vitest, TypeScript, and production build.
  - Run testbed smoke or document any external model blocker.
  - Push branch and open PR.

