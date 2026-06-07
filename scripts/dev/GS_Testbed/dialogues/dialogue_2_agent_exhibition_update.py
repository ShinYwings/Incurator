"""Dialogue 2: update a workspace Exhibition through MCP and trigger sync.

Tests curator_curate_workspace (creates/refreshes Exhibition) and
curator_update_node (agent correction + upstream propagation).

Prerequisites (for full validation):
    python scripts/dev/GS_Testbed/create_testbed.py --force
    WIKI_ROOT=testbed wiki add
    WIKI_ROOT=testbed wiki curate --workspace testbed/01_Workspaces/Gaussian\\ Splatting\\ Geometry\\ Lab

If no L3 Concepts exist, curator_curate_workspace returns exhibition=None and
the dialogue exits early with a clear message instead of silently passing.
"""

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


# Sentinel: set to a non-empty string to signal a prerequisite failure from inside async
_prereq_error: str = ""


async def run_scenario() -> None:
    global _prereq_error
    root = Path(__file__).resolve().parents[4] / "testbed"
    workspace = root / "01_Workspaces" / "Gaussian Splatting Geometry Lab"
    if not (workspace / "curate.yml").exists():
        _prereq_error = "workspace curate.yml missing"
        return

    env = os.environ.copy()
    env["WIKI_ROOT"] = str(root)
    env["WORKSPACE_PATH"] = str(workspace)

    params = StdioServerParameters(command=sys.executable, args=["-m", "curator.cli", "mcp"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # --- Step 1: check current Exhibition count ---
            layers = _data(await session.call_tool("curator_layer_index", arguments={}))
            exh_count_before = layers["layers"]["exhibition"]["count"]
            print(f"  exhibitions before: {exh_count_before}")

            # --- Step 2: if no Exhibitions, use curator_curate_workspace to create one ---
            if exh_count_before == 0:
                print("  no Exhibitions found — calling curator_curate_workspace...")
                curate_result = _data(
                    await session.call_tool(
                        "curator_curate_workspace",
                        arguments={"workspace_path": str(workspace)},
                    )
                )
                assert isinstance(curate_result, dict), curate_result
                if "error" in curate_result:
                    _prereq_error = (
                        f"curator_curate_workspace returned error: {curate_result['error']}\n"
                        "Run wiki add + wiki curate first, then re-run this dialogue."
                    )
                    return
                if curate_result.get("exhibition") is None:
                    _prereq_error = (
                        "curator_curate_workspace ran but created no Exhibition "
                        "(no L3 Concepts staged — run wiki add first)."
                    )
                    return
                print(f"  curator_curate_workspace ok — created {curate_result['exhibition']}")

                # re-fetch layer index to confirm Exhibition was registered
                layers = _data(await session.call_tool("curator_layer_index", arguments={}))
                exh_count_after = layers["layers"]["exhibition"]["count"]
                assert exh_count_after > 0, \
                    f"Exhibition count still 0 after curator_curate_workspace: {layers}"
                print(f"  exhibitions after auto-create: {exh_count_after}")

            # --- Step 3: grab the first Exhibition and update it ---
            exhibitions = layers["layers"]["exhibition"]["samples"]
            assert exhibitions, "No Exhibition IDs returned by curator_layer_index"
            exh_id = exhibitions[0]

            node = _data(await session.call_tool("curator_get_node", arguments={"node_id": exh_id}))
            assert "body" in node and "frontmatter" in node, \
                f"curator_get_node missing expected keys: {node}"
            print(f"  curator_get_node ok — {exh_id}")

            body = node["body"].rstrip() + "\n\n## Agent Session Notes\n\nWorkspace agent verified this Exhibition during MCP scenario testing.\n"
            fm = yaml.safe_dump(node["frontmatter"], sort_keys=False)
            updated_content = f"---\n{fm}---\n{body}\n"

            result = _data(
                await session.call_tool(
                    "curator_update_node",
                    arguments={"node_id": exh_id, "new_content": updated_content},
                )
            )
            assert result.get("updated") is True, \
                f"curator_update_node did not confirm update: {result}"
            assert "gaps" in result, f"curator_update_node missing 'gaps' key: {result}"
            assert result.get("routing_tables_rebuilt") is True, \
                f"curator_update_node did not rebuild routing tables: {result}"
            print(f"  curator_update_node ok — gaps: {len(result['gaps'])}")


def main() -> None:
    asyncio.run(run_scenario())
    if _prereq_error:
        print(f"SKIP (prerequisites not met): {_prereq_error}", file=sys.stderr)
        sys.exit(2)  # exit code 2 = skip (not an error)
    print("dialogue_2_agent_exhibition_update: ok")


if __name__ == "__main__":
    main()
