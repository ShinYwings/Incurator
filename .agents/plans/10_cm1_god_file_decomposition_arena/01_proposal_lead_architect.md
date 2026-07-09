# CLI/MCP/API Proposal: Facade Modules With Registrar Packages

Date: 2026-07-09 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

Keep the existing public module names as facades:

- `curator.cli`
- `curator.mcp_server`
- `curator.plugin_api`

Introduce focused packages behind them:

```text
backend/src/curator/commands/
  __init__.py
  helpers.py
  core.py
  config.py
  sources.py
  jobs.py
  db.py
  plugin.py
  mcp.py
  workspace.py
  inspect.py
  prompts.py
  devices.py

backend/src/curator/mcp/
  __init__.py
  server.py
  helpers.py
  tools/
    __init__.py
    sources.py
    query.py
    context.py
    workspace.py
    graph.py
    zotero.py
    config.py

backend/src/curator/plugin_api/
  __init__.py
  sources.py
  pdf.py
  context.py
  query.py
  helpers.py
```

`curator.cli` remains the `wiki` entrypoint. It should construct the root `app`
object, import sub-app objects from command modules, and re-export any helper
symbols already imported by tests. Each command group module owns its own
isolated `typer.Typer()` instance and command handlers. There is no central
sub-app registry module; root wiring stays top-down in `curator.cli` to avoid
registry <-> command module import cycles.

`curator.mcp_server.build_server()` remains the public entrypoint. Internally it
creates the FastMCP instance and calls tool registrar functions from
`curator.mcp.tools.*`. Registrar functions receive the dynamic `mcp` instance
and define or attach `@mcp.tool()` decorated functions inside the registrar call.
Module-level MCP decorators are forbidden because no `mcp` instance exists at
import time.

`curator.plugin_api` is currently a direct function API, not a router. Convert it
to a package with `__init__.py` re-exporting the existing function names. Hidden
plugin commands and MCP handlers continue importing `from . import plugin_api`.
All extracted modules must rewrite current single-dot sibling imports to
double-dot parent imports, e.g. `from . import db` becomes `from .. import db`.

Implementation order:

1. Add characterization tests for command tree, selected command help, MCP tool
   names, MCP version, and plugin API export set.
2. Extract CLI helper functions and app registration first.
3. Extract CLI command groups in small commits.
4. Extract MCP helper blocks and tool registrars.
5. Extract plugin API helper/domain functions.
6. Keep compatibility re-exports until all tests pass.

## 2. Pros & Cons

Pros:

- Keeps public import paths stable.
- Matches existing package style in `curator.retrieval`, `curator.pipeline`,
  `curator.prompting`, and `curator.db`.
- Supports small commits and simple rollback.
- Makes future command changes local to one package.

Cons:

- Compatibility re-exports mean the old module names remain visible.
- Some shared helpers may initially be awkwardly placed until call graph pressure
  is clear.
- Moving decorated Typer/FastMCP functions can trigger subtle registration
  changes unless tests snapshot the surface first.
