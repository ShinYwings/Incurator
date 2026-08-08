"""v0.52.2: unreadable regions must be recorded and must reach the reader.

Two gaps, measured on the reporting vault:

1. `classify_span_loss` runs only in the span *builder*, so it never revisits
   existing rows — 132 placeholder spans carried 2 loss records between them.
   The §26.2b check worked and had simply never run on the corpus it was for.
2. Nothing in retrieval knew what the placeholder meant, so a region the parser
   discarded reached the model as `**==> picture [185 x 12] intentionally
   omitted <==**`. The answer hedged ("I cannot retrieve the text of equation
   29") without naming the cause or the remedy.
"""

import json
import tempfile
import unittest
from pathlib import Path

from curator import config as cfg
from curator import db
from curator.pipeline.source_spans import (
    backfill_span_loss,
    classify_span_loss,
    describe_span_loss,
)
from curator.retrieval import evidence

# The exact artifact stored for equation 29 of source 37.
PLACEHOLDER = "**==> picture [185 x 12] intentionally omitted <==**"
PLACEHOLDER_NO_GEOMETRY = "**==> picture intentionally omitted <==**"


def _register_source(db_path: Path, relpath: str = "04_Resources/paper.md") -> int:
    with db.connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO sources
                (relpath, content_hash, file_type, bytes, added_at, l1_status)
            VALUES (?, ?, 'pdf', 12, datetime('now'), 'done')
            """,
            (relpath, "abc123abc123abc1"),
        )
        return int(cur.lastrowid)


def _insert_span(
    db_path: Path,
    source_id: int,
    span_id: str,
    text: str,
    metadata: str | None = None,
) -> None:
    with db.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO source_spans
                (id, source_id, relpath, span_type, page_number, content_hash,
                 text_preview, metadata, created_at)
            VALUES (?, ?, '04_Resources/paper.md', 'paragraph', 11, ?, ?, ?,
                    datetime('now'))
            """,
            (span_id, source_id, f"hash-{span_id}", text, metadata),
        )


def _metadata(db_path: Path, span_id: str) -> dict:
    with db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT metadata FROM source_spans WHERE id = ?", (span_id,)
        ).fetchone()
    return json.loads(row["metadata"]) if row and row["metadata"] else {}


