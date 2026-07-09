# v0.34.0 Master Implementation Plan

Date: 2026-07-09
Status: DRAFT - Arena debate concluded; awaiting human approval before implementation.

## 1. Objective

Decompose `backend/src/curator/cli.py`, `backend/src/curator/mcp_server.py`,
and `backend/src/curator/plugin_api.py` into focused internal packages while
preserving every observable CLI, MCP, and hidden plugin command contract.

Definition of done:

- `curator.cli`, `curator.mcp_server`, and `curator.plugin_api` remain valid
  public import paths.
- CLI command names, option names, hidden flags, default values, help behavior,
  exit behavior, and JSON envelopes remain unchanged.
- MCP tool names, schemas, defaults, and result shapes remain unchanged.
- Hidden plugin command wrappers keep the same backend response payloads.
- Backend checks, plugin tests, diff checks, and testbed smoke validation pass.

## 2. Explicit Non-Goals

- No DB schema changes or migrations.
- No new user-facing CLI commands, MCP tools, plugin settings, or plugin UI.
- No behavior fixes discovered during characterization unless explicitly
  approved as a separate fix.
- No service-layer redesign of retrieval, ingest, sync, or query orchestration.
- No HTTP API introduction for `plugin_api`; it remains the backend-local
  function surface behind hidden plugin commands.

## 3. Strict Quality Conditions & Release Gates

- Characterization tests are written before moving code.
- Every phase ends green on the targeted characterization tests plus
  `scripts/backend-check ruff` and `scripts/backend-check mypy`.
- Full release gate:
  - `scripts/backend-check pytest`
  - `scripts/backend-check ruff`
  - `scripts/backend-check mypy`
  - `npx vitest run -c ./plugin/vitest.config.ts`
  - `git diff --check`
- Testbed smoke must run after backend extraction:
  `VAULT_ROOT=testbed wiki status`, `add`, `sync`, and `lint`.
- Version strings in backend/package/plugin manifests must agree, and
  `CHANGELOG.md` must include v0.34.0 release notes.
- Because this is a minor-line bump, static spec title lines must be synced to
  the active `v0.34` line during the release step.

## 4. Locked Design Decisions (Arena Consensus)

- Use facade modules plus internal packages:
  - `curator.cli` -> `curator.commands.*`
  - `curator.mcp_server` -> `curator.mcp.*`
  - `curator.plugin_api` -> `curator.plugin_api.*` package modules
- Keep `curator.cli.app`, `curator.mcp_server.build_server`, and
  `from curator import plugin_api` compatible.
- Preserve tested private CLI/helper exports for this release.
- Split by transport/domain boundary, not by lower-level business-service
  redesign.
- CLI extraction runs first, MCP second, plugin API third.
- CLI command modules must each instantiate their own isolated
  `typer.Typer()` sub-app. The root `curator.cli` facade imports those sub-apps
  and wires the tree top-down with `app.add_typer()`. A centralized sub-app
  registry module is forbidden because it creates registry <-> command module
  import cycles.
- MCP extraction must use registrar functions such as
  `register_source_tools(mcp: FastMCP)`. Module-level `@mcp.tool()` registration
  is forbidden because the `FastMCP` instance exists only inside
  `build_server()`.
- `plugin_api.py` to `plugin_api/` must be an atomic module-to-package
  conversion with `__init__.py` re-exports. All extracted modules must rewrite
  relative sibling imports from `from . import ...` to `from .. import ...`
  because they move one package level deeper.
- Prior art supports this shape:
  Typer nested apps use `add_typer()`;
  Click groups are nested command boundaries;
  FastMCP exposes ordinary Python functions as tools.

## 5. Scope Exclusions & Stop Conditions

Exclusions:

- Plugin god-file decomposition (`chatSidebar.ts`, `llmClient.ts`,
  `externalPdfView.ts`) remains a later PL-1 milestone.
- Error-handling hardening beyond extraction safety remains a later XC-1 slice.
- RAG/DAG performance work remains a later performance milestone.

Stop conditions:

- Stop if a characterization test reveals existing behavior that is probably a
  bug; ask whether to preserve or fix it.
- Stop if any phase requires schema, command, MCP, or plugin JSON contract
  changes.
- Stop if any proposed CLI extraction requires command modules to import app
  objects from a central registry that also imports command modules.
- Stop if any proposed MCP extraction relies on module-level tool decorators.
- Stop if any plugin API module still contains single-dot imports for parent
  `curator` siblings after extraction.
- Stop if `plugin_api` package conversion breaks direct imports in a way that
  cannot be solved through re-exports.
- Stop after plan approval gate before implementation starts.

## 6. Evidence Ledger

- Current file sizes:
  - `cli.py`: 7,611 lines.
  - `mcp_server.py`: 3,491 lines.
  - `plugin_api.py`: 1,100 lines.
- Current branch: `release/v0.34.0`.
- Current active evidence file:
  `.agents/plans/10_roadmap_evidence.md`.
