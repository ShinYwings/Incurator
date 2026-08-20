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


@pytest.fixture(autouse=True)
def _no_capacity_leak():
    """Clear the block before AND after every test in this file.

    The block is process-wide state. Clearing it only at the start of each test
    happens to self-heal in a full-suite run and is not enforced by anything —
    running just one of these tests alongside `test_v021_background_jobs.py`
    leaves the block set and makes six unrelated tests fail, because
    `run_next_job` defers before it ever reaches `claim_next_job`. A fixture is
    the only version of this that a future test cannot forget.
    """
    llm.clear_capacity_block()
    yield
    llm.clear_capacity_block()


def test_a_capacity_refusal_is_visible_to_a_later_client() -> None:
    """A new client must not be born believing the provider is available.

    `run_next_job` builds one per job, so a per-instance flag can never survive
    the retry it is meant to govern.
    """
    first = llm.AntigravityCliClient(model="m")
    with pytest.raises(llm.AntigravityCliError):
        first._raise_capacity_error()

    second = llm.AntigravityCliClient(model="m")
    assert llm.capacity_blocked_for("antigravity-cli") > 0, "the block did not outlive the client"
    assert second.ping() is False, "a fresh client ignored a refusal seconds old"


def test_the_block_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    """It is a wait, not a shutdown — the whole point is that quota returns."""
    with pytest.raises(llm.AntigravityCliError):
        llm.AntigravityCliClient(model="m")._raise_capacity_error()
    assert llm.capacity_blocked_for("antigravity-cli") > 0

    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 10_000)
    assert llm.capacity_blocked_for("antigravity-cli") == 0


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

    with pytest.raises(llm.AntigravityCliError):
        llm.AntigravityCliClient(model="m")._raise_capacity_error()

    result = ingest_worker.run_next_job(paths, cfg.DEFAULT_CONFIG)

    assert result.get("deferred") is True
    # The property that matters is the JOB, not whether a client object was
    # constructed -- one is built to ask whether its provider is refusing.
    # Untouched means: never claimed, no retry spent, no start recorded.
    with db.connect(paths.state_db) as conn:
        row = conn.execute(
            "SELECT state, retry_count, started_at FROM ingest_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    assert row[0] == "queued", "the job must stay claimable, not be consumed"
    assert row[1] == 0, "a deferral must not spend a retry"
    assert row[2] is None, "a deferred job was never started"


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

    with pytest.raises(llm.AntigravityCliError):
        llm.AntigravityCliClient(model="m")._raise_capacity_error()

    out = ingest_worker.run_queued_jobs(paths, cfg.DEFAULT_CONFIG)
    assert len(out) == 1 and out[0].get("deferred") is True


def test_an_empty_queue_still_reports_nothing(tmp_path) -> None:
    """The other side of the same distinction, so the first test cannot pass by
    accident."""
    from curator import config as cfg, db, ingest_worker

    paths = cfg.paths_from_config(tmp_path)
    paths.root.mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    assert ingest_worker.run_queued_jobs(paths, cfg.DEFAULT_CONFIG) == []


def test_the_background_worker_resumes_by_itself_when_the_block_lifts(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A block is a delay, not a stop. Nothing should have to restart anything.

    The MCP-hosted worker treats "no job" as idle and polls again, so a deferral
    just makes it wait. Pinned because it is the difference between "quota came
    back and the book finished overnight" and "quota came back and someone had
    to notice".
    """
    from curator import config as cfg, db, ingest_worker

    paths = cfg.paths_from_config(tmp_path)
    paths.root.mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    db.enqueue_job(paths.state_db, source_id=1, job_type="l2_atoms")

    with pytest.raises(llm.AntigravityCliError):
        llm.AntigravityCliClient(model="m")._raise_capacity_error()

    blocked = ingest_worker.run_next_job(paths, cfg.DEFAULT_CONFIG)
    assert blocked.get("deferred") is True
    assert blocked.get("job") is None, (
        "the worker loop keys idling on job-is-None; a deferral must look idle "
        "to it or the daemon would spin"
    )

    llm.clear_capacity_block("antigravity-cli")   # the block expires
    started: list[int] = []
    monkeypatch.setattr(
        ingest_worker, "build_client",
        lambda *_a, **_k: started.append(1) or object(),
    )
    ingest_worker.run_next_job(paths, cfg.DEFAULT_CONFIG)
    assert started, "the job was not picked up after the block lifted"


# --------------------------------------------------------------------------
# The block is per-provider. A global one would stop work a healthy fallback
# can do -- and the default topology for antigravity-cli IS a failover.
# --------------------------------------------------------------------------


def test_one_provider_refusing_does_not_block_another() -> None:
    """`antigravity-cli` defaults to a FailoverClient with an Ollama fallback,
    and `AntigravityCliError` is already in the failover set — so a 429 there is
    absorbed. Blocking globally would stop jobs that Ollama could run, including
    in a vault configured with no Antigravity at all.
    """
    with pytest.raises(llm.AntigravityCliError):
        llm.AntigravityCliClient(model="m")._raise_capacity_error()

    assert llm.capacity_blocked_for("antigravity-cli") > 0
    assert llm.capacity_blocked_for("ollama") == 0
    assert llm.OllamaClient().capacity_blocked_for() == 0, (
        "a refusal from one backend blocked an unrelated one"
    )


def test_a_failover_is_free_while_any_delegate_is() -> None:
    """The whole point of a failover is that one provider refusing is survivable."""
    fc = llm.FailoverClient.__new__(llm.FailoverClient)
    fc.providers = [llm.AntigravityCliClient(model="m"), llm.OllamaClient()]
    with pytest.raises(llm.AntigravityCliError):
        fc.providers[0]._raise_capacity_error()

    assert fc.providers[0].capacity_blocked_for() > 0
    assert fc.capacity_blocked_for() == 0, (
        "the failover reported itself blocked while its fallback was healthy"
    )