class TestBackfill(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = cfg.WikiPaths(Path(self.tmp.name))
        db.init_db(self.paths.state_db)
        self.source_id = _register_source(self.paths.state_db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_records_loss_on_a_span_that_predates_the_check(self) -> None:
        _insert_span(self.paths.state_db, self.source_id, "SPAN-old", PLACEHOLDER)
        self.assertEqual(backfill_span_loss(self.paths.state_db), 1)

        loss = _metadata(self.paths.state_db, "SPAN-old")["loss"]
        self.assertEqual(loss["verdict"], "image_only")
        self.assertEqual(loss["region"], {"width": 185, "height": 12})

    def test_is_idempotent(self) -> None:
        _insert_span(self.paths.state_db, self.source_id, "SPAN-old", PLACEHOLDER)
        self.assertEqual(backfill_span_loss(self.paths.state_db), 1)
        first = _metadata(self.paths.state_db, "SPAN-old")
        self.assertEqual(backfill_span_loss(self.paths.state_db), 0)
        self.assertEqual(_metadata(self.paths.state_db, "SPAN-old"), first)

    def test_never_overwrites_a_record_written_at_ingest(self) -> None:
        original = json.dumps({"loss": {"verdict": "image_only", "classified_at": "X"}})
        _insert_span(
            self.paths.state_db, self.source_id, "SPAN-ingested", PLACEHOLDER, original
        )
        self.assertEqual(backfill_span_loss(self.paths.state_db), 0)
        self.assertEqual(
            _metadata(self.paths.state_db, "SPAN-ingested")["loss"]["classified_at"], "X"
        )

    def test_preserves_unrelated_metadata_keys(self) -> None:
        _insert_span(
            self.paths.state_db,
            self.source_id,
            "SPAN-meta",
            PLACEHOLDER,
            json.dumps({"toc_depth": 3}),
        )
        backfill_span_loss(self.paths.state_db)
        stored = _metadata(self.paths.state_db, "SPAN-meta")
        self.assertEqual(stored["toc_depth"], 3)
        self.assertIn("loss", stored)

    def test_leaves_readable_spans_alone(self) -> None:
        _insert_span(
            self.paths.state_db, self.source_id, "SPAN-text", "Then inserting into (28)"
        )
        self.assertEqual(backfill_span_loss(self.paths.state_db), 0)
        self.assertEqual(_metadata(self.paths.state_db, "SPAN-text"), {})

    def test_skips_unparseable_metadata_instead_of_destroying_it(self) -> None:
        _insert_span(
            self.paths.state_db, self.source_id, "SPAN-bad", PLACEHOLDER, "{not json"
        )
        self.assertEqual(backfill_span_loss(self.paths.state_db), 0)
        with db.connect(self.paths.state_db) as conn:
            row = conn.execute(
                "SELECT metadata FROM source_spans WHERE id = 'SPAN-bad'"
            ).fetchone()
        self.assertEqual(row["metadata"], "{not json")

    def test_handles_a_placeholder_with_no_stated_geometry(self) -> None:
        _insert_span(
            self.paths.state_db, self.source_id, "SPAN-nogeo", PLACEHOLDER_NO_GEOMETRY
        )
        self.assertEqual(backfill_span_loss(self.paths.state_db), 1)
        loss = _metadata(self.paths.state_db, "SPAN-nogeo")["loss"]
        self.assertEqual(loss["verdict"], "image_only")
        self.assertNotIn("region", loss)


class TestDescription(unittest.TestCase):
    def test_names_the_cause_and_the_remedy(self) -> None:
        loss = classify_span_loss(PLACEHOLDER)
        assert loss is not None
        text = describe_span_loss(loss)
        self.assertIn("185x12", text)
        self.assertIn("image", text)
        self.assertIn("vision_model", text)
        self.assertIn("snip", text.lower())

    def test_tells_the_model_not_to_guess(self) -> None:
        loss = classify_span_loss(PLACEHOLDER)
        assert loss is not None
        self.assertIn("Do not guess", describe_span_loss(loss))

    def test_omits_geometry_when_the_parser_stated_none(self) -> None:
        loss = classify_span_loss(PLACEHOLDER_NO_GEOMETRY)
        assert loss is not None
        text = describe_span_loss(loss)
        self.assertIn("image", text)
        self.assertNotIn("None", text)
        self.assertNotIn("x ", text.split("image")[0].replace("stores", ""))


class TestEvidenceSubstitution(unittest.TestCase):
    """The artifact must never reach the model as evidence."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = cfg.WikiPaths(Path(self.tmp.name))
        db.init_db(self.paths.state_db)
        self.source_id = _register_source(self.paths.state_db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_backfilled_span_serves_the_description_not_the_artifact(self) -> None:
        _insert_span(self.paths.state_db, self.source_id, "SPAN-eq29", PLACEHOLDER)
        backfill_span_loss(self.paths.state_db)

        items = evidence._span_items(self.paths.state_db, ["SPAN-eq29"])
        self.assertEqual(len(items), 1)
        self.assertNotIn("intentionally omitted", items[0].text)
        self.assertIn("unreadable region", items[0].text)

    def test_works_before_any_sync_has_backfilled(self) -> None:
        """A vault that has not synced yet must still get a truthful answer."""
        _insert_span(self.paths.state_db, self.source_id, "SPAN-nosync", PLACEHOLDER)
        items = evidence._span_items(self.paths.state_db, ["SPAN-nosync"])
        self.assertNotIn("intentionally omitted", items[0].text)
        self.assertIn("unreadable region", items[0].text)

    def test_readable_spans_are_served_verbatim(self) -> None:
        body = "Then inserting into (28) we get"
        _insert_span(self.paths.state_db, self.source_id, "SPAN-ok", body)
        items = evidence._span_items(self.paths.state_db, ["SPAN-ok"])
        self.assertEqual(items[0].text, body)

    def test_unparseable_metadata_still_yields_a_truthful_item(self) -> None:
        _insert_span(
            self.paths.state_db, self.source_id, "SPAN-bad", PLACEHOLDER, "{not json"
        )
        items = evidence._span_items(self.paths.state_db, ["SPAN-bad"])
        self.assertIn("unreadable region", items[0].text)


if __name__ == "__main__":
    unittest.main()
