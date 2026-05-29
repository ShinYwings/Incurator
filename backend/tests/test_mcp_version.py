import unittest
from curator.mcp_server import build_server

class McpVersionToolTests(unittest.TestCase):
    def test_curator_get_version_registered(self) -> None:
        """The curator_get_version tool must be registered in the MCP server."""
        server = build_server()
        
        # FastMCP manages tools in _tool_manager._tools
        tool_found = False
        if hasattr(server, "_tool_manager"):
            tools = getattr(server._tool_manager, "_tools", {})
            if isinstance(tools, dict):
                for name, tool in tools.items():
                    if name == "curator_get_version" or getattr(tool, "name", "") == "curator_get_version":
                        tool_found = True
                        break
            elif isinstance(tools, list):
                for tool in tools:
                    if getattr(tool, "name", "") == "curator_get_version":
                        tool_found = True
                        break
        
        self.assertTrue(tool_found, "curator_get_version tool not found in server")

if __name__ == "__main__":
    unittest.main()
