"""Scenario 1: prepare testbed workspace and verify scoped MCP search."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _testbed() -> Path:
    root = Path("testbed").resolve()
    if not root.exists():
        raise SystemExit("testbed/ not found; run scripts/create_testbed.py first")
    return root


def _workspace(root: Path) -> Path:
    workspace = root / "01_Workspaces" / "Gaussian Splatting Geometry Lab"
    if not (workspace / "curate.yml").exists():
        raise SystemExit(f"curate.yml missing: {workspace / 'curate.yml'}")
    return workspace


def _data(result):
    if hasattr(result, "content") and result.content:
        return json.loads(result.content[0].text)
    return result


async def run_scenario() -> None:
    root = _testbed()
    workspace = _workspace(root)
    env = os.environ.copy()
    env["WIKI_ROOT"] = str(root)
    env["WORKSPACE_PATH"] = str(workspace)

    params = StdioServerParameters(command=sys.executable, args=["-m", "llm_wiki.cli", "mcp"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            status = _data(await session.call_tool("curator_status", arguments={}))
            search = _data(
                await session.call_tool(
                    "search_curator",
                    arguments={"query": "Gaussian splatting geometry", "limit": 5},
                )
            )
            assert status.get("vault_root"), status
            assert search.get("curate_spec_applied") == "Gaussian Splatting Geometry Lab", search
            assert search.get("count", 0) >= 0, search
            print("scenario_1_workspace_mcp: ok")


if __name__ == "__main__":
    asyncio.run(run_scenario())
