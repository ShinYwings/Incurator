"""A `source_spans.metadata` write must survive cross-device import.

`source_spans` has no `updated_at`; `db_sync._UPDATED_AT_COL` maps it to
`created_at`, which is immutable. But `metadata` IS mutated in place — by
`recover_formula()` (SCHEMA §20.4, shipped v0.8.0) and by the `loss` record
(§20.4a). With an immutable clock the LWW comparison in `_lw_upsert` ties, the
strict `>` fails, and the peer silently drops the write. `_local_max_ts` never
moves either, so the writing device does not even detect it has something to
export.

These tests pin the round trip, not the mechanism, so a future clock redesign
stays free to change how the revision is derived.

Timestamps here are FAR-FUTURE / FAR-PAST sentinels, never wall-clock dates. The
derived revision is `max(created_at, metadata stamps)`, and `created_at` is
`now` — so a "newer" stamp written as a real date silently stops being newer the
moment the clock passes it. The first version of this file hardcoded
`2026-08-08T00:00:00Z`, which was in the future when written and in the past a
day later; the suite went red on a calendar boundary with no code change.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from curator import db, db_sync

# Comfortably beyond any `created_at` a test run can produce.
NEWER = "2099-01-01T00:00:00+00:00"
NEWEST = "2099-12-31T00:00:00+00:00"
BEFORE_ANY_EXPORT = "2000-01-01T00:00:00+00:00"

# Comfortably beyond any `created_at` a test run can produce.
NEWER = "2099-01-01T00:00:00+00:00"
NEWEST = "2099-12-31T00:00:00+00:00"
BEFORE_ANY_EXPORT = "2000-01-01T00:00:00+00:00"


def _make_vault(tmp_path: Path, name: str) -> Path:
    db_path = tmp_path / name / "state.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db.init_db(db_path)
    return db_path


def _seed_span(db_path: Path, *, text: str = "picture omitted") -> tuple[int, str]:
    # Both devices must produce the SAME sync identity for the same source, so
    # the values here are fixed rather than generated.
    with db.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES (?, ?, ?, 0, ?)",
            ("04_Resources/paper.md", "h1", "pdf", "2026-06-19T00:00:00Z"),
        )
        source_id = int(
            conn.execute(
                "SELECT id FROM sources WHERE relpath = ?",
                ("04_Resources/paper.md",),
            ).fetchone()["id"]
        )
    span_id = db.upsert_source_span(
        db_path,
        source_id=source_id,
        relpath="04_Resources/paper.md",
        span_type="paragraph",
        content_hash="deadbeefdeadbeef",
        page_number=11,
        text_preview=text,
    )
    return source_id, span_id


def _set_loss(db_path: Path, span_id: str, classified_at: str) -> None:
    with db.connect(db_path) as conn:
        conn.execute(
            "UPDATE source_spans SET metadata = ? WHERE id = ?",
            (
                json.dumps(
                    {
                        "loss": {
                            "verdict": "image_only",
                            "region": {"width": 221, "height": 18},
                            "classified_at": classified_at,
                        }
                    },
                    sort_keys=True,
                ),
                span_id,
            ),
        )


def _read_meta(db_path: Path, span_id: str) -> dict:
    with db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT metadata FROM source_spans WHERE id = ?", (span_id,)
        ).fetchone()
    return json.loads(row["metadata"] or "{}")


def _synced_pair(tmp_path: Path) -> tuple[Path, Path, str]:
    """Two vaults that have already exchanged the span, as after any prior sync.

    B must hold the span under A's id — each device mints its own SPAN- id, so
    seeding both independently would compare two different rows.
    """
    device_a = _make_vault(tmp_path, "a")
    device_b = _make_vault(tmp_path, "b")
    _, span_id = _seed_span(device_a)

    first = tmp_path / "initial.jsonl"
    db_sync.export_knowledge(device_a, first)
    db_sync.import_knowledge(device_b, first)

    with db.connect(device_b) as conn:
        assert conn.execute(
            "SELECT 1 FROM source_spans WHERE id = ?", (span_id,)
        ).fetchone(), "fixture broken: the initial sync did not deliver the span"
    return device_a, device_b, span_id


def test_metadata_loss_write_reaches_a_peer_that_already_has_the_span(
    tmp_path: Path,
) -> None:
    """The reported defect: both devices have the span, one records a loss."""
    device_a, device_b, span_id = _synced_pair(tmp_path)

    _set_loss(device_a, span_id, NEWER)

    export = tmp_path / "a.jsonl"
    db_sync.export_knowledge(device_a, export)
    db_sync.import_knowledge(device_b, export)

    meta = _read_meta(device_b, span_id)
    assert meta.get("loss", {}).get("verdict") == "image_only", (
        "peer dropped the metadata write: source_spans has no updated_at, so the "
        "LWW clock tied on the immutable created_at and _lw_upsert skipped the row"
    )


def test_export_gate_detects_a_metadata_only_change(tmp_path: Path) -> None:
    """The writing device must know it has something to export."""
    device_a = _make_vault(tmp_path, "a")
    _, span_id = _seed_span(device_a)

    before = db_sync._local_max_ts(device_a)
    _set_loss(device_a, span_id, NEWER)
    after = db_sync._local_max_ts(device_a)

    assert db_sync._timestamp_key(after) > db_sync._timestamp_key(before), (
        "_local_max_ts did not move after a metadata write, so the export gate "
        "never fires and the peer is never offered the change"
    )


def test_older_metadata_write_does_not_clobber_a_newer_one(tmp_path: Path) -> None:
    """LWW still applies — the fix must not make metadata writes unconditional."""
    device_a, device_b, span_id = _synced_pair(tmp_path)

    _set_loss(device_a, span_id, NEWER)   # older of the two
    _set_loss(device_b, span_id, NEWEST)  # newer, and local

    export = tmp_path / "a.jsonl"
    db_sync.export_knowledge(device_a, export)
    db_sync.import_knowledge(device_b, export)

    meta = _read_meta(device_b, span_id)
    assert meta["loss"]["classified_at"] == NEWEST, (
        "an older remote metadata write overwrote a newer local one"
    )


def test_span_without_metadata_still_syncs_on_created_at(tmp_path: Path) -> None:
    """No metadata means the ordinary created_at clock, unchanged."""
    device_a = _make_vault(tmp_path, "a")
    device_b = _make_vault(tmp_path, "b")
    _, span_id = _seed_span(device_a)

    export = tmp_path / "a.jsonl"
    db_sync.export_knowledge(device_a, export)
    db_sync.import_knowledge(device_b, export)

    with db.connect(device_b) as conn:
        row = conn.execute(
            "SELECT id FROM source_spans WHERE id = ?", (span_id,)
        ).fetchone()
    assert row is not None, "a plain span failed to reach the peer at all"


def test_since_filtered_export_includes_a_metadata_only_edit(tmp_path: Path) -> None:
    """`wiki db export --since` is user-facing and filtered on the raw column.

    A span whose metadata was edited after `since` but whose immutable
    `created_at` predates it would be silently omitted.
    """
    device_a = _make_vault(tmp_path, "a")
    _, span_id = _seed_span(device_a)
    _set_loss(device_a, span_id, NEWER)

    export = tmp_path / "since.jsonl"
    db_sync.export_knowledge(device_a, export, since="2098-01-01T00:00:00+00:00")

    body = export.read_text()
    assert span_id in body, (
        "the --since export dropped a span whose metadata was edited after the "
        "cutoff, because it filtered on the immutable created_at"
    )


def test_since_filtered_export_still_excludes_untouched_rows(tmp_path: Path) -> None:
    """The derived revision must not make --since export everything."""
    device_a = _make_vault(tmp_path, "a")
    _, span_id = _seed_span(device_a)  # created now, no metadata

    export = tmp_path / "since.jsonl"
    db_sync.export_knowledge(device_a, export, since=NEWEST)
    assert span_id not in export.read_text()


def test_a_newer_metadata_edit_survives_an_older_tombstone(tmp_path: Path) -> None:
    """Tombstone-vs-edit is LWW too: a genuinely newer edit must not be blocked.

    Ranking a span by its immutable `created_at` made every later metadata edit
    look older than any tombstone, so it was always blocked and dropped.
    """
    device_a, device_b, span_id = _synced_pair(tmp_path)

    # B deletes the span; A edits its metadata strictly later.
    with db.connect(device_b) as conn:
        row = conn.execute(
            "SELECT source_id FROM source_spans WHERE id = ?", (span_id,)
        ).fetchone()
        assert row is not None
    with db.connect(device_b) as conn:
        db_sync.record_tombstone_on_connection(
            conn, "source_spans", span_id, deleted_at=NEWER
        )
        conn.execute("DELETE FROM source_spans WHERE id = ?", (span_id,))

    _set_loss(device_a, span_id, NEWEST)  # strictly newer than the delete

    export = tmp_path / "a.jsonl"
    db_sync.export_knowledge(device_a, export)
    db_sync.import_knowledge(device_b, export)

    meta = _read_meta(device_b, span_id)
    assert meta.get("loss", {}).get("verdict") == "image_only", (
        "a metadata edit newer than the tombstone was blocked, because the "
        "tombstone check ranked the span by its immutable created_at"
    )
