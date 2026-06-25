import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
        self.assertIn("Structural L1 context for **Intro**", parsed.body)
        self.assertIn("## Source Guide", parsed.body)
        self.assertIn("`s1` p.1 — **Intro**: Alpha claim.", parsed.body)
        self.assertIn("<!-- section:s1 page:1 -->", parsed.body)
        self.assertIn("## 2. Atom Candidates", parsed.body)
        self.assertIn("- [fact] Intro:", parsed.body)
        self.assertIn("Preview: Alpha claim.", parsed.body)

        with db.connect(self.paths.state_db) as conn:
            row = conn.execute(
                "SELECT context_id, l1_status, layer_error FROM sources WHERE id = ?",
                (source_id,),
            ).fetchone()
        self.assertEqual(row["context_id"], context_id)
        self.assertEqual(row["l1_status"], "done")
        self.assertIsNone(row["layer_error"])

    def test_large_l1_uses_on_demand_source_sections(self) -> None:
        relpath = "03_Notes/large-source.md"
        source = self.root / relpath
        source.parent.mkdir(parents=True, exist_ok=True)
        deep_evidence = "DEEP_SECRET_EVIDENCE_SHOULD_ONLY_LIVE_IN_SOURCE"
        source.write_text(
            "# Large Source\n\n"
            "## Overview\n\n"
            "Short preview sentence. "
            + ("filler text " * 80)
            + deep_evidence
            + "\n\n## Method\n\nMethod details.\n",
            encoding="utf-8",
        )
        source_id, content_hash = self._insert_source(relpath)

        with patch.object(ingest_raw, "L1_INLINE_SOURCE_MAX_CHARS", 120):
            context_id = ingest_raw.generate_l1_structural_context(
                self.paths,
                source_id=source_id,
                relpath=relpath,
                content_hash=content_hash,
            )

        self.assertIsNotNone(context_id)
        parsed = page_writer.read_page(self.paths.contexts / f"{context_id}.md")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertFalse(parsed.frontmatter["source_sections_inline"])
        self.assertEqual(parsed.frontmatter["source_text_policy"], "on_demand")
        self.assertIn("fetch_document_section", parsed.body)
        self.assertIn("Preview: Short preview sentence.", parsed.body)
        self.assertNotIn(deep_evidence, parsed.body)

    def test_structural_l1_plaintexts_parser_generated_heading_wikilinks(self) -> None:
        relpath = "03_Notes/mvg.md"
        source = self.root / relpath
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            "# [[MultipleViewGeometry#1 Introduction|1 Introduction]]\n\n"
            "See [[MultipleViewGeometry#Equation 19.11]] for the epipolar constraint.\n",
            encoding="utf-8",
        )
        source_id, content_hash = self._insert_source(relpath)

        context_id = ingest_raw.generate_l1_structural_context(
            self.paths,
            source_id=source_id,
            relpath=relpath,
            content_hash=content_hash,
        )

        parsed = page_writer.read_page(self.paths.contexts / f"{context_id}.md")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.frontmatter["toc"][0]["title"], "1 Introduction")
        self.assertNotIn("[[MultipleViewGeometry#", parsed.body)
        self.assertIn("Equation 19.11", parsed.body)

    def test_structural_l1_preserves_cross_document_heading_wikilinks(self) -> None:
        relpath = "03_Notes/MultipleViewGeometry.md"
        source = self.root / relpath
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            "# Overview\n\n"
            "See [[MultipleViewGeometry#Equation 19.11]] for self-reference.\n"
            "See [[OtherNote#Key Lemma]] for cross-document reference.\n",
            encoding="utf-8",
        )
        source_id, content_hash = self._insert_source(relpath)

        context_id = ingest_raw.generate_l1_structural_context(
            self.paths,
            source_id=source_id,
            relpath=relpath,
            content_hash=content_hash,
        )

        parsed = page_writer.read_page(self.paths.contexts / f"{context_id}.md")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        # Self-referential wikilink stripped (MultipleViewGeometry matches file stem).
        self.assertNotIn("[[MultipleViewGeometry#", parsed.body)
        self.assertIn("Equation 19.11", parsed.body)
        # Cross-document wikilink preserved.
        self.assertIn("[[OtherNote#Key Lemma]]", parsed.body)


if __name__ == "__main__":
    unittest.main()
