"""A capacity refusal must outlive the client that received it.

Measured twice on a 673-page book: it completed all 277 extraction batches, hit
a 429 at the staged compile, and was requeued — which restarted it at batch 1,
re-spent the same provider budget, and arrived at the same wall. Both runs
discarded ~90 minutes of work and published nothing.

The 429 is a burst limit, not exhaustion: a trivial call succeeded within a
minute of the failure. So a retry that simply waited would have published. The
backoff for that already exists — `_raise_capacity_error` sets
`_capacity_blocked_until = now + 300` — but it is doubly inert:

  * it is INSTANCE state, and `run_next_job` builds a fresh client per job
  * it is consulted only by `ping()`, which the ingest path never calls

so the retry re-runs immediately, every time.
"""

from __future__ import annotations

import time

import pytest

from curator import llm


def test_a_capacity_refusal_is_visible_to_a_later_client() -> None:
    """A new client must not be born believing the provider is available.

    `run_next_job` builds one per job, so a per-instance flag can never survive
    the retry it is meant to govern.
    """
    llm.clear_capacity_block()
    first = llm.AntigravityCliClient(model="m")
    with pytest.raises(llm.AntigravityCliError):
        first._raise_capacity_error()

    second = llm.AntigravityCliClient(model="m")
    assert llm.capacity_blocked_for() > 0, "the block did not outlive the client"
    assert second.ping() is False, "a fresh client ignored a refusal seconds old"


def test_the_block_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    """It is a wait, not a shutdown — the whole point is that quota returns."""
    llm.clear_capacity_block()
    with pytest.raises(llm.AntigravityCliError):
        llm.AntigravityCliClient(model="m")._raise_capacity_error()
    assert llm.capacity_blocked_for() > 0

    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 10_000)
    assert llm.capacity_blocked_for() == 0


def test_a_job_is_not_restarted_while_the_provider_is_refusing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The expensive half: do not re-spend the budget that just ran out.

    Restarting Hartley costs ~90 minutes and 277 provider calls before it can
    even reach the step that failed. Doing that while the provider is still
    refusing guarantees the same outcome.
    """
    from curator import config as cfg, db, ingest_worker

    paths = cfg.paths_from_config(tmp_path)
    paths.root.mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at, l1_status) "
            "VALUES ('03_Notes/a.md', 'h', 'md', 10, datetime('now'), 'done')"
        )
    job_id = db.enqueue_job(paths.state_db, source_id=1, job_type="l2_atoms")

    llm.clear_capacity_block()
    with pytest.raises(llm.AntigravityCliError):
        llm.AntigravityCliClient(model="m")._raise_capacity_error()

    started = []
    monkeypatch.setattr(
        ingest_worker, "build_client",
        lambda *_a, **_k: started.append(1) or object(),
    )
    result = ingest_worker.run_next_job(paths, cfg.DEFAULT_CONFIG)

    assert not started, "a job was started while the provider was refusing"
    assert result.get("deferred") is True
    with db.connect(paths.state_db) as conn:
        state = conn.execute(
            "SELECT state FROM ingest_jobs WHERE id = ?", (job_id,)
        ).fetchone()[0]
    assert state == "queued", "the job must stay claimable, not be consumed"


def test_the_drain_reports_a_deferral_rather_than_a_clean_finish(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """"Nothing to do" and "work is waiting, the provider is refusing" both stop
    the loop and mean opposite things.

    Reporting a clean finish over a queue that is still full is how a stalled
    ingest looks like a completed one — the failure this project keeps meeting.
    """
    from curator import config as cfg, db, ingest_worker

    paths = cfg.paths_from_config(tmp_path)
    paths.root.mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    db.enqueue_job(paths.state_db, source_id=1, job_type="l2_atoms")

    llm.clear_capacity_block()
    with pytest.raises(llm.AntigravityCliError):
        llm.AntigravityCliClient(model="m")._raise_capacity_error()

    out = ingest_worker.run_queued_jobs(paths, cfg.DEFAULT_CONFIG)
    assert len(out) == 1 and out[0].get("deferred") is True

    llm.clear_capacity_block()


def test_an_empty_queue_still_reports_nothing(tmp_path) -> None:
    """The other side of the same distinction, so the first test cannot pass by
    accident."""
    from curator import config as cfg, db, ingest_worker

    paths = cfg.paths_from_config(tmp_path)
    paths.root.mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    llm.clear_capacity_block()
    assert ingest_worker.run_queued_jobs(paths, cfg.DEFAULT_CONFIG) == []
