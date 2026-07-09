"""MCP server package for Incurator."""

from .server import build_server, render_install_snippets, serve_stdio

__all__ = ["build_server", "render_install_snippets", "serve_stdio"]
