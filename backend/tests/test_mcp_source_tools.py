"""Tests for curator_import_source and curator_search_sources behaviour.

These tests exercise the underlying functions directly rather than going
through the FastMCP wire protocol, which keeps the suite fast and
dependency-free.
"""
import tempfile
import unittest
from pathlib import Path

from curator import config as cfg
from curator import db, ingest_raw, search, source_tools


class ImportSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        for raw_dir in self.paths.raw_dirs:
            raw_dir.mkdir(parents=True, exist_ok=True)
        db.init_db(self.paths.state_db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_external_file_lands_in_04_resources_imports(self) -> None:
        """A file outside the vault should be imported into 04_Resources/Imports/."""
        external_root = self.root.parent / "external_library"
        external_root.mkdir(parents=True, exist_ok=True)
        external = external_root / "external_doc.md"
        external.write_text(
            "# External Note\n\nThis is an external document with enough words to pass import.",
            encoding="utf-8",
        )

        outcome = ingest_raw.import_source_file(self.paths, external, policy="into_04_resources")

        self.assertIn(outcome.result, {ingest_raw.AddResult.ADDED, ingest_raw.AddResult.DEDUPED})
        self.assertTrue(outcome.relpath.startswith("04_Resources/Imports/"))
        self.assertTrue((self.root / outcome.relpath).exists())

    def test_reference_import_tracks_external_path_without_copying(self) -> None:
        external_root = self.root.parent / f"{self.root.name}_zotero_library"
        external_root.mkdir(parents=True, exist_ok=True)
        external = external_root / "paper.md"
        external.write_text(
            "# External Reference\n\nThis source remains outside the vault but is searchable.",
            encoding="utf-8",
        )

        outcome = ingest_raw.import_source_file(self.paths, external, policy="reference")

        self.assertEqual(outcome.result, ingest_raw.AddResult.ADDED)
        self.assertEqual(outcome.relpath, "04_Resources/References/paper.md")
        stub = self.root / outcome.relpath
        self.assertTrue(stub.exists())
        stub_text = stub.read_text(encoding="utf-8")
        self.assertIn("type: reference", stub_text)
        self.assertIn("logical_source_id:", stub_text)
        self.assertNotIn(str(external.resolve()), stub_text)
        self.assertFalse((self.root / "04_Resources" / "Imports" / external.name).exists())
        row = ingest_raw.get_source(self.paths, outcome.source_id or -1)
        self.assertIsNotNone(row)
        self.assertEqual(row["relpath"], "04_Resources/References/paper.md")
        self.assertEqual(row["is_reference"], 1)
        self.assertEqual(row["external_path"], str(external.resolve()))
        self.assertTrue(str(row["logical_source_id"]).startswith("ref-"))

    def test_reference_import_reuses_existing_stub_for_same_external_path(self) -> None:
        external_root = self.root.parent / f"{self.root.name}_zotero_library"
        external_root.mkdir(parents=True, exist_ok=True)
        external = external_root / "paper.md"
        external.write_text(
            "# External Reference\n\nThis source remains outside the vault but is searchable.",
            encoding="utf-8",
        )

        first = ingest_raw.import_source_file(self.paths, external, policy="reference")
        second = ingest_raw.import_source_file(self.paths, external, policy="reference")

        self.assertEqual(first.relpath, "04_Resources/References/paper.md")
        self.assertEqual(second.relpath, first.relpath)
        self.assertEqual(second.result, ingest_raw.AddResult.DEDUPED)
        self.assertFalse((self.root / "04_Resources" / "References" / "paper-2.md").exists())

    def test_reference_import_reuses_disk_stub_when_db_row_missing(self) -> None:
        """A surviving stub must not spawn a duplicate `<name>-2.md` when its
        sources DB row was lost (e.g. after a state.sqlite rebuild)."""
        external_root = self.root.parent / f"{self.root.name}_zotero_library"
        external_root.mkdir(parents=True, exist_ok=True)
        external = external_root / "paper.md"
        external.write_text(
            "# External Reference\n\nZotero-backed source kept outside the vault.",
            encoding="utf-8",
        )

        first = ingest_raw.import_source_file(
            self.paths,
            external,
            policy="reference",
            logical_source_id="zotero:ABCD1234",
        )
        self.assertEqual(first.relpath, "04_Resources/References/paper.md")

        # Simulate a state rebuild: the stub file survives, its DB row is gone.
        with db.connect(self.paths.state_db) as conn:
            conn.execute("DELETE FROM sources")

        second = ingest_raw.import_source_file(
            self.paths,
            external,
            policy="reference",
            logical_source_id="zotero:ABCD1234",
        )

        self.assertEqual(second.relpath, "04_Resources/References/paper.md")
        self.assertFalse(
            (self.root / "04_Resources" / "References" / "paper-2.md").exists()
        )
        # Only one reference stub remains on disk for the same document.
        stubs = list((self.root / "04_Resources" / "References").glob("*.md"))
        self.assertEqual(len(stubs), 1)

    def test_reference_status_detects_hash_drift_without_mutation(self) -> None:
        external_root = self.root.parent / f"{self.root.name}_zotero_library"
        external_root.mkdir(parents=True, exist_ok=True)
        external = external_root / "paper.md"
        external.write_text(
            "# External Reference\n\nThis source remains stable before the edit.",
            encoding="utf-8",
        )
        outcome = ingest_raw.import_source_file(self.paths, external, policy="reference")
        row = ingest_raw.get_source(self.paths, outcome.source_id or -1)
        self.assertIsNotNone(row)

        external.write_text(
            "# External Reference\n\nThis source changed after an iPad annotation update.",
            encoding="utf-8",
        )

        status = source_tools.source_status(self.paths, row, cfg.DEFAULT_CONFIG)
        self.assertEqual(status["state"], "hash_drift")
        self.assertTrue(status["requires_rebind"])
        fresh_row = ingest_raw.get_source(self.paths, outcome.source_id or -1)
        self.assertEqual(fresh_row["content_hash"], row["content_hash"])

    def test_reference_status_finds_moved_candidate_in_external_root(self) -> None:
        external_root = self.root.parent / f"{self.root.name}_zotero_library"
        external_root.mkdir(parents=True, exist_ok=True)
        original = external_root / "paper.md"
        original.write_text(
            "# External Reference\n\nThis file will move without changing content.",
            encoding="utf-8",
        )
        outcome = ingest_raw.import_source_file(self.paths, original, policy="reference")
        row = ingest_raw.get_source(self.paths, outcome.source_id or -1)
        self.assertIsNotNone(row)

        moved_dir = external_root / "nested"
        moved_dir.mkdir()
        moved = moved_dir / "paper.md"
        original.rename(moved)
        config = {"external": {"zotero": {"enabled": True, "roots": [str(external_root)]}}}

        status = source_tools.source_status(self.paths, row, config)
        self.assertEqual(status["state"], "moved")
        self.assertEqual(status["candidate_path"], str(moved.resolve()))
        self.assertTrue(status["requires_rebind"])

    def test_rebind_requires_apply_before_mutating_source_row(self) -> None:
        external_root = self.root.parent / f"{self.root.name}_zotero_library"
        external_root.mkdir(parents=True, exist_ok=True)
        original = external_root / "paper.md"
        original.write_text(
            "# External Reference\n\nThis file will be rebound to a new path.",
            encoding="utf-8",
        )
        outcome = ingest_raw.import_source_file(self.paths, original, policy="reference")
        row = ingest_raw.get_source(self.paths, outcome.source_id or -1)
        self.assertIsNotNone(row)
        moved = external_root / "renamed.md"
        original.rename(moved)

        proposal = source_tools.rebind_source(self.paths, row, moved, apply=False)
        self.assertEqual(proposal["state"], "rebind_proposal")
        unchanged = ingest_raw.get_source(self.paths, outcome.source_id or -1)
        self.assertEqual(unchanged["external_path"], str(original.resolve()))

        applied = source_tools.rebind_source(self.paths, row, moved, apply=True)
        self.assertEqual(applied["state"], "rebound")
        updated = ingest_raw.get_source(self.paths, outcome.source_id or -1)
        self.assertEqual(updated["external_path"], str(moved.resolve()))

    def test_external_resources_normalizes_global_config_roots(self) -> None:
        config = {
            "external": {
                "roots": ["/tmp/generic-library"],
                "zotero": {"enabled": True, "roots": ["/tmp/zotero-a", "/tmp/zotero-b"]},
            }
        }

        resources = source_tools.external_resources(config)
        self.assertEqual([r["name"] for r in resources], ["external", "zotero", "zotero"])
        self.assertEqual(resources[1]["path"], "/tmp/zotero-a")

    def test_repeated_import_of_03_notes_creates_unique_destination(self) -> None:
        """Re-importing the same 03_Notes file creates a new destination, not a dedup.

        _unique_destination() guarantees no overwrites: the second call lands
        at 04_Resources/Research/paper-2.md while the first stays at paper.md.
        """
        note = self.root / "03_Notes" / "Research" / "paper.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text(
            "# Research Paper\n\nThis note has enough words for the ingestion to succeed.",
            encoding="utf-8",
        )

        first = ingest_raw.import_source_file(self.paths, note)
        second = ingest_raw.import_source_file(self.paths, note)

        self.assertEqual(first.result, ingest_raw.AddResult.ADDED)
        self.assertEqual(second.result, ingest_raw.AddResult.ADDED)
        self.assertNotEqual(first.relpath, second.relpath)
        # Both files exist; neither overwrites the other.
        self.assertTrue((self.root / first.relpath).exists())
        self.assertTrue((self.root / second.relpath).exists())

    def test_add_file_dedup_on_same_content(self) -> None:
        """Calling add_file on an already-tracked file with identical content returns DEDUPED."""
        resource = self.root / "04_Resources" / "papers" / "doc.md"
        resource.parent.mkdir(parents=True, exist_ok=True)
        resource.write_text(
            "# Document\n\nSufficient content for tracking with at least ten words here.",
            encoding="utf-8",
        )

        first = ingest_raw.add_file(self.paths, resource)
        second = ingest_raw.add_file(self.paths, resource)

        self.assertEqual(first.result, ingest_raw.AddResult.ADDED)
        self.assertEqual(second.result, ingest_raw.AddResult.DEDUPED)
        self.assertEqual(first.source_id, second.source_id)

    def test_mirror_03_notes_subfolder_preserved(self) -> None:
        """03_Notes/Topic/file.md mirrors to 04_Resources/Topic/file.md."""
        note = self.root / "03_Notes" / "Topic" / "SubTopic" / "file.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text(
            "# Topic File\n\nSufficient content for import to register in the database.",
            encoding="utf-8",
        )

        outcome = ingest_raw.import_source_file(self.paths, note)

        self.assertEqual(outcome.result, ingest_raw.AddResult.ADDED)
        self.assertEqual(outcome.relpath, "04_Resources/Topic/SubTopic/file.md")


class SearchSourcePagesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        for raw_dir in self.paths.raw_dirs:
            raw_dir.mkdir(parents=True, exist_ok=True)
        db.init_db(self.paths.state_db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _add_markdown(self, relpath: str, content: str) -> int:
        """Create a file inside the vault and register it as a source."""
        full = self.root / relpath
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        outcome = ingest_raw.add_file(self.paths, full)
        self.assertIsNotNone(outcome.source_id)
        return outcome.source_id  # type: ignore[return-value]

    def test_keyword_in_source_returns_hit(self) -> None:
        """A query matching a word in the source content returns at least one hit."""
        self._add_markdown(
            "04_Resources/papers/neural_scaling.md",
            "# Neural Scaling\n\nScaling laws for language model performance are a hot topic.",
        )

        hits = search.search_source_pages(self.paths, "scaling laws")

        self.assertGreater(len(hits), 0)
        self.assertTrue(
            any("neural_scaling" in h.relpath for h in hits),
            msg=f"Expected neural_scaling in results, got: {[h.relpath for h in hits]}",
        )

    def test_unrelated_query_returns_no_hits(self) -> None:
        """A query with no matching words returns an empty hit list."""
        self._add_markdown(
            "04_Resources/papers/climate.md",
            "# Climate Change\n\nGlobal temperatures are rising due to greenhouse gases.",
        )

        hits = search.search_source_pages(self.paths, "xyzzy_nonexistent_term_qqqq")

        self.assertEqual(hits, [])

    def test_source_id_filter_restricts_search(self) -> None:
        """Passing source_id only searches the named source."""
        sid_a = self._add_markdown(
            "04_Resources/papers/transformers.md",
            "# Transformers\n\nAttention is all you need for sequence modelling.",
        )
        self._add_markdown(
            "04_Resources/papers/rnns.md",
            "# RNNs\n\nRecurrent neural networks model sequences step by step.",
        )

        hits = search.search_source_pages(self.paths, "attention", source_id=sid_a)

        self.assertTrue(all(h.source_id == sid_a for h in hits))
        self.assertGreater(len(hits), 0)

    def test_multiple_sources_ranked_by_score(self) -> None:
        """When both sources match, the one with more occurrences ranks first."""
        self._add_markdown(
            "04_Resources/papers/dense.md",
            (
                "# Dense Retrieval\n\nRetrieval retrieval retrieval retrieval retrieval "
                "retrieval retrieval is the key technique in dense passage retrieval."
            ),
        )
        self._add_markdown(
            "04_Resources/papers/sparse.md",
            "# Sparse Methods\n\nRetrieval is also important for sparse term matching.",
        )

        hits = search.search_source_pages(self.paths, "retrieval")

        self.assertGreaterEqual(len(hits), 2)
        self.assertGreaterEqual(hits[0].score, hits[1].score)


if __name__ == "__main__":
    unittest.main()
