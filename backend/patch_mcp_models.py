import sys
import json
import os
from pathlib import Path

with open("src/curator/mcp_server.py", "r") as f:
    content = f.read()

# Replace curator_get_provider_config to include models
new_get_provider = """    @mcp.tool()
    def curator_get_provider_config(workspace_path: str = "") -> dict[str, Any]:
        \"\"\"Get the current LLM provider configuration and available models.\"\"\"
        paths = _resolve_paths(workspace_path)
        config = cfg.load_config(paths)
        
        models_data = {}
        try:
            models_path = Path(__file__).parent / "data" / "models.json"
            if models_path.exists():
                with open(models_path, "r", encoding="utf-8") as f:
                    models_data = json.load(f)
        except Exception:
            pass
            
        return {"ok": True, "llm": config.get("llm", {}), "models_json": models_data}
"""

import re
content = re.sub(
    r"    @mcp\.tool\(\)\n    def curator_get_provider_config.*?return {\"ok\": True, \"llm\": config\.get\(\"llm\", \{\}\)}\n",
    new_get_provider,
    content,
    flags=re.DOTALL
)

with open("src/curator/mcp_server.py", "w") as f:
    f.write(content)
print("Patched mcp_server.py for models.json")