- Domain analyses:
  - `.agents/plans/A_cm1_cli_domain_analysis.md`
  - `.agents/plans/B_cm1_mcp_domain_analysis.md`
  - `.agents/plans/C_cm1_plugin_api_domain_analysis.md`
- Arena folder:
  `.agents/plans/10_cm1_god_file_decomposition_arena/`
- Existing import compatibility requirements include `curator.cli.app`,
  selected private CLI helpers, `curator.mcp_server.build_server`, and
  `curator.plugin_api` direct functions.

## 7. Execution Phases (Follow TDD And CI At Each Phase)

### P0 - Baseline And Characterization

- Add `backend/tests/test_command_surface_characterization.py`.
- Assert CLI command tree and selected help output for root, `db autosync`,
  `plugin source register`, and `mcp install`.
- Assert direct imports from `curator.cli`, `curator.mcp_server`, and
  `curator.plugin_api`.
- Assert MCP tool names and representative schemas after `build_server()`.
- Assert plugin API export set and representative validation envelopes.

Verify:

- `scripts/backend-check pytest backend/tests/test_command_surface_characterization.py`
- Targeted existing tests:
  `test_cli_commands.py`, `test_plugin_cli.py`, `test_mcp_version.py`

### P1 - Contract Documentation

- Update `SYSTEM_BEHAVIOR.md` with a behavior-preserving architecture note for
  CLI/MCP/plugin transport facades.
- Update `PLUGIN_SCHEMA.md` only if needed to clarify that hidden plugin commands
  call backend-local `plugin_api` package functions.
- Update matching guides only where they mention module ownership.
- Update Korean counterparts faithfully if guide text changes.

Verify:

- `scripts/backend-check pytest backend/tests/test_spec_sync.py`

### P2 - CLI Package Extraction

- Create `curator.commands`.
- Move shared CLI helpers first, but do not move all Typer app construction into
  a centralized registry.
- For each command group, create an isolated module-local `typer.Typer()` object
  and decorate commands against that local object.
- Keep root `app = typer.Typer(...)` and all `app.add_typer(...)` tree wiring in
  `curator.cli`, importing sub-apps from command modules in the current order.
- Move command groups incrementally:
  core/root, config, source, db, jobs, plugin, workspace/testbed, prompt/persona,
  inspect/insight, devices, MCP install/connect.
- Keep `curator.cli` as the entrypoint facade and compatibility export module.

Verify after each group:

- New characterization tests.
- Relevant existing CLI tests.
- `scripts/backend-check ruff`
- `scripts/backend-check mypy`

### P3 - MCP Package Extraction

- Create `curator.mcp`.
- Move server creation into `curator.mcp.server`.
- Move tool helpers and domain registrars incrementally.
- Every extracted tool domain module must expose registrar functions that accept
  the dynamic server instance, for example
  `def register_source_tools(mcp: FastMCP) -> None:`.
- Decorated tool functions may be defined inside those registrar functions or
  otherwise attached using the passed instance. Do not use module-level
  `@mcp.tool()` decorators.
- Keep `curator.mcp_server.build_server()` as the public facade.

Verify:

- MCP characterization tests.
- `scripts/backend-check pytest backend/tests/test_mcp_version.py`
- `scripts/backend-check ruff`
- `scripts/backend-check mypy`

### P4 - Plugin API Package Extraction

- Add export characterization first.
- Convert `plugin_api.py` into `plugin_api/` package atomically.
- Rewrite extracted sibling imports for the deeper package context:
  - `from . import db, ingest_raw, llm, ...` -> `from .. import db, ingest_raw, llm, ...`
  - lazy imports such as `from . import zotero_tools` -> `from .. import zotero_tools`
  - parser/service imports such as `from .parsers.pdf import ...` -> `from ..parsers.pdf import ...`
- Split source, PDF, context, query, and helper functions into package modules.
- Re-export existing public and tested private names from `plugin_api/__init__.py`.

Verify:

- Plugin API characterization tests.
- `scripts/backend-check pytest backend/tests/test_plugin_cli.py`
- Existing plugin API focused tests such as `test_error_handling_plugin_api.py`
  and `test_plugin_pdf_context_identity.py`.

### P5 - Full Validation And Testbed

- Run:
  - `scripts/backend-check pytest`
  - `scripts/backend-check ruff`
  - `scripts/backend-check mypy`
  - `npx vitest run -c ./plugin/vitest.config.ts`
  - `git diff --check`
- Discover or confirm the active `tests/scenarios/` scenario.
- Initialize `testbed/` if missing, then run required testbed smoke.
- Document any LLM or external dependency blockers explicitly.

### P6 - Release Hygiene

- Update versions in `backend/pyproject.toml`, `package.json`,
  `plugin/package.json`, and `plugin/manifest.json` as applicable.
- Update `CHANGELOG.md`.
- Sync static spec title lines to the v0.34 line.
- Remove implemented plan files after implementation is complete.
- Final commit: `chore(release): v0.34.0`.
- Push branch and open PR with Why, What, and How.
