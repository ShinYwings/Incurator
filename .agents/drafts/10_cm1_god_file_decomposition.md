# CM-1 God-File Decomposition Briefing: `cli.py`, `mcp_server.py`, and `plugin_api.py`

## 1. Problem Definition & Architectural Debt

The Incurator backend currently houses three monolithic "god-files" in `backend/src/curator/` that violate separation of concerns, slow down IDE indexing, increase merge conflicts, and bundle disparate domains into single files:

1. **`backend/src/curator/cli.py` (7,611 LOC)**:
   - Houses the top-level Typer application (`app`) and over 25 subcommand groups (`source_app`, `inspect_app`, `workspace_app`, `config_app`, `config_secret_app`, `persona_app`, `config_models_app`, `testbed_app`, `jobs_app`, `plugin_app` with its 12 nested subcommands, `devices_app`, `db_app`, `models_app`, `prompt_app`, `insight_app`, `mcp_app`).
   - Mixes CLI argument parsing, console formatting/styling helpers (`_ok`, `_err`, `_warn`, `_status_style`), helper utilities (`_resolve_root_or_die`), orchestration logic, and command registration.

2. **`backend/src/curator/mcp_server.py` (3,491 LOC)**:
   - Houses the entire Model Context Protocol (MCP) server implementation, including all tool definitions, JSON-RPC handling, schema formatting, and command/query dispatch across knowledge graph, RAG, curation, and vault operations.

3. **`backend/src/curator/plugin_api.py` (1,100 LOC)**:
   - Houses the local HTTP server endpoints and handlers serving the Obsidian plugin (search, status, jobs, ingest, chat sidechat/popover execution, Zotero integrations).

## 2. Core Architectural Principles & Prior Art

Following standard enterprise CLI/server patterns (e.g., mature Typer/Click command packages, FastAPI router packages, modular MCP tool registries):

### A. Modular Package Seams (`curator/commands/`, `curator/mcp/`, `curator/api/`)
- **CLI Decomposition (`curator/commands/`)**:
  - Keep `backend/src/curator/cli.py` as a slim top-level entrypoint that initializes the root Typer `app` and includes/adds sub-typers from focused command modules inside `backend/src/curator/commands/`.
  - Cohesive command modules should group related domains:
    - `commands/sources.py` (`source_app`)
    - `commands/jobs.py` (`jobs_app`)
    - `commands/db.py` (`db_app`)
    - `commands/config.py` (`config_app`, `config_secret_app`, `config_models_app`)
    - `commands/plugin.py` (all `plugin_app` and sub-commands: `plugin_zotero_app`, `plugin_source_app`, `plugin_pdf_app`, `plugin_context_app`, etc.)
    - `commands/inspect.py` (`inspect_app`, `insight_app`)
    - `commands/prompts.py` (`prompt_app`, `persona_app`)
    - `commands/devices.py` (`devices_app`)
    - `commands/workspace.py` (`workspace_app`, `testbed_app`)
    - `commands/mcp.py` (`mcp_app`)
    - Shared UI/helper formatting utilities extracted to `backend/src/curator/commands/helpers.py` or `backend/src/curator/cli_helpers.py`.

### B. Safety-Net First (Characterization Coverage)
- Before moving functions or breaking up modules, ensure comprehensive characterization tests exist.
- Verify that every CLI command name, argument signature, option flag, and output exit code remains 100% backward-compatible.
- Ensure all existing test suites importing `from curator.cli import ...` or invoking `CliRunner` continue to pass without breaking public imports (re-export critical symbols in `cli.py` if imported externally by tests).

## 3. Success Criteria & Verification Gates

1. **Zero Regression in CLI, MCP, and Plugin API Surface**:
   - `wiki --help` and every subcommand (`wiki status`, `wiki db autosync`, `wiki plugin query`, etc.) must execute identically.
   - All MCP tools registered in `mcp_server.py` must retain identical tool names, input schemas, and execution behavior.
   - All HTTP endpoints in `plugin_api.py` must retain identical route definitions and response payloads.

2. **Strict Environment & Quality Validation**:
   - Run `scripts/backend-check pytest` across the entire test suite (`backend/tests/`).
   - Run `scripts/backend-check ruff` and `scripts/backend-check mypy` with zero errors.
   - Check `git diff --check` to ensure no trailing whitespaces or formatting issues.
