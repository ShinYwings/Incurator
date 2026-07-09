# CM-1 Roadmap Evidence Ledger

Date: 2026-07-09

## Rollback Anchor

- Branch: `release/v0.34.0`
- Upstream: `origin/release/v0.34.0`
- Worktree before planning edits: only `.agents/RELAY.md` was dirty from relay
  refresh.
- No implementation files were changed during plan synthesis.

## Current Repository Reality

- `backend/src/curator/cli.py`: 7,611 lines.
- `backend/src/curator/mcp_server.py`: 3,491 lines.
- `backend/src/curator/plugin_api.py`: 1,100 lines.
- Existing modular packages already include `curator.db`, `curator.retrieval`,
  `curator.pipeline`, `curator.prompting`, `curator.inspection`, and
  `curator.workspace`.
- `plugin_api.py` is currently a backend-local function API, not an HTTP router.

## Public Import Reality

Tests currently import:

- `from curator.cli import app`
- `from curator.cli import _maybe_auto_export`
- `from curator.cli import _filter_sync_structural_issues`
- `from curator.cli import _parse_persona_done_response`
- `from curator.cli import _run_curator_persona_wizard`
- `from curator.mcp_server import build_server`
- `from curator import plugin_api`

These imports are compatibility requirements for CM-1.

## Docs Reality

- `SYSTEM_BEHAVIOR.md` title line is currently `v0.33.0`.
- `PLUGIN_SCHEMA.md` title line is currently `v0.33.0`.
- CM-1 is behavior-preserving. Specs/guides should document the internal
  transport-module ownership change without changing user command semantics.
- If this release bumps from `0.33.x` to `0.34.0`, the mandatory spec title line
  sync must update all static spec titles to the `v0.34` line during the release
  step.

## Prior Art Evidence

- Typer supports nested apps added to a root app with `add_typer()`:
  https://typer.tiangolo.com/tutorial/subcommands/add-typer/
- Click command groups provide nested command boundaries with command-local
  arguments:
  https://click.palletsprojects.com/en/stable/commands/
- FastMCP tools are ordinary Python functions exposed as executable protocol
  capabilities:
  https://gofastmcp.com/servers/tools

## Pre-Implementation Validation To Run

Before extraction:

- `scripts/backend-check pytest backend/tests/test_cli_commands.py`
- `scripts/backend-check pytest backend/tests/test_plugin_cli.py`
- `scripts/backend-check pytest backend/tests/test_mcp_version.py`
- New characterization tests must be added and initially pass against the
  current monolithic files.

After each extraction phase:

- Targeted characterization test subset for the touched surface.
- `scripts/backend-check ruff`
- `scripts/backend-check mypy`
- `scripts/backend-check pytest`

Before release:

- `npx vitest run -c ./plugin/vitest.config.ts`
- `git diff --check`
- Testbed smoke with the active scenario:
  `VAULT_ROOT=testbed wiki status`, `VAULT_ROOT=testbed wiki add`,
  `VAULT_ROOT=testbed wiki sync`, and `VAULT_ROOT=testbed wiki lint`.

## Blockers And Stop Conditions

- Stop if a characterization test exposes existing behavior that appears buggy.
- Stop if extraction requires a DB schema or JSON contract change.
- Stop if any hidden plugin command output shape changes.
- Stop if MCP tool schema comparison shows renamed/missing parameters.
- Stop if CLI extraction introduces a central Typer sub-app registry that imports
  command modules for decorator side effects. Each command module must own its
  own sub-app, and `curator.cli` must wire the tree top-down.
- Stop if MCP extraction uses module-level `@mcp.tool()` decorators. Tool modules
  must export registrar functions that receive the `FastMCP` instance created by
  `build_server()`.
- Stop if plugin API package extraction leaves parent-sibling imports as
  single-dot relative imports. Extracted modules under `curator.plugin_api`
  must use double-dot imports for `curator` siblings.

## Plan Review Corrections Incorporated

The 2026-07-09 plan review identified three structural flaws in the first CM-1
plan draft:

1. Centralized Typer app construction would risk a registry/command cyclic
   import.
2. Moving `plugin_api.py` into a package without import rewrites would make
   single-dot imports resolve under `curator.plugin_api`.
3. Extracted MCP modules cannot use module-level decorators because `FastMCP` is
   created inside `build_server()`.

The master plan, domain analyses, and Arena consensus now include these
constraints explicitly.
