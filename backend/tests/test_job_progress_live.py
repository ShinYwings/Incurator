"""A real L2 job must leave a history. Not the writer — the job.

v0.58.0 added `job_events`, a writer for it, and `wiki jobs events`. Every test
passed. On the live vault two jobs then completed with **zero** event rows,
because the writer hung off `WorkerCallbacks` and `run_next_job` compiles L2
through `compile_source_l2`, which never touches those callbacks.

The tests that missed it called `job_events.append` directly. They proved the
writer worked; nothing proved anything called it.

So these tests run the job. Note what they deliberately do NOT do: every other
worker test in `test_v021_background_jobs.py` patches `compile_source_l2` out
(lines 67, 82, 131, 143, ...), which here would mock away the exact function
under test and go green with the sink never invoked. The stub is the LLM client,
not the compile.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db, ingest_worker
from curator.db import job_events


class StubLLMClient:
    """An LLM that returns no units, so the batch loop runs and nothing is written.

    `optimal_chunk_chars` is read by `pipeline.chunking.client_optimal_chunk_chars`
    and is what makes the batch count deterministic: a modest value gives several
    batches with no large fixture.

    Keep it comfortably above 500. `extract_knowledge_units` subdivides an
    oversized span with `_chunk_text(chunk_size=max_chars - 500, overlap=500)`,
    so a client claiming less than 500 passes a NEGATIVE chunk size and the
    batch count explodes — 1,148 batches out of this eight-section fixture at
    `200`. No real client reports a window that small (the default is 60,000),
    so this stub stays realistic rather than pinning the pathology; the guard
    itself is tracked separately.
    """

    model = "stub"
    optimal_chunk_chars = 1200

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, *, json_mode: bool = False, temperature: float = 0.3) -> str:
        self.calls += 1
        return json.dumps({"units": []})


def _seed_source(paths: cfg.WikiPaths, body: str) -> int:
    """Register one L1-done source with enough sections to produce several batches."""
    rel = "03_Notes/Long.md"
    target = paths.root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    with db.connect(paths.state_db) as conn:
        cur = conn.execute(
            "INSERT INTO sources "
            "(relpath, content_hash, file_type, bytes, added_at, l1_status) "
            "VALUES (?, 'long-v1', 'md', ?, datetime('now'), 'done')",
            (rel, len(body.encode("utf-8"))),
        )
        return int(cur.lastrowid)


@pytest.fixture()
def vault(tmp_path: Path) -> cfg.WikiPaths:
    paths = cfg.paths_from_config(tmp_path)
    paths.root.mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    return paths


@pytest.fixture()
def stub_llm(monkeypatch: pytest.MonkeyPatch) -> StubLLMClient:
    """Replace the LLM the worker builds — NOT the compile it runs.

    `run_next_job` builds its own client from config (`ingest_worker.py:170`),
    so the seam for a test is the client factory. Patching here keeps the real
    `compile_source_l2` and the real batch loop in the call path, which is the
    entire point of this file.
    """
    client = StubLLMClient()
    monkeypatch.setattr(ingest_worker, "build_client", lambda *_a, **_k: client)
    return client


def _job_state(paths: cfg.WikiPaths, job_id: int) -> str:
    with db.connect(paths.state_db) as conn:
        row = conn.execute(
            "SELECT state FROM ingest_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    return str(row[0])


def _long_body(sections: int = 8) -> str:
    out = ["# Long Source\n"]
    for i in range(sections):
        out.append(f"\n## Section {i}\n")
        out.append(("Sentence about topic %d. " % i) * 12)
    return "".join(out)


def test_a_real_l2_job_leaves_a_history(vault: cfg.WikiPaths, stub_llm: StubLLMClient) -> None:
    """G1. The whole point: run the job, then look at what it recorded."""
    source_id = _seed_source(vault, _long_body())
    job_id = db.enqueue_job(vault.state_db, source_id=source_id, job_type="l2_atoms")

    result = ingest_worker.run_next_job(vault, cfg.DEFAULT_CONFIG)

    # Assert the job SUCCEEDED before reading its history. Without this the
    # test passes on a failed compile, because a failure also produces events
    # (status, some extracted, then error) -- and it did: an AttributeError in
    # the publishing emit went green here until a sibling test caught it.
    assert result.get("ok"), f"the job did not succeed: {result.get('error')}"
    assert _job_state(vault, job_id) == "done"

    events = job_events.listing(vault.state_db, job_id, limit=1000)
    assert events, "a completed L2 job recorded no history at all"
    assert events[-1]["kind"] == "done", (
        f"a finished job must record how it ended, got {events[-1]['kind']}"
    )
    assert len({e["kind"] for e in events}) >= 2, f"only one kind of event: {events}"
    extracted = [e for e in events if e["kind"] == "extracted"]
    assert len(extracted) >= 2, (
        "expected one event per extraction batch; a single event means the sink "
        f"fired at a boundary and never inside the loop: {events}"
    )
    # Ordering is the property that makes the history readable as a story.
    assert [e["seq"] for e in events] == sorted(e["seq"] for e in events)


def test_progress_advances_during_l2_not_only_at_its_ends(
    vault: cfg.WikiPaths, stub_llm: StubLLMClient
) -> None:
    """The user-facing half: `0/1` for twenty minutes is the reported symptom."""
    source_id = _seed_source(vault, _long_body())
    job_id = db.enqueue_job(vault.state_db, source_id=source_id, job_type="l2_atoms")

    ingest_worker.run_next_job(vault, cfg.DEFAULT_CONFIG)

    events = job_events.listing(vault.state_db, job_id, limit=1000)
    batches = [e["data"].get("batch") for e in events if e["kind"] == "extracted"]
    assert batches == sorted(batches), f"batch numbers not monotonic: {batches}"
    assert batches[0] == 1 and batches[-1] > 1, (
        f"progress must move through the batches, saw {batches}"
    )
    totals = {e["data"].get("batches") for e in events if e["kind"] == "extracted"}
    assert len(totals) == 1 and totals != {None}, (
        f"the denominator must be stable and known: {totals}"
    )


def test_the_test_does_not_mock_the_function_under_test() -> None:
    """G1's binding constraint (plan review R1), pinned mechanically.

    Patching `compile_source_l2` is the path of least resistance here — every
    neighbouring worker test does it — and it is exactly what would make this
    file green while the sink is never called. That mistake has already shipped
    once; a comment would not have stopped it.
    """
    src = Path(__file__).read_text(encoding="utf-8")
    for match in re.finditer(r"patch\(([^)]*)\)", src):
        assert "compile_source_l2" not in match.group(1), (
            "this file must run the real compile; stub the LLM client instead"
        )


class InterruptingClient(StubLLMClient):
    """Dies partway through, like a provider refusing mid-extraction."""

    def __init__(self, fail_on_call: int) -> None:
        super().__init__()
        self.fail_on_call = fail_on_call

    def chat(self, messages, *, json_mode: bool = False, temperature: float = 0.3) -> str:
        self.calls += 1
        if self.calls >= self.fail_on_call:
            raise RuntimeError("provider gave up")
        return json.dumps({"units": [{
            "claim": f"claim {self.calls}", "claim_type": "fact",
            "span_id": 1, "one_liner": f"unit {self.calls}",
        }]})


def test_progress_events_did_not_make_extraction_resumable(
    vault: cfg.WikiPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G2. Observing a loop must not turn it into a checkpointed one.

    L2 extraction is all-or-nothing on purpose: units accumulate in memory and
    are bulk-persisted only on full success. Emitting an event per batch puts a
    callback exactly where a checkpoint would go, three lines below a docstring
    that says an interrupted run re-processes every batch. If a later change
    quietly starts persisting per batch, this fails.
    """
    client = InterruptingClient(fail_on_call=2)
    monkeypatch.setattr(ingest_worker, "build_client", lambda *_a, **_k: client)
    source_id = _seed_source(vault, _long_body())
    db.enqueue_job(vault.state_db, source_id=source_id, job_type="l2_atoms")

    ingest_worker.run_next_job(vault, cfg.DEFAULT_CONFIG)

    assert client.calls >= 2, "the run must actually have reached the failing batch"
    with db.connect(vault.state_db) as conn:
        published = conn.execute(
            "SELECT COUNT(*) FROM knowledge_units WHERE source_id = ?", (source_id,)
        ).fetchone()[0]
    assert published == 0, (
        f"{published} unit(s) survived an interrupted extraction; L2 must stay "
        "all-or-nothing — progress events observe the loop, they do not commit it"
    )


