import sys

with open("src/curator/mcp_server.py", "r") as f:
    content = f.read()

import re
old_code = """        elif primary == "claude-code":
            if model:
                llm_cfg["claude_think_model"] = model
                
        config["llm"] = llm_cfg"""
        
new_code = """        elif primary == "claude-code":
            if model:
                llm_cfg["claude_think_model"] = model
        elif primary == "codex-cli":
            if model:
                llm_cfg["codex_think_model"] = model
                
        config["llm"] = llm_cfg"""

content = content.replace(old_code, new_code)

with open("src/curator/mcp_server.py", "w") as f:
    f.write(content)

print("Patched set_provider")
