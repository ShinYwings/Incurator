"""Job history — the difference between a slow job and a stopped one.

`ingest_jobs` carries only the LATEST phase and progress, so a job that stalls
and a job that is working look identical: the same row, forever. That is not
hypothetical. A `wiki add` run on a 673-page book sat at 0% CPU for 26 minutes
and was diagnosed as hung; it was in fact transcribing pages one at a time, and
nothing in the database could tell the two apart.

`job_events` existed for this — created in the schema, transported by
`db_sync`, deleted from by `sources.py` — and nothing ever inserted a row. This
pins that it does now, and pins the two properties that make the history worth
trusting: ordering, and never costing the job it describes.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from curator import db
from curator.db import job_events


@pytest.fixture()
def job(tmp_path: Path) -> tuple[Path, int]:
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    # ingest_jobs.source_id carries no FK, so a job needs no source row here.
    job_id = db.enqueue_job(db_path, source_id=1, job_type="l2")
    return db_path, job_id


def test_events_are_recorded_and_read_back_in_order(job: tuple[Path, int]) -> None:
    db_path, job_id = job
    job_events.append(db_path, job_id, "status", {"phase": "l2"})
    job_events.append(db_path, job_id, "extracted", {"done": 1})
    job_events.append(db_path, job_id, "extracted", {"done": 2})

    events = job_events.listing(db_path, job_id)
    assert [e["kind"] for e in events] == ["status", "extracted", "extracted"]
    # Oldest first: a reader follows the story forwards.
    assert [e["seq"] for e in events] == [1, 2, 3]
    assert events[2]["data"] == {"done": 2}


def test_seq_is_assigned_by_the_writer_not_the_caller(job: tuple[Path, int]) -> None:
    # Two callers cannot disagree about ordering if neither picks the number.
    db_path, job_id = job
    for i in range(5):
        job_events.append(db_path, job_id, "chunk", {"i": i})
    assert [e["seq"] for e in job_events.listing(db_path, job_id)] == [1, 2, 3, 4, 5]


def test_events_are_scoped_to_their_job(job: tuple[Path, int]) -> None:
    db_path, job_id = job
    other = db.enqueue_job(db_path, source_id=2, job_type="l2")

    job_events.append(db_path, job_id, "status", {"which": "first"})
    job_events.append(db_path, other, "status", {"which": "second"})

    assert [e["data"]["which"] for e in job_events.listing(db_path, job_id)] == ["first"]
    assert [e["data"]["which"] for e in job_events.listing(db_path, other)] == ["second"]
    # Each job's sequence starts at 1 — seq is per job, not global.
    assert job_events.listing(db_path, other)[0]["seq"] == 1


def test_recording_an_event_never_fails_the_job(job: tuple[Path, int]) -> None:
    """Observability must not be able to destroy the work it observes.

    The append runs inside the ingest path, so a locked database, a disk error,
    or an unserialisable payload must degrade to "no event recorded" rather than
    take down a run that may already have spent an hour of provider quota.
    """
    db_path, job_id = job

    class Unserialisable:
        def __repr__(self) -> str:  # pragma: no cover - defensive
            raise RuntimeError("cannot repr")

    # Must not raise.
    job_events.append(db_path, job_id, "status", {"bad": Unserialisable()})
    job_events.append(Path("/nonexistent/dir/state.sqlite"), job_id, "status", {})


def test_a_malformed_row_does_not_hide_the_rest(job: tuple[Path, int]) -> None:
    db_path, job_id = job
    job_events.append(db_path, job_id, "status", {"ok": True})
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO job_events (job_id, seq, kind, data, at) VALUES (?,?,?,?,?)",
            (job_id, 2, "status", "{not json", "2026-01-01T00:00:00Z"),
        )
    events = job_events.listing(db_path, job_id)
    assert len(events) == 2
    assert events[0]["data"] == {"ok": True}
    assert "raw" in events[1]["data"]


def test_the_frozen_evaluated_files_are_untouched() -> None:
    """This module exists in its own file for a reason; pin the reason.

    `db/jobs.py` and `db/__init__.py` are recorded by content hash in
    `docs/specs/failure_atlas/D2_HOLDOUT_RESULT.yml`, which freezes a specific
    evaluation against specific code. Adding the event functions there — or even
    a re-export in `__init__.py` — silently invalidates that result for a reason
    that has nothing to do with retrieval. The first draft of this work did
    exactly that and D2 caught it.
    """
    import hashlib
    import re

    repo = Path(__file__).resolve().parents[2]
    recorded = (repo / "docs/specs/failure_atlas/D2_HOLDOUT_RESULT.yml").read_text(
        encoding="utf-8"
    )
    section = recorded.split("file_sha256:")[1]
    checked = 0
    for line in section.split("\n"):
        m = re.match(r"\s+(\S+\.py):\s+([0-9a-f]{64})", line)
        if not m:
            if line.strip() and not line.startswith("    "):
                break
            continue
        rel, want = m.group(1), m.group(2)
        got = hashlib.sha256((repo / rel).read_bytes()).hexdigest()
        assert got == want, f"{rel} is evaluated code and must not change here"
        checked += 1
    assert checked > 0


def test_limit_caps_the_read(job: tuple[Path, int]) -> None:
    db_path, job_id = job
    for i in range(10):
        job_events.append(db_path, job_id, "chunk", {"i": i})
    assert len(job_events.listing(db_path, job_id, limit=4)) == 4
