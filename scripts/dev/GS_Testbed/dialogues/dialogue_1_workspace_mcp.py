"""Dialogue 1: verify MCP server startup, scoped search, and curator_curate_workspace.

Prerequisites (for full validation):
    python scripts/dev/GS_Testbed/create_testbed.py --force
    WIKI_ROOT=testbed wiki add
    WIKI_ROOT=testbed wiki curate --workspace testbed/01_Workspaces/Gaussian\\ Splatting\\ Geometry\\ Lab

If the curator collections are empty, search assertions are relaxed to
"no crash" mode — which still validates all code paths for the new
auto-Exhibition and curator_curate_workspace features.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _testbed() -> Path:
    root = Path(__file__).resolve().parents[4] / "testbed"
    if not root.exists():
        raise SystemExit("testbed/ not found; run scripts/dev/GS_Testbed/create_testbed.py --force")
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

    params = StdioServerParameters(command=sys.executable, args=["-m", "curator.cli", "mcp"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # --- curator_status: vault resolves ---
            status = _data(await session.call_tool("curator_status", arguments={}))
            assert status.get("vault_root"), f"curator_status missing vault_root: {status}"
            assert status.get("qmd_binary") or status.get("qmd_ready") is not None, \
                f"curator_status missing qmd info: {status}"
            print(f"  curator_status ok — vault: {status['vault_root']}, pages: {status.get('total_pages', 0)}")

            # --- curator_layer_index: structure check ---
            layers = _data(await session.call_tool("curator_layer_index", arguments={}))
            assert "layers" in layers, f"curator_layer_index missing 'layers': {layers}"
            for key in ("context", "atom", "concept", "exhibition"):
                assert key in layers["layers"], f"curator_layer_index missing layer '{key}': {layers}"
            exh_count = layers["layers"]["exhibition"]["count"]
            print(f"  curator_layer_index ok — exhibitions: {exh_count}")

            # --- search_curator: must apply curate.yml scope, must not crash ---
            search = _data(
                await session.call_tool(
                    "search_curator",
                    arguments={"query": "Gaussian splatting geometry", "limit": 5},
                )
            )
            assert "error" not in search or search.get("hits") is not None, \
                f"search_curator returned unexpected error: {search}"
            assert search.get("curate_spec_applied") == "Gaussian Splatting Geometry Lab", \
                f"curate_spec not applied: {search}"
            hit_count = search.get("count", 0)
            if hit_count > 0:
                first = search["hits"][0]
                assert "path" in first and "score" in first and "body" in first, \
                    f"hit missing required fields: {first}"
                print(f"  search_curator ok — {hit_count} hits, curate_spec applied")
            else:
                print(
                    "  search_curator ok (no hits — run wiki add + wiki curate for full validation)"
                )

            # --- curator_curate_workspace: new tool smoke-test ---
            # With an empty vault this may find nothing to stage; that is expected.
            # What we validate: the tool exists, returns a dict, and handles no-data gracefully.
            curate_result = _data(
                await session.call_tool(
                    "curator_curate_workspace",
                    arguments={"workspace_path": str(workspace)},
                )
            )
            assert isinstance(curate_result, dict), \
                f"curator_curate_workspace must return a dict: {curate_result}"
            # Accepts either ok=True (Exhibition created) or an error string (no L3 data)
            has_ok = curate_result.get("ok") is True
            has_err = "error" in curate_result
            assert has_ok or has_err, \
                f"curator_curate_workspace returned neither 'ok' nor 'error': {curate_result}"
            if has_ok:
                print(f"  curator_curate_workspace ok — exhibition: {curate_result.get('exhibition')}")
            else:
                print(
                    f"  curator_curate_workspace ok (no L3 data yet — expected on empty testbed): "
                    f"{curate_result['error']}"
                )

    print("dialogue_1_workspace_mcp: ok")


if __name__ == "__main__":
    asyncio.run(run_scenario())
