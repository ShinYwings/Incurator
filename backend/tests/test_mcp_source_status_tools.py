import os
import tempfile
import unittest
from pathlib import Path

from curator import config as cfg
from curator import db, mcp_server
from curator import parsers


class McpSourceStatusToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        for raw_dir in self.paths.raw_dirs:
            raw_dir.mkdir(parents=True, exist_ok=True)
        self.paths.internal.mkdir(parents=True, exist_ok=True)
        cfg.save_config(self.paths, cfg.DEFAULT_CONFIG)
        db.init_db(self.paths.state_db)
        os.environ["VAULT_ROOT"] = str(self.root)
        os.environ["CURATOR_DISABLE_INGEST_WORKER"] = "1"

    def tearDown(self) -> None:
        os.environ.pop("VAULT_ROOT", None)
        os.environ.pop("CURATOR_DISABLE_INGEST_WORKER", None)
        self.tmp.cleanup()

    def _insert_source(self, relpath: str) -> tuple[int, str]:
        source = self.root / relpath
        content_hash = parsers.parse(source).content_hash
        with db.connect(self.paths.state_db) as conn:
            cur = conn.execute(
                """INSERT INTO sources
                   (relpath, content_hash, file_type, bytes, added_at, status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    relpath,
                    content_hash,
                    source.suffix.lstrip(".") or "txt",
                    source.stat().st_size,
                    "2026-06-01T00:00:00Z",
                    "pending",
                ),
            )
        return int(cur.lastrowid), content_hash

    def _tool(self, name: str):
        server = mcp_server.build_server()
        tools = getattr(server._tool_manager, "_tools", {})
        self.assertIn(name, tools)
        return tools[name].fn

    def test_check_source_status_supports_file_hash_contract(self) -> None:
        relpath = "03_Notes/source.md"
        source = self.root / relpath
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# Source\n\nBody.\n", encoding="utf-8")
        source_id, content_hash = self._insert_source(relpath)

        result = self._tool("check_source_status")(
            file_hash=content_hash,
            workspace_path=str(self.root),
        )

        self.assertTrue(result["registered"])
        self.assertEqual(result["source_id"], source_id)
        self.assertEqual(result["relpath"], relpath)
        self.assertIn("source", result)

    def test_fetch_document_section_supports_source_key_and_toc_id(self) -> None:
        relpath = "03_Notes/sectioned.md"
        source = self.root / relpath
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            "# Paper\n\n"
            "<!-- section:s1 page:1 -->\n"
            "Intro text.\n\n"
            "<!-- section:s2 page:2 -->\n"
            "Method text.\n",
            encoding="utf-8",
        )
        source_id, _ = self._insert_source(relpath)

        result = self._tool("fetch_document_section")(
            source_key=relpath,
            toc_id="s2",
            workspace_path=str(self.root),
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["source_id"], source_id)
        self.assertEqual(result["relpath"], relpath)
        self.assertIn("Method text.", result["text"])
        self.assertNotIn("Intro text.", result["text"])

    def test_fetch_document_section_maps_toc_id_to_original_heading(self) -> None:
        relpath = "03_Notes/headings.md"
        source = self.root / relpath
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            "# Paper\n\n"
            "## Intro\n\nIntro text.\n\n"
            "## Method\n\nMethod evidence from original source.\n",
            encoding="utf-8",
        )
        source_id, _ = self._insert_source(relpath)

        result = self._tool("fetch_document_section")(
            source_id=source_id,
            toc_id="s3",
            workspace_path=str(self.root),
        )

        self.assertTrue(result["ok"])
        self.assertIn("Method evidence from original source.", result["text"])
        self.assertNotIn("Intro text.", result["text"])
        self.assertEqual(result["metadata"]["section_id"], "s3")

    def test_curator_add_all_scans_raw_dirs_and_generates_l1(self) -> None:
        source = self.root / "03_Notes" / "paper.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            "# Paper\n\n## Claim\n\n"
            "Residual blocks help optimization by preserving an identity path "
            "while learned residual functions model changes across network layers.\n",
            encoding="utf-8",
        )

        result = self._tool("curator_add_all")(workspace_path=str(self.root))

        self.assertTrue(result["ok"])
        self.assertEqual(result["discovered"], 1)
        self.assertEqual(result["summarized"], 1)
        contexts = list(self.paths.contexts.glob("CTX-*.md"))
        self.assertEqual(len(contexts), 1)
        self.assertIn("Residual blocks help optimization", contexts[0].read_text(encoding="utf-8"))

    def test_check_source_status_reports_layer_error_before_ready_state(self) -> None:
        relpath = "03_Notes/broken.md"
        source = self.root / relpath
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# Source\n\nBody.\n", encoding="utf-8")
        _source_id, content_hash = self._insert_source(relpath)
        with db.connect(self.paths.state_db) as conn:
            conn.execute(
                "UPDATE sources SET l1_status = 'done', l2_status = 'done', "
                "l3_status = 'error', l4_status = 'pending', layer_error = 'L3 failed' "
                "WHERE relpath = ?",
                (relpath,),
            )

        result = self._tool("check_source_status")(
            file_hash=content_hash,
            workspace_path=str(self.root),
        )

        self.assertEqual(result["source"]["state"], "error")
        self.assertTrue(result["source"]["l1_complete"])
        self.assertTrue(result["source"]["l2_complete"])
        self.assertFalse(result["source"]["l3_complete"])

    def test_check_source_status_uses_l4_for_l4_ready_state(self) -> None:
        relpath = "03_Notes/l3-ready.md"
        source = self.root / relpath
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# Source\n\nBody.\n", encoding="utf-8")
        _source_id, content_hash = self._insert_source(relpath)
        with db.connect(self.paths.state_db) as conn:
            conn.execute(
                "UPDATE sources SET status = 'curated', l1_status = 'done', "
                "l2_status = 'done', l3_status = 'done', l4_status = 'pending' "
                "WHERE relpath = ?",
                (relpath,),
            )

        result = self._tool("check_source_status")(
            file_hash=content_hash,
            workspace_path=str(self.root),
        )

        self.assertEqual(result["source"]["state"], "l3_ready")

        with db.connect(self.paths.state_db) as conn:
            conn.execute(
                "UPDATE sources SET l4_status = 'done' WHERE relpath = ?",
                (relpath,),
            )

        result = self._tool("check_source_status")(
            file_hash=content_hash,
            workspace_path=str(self.root),
        )

        self.assertEqual(result["source"]["state"], "l4_ready")
        self.assertTrue(result["source"]["l4_complete"])


if __name__ == "__main__":
    unittest.main()
