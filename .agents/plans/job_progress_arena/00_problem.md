# Briefing: a job's progress is still unobservable, and v0.58.0 fixed the wrong layer

Date: 2026-08-18 | Author: main agent (measured against the live `second_brain` vault)

## 1. The symptom the user actually reported

A `wiki add` on a 673-page book sat at 0% CPU for 26 minutes and was diagnosed
as hung. It was working correctly — transcribing pages one at a time through a
subprocess. Nothing on screen or in the database could tell the two apart.

v0.58.0 (#159) shipped two things for this: per-page progress printing in the
vision loop, and `wiki jobs events <id>` reading an append-only `job_events`
history. The vision half works and is verified. **The `job_events` half does not
run at all on a real job.**

## 2. Measured: the writer is never called

`wiki build` queued 36 L2 jobs against the live vault. Jobs 42 and 43 completed
successfully:

```
id | state | phase | progress_current/progress_total
42 | done  | done  | 5/5
43 | done  | done  | 11/11
SELECT COUNT(*) FROM job_events  ->  0
```

Instrumented `job_events.append` with a tracing wrapper and re-ran one queued
job in the foreground with `run_queued_jobs(paths, limit=1)`. The job returned
`ok=True`. **The wrapper never printed.** `append` is not called once during a
successful L2 job.

An isolated call confirms the write path itself is sound — a direct
`job_events.append(db, 43, 'probe2', {})` inserts fine, so this is not a locked
database, not a foreign-key failure, and not a wrong `state_db` path.

## 3. Cause: the event writer hangs off a callback class the L2 job does not use

v0.58.0 put the writes in `WorkerCallbacks` (`ingest_worker.py:40-108`). Each of
`on_pass1_start`, `on_fragment_written`, `on_pass2_start`, `on_theme_written`
calls `self._event(...)`.

But `run_next_job` does not drive L2 through those callbacks. It calls the
v0.3.1 pipeline directly:

```python
# ingest_worker.py:205
db.update_job_progress(paths.state_db, job_id, phase=PHASE_L2, progress=0.1,
                       progress_current=0, progress_total=1)
# ingest_worker.py:211
cr = _compile.compile_source_l2(paths, client, source_id)
# ingest_worker.py:219
db.update_job_progress(paths.state_db, job_id, phase=PHASE_L2, progress=0.5,
                       progress_current=pages_created,
                       progress_total=max(1, pages_created))
```

`compile_source_l2` (`pipeline/compile.py:274`) takes **no callbacks
parameter**. `WorkerCallbacks` survives only as the factory handed to
`run_l3_from_existing_atoms` (`:177`, `:245`) — the legacy L3 path. For an L2
job the event writer is structurally unreachable.

So ROADMAP item 8 was closed against unit tests that call `job_events.append`
directly plus a code path nobody executes. The table moved from "nothing
inserts" to "the inserter is never called": the same empty table, one layer
further from the symptom.

## 4. The larger finding falling out of the same trace

**L2 progress is not incremental.** The two `update_job_progress` calls above
are the only progress writes for an L2 job. Everything between them — span
extraction, every LLM knowledge-unit batch, staging, gating, atomic publish — is
one opaque block. A job sitting at `0/1` for twenty minutes is indistinguishable
from a stalled one.

That is the user's original symptom, unfixed, in the layer that now does most of
the work. ROADMAP item 8's earlier sub-claim — *"resolved. `WorkerCallbacks`
reports 0.25 / 0.5 / 0.75 / 0.9 across `on_pass1_start`, `on_fragment_written`,
`on_pass2_start`, `on_theme_written`"* — is true only of the legacy L3 path and
false for every L2 job.

## 5. Where the time actually goes

`compile_source_l2` → `knowledge_units.extract_knowledge_units`
(`pipeline/knowledge_units.py:302`). That function already batches spans and
already computes a human label per batch:

```python
# knowledge_units.py:382
for index, batch in enumerate(batches, start=1):
    result = _run_batch_with_retry(
        ..., label=f"batch {index}/{len(batches)}", ...
    )
```

One LLM call per batch, each slow. **This loop is the natural progress signal**
and it already knows both the numerator and the denominator. Nothing is
computed for the purpose; the information exists and is thrown away.

## 6. Constraint the debate must respect

`extract_knowledge_units` is documented as all-or-nothing:

> *"Extraction is all-or-nothing: staged units from a previous interrupted run
> are discarded first, then units accumulate in memory and are bulk-persisted
> only on full success. An interrupted run therefore re-processes every batch."*

That is deliberate (a v0.52.0 removal of a checkpoint mechanism that could never
run). **A progress hook must not become a resumability mechanism by accident** —
ROADMAP item 6 owns that, and its docstring warns the old resume path returned
the staged-unit list, which is empty after a successful publish and would have
retired the source's entire authoritative unit set. Emitting an event is not
committing a checkpoint; the plan must keep those separate and say so.

## 7. Why the verification missed it

The v0.58.0 tests call `job_events.append` and `listing` directly and assert
ordering, per-job scoping, and the never-fail guarantee. **Not one of them runs
a job.** And `append`'s `except Exception` — correct in itself, an event must
never fail the job it describes — makes a broken writer silent: "no rows" reads
identically to "no events happened."

Any accepted proposal must include a test that runs a real job end to end and
asserts a non-zero row count. A unit test on the writer is not evidence that
anything calls it.

## 8. Question for the Arena

Where does the progress signal come from, and what is the smallest contract
change that makes "slow or stalled" answerable for L2 without turning an
observability feature into a durability one?

Non-negotiable: the answer must be verified by running a job, not by asserting
on the writer.
