# CM-1 Command Module Decomposition - Problem Briefing

Date: 2026-07-09

## 1. Problem

The backend command boundary is concentrated in three large modules:

- `backend/src/curator/cli.py` - 7,611 lines, root Typer app, command groups,
  command handlers, output helpers, root resolution, autosync hooks, and hidden
  plugin command wrappers.
- `backend/src/curator/mcp_server.py` - 3,491 lines, FastMCP server creation,
  tool registration, tool handlers, and transport-adapter logic.
- `backend/src/curator/plugin_api.py` - 1,100 lines, backend-local function API
  used by hidden plugin JSON commands and selected MCP handlers.

The files are not broken because of size alone. They are risky because unrelated
surfaces share one edit target, making command changes harder to review and
increasing the chance that a refactor changes CLI, MCP, or plugin behavior.

## 2. Source Contracts To Preserve

- `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md` owns backend, CLI, MCP, and
  workspace behavior.
- `docs/specs/plugin_schema/PLUGIN_SCHEMA.md` owns hidden plugin command and
  Obsidian plugin contracts.
- `docs/guides/MCP_USER_GUIDE.md` documents external MCP tool behavior.
- `docs/guides/PLUGIN_GUIDE.md` documents plugin-facing backend commands.
- Existing tests import public and private symbols from the current modules,
  including `curator.cli.app`, `_maybe_auto_export`,
  `_filter_sync_structural_issues`, `_parse_persona_done_response`,
  `_run_curator_persona_wizard`, `curator.mcp_server.build_server`, and direct
  `curator.plugin_api` functions.

## 3. Prior Art

- Typer documents nested command apps with `app.add_typer()`:
  https://typer.tiangolo.com/tutorial/subcommands/add-typer/
- Click treats command groups as nested command boundaries with independent
  command arguments:
  https://click.palletsprojects.com/en/stable/commands/
- FastMCP exposes ordinary Python functions as protocol tools:
  https://gofastmcp.com/servers/tools

These sources support a conservative package split where the root module remains
the compatibility facade and domain modules register unchanged command/tool
objects.

## 4. Design Question

How can CM-1 reduce the god-file coupling while preserving every observable
contract and keeping the refactor reviewable?

The answer must:

- Add characterization tests before extraction.
- Preserve import compatibility for current tests and any downstream scripts.
- Avoid DB schema changes.
- Avoid changing CLI/MCP/plugin semantics.
- Move one surface at a time with rollback-friendly phases.
