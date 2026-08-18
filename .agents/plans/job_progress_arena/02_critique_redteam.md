# Critique on the progress-sink proposal

Date: 2026-08-18 | Agent Persona: red_teamer

## 1. Vulnerabilities & Flaws

### F1 — CRITICAL. One DB write per batch, inside the hot loop, with WAL

`_sink` does **two** `connect()` calls per batch: `job_events.append` and
`db.update_job_progress`. And `connect()` is not cheap — read it:

```python
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys = ON")
conn.executescript(SCHEMA_SQL)          # <- the entire schema, every call
if _triggers_need_refresh(conn): _refresh_current_triggers(conn)
_stamp_schema_version(conn)
```

`executescript` issues an implicit COMMIT and takes a write lock. Doing that
twice per batch while a compile holds its own connections is the classic recipe
for `database is locked` — which `append` then **swallows**, reproducing the
exact silent-failure mode this whole plan exists to eliminate.

Worse, the failure would be *load-dependent*: green in a 3-batch test, silently
empty on a 200-batch book. That is the v0.58.0 mistake with extra steps.

**Required:** measure `connect()` cost and lock behaviour under a realistic
batch count **before** writing the sink, and record the number. If it is
material, the sink batches its writes or holds one connection. A plan that
guesses here has learned nothing from the thing it is fixing.

### F2 — The progress formula silently caps L2 at 50%

`progress = 0.1 + 0.4 * (batch / batches)` reaches 0.5 at the last batch, which
happens to match the existing post-compile write. Fine — but the existing code
then also writes `progress=0.5` at `:219`, and `0.75`/`0.9` come from the L3
branch. Nobody has stated what the 0.0–1.0 axis *means* across L2+L3 in one job.
The proposal inherits an undocumented convention and hardcodes magic numbers
(`0.1`, `0.4`) into a second location. Two places now encode the same unwritten
contract.

**Required:** either write the phase→progress mapping down in
`SYSTEM_BEHAVIOR.md` §12 as part of P1, or drop the float entirely for L2 and
let `progress_current/progress_total` carry the meaning. The float is the
weakest of the three fields and the only one that needs a convention.

### F3 — `progress_total` changes meaning mid-flight, and a reader cannot tell

Today `progress_total` for an L2 job ends as *atoms created*. Under the
proposal it becomes *batch count* during the run and then `:219` overwrites it
with atoms created at the end. So the same column means two different things
depending on when you look, with no marker saying which. `wiki jobs list`
renders it as a bare fraction. A user watching `4/7` then seeing `11/11` will
reasonably conclude 11 batches ran.

**Required:** pick one meaning for the column's whole lifetime. Recommend
batches during L2 and *leave it alone* at the end (atoms created already live in
`pages_created`, which is what `mark_job_done` sets and what the dashboard should
read for that number).

### F4 — `on_progress` threaded into `extract_knowledge_units` is one step from resumability, and the docstring is a landmine

The briefing already flags this, but the proposal understates it. The batch loop
is *precisely* where a checkpoint would go, and v0.52.0 removed a checkpoint
mechanism from this exact function after discovering it could never run. The
next contributor sees `on_progress(batch=3, batches=7)` firing per batch and the
words "an interrupted run therefore re-processes every batch" three lines up,
and wires a resume. Then the staged-unit bug in the removed path comes back.

**Required:** a comment at the emit site stating in one sentence that this is an
observation, not a checkpoint, and that resumability is ROADMAP 6 — plus a test
that pins the all-or-nothing behaviour is unchanged (interrupt after batch 2,
assert zero published units). Without the test the comment is decoration.

### F5 — The end-to-end test the briefing demands is not in the proposal

Section 7 of the briefing says an accepted proposal *must* include a test that
runs a real job and asserts a non-zero row count. The proposal describes code
and never names that test. Given that this defect shipped because every test
asserted on the writer instead of the caller, omitting it here is the single
most likely way to repeat the failure.

**Required:** name it, and make it assert on the *number of distinct `kind`s*
and that `batch` events outnumber 1 — a test asserting `count > 0` would pass on
a sink that fires once at "spans_stored" and never again, which is most of the
bug.

### F6 — Mutation-check the new test, or it proves nothing

`test_job_events.py` already passed against a writer nothing called. The new
end-to-end test must be shown to fail against `master` before it is trusted.

## 2. Suggested Alternatives

- Keep the sink signature. It is right, and rejecting `IngestCallbacks` is
  correct for the stated reason.
- **Add P0 as a measurement phase**, not a formality: `connect()` cost per call
  and observed lock contention at realistic batch counts. Let the number decide
  whether the sink writes per event or buffers.
- Drop the `progress` float from the L2 sink (F2) and freeze `progress_total`'s
  meaning to batches for the run (F3).
- Add the anti-checkpoint test (F4) and the end-to-end test with mutation
  verification (F5, F6) to the release gates, not the nice-to-haves.
