"""Curator state DB — append-only job history.

`ingest_jobs` carries only the LATEST phase and progress, so a reader sees where
a job IS and never how it got there. A job that stalls and a job that is working
therefore look identical: the same row, indefinitely. That is not hypothetical —
a `wiki add` run on a 673-page book sat at 0% CPU for 26 minutes and was
diagnosed as hung, when it was in fact transcribing pages one at a time through
a subprocess. Nothing in the database could tell the two apart.

`job_events` was created for exactly this in the schema, is transported by
`db_sync`, and is deleted from by `sources.py` — and until v0.58.0 nothing ever
inserted a row, so every job's history was empty.

**Why this lives in its own module rather than in `db/jobs.py`.** Both
`db/jobs.py` and `db/__init__.py` are pinned by content hash in
`docs/specs/failure_atlas/D2_HOLDOUT_RESULT.yml`: that result records a frozen
evaluation of specific code, and editing an evaluated file silently invalidates
the claim it makes. Adding a function there — or even a re-export in
`__init__.py` — would have broken that guarantee for an unrelated reason. So
callers import this module directly:

    from .db import job_events
    job_events.append(db_path, job_id, "status", {"phase": "l2"})
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from .schema import _now_iso, connect

_log = logging.getLogger(__name__)

__all__ = ["append", "listing"]

# Long enough to ride out a normal write, short enough that a genuinely
# contended database fails while the caller can still do something about it.
#
# Measured on a real state.sqlite: going through `connect()` under a held write
# lock blocks for SQLite's 5 s default and THEN loses the row. At one event per
# extraction batch that is minutes of blocking to record nothing. With this
# timeout the same write fails in ~0.3 s, visibly, and the caller counts it.
_BUSY_TIMEOUT_S = 0.25


def _write(db_path: Path, job_id: int, kind: str, payload: str, *, heal: bool) -> None:
    """One insert. ``heal=True`` routes through the schema-managing connection."""
    if heal:
        with connect(db_path) as conn:
            _insert(conn, job_id, kind, payload)
        return
    # The lightweight path deliberately skips `connect()`. That helper re-runs
    # `executescript(SCHEMA_SQL)` on EVERY call — measured at 1.31 ms and, worse,
    # it takes a write lock just to record an event. A plain connection costs
    # 1.17 ms and contends with nothing it does not need.
    conn = sqlite3.connect(db_path, timeout=_BUSY_TIMEOUT_S)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        _insert(conn, job_id, kind, payload)
        conn.commit()
    finally:
        conn.close()


def _insert(conn: sqlite3.Connection, job_id: int, kind: str, payload: str) -> None:
    row = conn.execute(
        "SELECT COALESCE(MAX(seq), 0) + 1 FROM job_events WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    conn.execute(
        "INSERT INTO job_events (job_id, seq, kind, data, at) VALUES (?, ?, ?, ?, ?)",
        (job_id, int(row[0]), kind, payload, _now_iso()),
    )


def append(
    db_path: Path,
    job_id: int,
    kind: str,
    data: dict[str, object] | None = None,
) -> bool:
    """Append one immutable event to a job's history. Returns whether it landed.

    `seq` is monotonic per job and assigned here rather than by the caller, so
    two writers cannot disagree about ordering.

    Recording an event MUST NOT be able to fail the job it describes. This runs
    inside the ingest path, where a run may already have spent an hour of
    provider quota; a locked database or an unserialisable payload degrades to
    "no event recorded" rather than destroying the work being observed.

    But a writer that loses rows silently is indistinguishable from a job that
    did nothing — which is the defect this whole surface exists to remove. So
    the guard stays and the silence goes: the return value says whether the row
    was written, and the caller counts what it lost (SYSTEM_BEHAVIOR §12.1).
    Callers written before v0.59.0 ignored a `None` return and are unaffected.
    """
    try:
        payload = json.dumps(data or {}, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001 - an unserialisable payload is not fatal
        _log.debug("Could not serialise job event (non-fatal)", exc_info=True)
        return False

    for heal in (False, True):
        try:
            _write(db_path, job_id, kind, payload, heal=heal)
            return True
        except sqlite3.OperationalError as e:
            # A database that predates `job_events` has no such table, and only
            # `connect()` creates it. Retry once through the healing path — once,
            # not in a loop.
            if not heal and "no such table" in str(e).lower():
                continue
            _log.debug("Could not append job event (non-fatal): %s", e)
            return False
        except Exception:  # noqa: BLE001 - see docstring: never fail the job
            _log.debug("Could not append job event (non-fatal)", exc_info=True)
            return False
    return False


def listing(db_path: Path, job_id: int, *, limit: int = 200) -> list[dict[str, object]]:
    """A job's events oldest-first, so a reader follows the story forwards."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT seq, kind, data, at FROM job_events WHERE job_id = ? "
            "ORDER BY seq ASC LIMIT ?",
            (job_id, int(limit)),
        ).fetchall()
    out: list[dict[str, object]] = []
    for seq, kind, data, at in rows:
        try:
            parsed = json.loads(data)
        except Exception:  # noqa: BLE001 - a malformed row must not hide the rest
            parsed = {"raw": data}
        out.append({"seq": seq, "kind": kind, "data": parsed, "at": at})
    return out
