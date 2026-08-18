# v0.59.0 Master Implementation Plan — L2 job progress that a reader can act on

Date: 2026-08-18
Status: APPROVED — Arena debate concluded, measurements taken, pre-implementation
review applied (D7 reversed, D5 restated, D9 added, G1 constrained).

Arena record: `.agents/plans/job_progress_arena/`
(`00_problem.md`, `01_proposal_lead_architect.md`, `02_critique_redteam.md`,
`03_defense_measured.md`, `04_plan_review.md`)

## 1. Objective

Make `wiki jobs list` and `wiki jobs events <id>` answer one question for an L2
job: **is this working or has it stopped?**

Definition of done, all three required:

1. A real `wiki build` L2 job leaves **more than one** `job_events` row, with at
   least two distinct `kind`s, and the per-batch events outnumber one.
2. `progress_current/progress_total` advances **during** L2, not only at its
   two endpoints.
3. If any event is dropped, the job's own history says so. Observability that
   cannot report its own failure is the defect being fixed.

Verified by running a job. A unit test on the writer is not evidence that
anything calls it — that is precisely how v0.58.0 shipped broken.

## 2. Explicit Non-Goals

- **Not resumability.** `extract_knowledge_units` stays all-or-nothing. Emitting
  an event is not committing a checkpoint. ROADMAP 6 owns resumable L2 and is
  untouched here; v0.52.0 removed a checkpoint mechanism from this exact
  function and the staged-unit hazard in that removal is not being reopened.
- **Not sub-batch progress.** One event per LLM call, not during one. Streaming
  callbacks through the LLM client are out of scope.
- **Not an ETA.** Batch counts are counts, not time. `3/7` means three of seven
  calls returned.
- **Not a `WorkerCallbacks` rehabilitation.** The legacy L3 path keeps using it;
  this plan does not migrate or delete it.
- **No schema change.** `job_events` already exists with the right columns.
- **Not the vision loop.** v0.58.0's per-page printing works and is verified.

## 3. Strict Quality Conditions & Release Gates

- **G1.** An end-to-end test runs a queued L2 job through `run_next_job` with a
  stub client and asserts `job_events` rows > 1, ≥ 2 distinct `kind`s, and
  ≥ 2 `extracted` events. **Mutation-verified**: must fail against `master`.
  **Binding constraint (review R1): the test must NOT patch
  `compile_source_l2`.** Every existing worker test does
  (`test_v021_background_jobs.py:67, 82, 131, 143, 164, 184, 203`), and doing so
  here would mock away the exact function that must call the sink — a green test
  proving nothing, which is how v0.58.0 shipped. G1 runs the real compile with a
  stub **LLM client** (`test_authored_topology.py:33` `_EmptyUnitsClient`).
  Multiple batches are forced deterministically with `optimal_chunk_chars = 200`
  on the stub, read by `pipeline/chunking.py:8`. The word `compile_source_l2`
  must not appear inside any `patch(...)` in the new test file.
- **G2.** A test pins all-or-nothing extraction is unchanged — interrupt after
  batch 2 of N, assert zero published knowledge units for that source.
- **G3.** A test pins that a dropped event is reported: force contention, assert
  the terminal event carries a non-zero `events_dropped` and the CLI says so.
- **G4.** Sink overhead stays under 5 ms/batch (measured baseline: 1.17 ms
  lightweight, 3.39 ms via `connect()`), and a contended write fails in under
  1 s rather than blocking on SQLite's 5 s default.
- **G5.** `scripts/backend-check pytest | ruff | mypy` all green; plugin vitest
  green. `compile_source_l2`'s 21 existing test call sites unmodified.
- **G6.** Docs updated before merge: `SYSTEM_BEHAVIOR.md` §12,
  `WORKFLOW_GUIDE.md` + `_KR.md`, `USER_GUIDE.md` + `_KR.md`, `CHANGELOG.md`.

## 4. Locked Design Decisions (Arena Consensus)

**D1 — A one-verb sink, not `IngestCallbacks`.**
`ProgressSink = Callable[[str, dict[str, object]], None]`. `IngestCallbacks` has
fourteen methods built for the interactive L1 flow; importing it into a batch
compiler would force every test double to grow fourteen no-ops.

**D2 — Optional keyword argument, `None` default.**
`compile_source_l2(..., *, on_progress: ProgressSink | None = None)`. Load-bearing:
21 call sites in `test_authored_topology.py` plus `ingest_llm.py:545` stay
untouched.

**D3 — The signal comes from the batch loop.**
`knowledge_units.py:382` already computes `f"batch {index}/{len(batches)}"` for
its retry label. Nothing new is measured; existing information stops being
thrown away.

**D4 — The event writer gets its own lightweight connection.** Measured: going
through `connect()` costs 1.79 ms and re-runs `executescript(SCHEMA_SQL)` every
call, taking a write lock to write an event. A direct connection with
`timeout=0.25` costs 1.17 ms and, under a held write lock, fails in 0.29 s
instead of blocking 5.23 s and then silently discarding the row.

**D5 — Drops are counted and surfaced (revised by review R4).** `append` keeps
its never-raise contract and **returns `bool`** — True when the row was written.
It returns `None` today, so every existing caller is unaffected. The worker's
`_sink` closure owns the counter; there is **no module-level mutable state**,
because `IngestWorker` is a `threading.Thread` and a shared counter would race
and misattribute one job's drops to another. The terminal `done` event carries
`events_dropped`, and the count is also logged at WARNING (review R6: if
contention persists, the event carrying the count is itself droppable, and the
log does not depend on the resource that is failing). `wiki jobs events` prints
an incomplete-history line when the count is non-zero.

