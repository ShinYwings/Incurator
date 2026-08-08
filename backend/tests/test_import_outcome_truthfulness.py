"""An import that drops a row must never report it as inserted.

B2 / sync_db-1, the milestone's stated hard condition. `_do_insert` used
`INSERT OR IGNORE`, so a row that violated a constraint was silently discarded
while `_lw_upsert` still returned "inserted" and the caller incremented
`stats.inserted`. The user is then told a peer's data arrived when it did not,
and `wiki db import` reports a clean run over a silent loss.

`INSERT OR IGNORE` is load-bearing for the legitimate case — two devices racing
to insert the SAME row must not error — so the fix cannot simply drop OR IGNORE.
It has to distinguish "already present" from "rejected".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from curator import db, db_sync

GOOD = {
    "id": "ATM-good",
    "name": "good",
    "parent_source": "01_Contexts/CTX-1.md",
    "claim_type": "fact",
    "one_liner": "good",
    "last_updated": "2099-01-01T00:00:00Z",
}
# NOT NULL on claim_type — what a truncated or malformed peer export looks like.
REJECTED = {**GOOD, "id": "ATM-bad", "claim_type": None}


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "state.sqlite"
    db.init_db(p)
    return p


def _count(db_path: Path) -> int:
    with db.connect(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM atoms").fetchone()[0])


def test_a_rejected_row_is_not_reported_as_inserted(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        result = db_sync._lw_upsert(conn, "atoms", dict(REJECTED), primary_keys=["id"])

    assert _count(db_path) == 0, "fixture wrong: the row was actually stored"
    assert result != "inserted", (
        "a row the database refused was reported as inserted, so the import "
        "summary claims data arrived that was silently dropped"
    )


def test_a_genuine_insert_is_still_reported_as_inserted(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        result = db_sync._lw_upsert(conn, "atoms", dict(GOOD), primary_keys=["id"])
    assert result == "inserted"
    assert _count(db_path) == 1


def test_reinserting_an_identical_row_is_not_an_error(db_path: Path) -> None:
    """Two devices racing to insert the same row is normal, not a failure.

    This is why `INSERT OR IGNORE` was there; the fix must keep it working.
    """
    with db.connect(db_path) as conn:
        db_sync._lw_upsert(conn, "atoms", dict(GOOD), primary_keys=["id"])
    with db.connect(db_path) as conn:
        result = db_sync._lw_upsert(conn, "atoms", dict(GOOD), primary_keys=["id"])
    assert result in {"skipped", "updated"}
    assert _count(db_path) == 1


def test_one_rejected_row_does_not_abort_the_rest_of_the_import(
    tmp_path: Path, db_path: Path
) -> None:
    """B2: a bad peer file must not wedge the pass — the good rows still land."""
    # Build a real peer file, then append the malformed row a truncated or
    # partially-written export would contain.
    donor = tmp_path / "donor.sqlite"
    db.init_db(donor)
    export = tmp_path / "peer.jsonl"
    db_sync.export_knowledge(donor, export)
    with export.open("a", encoding="utf-8") as fh:
        for row in (REJECTED, GOOD):
            fh.write(
                db_sync.json.dumps(
                    {"type": "row", "table": "atoms", "row": row}, default=str
                )
                + "\n"
            )

    stats = db_sync.import_knowledge(db_path, export)

    assert _count(db_path) == 1, "the good row was lost along with the bad one"
    assert stats.inserted == 1, (
        f"import reported {stats.inserted} inserted but only 1 row landed"
    )
