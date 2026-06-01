import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from curator import config as cfg
from curator import db, mcp_server


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
        content_hash = hashlib.sha256(source.read_bytes()).hexdigest()
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


if __name__ == "__main__":
    unittest.main()
