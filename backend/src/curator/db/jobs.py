"""Curator state DB — ingest job queue (DB-2 slice 2).

Carved verbatim from db/_entities.py; re-exported by db/__init__.py.
"""

from __future__ import annotations

from pathlib import Path

from .. import constants as consts
from .schema import (
    _now_iso,
    connect,
)

def enqueue_job(
    db_path: Path,
    source_id: int,
    job_type: str,
    *,
    trigger: str = "wiki_add",
    node_id: str | None = None,
    source_name: str = "",
) -> int:
    """Create or reuse a queued/running ingest job for a source and job type.

    source_id=0 is the sentinel for global jobs (e.g. L3 clustering) that are
    not tied to a specific source row.  The ingest_jobs table has no FK on
    source_id (removed in migration) so 0 inserts cleanly.
    """
    with connect(db_path) as conn:
        existing = conn.execute(
            f"""
            SELECT id FROM ingest_jobs
            WHERE source_id = ? AND job_type = ? AND state IN ('{consts.STATUS_QUEUED}', '{consts.STATUS_RUNNING}')
            ORDER BY id DESC LIMIT 1
            """,
            (source_id, job_type),
        ).fetchone()
        if existing:
            return int(existing["id"])
        cur = conn.execute(
            f"""
            INSERT INTO ingest_jobs
                (source_id, job_type, trigger, node_id, state, phase, progress,
                 progress_current, progress_total, source_name, created_at)
            VALUES (?, ?, ?, ?, '{consts.STATUS_QUEUED}', ?, 0.0, 0, 0, ?, ?)
            """,
            (
                source_id,
                job_type,
                trigger,
                node_id,
                "queued",
                source_name,
                _now_iso(),
            ),
        )
        if cur.lastrowid is None:
            raise RuntimeError("failed to create ingest job")
        return int(cur.lastrowid)



def get_pending_jobs_for_source(db_path: Path, source_id: int) -> list[dict]:
    """Return queued/running jobs for one source."""
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM ingest_jobs
            WHERE source_id = ? AND state IN ('{consts.STATUS_QUEUED}', '{consts.STATUS_RUNNING}')
            ORDER BY id ASC
            """,
            (source_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def list_ingest_jobs(
    db_path: Path,
    *,
    states: tuple[str, ...] | None = None,
    limit: int = 50,
) -> list[dict]:
    """List ingest jobs, newest first unless filtered to queued/running."""
    params: list[object] = []
    query = "SELECT * FROM ingest_jobs"
    if states:
        query += f" WHERE state IN ({','.join('?' for _ in states)})"
        params.extend(states)
    order = "ASC" if states and any(s in {consts.STATUS_QUEUED, consts.STATUS_RUNNING} for s in states) else "DESC"
    query += f" ORDER BY id {order} LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    with connect(db_path) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]


def get_ingest_job(db_path: Path, job_id: int) -> dict | None:
    """Return one ingest job by id."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM ingest_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        return dict(row) if row else None


