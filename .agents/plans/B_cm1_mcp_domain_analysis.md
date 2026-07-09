# B - MCP Domain Analysis

Date: 2026-07-09

## Design Constraints From Codebase

- `backend/src/curator/mcp_server.py` is 3,491 lines.
- `build_server()` starts around line 679 and registers all tools on a fresh
  FastMCP instance.
- Existing tests import `curator.mcp_server.build_server`.
- The module includes standalone persona update helpers before server creation.
- MCP handlers call shared services and also call `plugin_api` for some PDF and
  source-context behavior.

## Docs And Spec Invariants

- `MCP_USER_GUIDE.md` is the user-facing MCP tool guide.
- `SYSTEM_BEHAVIOR.md` states MCP tools are external-agent safe transport
  surfaces backed by shared services.
- MCP tools must not mutate read-only source truth except through explicit
  approved backend operations.

## Alternatives And Tradeoffs

- Keep all decorators in `build_server()`: preserves closure simplicity but keeps
  the god-file intact.
- Registrar functions per domain: slightly more import wiring, but each file can
  attach tools to a passed `FastMCP` instance while preserving `build_server()`.
- New MCP framework or provider abstraction: rejected as scope creep.

## Final Decision

Create `curator.mcp` as an internal package with a `server.py` builder and
domain registrar modules. Keep `curator.mcp_server.build_server()` as the public
facade.

Extracted MCP modules must not use module-level `@mcp.tool()` decorators. The
`FastMCP` instance is created dynamically inside `build_server()`, so domain
modules must expose registrar functions that receive that instance and define or
attach decorated tool functions inside the registrar call.

## Pseudocode

```python
# curator/mcp/tools/sources.py
def register_source_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def curator_register_source(...):
        ...

# curator/mcp/server.py
def build_server() -> FastMCP:
    mcp = FastMCP(...)
    register_zotero_tools(mcp)
    register_source_tools(mcp)
    register_query_tools(mcp)
    register_context_tools(mcp)
    register_workspace_tools(mcp)
    return mcp

# curator/mcp_server.py
from .mcp.server import build_server
```

## Required Characterization

- Assert `build_server()` returns a server exposing the same tool names.
- Assert representative tool schemas keep parameter names/defaults.
- Assert `curator_get_version`, `curator_status`, `curator_query`,
  `curator_get_pdf_context`, and source registration tools remain present.
