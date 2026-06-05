import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from curator import config as cfg
from curator import constants as consts
from curator import db, mcp_server, search


class SearchCuratorWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        for folder in (self.paths.contexts, self.paths.atoms, self.paths.concepts, self.paths.synthesis):
            folder.mkdir(parents=True, exist_ok=True)
        self.paths.internal.mkdir(parents=True, exist_ok=True)
        cfg.save_config(self.paths, cfg.DEFAULT_CONFIG)
        self.workspace = self.root / consts.DIR_WORKSPACES / "Boosted"
        self.workspace.mkdir(parents=True)
        (self.workspace / consts.FILE_CURATE_YML).write_text(
            "\n".join(
                [
                    "project: Boosted",
                    f"vault_root: {self.root}",
                    "persona:",
                    "  domain: unhelpful-domain",
                    "  disambiguation_keywords:",
                    "    - noisy-term",
                    "min_confidence: 0.6",
                ]
            ),
            encoding="utf-8",
        )
        (self.paths.synthesis / "SYN-test0001.md").write_text(
            "---\n"
            "id: SYN-test0001\n"
            "type: synthesis\n"
            "workspace: Boosted\n"
            "---\n\n"
            "# Boosted\n\nWorkspace context.",
            encoding="utf-8",
        )
        db.init_db(self.paths.state_db)
        os.environ["VAULT_ROOT"] = str(self.root)
        os.environ["CURATOR_DISABLE_INGEST_WORKER"] = "1"

    def tearDown(self) -> None:
        os.environ.pop("VAULT_ROOT", None)
        os.environ.pop("CURATOR_DISABLE_INGEST_WORKER", None)
        self.tmp.cleanup()

    def test_search_curator_retries_unboosted_workspace_query(self) -> None:
        empty = search.SearchResults(hits=[])
        hit = search.SearchResults(
            hits=[
                search.SearchHit(
                    full_path=f"{consts.LAYER_L4}/SYN-test0001.md",
                    title="Boosted",
                    score=0.9,
                    full_content="Workspace context.",
                )
            ]
        )

        server = mcp_server.build_server()
        tool = server._tool_manager._tools["search_curator"].fn

        with patch("curator.search.query", side_effect=[empty, hit]) as search_mock:
            result = tool(
                query="dual absolute quadric metric reconstruction",
                mode="lex",
                limit=5,
                workspace_path=str(self.workspace),
            )

        self.assertEqual(search_mock.call_count, 2)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["hits"][0]["path"], f"{consts.LAYER_L4}/SYN-test0001.md")


if __name__ == "__main__":
    unittest.main()