def claim_next_job(db_path: Path) -> dict | None:
    """Atomically claim the oldest queued job."""
    with connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            f"""
            SELECT * FROM ingest_jobs
            WHERE state = '{consts.STATUS_QUEUED}'
            ORDER BY id ASC LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            f"""
            UPDATE ingest_jobs
            SET state = '{consts.STATUS_RUNNING}', phase = '{consts.STATUS_RUNNING}', started_at = ?, error = NULL
            WHERE id = ?
            """,
            (_now_iso(), row["id"]),
        )
        updated = conn.execute(
            "SELECT * FROM ingest_jobs WHERE id = ?",
            (row["id"],),
        ).fetchone()
        return dict(updated) if updated else None


def recover_stale_jobs(db_path: Path) -> int:
    """Return interrupted running jobs to the queue after a process restart."""
    with connect(db_path) as conn:
        source_ids = [
            int(row["source_id"])
            for row in conn.execute(
                f"SELECT DISTINCT source_id FROM ingest_jobs "
                f"WHERE state = '{consts.STATUS_RUNNING}' AND source_id > 0"
            ).fetchall()
        ]
        cur = conn.execute(
            f"""
            UPDATE ingest_jobs
            SET state = '{consts.STATUS_QUEUED}', phase = 'recovered', error = NULL
            WHERE state = '{consts.STATUS_RUNNING}'
            """
        )
        if source_ids:
            conn.execute(
                f"UPDATE sources SET l2_status = '{consts.STATUS_PENDING}', "
                "layer_error = NULL "
                f"WHERE l2_status = '{consts.STATUS_RUNNING}' "
                f"AND id IN ({','.join('?' * len(source_ids))})",
                source_ids,
            )
        return int(cur.rowcount or 0)


def update_job_progress(
    db_path: Path,
    job_id: int,
    *,
    phase: str,
    progress: float | None = None,
    progress_current: int | None = None,
    progress_total: int | None = None,
) -> None:
    """Update progress fields for a running job."""
    fields = ["phase = ?"]
    values: list[object] = [phase]
    if progress is not None:
        fields.append("progress = ?")
        values.append(max(0.0, min(1.0, float(progress))))
    if progress_current is not None:
        fields.append("progress_current = ?")
        values.append(int(progress_current))
    if progress_total is not None:
        fields.append("progress_total = ?")
        values.append(int(progress_total))
    values.append(job_id)
    with connect(db_path) as conn:
        conn.execute(
            f"UPDATE ingest_jobs SET {', '.join(fields)} WHERE id = ?",
            tuple(values),
        )


def mark_job_done(
    db_path: Path,
    job_id: int,
    *,
    pages_created: int = 0,
    pages_updated: int = 0,
) -> None:
    """Mark a job as completed."""
    with connect(db_path) as conn:
        conn.execute(
            f"""
            UPDATE ingest_jobs
            SET state = '{consts.STATUS_DONE}', phase = '{consts.STATUS_DONE}', progress = 1.0,
                finished_at = ?, pages_created = ?, pages_updated = ?, error = NULL
            WHERE id = ?
            """,
            (_now_iso(), pages_created, pages_updated, job_id),
        )


def mark_job_failed(db_path: Path, job_id: int, error: str) -> None:
    """Mark a job as failed."""
    with connect(db_path) as conn:
        conn.execute(
            f"""
            UPDATE ingest_jobs
            SET state = '{consts.STATUS_FAILED}', phase = '{consts.STATUS_FAILED}', finished_at = ?, error = ?
            WHERE id = ?
            """,
            (_now_iso(), error[:2000], job_id),
        )


def cancel_job(db_path: Path, job_id: int) -> bool:
    """Cancel a queued job. Running jobs are left untouched by design."""
    with connect(db_path) as conn:
        cur = conn.execute(
            f"""
            UPDATE ingest_jobs
            SET state = '{consts.STATUS_CANCELLED}', phase = '{consts.STATUS_CANCELLED}',
                finished_at = ?, error = 'Cancelled by user'
            WHERE id = ? AND state = '{consts.STATUS_QUEUED}'
            """,
            (_now_iso(), job_id),
        )
        return bool(cur.rowcount)


def rerun_job(db_path: Path, job_id: int) -> bool:
    """Return a completed, failed, or cancelled job to the queued state."""
    with connect(db_path) as conn:
        cur = conn.execute(
            f"""
            UPDATE ingest_jobs
            SET state = '{consts.STATUS_QUEUED}', phase = 'rerun', progress = 0.0,
                progress_current = 0, progress_total = 0, retry_count = 0,
                error = NULL, started_at = NULL, finished_at = NULL
            WHERE id = ? AND state IN (?, ?, ?)
            """,
            (job_id, consts.STATUS_DONE, consts.STATUS_FAILED, consts.STATUS_CANCELLED),
        )
        return bool(cur.rowcount)


def requeue_job_for_retry(db_path: Path, job_id: int, retry_count: int, error: str) -> None:
    """Reset a failed job back to queued for retry, recording the attempt count."""
    with connect(db_path) as conn:
        conn.execute(
            f"""
            UPDATE ingest_jobs
            SET state = '{consts.STATUS_QUEUED}', phase = 'retry', progress = 0.0,
                retry_count = ?, error = ?, started_at = NULL, finished_at = NULL
            WHERE id = ?
            """,
            (retry_count, error[:2000], job_id),
        )


def accumulate_job_tokens(
    db_path: Path,
    job_id: int,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float = 0.0,
) -> None:
    """Add token counts to a job row (cumulative, safe to call multiple times)."""
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE ingest_jobs
            SET input_tokens  = COALESCE(input_tokens, 0)  + ?,
                output_tokens = COALESCE(output_tokens, 0) + ?,
                estimated_cost_usd = COALESCE(estimated_cost_usd, 0.0) + ?
            WHERE id = ?
            """,
            (int(input_tokens), int(output_tokens), float(cost_usd), job_id),
        )


def count_active_l2_jobs(db_path: Path) -> int:
    """Return the number of queued or running l2_atoms jobs."""
    if not db_path.exists():
        return 0
    with connect(db_path) as conn:
        row = conn.execute(
            f"SELECT COUNT(*) FROM ingest_jobs WHERE job_type = 'l2_atoms' AND state IN ('{consts.STATUS_QUEUED}', '{consts.STATUS_RUNNING}')"
        ).fetchone()
        return int(row[0]) if row else 0


def get_jobs_done_today(db_path: Path) -> list[dict]:
    """Return jobs completed today (UTC date), newest first."""
    if not db_path.exists():
        return []
    today_prefix = _now_iso()[:10]  # "YYYY-MM-DD"
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM ingest_jobs WHERE state = '{consts.STATUS_DONE}' AND finished_at LIKE ? ORDER BY id DESC",
            (f"{today_prefix}%",),
        ).fetchall()
        return [dict(r) for r in rows]