def test_a_lost_event_is_reported_rather_than_hidden(
    vault: cfg.WikiPaths, stub_llm: StubLLMClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G3. A writer that silently loses rows is the bug, not the mitigation."""
    source_id = _seed_source(vault, _long_body())
    job_id = db.enqueue_job(vault.state_db, source_id=source_id, job_type="l2_atoms")

    real_append = job_events.append
    state = {"n": 0}

    def flaky(db_path, jid, kind, data=None):
        state["n"] += 1
        if kind == "extracted" and state["n"] % 2 == 0:
            return False  # what a contended database looks like to the caller
        return real_append(db_path, jid, kind, data)

    monkeypatch.setattr(ingest_worker.job_events, "append", flaky)
    ingest_worker.run_next_job(vault, cfg.DEFAULT_CONFIG)

    events = job_events.listing(vault.state_db, job_id, limit=1000)
    done = [e for e in events if e["kind"] == "done"]
    assert done, f"a finished job must record how it ended: {events}"
    assert done[-1]["data"].get("events_dropped", 0) > 0, (
        "events were dropped and the history does not admit it"
    )


def test_a_failed_job_still_reports_what_its_history_lost(
    vault: cfg.WikiPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The failure path is where an operator most needs to know rows went missing.

    The first draft carried `events_dropped` only on the success event, so a job
    that dropped events and then failed reported neither.
    """
    class Exploding(StubLLMClient):
        def chat(self, messages, *, json_mode=False, temperature=0.3):
            raise RuntimeError("permanent provider failure")

    monkeypatch.setattr(ingest_worker, "build_client", lambda *_a, **_k: Exploding())
    source_id = _seed_source(vault, _long_body())
    job_id = db.enqueue_job(vault.state_db, source_id=source_id, job_type="l2_atoms")

    real = job_events.append

    def flaky(db_path, jid, kind, data=None):
        return False if kind == "extracted" else real(db_path, jid, kind, data)

    monkeypatch.setattr(ingest_worker.job_events, "append", flaky)
    ingest_worker.run_next_job(vault, cfg.DEFAULT_CONFIG)

    events = job_events.listing(vault.state_db, job_id, limit=1000)
    terminal = [e for e in events if e["kind"] in ("done", "error")]
    assert terminal, f"a job that ended must say so: {events}"
    assert "events_dropped" in terminal[-1]["data"], (
        "the terminal event of a FAILED job must carry the drop count too"
    )


def test_losing_the_terminal_event_itself_is_logged(
    vault: cfg.WikiPaths, stub_llm: StubLLMClient, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If contention eats the `done` row, the history just stops — with no `done`
    line and no count anywhere. The log does not depend on the database, so it is
    the one place that can still say the history is incomplete.
    """
    source_id = _seed_source(vault, _long_body())
    db.enqueue_job(vault.state_db, source_id=source_id, job_type="l2_atoms")

    real = job_events.append
    monkeypatch.setattr(
        ingest_worker.job_events, "append",
        lambda db_path, jid, kind, data=None: (
            False if kind in ("done", "error") else real(db_path, jid, kind, data)
        ),
    )
    with caplog.at_level("WARNING"):
        ingest_worker.run_next_job(vault, cfg.DEFAULT_CONFIG)

    assert any("history is incomplete" in r.getMessage() for r in caplog.records), (
        f"losing the terminal event was not reported: {[r.getMessage() for r in caplog.records]}"
    )
