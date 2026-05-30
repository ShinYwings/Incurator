import sys
import re

with open("src/curator/mcp_server.py", "r") as f:
    content = f.read()

tool_code = """
    @mcp.tool()
    def curator_get_provider_config(workspace_path: str = "") -> dict[str, Any]:
        \"\"\"Get the current LLM provider configuration.\"\"\"
        paths = _resolve_paths(workspace_path)
        config = cfg.load_config(paths)
        return {"ok": True, "llm": config.get("llm", {})}

    @mcp.tool()
    def curator_set_provider_config(
        primary: str,
        model: str = "",
        host: str = "",
        workspace_path: str = ""
    ) -> dict[str, Any]:
        \"\"\"Set the LLM provider configuration.\"\"\"
        paths = _resolve_paths(workspace_path)
        config = cfg.load_config(paths)
        llm_cfg = config.get("llm", {})
        llm_cfg["primary"] = primary
        if primary == "ollama":
            if model:
                llm_cfg["model"] = model
            if host:
                llm_cfg["host"] = host
        elif primary == "antigravity-cli":
            if model:
                llm_cfg["antigravity_think_model"] = model
        elif primary == "claude-code":
            if model:
                llm_cfg["claude_think_model"] = model
                
        config["llm"] = llm_cfg
        
        # Save to global config to match CLI behavior, or vault config if preferred
        # Since MCP server might be used across vaults, modifying vault config is safest:
        cfg.save_config(paths, config)
        return {"ok": True, "llm": config["llm"]}
"""

content = content.replace("    @mcp.tool()\n    def check_source_status", tool_code + "\n    @mcp.tool()\n    def check_source_status")

with open("src/curator/mcp_server.py", "w") as f:
    f.write(content)

print("Patched mcp_server.py")