**D6 — `progress_total` means batches for the whole L2 run.** The post-compile
write at `ingest_worker.py:219` stops overwriting it with the atom count. Atoms
created already live in `pages_created` via `mark_job_done`. Verified safe
(review R3): both consumers render the fraction only for a **running** job —
`incuratorDashboardModal.ts:1304` and `ingest_worker.py:387` — so no consumer
reads `progress_total` on a finished job and F3's "4/7 then 11/11" cannot occur.

**D7 — REVERSED by review R2. The L2 sink writes the `progress` float too.**
The original concession to F2 was wrong: `wiki jobs list` renders **only** the
float (`commands/jobs.py:41-42`); `progress_current`/`progress_total` are not in
that table. Dropping it would freeze the primary CLI surface at 10% for the
whole L2 run — a regression delivered by the plan meant to fix that surface. The
sink writes all three fields, and F2's real complaint (an undocumented
convention hardcoded twice) is answered by writing the phase→float mapping into
`SYSTEM_BEHAVIOR.md` §12 in P1.

**D9 — The lightweight connection self-heals once (review R5).** Skipping
`connect()` also skips `executescript(SCHEMA_SQL)`, which is what creates
`job_events` on a DB predating the table. On an `OperationalError` naming a
missing table, retry once through `connect()`. One fallback, not a loop.

**D8 — Guard at the call site.** `_emit()` wraps the sink in try/except because
a sink is caller-supplied and the compiler must not inherit its bugs.
`job_events.append` keeps its own guard as defence in depth.

## 5. Scope Exclusions & Stop Conditions

**Exclusions.** ROADMAP 6 (resumable L2), ROADMAP 1 (formula recovery),
sub-batch streaming, migrating the legacy L3 `WorkerCallbacks`, and the
`wiki add --help` "without an LLM call" text — all tracked separately.

**Stop conditions — halt and ask the user:**

- G1's test passes against `master` (it would prove the test is vacuous, which
  is the v0.58.0 failure repeating).
- Threading `on_progress` requires changing any of the 21 existing
  `compile_source_l2` call sites.
- G2 fails — i.e. the change altered publication semantics. Revert immediately;
  a progress feature must not touch durability.
- Measured overhead exceeds 5 ms/batch.

## 6. Evidence Ledger

To be written as `.agents/plans/06_job_progress_evidence.md` immediately before
coding. Pre-recorded here:

- **Rollback anchor**: `master` at `98c70d7` (v0.58.0 merged as `ec60bb5`).
- **Schema reality**: `job_events` exists with `id, job_id, seq, kind, data, at`
  and `FOREIGN KEY (job_id) REFERENCES ingest_jobs(id)`; index
  `idx_events_job_seq(job_id, seq)`. **No migration needed.**
- **Live-vault baseline**: 36 L2 jobs queued 2026-08-18; jobs 42 and 43 done at
  `5/5` and `11/11` with `job_events` at 0 rows. `append` traced and confirmed
  never called.
- **Measured costs**: `connect()` 1.31 ms; `append` via `connect()` 1.79 ms;
  proposed two-connection sink 3.39 ms; lightweight append 1.17 ms. Under a held
  write lock: 5.23 s then silent loss vs 0.29 s visible failure.
- **Dirty worktree**: clean at plan time; a `wiki jobs run` daemon is draining
  the queue against the live vault and must be stopped before any test run that
  touches that DB.

## 7. Execution Phases

Each phase passes `pytest` + `ruff` + `mypy` before the next begins.

- **P0 — Baseline, already done.** Costs and contention measured (§6). Remaining
  P0 item: capture the current `job_events` row count for a control job so the
  end-to-end test's mutation check has a recorded before-value.
- **P1 — Contract first, STOP for approval if it widens further.**
  `SYSTEM_BEHAVIOR.md` §12 gains: the `ProgressSink` contract, the event
  vocabulary, `progress_total` meaning batches during L2 (D6), the phase→float
  convention (D7), and the dropped-event reporting rule (D5).
- **P2 — Failing tests first (TDD).** Write G1, G2, G3. Run them against
  `master` and record that G1 and G3 fail. **If G1 passes here, stop.**
- **P3 — The sink.** `ProgressSink` alias, `_emit`, `on_progress` threaded
  through `compile_source_l2` → `extract_knowledge_units`, emit at the batch
  loop and the two compile boundaries. Anti-checkpoint comment at the emit site
  (D-F4).
- **P4 — The writer.** Lightweight connection for `append` (D4), drop counter
  and `events_dropped` on the terminal event (D5). Symmetric `done` event on the
  source-L2 success path, which today has none while the global-L3 path at
  `ingest_worker.py:184` does.
- **P5 — The worker wiring.** `run_next_job` supplies `_sink`; per-batch
  `progress_current/progress_total`; stop overwriting `progress_total` at `:219`.
- **P6 — CLI.** `wiki jobs events` renders the incomplete-history line.
- **P7 — Live acceptance.** Stop the daemon, queue one real L2 job against
  `second_brain`, run it, and paste the actual `wiki jobs events` output into
  the evidence ledger. **This phase is the point of the plan** — v0.58.0 had
  every other phase and skipped this one.
- **P8 — Docs, version bump, CHANGELOG, PR.** Minor → **v0.59.0**, and all four
  spec titles to the `v0.59` line. The bump is Minor because **D6 changes the
  meaning of a stored field** (`progress_total`) — a contract change under the
  0.x criteria — not merely because a surface got better. `wiki jobs events`
  already existed, so on capability alone this would read as a `### Fixed`-only
  Patch (review R7). Say the reason in `CHANGELOG.md`.

## 8. Note on how this plan came to exist

v0.58.0 closed ROADMAP 8 on unit tests that call `job_events.append` directly
and a code path that no L2 job executes. Every test was green; the feature had
never run. The gate that would have caught it is P7, and it costs one job.
