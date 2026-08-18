# Evidence Ledger — v0.59.0 job progress observability

Date: 2026-08-18 | Plan: `.agents/plans/06_job_progress_observability.md`

## Rollback anchor

- `master` at `0c0ebeb` (v0.58.0 merged as `ec60bb5`).
- Branch: `feature/v0.59.0-job-progress`.
- No schema migration. `job_events` already existed with the right columns, so a
  revert is a code revert with nothing to undo in any database.

## Pre-change reality (measured, not assumed)

Live vault `second_brain`, DB at `.cache/vaults/13ed51f8b06cb88e/state.sqlite`:

- 36 L2 jobs queued 2026-08-18. Jobs 42 and 43 completed (`5/5`, `11/11`) with
  `SELECT COUNT(*) FROM job_events` = **0**.
- `job_events.append` traced with a wrapper and one job re-run in the
  foreground: **never called**.
- A direct `append` against the same DB and job id inserted fine, ruling out a
  lock, a foreign-key failure, and a wrong `state_db` path.

Write costs, on a real `init_db` database:

| operation | ms/call |
|---|---|
| `connect()` alone | 1.31 |
| `append` via `connect()` | 1.79 |
| append + `update_job_progress` (two `connect()`s) | 3.39 |
| lightweight append (`timeout=0.25`, no schema setup) | **1.17** |

Under a held `BEGIN IMMEDIATE` write lock:

| path | result |
|---|---|
| via `connect()` | blocks **5.23 s**, then **silently loses the row** |
| lightweight | raises `OperationalError` after **0.29 s**, visibly |

## Gate results

| gate | result |
|---|---|
| G1 real L2 job leaves a history | PASS; **fails on `master`** (mutation-verified) |
| G2 extraction stayed all-or-nothing | PASS |
| G3 a dropped event is reported | PASS; **fails on `master`** |
| G4 overhead / fast failure | PASS (1.17 ms; 0.29 s under lock) |
| G5 full suite, ruff, mypy | PASS — **1595 passed**, 6 skipped, 4 xfailed |
| G6 docs | see the PR |

`compile_source_l2`'s existing call sites were not modified: `on_progress`
defaults to `None`.

## P7 — live acceptance, the gate v0.58.0 skipped

Job 62 (`...Silhouette Based Reconstruction.md`) run against the live vault with
the branch code. Verbatim `wiki jobs events 62`:

```
2026-08-18T07:34:09Z    1  status     phase=l2 stage=spans_stored spans=156
2026-08-18T07:34:53Z    2  extracted  phase=l2 batch=1 batches=3 units=32
2026-08-18T07:35:53Z    3  extracted  phase=l2 batch=2 batches=3 units=65
2026-08-18T07:39:20Z    4  extracted  phase=l2 batch=3 batches=3 units=105
2026-08-18T07:39:21Z    5  status     phase=l2 stage=publishing units=105
2026-08-18T07:39:47Z    6  done       pages_created=30 pages_updated=0 events_dropped=0
```

```
job row: state=done phase=done progress=1.0 progress_current=3
         progress_total=3 pages_created=30
```

Read the timestamps: batch 1 took 44 s, batch 2 took 60 s, **batch 3 took 3 m
27 s** — 3.5× the others. Before this change that entire 5½-minute stretch was
one row reading `0/1`, and a job that had died would have looked identical.
That difference is the whole deliverable.

`events_dropped=0` on a real run confirms the drop counter is not firing
spuriously.

## Two pre-existing defects found on the way, deliberately NOT fixed here

Both reproduce on `master` with no local changes; a spawned task tracks them.

1. **`claim_next_job` can never claim a job on a freshly-created state DB.**
   `connect()` runs `_stamp_schema_version`, whose `INSERT` opens an implicit
   transaction that is not committed until `connect()` exits; `claim_next_job`
   then issues `BEGIN IMMEDIATE` inside it and raises `cannot start a
   transaction within a transaction`. The exception skips the commit, so the
   schema write rolls back and the next call fails identically — an infinite
   failure loop, not a transient one. Rarely seen because `init_db` normally
   commits first.

2. **A small client context window produces a negative chunk size.**
   `knowledge_units.py:348` computes `chunk_size=max_chars - 500`; any
   `optimal_chunk_chars` below 500 goes negative. Measured: at `200`, an
   eight-section document produced **1,148 batches**. Latent (real clients
   default to 60,000) but it fails by doing enormous work rather than erroring.

## Method note

The live run needed the real vault DB, but the repo cache resolves from the
running code's own location (`config.py:354`, `Path(__file__).parents[3]`), so a
worktree run silently creates a **new empty** database. `get_global_config_dir`
was therefore redirected for the live run only. Nothing under test — sink,
compile, worker, `job_events` — is affected by where the cache directory
resolves. Worth knowing before the next person tries to test a worktree against
a real vault and concludes their feature does nothing.
