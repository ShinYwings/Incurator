import hashlib
import tempfile
import unittest
from pathlib import Path

from curator import config as cfg
from curator import db, ingest_raw, page_writer


class InstantL1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        for raw_dir in self.paths.raw_dirs:
            raw_dir.mkdir(parents=True, exist_ok=True)
        self.paths.contexts.mkdir(parents=True, exist_ok=True)
        db.init_db(self.paths.state_db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _insert_source(self, relpath: str) -> tuple[int, str]:
        source = self.root / relpath
        content_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        with db.connect(self.paths.state_db) as conn:
            cur = conn.execute(
                """INSERT INTO sources
                   (relpath, content_hash, file_type, bytes, added_at, status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (relpath, content_hash, "md", source.stat().st_size,
                 "2026-05-29T00:00:00Z", "pending"),
            )
            return cur.lastrowid, content_hash

    def test_generate_l1_summary_defaults_to_no_llm_structural_context(self) -> None:
        class NoChatClient:
            optimal_chunk_chars = 30000

            def chat(self, *args, **kwargs):  # noqa: ANN002, ANN003
                raise AssertionError("instant L1 must not call the LLM")

        relpath = "03_Notes/instant-source.md"
        source = self.root / relpath
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            "# Intro\n\nAlpha claim.\n\n## Method\n\nBeta method.\n",
            encoding="utf-8",
        )
        source_id, content_hash = self._insert_source(relpath)

        context_id = ingest_raw.generate_l1_summary(
            self.paths,
            source_id=source_id,
            relpath=relpath,
            content_hash=content_hash,
            client=NoChatClient(),
            config={},
        )

        self.assertIsNotNone(context_id)
        parsed = page_writer.read_page(self.paths.contexts / f"{context_id}.md")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.frontmatter["id"], context_id)
        self.assertEqual(parsed.frontmatter["source_hash"], content_hash)
        self.assertEqual(parsed.frontmatter["tags"], ["md", "instant-l1"])
        self.assertEqual(parsed.frontmatter["toc"][0]["id"], "s1")
        self.assertEqual(parsed.frontmatter["toc"][0]["title"], "Intro")
        self.assertIn("<!-- section:s1 page:1 -->", parsed.body)
        self.assertIn("## 2. Atom Candidates", parsed.body)
        self.assertIn("- [fact] Intro:", parsed.body)

        with db.connect(self.paths.state_db) as conn:
            row = conn.execute(
                "SELECT context_id, l1_status, layer_error FROM sources WHERE id = ?",
                (source_id,),
            ).fetchone()
        self.assertEqual(row["context_id"], context_id)
        self.assertEqual(row["l1_status"], "done")
        self.assertIsNone(row["layer_error"])


if __name__ == "__main__":
    unittest.main()
