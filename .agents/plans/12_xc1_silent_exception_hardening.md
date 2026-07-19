# v0.36.1 Master Implementation Plan

Date: 2026-07-19
Status: DRAFT — Arena complete; awaiting user approval before implementation.

## 1. Objective

Classify and harden the 28 syntactically silent broad-exception handlers in
`commands/`, `mcp/`, and `plugin_api/`. Expected failures must be narrowed;
intentional best-effort or cleanup failures must become observable without
changing existing fallbacks, public envelopes, exit codes, or MCP stdio.

Definition of done:

- no unexplained `except Exception: pass` remains in the target packages;
- each changed site has a failing failure-injection or policy test first;
- public CLI/MCP/plugin response shapes and non-fatal behavior are preserved;
- docs state the exception/observability contract and all CI/testbed gates pass.

## 2. Explicit Non-Goals

- No audit or rewrite of all 148 broad catch-and-return handlers.
- No new CLI flag, MCP tool parameter, plugin JSON field, schema, or migration.
- No changes to retrieval, DAG compilation, prompts, or plugin UI.
- No generic exception framework or decorator abstraction.

## 3. Strict Quality Conditions & Release Gates

- Tests reproduce each fallback/error seam before application changes.
- MCP stdout remains protocol-only; diagnostics use module logging.
- Expected standard-library failures use explicit exception tuples.
- Broad cleanup/third-party catches require an inline reason, logging, and a
  reviewed static-policy allowlist entry.
- `scripts/backend-check pytest`, `ruff`, `mypy`, plugin Vitest/TypeScript/build,
  and `gaussian_splatting` testbed smoke all pass.

## 4. Locked Design Decisions (Arena Consensus)

- Patch version `0.36.1`: internal bug hardening, no new capability or contract.
- Scope by semantic silence, not raw `Exception` count.
- Preserve boundary catch-and-envelope behavior for CLI/MCP/plugin APIs.
- Narrow JSON/filesystem/config conversions; retain justified broad catches for
  arbitrary LLM/client cleanup with debug logging.
- Reuse existing `_warn`, warnings arrays, and module loggers; introduce no new
  response field.
- Add an AST policy test so new silent broad handlers fail CI.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: catch-and-return boundary audit, other backend modules, warning
  schema redesign, model/provider behavior changes.
- **Stop Conditions**: stop if a change requires a public envelope/exit-code
  change, emits MCP stdout diagnostics, changes persistence/schema, or makes an
  optional startup/fallback path fatal.

## 6. Evidence Ledger

- Current repository/doc/handler reality and prior art:
  `.agents/plans/12_roadmap_evidence.md`.
- Rollback anchor: PR #88 merge `b2a26e3`.
- No user-owned worktree changes were present at branch creation.

## 7. Execution Phases (Follow TDD and CI at each phase)

- **P0 — Policy Baseline**
  - Add AST inventory/policy tests for silent broad handlers and reviewed
    classifications.
  - Verify the tests fail on current unclassified sites.
- **P1 — Contract Specification**
  - Update `SYSTEM_BEHAVIOR.md` and the closest EN guide first, then KR if the
    user-visible warning contract changes. Record MCP stdio and fallback rules.
- **P2 — Command Handlers**
  - Add failure-injection tests and harden the five command silent sites.
  - Verify targeted tests, full pytest, Ruff before continuing.
- **P3 — MCP Handlers**
  - Add tests and harden the 22 MCP silent sites in small semantic clusters:
    path/parse, optional suggestions, cleanup, worker/provisioning.
  - Verify MCP tests, full pytest, Ruff, and stdio cleanliness.
- **P4 — Plugin API Handler**
  - Test and make promotion classification fallback observable without changing
    the success envelope.
- **P5 — Release Validation**
  - Run full backend/plugin CI and `gaussian_splatting` add/sync/lint plus
    autosync quiescence check.
  - Update v0.36.1 manifests/changelog, complete evidence, clean roadmap/report,
    delete implemented plan artifacts, release commit, push, and open PR.
