"""Scenario 2: update a workspace Exhibition through MCP and trigger sync."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import yaml
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _data(result):
    if hasattr(result, "content") and result.content:
        return json.loads(result.content[0].text)
    return result


async def run_scenario() -> None:
    root = Path("testbed").resolve()
    workspace = root / "01_Workspaces" / "Gaussian Splatting Geometry Lab"
    if not (workspace / "curate.yml").exists():
        raise SystemExit("workspace curate.yml missing")

    env = os.environ.copy()
    env["WIKI_ROOT"] = str(root)
    env["WORKSPACE_PATH"] = str(workspace)

    params = StdioServerParameters(command=sys.executable, args=["-m", "llm_wiki.cli", "mcp"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            layers = _data(await session.call_tool("curator_layer_index", arguments={}))
            exhibitions = layers.get("layers", {}).get("exhibition", {}).get("samples", [])
            if not exhibitions:
                raise SystemExit("no Exhibition nodes; run wiki curate first")

            exh_id = exhibitions[0]
            node = _data(await session.call_tool("curator_get_node", arguments={"node_id": exh_id}))
            body = node["body"].rstrip() + "\n\n## Agent Session Notes\n\nWorkspace agent verified this Exhibition during MCP scenario testing.\n"
            fm = yaml.safe_dump(node["frontmatter"], sort_keys=False)
            updated = f"---\n{fm}---\n{body}\n"
            result = _data(
                await session.call_tool(
                    "curator_update_node",
                    arguments={"node_id": exh_id, "new_content": updated},
                )
            )
            assert result.get("updated"), result
            print("scenario_2_agent_exhibition_update: ok")


if __name__ == "__main__":
    asyncio.run(run_scenario())
