# Core Proposal: a one-function progress sink threaded to the batch loop

Date: 2026-08-18 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

### 1.1 The shape of the hook

Do **not** reuse `ingest_llm.IngestCallbacks`. That protocol has fourteen
methods (`on_stream_chunk`, `ask_confirm`, `on_curation_written`, …) built for
the interactive L1 flow. Threading it into the compile pipeline would import an
interactive-CLI contract into a batch compiler and force every test double to
grow fourteen no-ops. The compile path needs exactly one verb: *something
happened, here is what*.

```python
# pipeline/compile.py  (new, module-level)
ProgressSink = Callable[[str, dict[str, object]], None]
"""kind, data -> None. Must never raise; callers treat it as fire-and-forget."""
```

`kind` reuses the vocabulary `job_events.data` already documents in the schema
comment (`status|extracted|page|chunk|error|done`), so `wiki jobs events` needs
no new rendering.

### 1.2 Threading it, two functions deep

```python
def compile_source_l2(
    paths, client, source_id, *, curate_spec_hash="",
    on_progress: ProgressSink | None = None,      # NEW, keyword-only, optional
) -> CompileResult:
```

Optional with a `None` default is load-bearing: `compile_source_l2` has **21
call sites in `backend/tests/test_authored_topology.py` alone** plus
`ingest_llm.py:545`. A required parameter would rewrite all of them for no gain
and would violate the surgical-change rule.

Emit at the four boundaries the function already crosses:

```python
    spans = source_spans.spans_from_sections(sections)
    span_ids = source_spans.store_source_spans(...)
    _emit(on_progress, "status", phase="l2", stage="spans_stored", spans=len(span_ids))

    ku_result = knowledge_units.extract_knowledge_units(
        ..., on_progress=on_progress,          # threaded one level deeper
    )
    ...
    _emit(on_progress, "status", phase="l2", stage="publishing", units=len(units))
```

and in the batch loop — the one place that knows the real denominator:

```python
# knowledge_units.py, inside `for index, batch in enumerate(batches, start=1)`
    ...
    pending_units.extend(result.units)
    _emit(on_progress, "extracted", phase="l2",
          batch=index, batches=len(batches), units=len(pending_units))
```

That is one event per LLM call. On the 673-page book that is a heartbeat every
few seconds through the phase that currently prints nothing for twenty minutes.

### 1.3 The worker supplies the sink

```python
# ingest_worker.py, replacing the two-point progress writes
def _sink(kind: str, data: dict) -> None:
    job_events.append(paths.state_db, job_id, kind, data)
    if kind == "extracted" and data.get("batches"):
        db.update_job_progress(
            paths.state_db, job_id, phase=consts.PHASE_L2,
            progress=0.1 + 0.4 * (data["batch"] / data["batches"]),
            progress_current=data["batch"], progress_total=data["batches"],
        )

cr = _compile.compile_source_l2(paths, client, source_id, on_progress=_sink)
```

This kills two birds. `job_events` gets rows from the path that actually runs,
**and** `progress_current/progress_total` becomes a real fraction of real work
instead of `0/1` then `n/n`. `wiki jobs list` becomes answerable without
`wiki jobs events` even being run.

### 1.4 `_emit` is where "never raise" lives

```python
def _emit(sink, kind, **data):
    if sink is None:
        return
    try:
        sink(kind, data)
    except Exception:
        _log.debug("progress sink failed (non-fatal)", exc_info=True)
```

The guard belongs at the **call site**, not only inside `job_events.append`. A
sink is caller-supplied and may be anything; the compiler must not inherit its
bugs. `job_events.append` keeps its own guard as defence in depth.

## 2. Pros & Cons

**Pros.**

- One new type alias and one optional keyword argument. No schema change, no
  migration, no new table, no new module.
- The signal is taken from a loop that already computes `f"batch {index}/{len(batches)}"` for its retry label. Nothing new is measured.
- Fixes the progress-granularity defect and the empty-table defect with the same wire — they are the same missing wire.
- `compile_source_l2`'s 21 existing test call sites are untouched.

**Cons / limits.**

- Two functions gain a parameter, so the compile contract is genuinely wider.
  `SYSTEM_BEHAVIOR.md` must record it (spec-first: contract before code).
- Batch count is not proportional to wall-clock. Batches differ in size and
  `_run_batch_with_retry` can retry, so `3/7` does not mean 43% of the time has
  passed. It means three of seven LLM calls have returned — which is exactly the
  liveness question being asked, and honest about being a count rather than an
  ETA.
- Nothing is emitted *during* a single batch. If one LLM call hangs for twenty
  minutes, the history goes quiet for twenty minutes. That is a true and useful
  signal (the previous event's timestamp localises the stall to one batch), but
  it is not sub-batch granularity and the plan should not claim it is.
