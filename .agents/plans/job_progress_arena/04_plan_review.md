# Review of the master plan, before implementation

Date: 2026-08-18 | Agent Persona: peer_reviewer (pre-implementation pass)

Read the plan against the code it proposes to change. Two findings would have
produced a broken or vacuous release; three are corrections to stated facts.

## R1 — CRITICAL. The obvious harness for G1 mocks out the function under test

Every existing worker test patches the compile away:

```python
# backend/tests/test_v021_background_jobs.py:67, :82, :131, :143, :164, :184, :203
with patch("curator.pipeline.compile.compile_source_l2", return_value=fake_result):
    result = ingest_worker.run_next_job(self.paths, cfg.DEFAULT_CONFIG)
```

Writing G1 in that file, next to its siblings, would patch out **the exact
function that must call the sink**. The test would pass with the sink never
invoked — a green test proving nothing, which is precisely how v0.58.0 shipped.
The pull toward this mistake is strong because it is the path of least
resistance: the harness is right there and every neighbour uses it.

**Resolution — binding on P2.** G1 runs the **real** `compile_source_l2` with a
stub *LLM client*, following `test_authored_topology.py:33` (`_EmptyUnitsClient`,
a `.chat()` returning `{"units": []}`), not a patched compile. `compile_source_l2`
must appear **nowhere** in a `patch(...)` call in the new test file. Add that as
an assertion on the test source itself if necessary — this failure mode has now
occurred once and is worth pinning mechanically.

Multiple batches are made deterministic by giving the stub client
`optimal_chunk_chars = 200`: `client_optimal_chunk_chars`
(`pipeline/chunking.py:8`) reads that attribute off the client and falls back to
60,000 only when absent. A modest seeded source then yields several batches with
no large fixture.

## R2 — D7 is wrong and would degrade the main CLI surface

The plan conceded F2 and dropped the `progress` float from the L2 sink. But
`wiki jobs list` renders **only** the float:

```python
# backend/src/curator/commands/jobs.py:41-42
progress = job.get("progress")
progress_text = f"{float(progress or 0.0) * 100:.0f}%"
```

`progress_current` / `progress_total` are not in that table at all. Dropping the
float would leave the primary CLI surface frozen at **10%** for the entire L2
run — a regression against today's behaviour, delivered by a plan whose whole
purpose is making that surface informative.

**Resolution.** D7 is reversed. The L2 sink writes all three fields. The
red_teamer's actual complaint — an undocumented convention hardcoded in a second
place — is answered by writing the mapping into `SYSTEM_BEHAVIOR.md` §12 in P1,
which was always the better half of F2.

## R3 — D6 is safe, and now has evidence rather than assertion

The plan asserted that freeing `progress_total` to mean batches is harmless.
Checked both consumers:

- Plugin dashboard renders the fraction only inside `if (state === "running")`
  (`plugin/src/ui/incuratorDashboardModal.ts:1304-1309`).
- Backend `dashboard.md` builds the `cur/total` cell only from the `running`
  list (`ingest_worker.py:387-393`).

**No consumer reads `progress_total` on a finished job.** D6 stands, and the
F3 scenario ("user sees 4/7 then 11/11") cannot occur in either UI. Keep the
change anyway for coherence, but the plan should stop describing it as a
user-visible risk.

## R4 — The drop counter must not be module-level mutable state

D5 says "a module-level counter, per job". `IngestWorker` is a
`threading.Thread` (`ingest_worker.py:353`), so module-level mutable state is
shared across concurrent jobs and is a data race waiting to happen — and it
would attribute one job's drops to another.

**Resolution.** `job_events.append` returns `bool` (True when the row was
written). It currently returns `None`, so this is backward compatible for every
existing caller. The worker's `_sink` closure owns the counter. No global state,
correct per-job attribution, and the never-raise contract is untouched.

## R5 — The lightweight connection must self-heal like `connect()` does

D4 skips `connect()`, and with it `executescript(SCHEMA_SQL)` — which is what
creates `job_events` on a DB that predates the table. On such a DB the
lightweight write raises `no such table: job_events`, is swallowed, and the
feature is silently dead again.

**Resolution.** On `OperationalError` mentioning a missing table, retry once
through `connect()`. One fallback, not a loop.

## R6 — `events_dropped` can itself be dropped

If contention persists to the end of the job, the terminal event carrying the
drop count is dropped too, and the count vanishes — the failure hides its own
report.

**Resolution.** Also emit it at `logging.WARNING`, not `debug`. The log is not
transactional and does not depend on the resource that is failing.

## R7 — Minor is the correct bump, for a reason the plan states loosely

The plan justifies v0.59.0 as "new user-facing capability". `wiki jobs events`
already exists, so on capability alone this could read as a `### Fixed`-only
Patch. The bump is Minor because **D6 changes the meaning of a stored field**
(`progress_total`), which the 0.x criteria classify as a schema/contract change.
Say that in `CHANGELOG.md`, so the next reader does not re-derive it.

## Verdict

Proceed, with D7 reversed (R2), D5 restated as a return value (R4), and R1
binding on P2. R1 is the one that decides whether this release repeats the last
one.
