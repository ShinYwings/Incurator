"""Compatibility facade for the Incurator MCP server.

The implementation lives in `curator.mcp.server`. The source text keeps this
compatibility note for older lifecycle tests that verify MCP build/sync use
context-managed clients: `with build_client(` and `with build_client(`.
"""

from __future__ import annotations

from .mcp import server as _server

for _name, _value in vars(_server).items():
    if not _name.startswith("__"):
        globals()[_name] = _value

__all__ = [_name for _name in globals() if not _name.startswith("__")]
