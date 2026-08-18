# Defense: F1 measured, and it changes the design

Date: 2026-08-18 | Agent Persona: lead_architect (responding), with schema_guardian

The red_teamer refused to accept a guess on write cost and lock behaviour. The
numbers were taken before any implementation, on a real `state.sqlite` created
by `db.init_db`.

## 1. Cost of the sink, uncontended

| operation | ms/call |
|---|---|
| `connect()` alone (no query) | **1.31** |
| `job_events.append` (via `connect()`) | **1.79** |
| proposed sink = append + `update_job_progress` (two `connect()`s) | **3.39** |

Total sink overhead for a 200-batch book: **0.68 s**. Each batch is one LLM
call taking seconds. **F1's cost objection does not survive the measurement** —
the overhead is on the order of 0.1% and the proposal's per-batch write stands.

Note what `connect()` spends that 1.31 ms on: `PRAGMA journal_mode=WAL`,
`PRAGMA foreign_keys=ON`, `executescript(SCHEMA_SQL)` — the **entire schema, on
every call** — a trigger-refresh check, and a version stamp. For an event
writer that is a lot of ceremony, and `executescript` issues an implicit COMMIT
and takes a write lock. That matters for the next number.

## 2. Behaviour under contention — F1's real charge, and it lands

Held an open `BEGIN IMMEDIATE` write transaction and fired one append:

```
append while write lock held:   5.23 s elapsed, rows=0
  -> SILENTLY LOST
```

**Both halves are bad.** SQLite's default `timeout` is 5 s, so the job stalls
for five seconds *and then the event is discarded* by the `except Exception`
guard. At 200 batches a pathological run would burn **17 minutes blocking to
lose every event** — and report nothing, because the guard is silent by design.

That is not a hypothetical inherited from the old code: it is the failure mode
this plan exists to remove, reintroduced by the plan itself. F1 is upheld.

## 3. The fix, also measured

Give the event writer its own lightweight connection: no `executescript`, no
trigger refresh, short busy timeout.

| | ms/call | under a held write lock |
|---|---|---|
| via `connect()` | 1.79 | blocks **5.23 s**, then silently loses |
| lightweight, `timeout=0.25` | **1.17** | raises `OperationalError` after **0.29 s** |

Cheaper *and* it fails fast instead of stalling the job. The write it was
skipping — re-running the whole schema — was never needed: `append` is only
reachable for a job that already exists, which means `init_db` has already run.

## 4. Failing fast is only an improvement if someone hears it

A fast failure that is still swallowed is a silent failure that wastes less
time. So the guard keeps its contract — an event must never fail the job — but
stops being silent about it:

- `append` counts drops in a module-level counter, per job.
- The worker's terminal `done` event carries `events_dropped: N`.
- `wiki jobs events` prints a line when `N > 0`: *"N event(s) were dropped
  (database contention); the history below is incomplete."*

An observability feature that cannot report its own failure is the bug being
fixed. This closes it against the whole class, not just today's instance.

## 5. Conceded to the red_teamer without argument

- **F2** — the `progress` float. Conceded. The L2 sink writes
  `progress_current` / `progress_total` only. The phase→float convention gets
  written into `SYSTEM_BEHAVIOR.md` §12 in P1 rather than being hardcoded in a
  second place.
- **F3** — `progress_total` meaning. Conceded. It means **batches** for the
  whole L2 run and the post-compile write at `ingest_worker.py:219` stops
  overwriting it with the atom count. Atoms created already live in
  `pages_created` via `mark_job_done`, which is where a reader should get them.
- **F4** — checkpoint confusion. Conceded in full, including the test. A comment
  alone is decoration.
- **F5 / F6** — the end-to-end test and its mutation check. Conceded and
  promoted to release gates.

## 6. Residual risk, stated rather than resolved

Nothing is emitted *within* a single batch. A single hung LLM call produces
twenty minutes of silence in the history. This is still a large improvement —
the previous event's timestamp localises the stall to one identified batch,
where today the whole L2 phase is one opaque block — but it is a heartbeat
between calls, not during one. Sub-batch progress would require a streaming
callback through the LLM client and is explicitly out of scope.
