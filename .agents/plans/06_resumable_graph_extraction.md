# v0.63.0 Master Implementation Plan — Resumable graph extraction

Arena record: `.agents/plans/resumable_graph_arena/`
(`00_problem.md`, `A_proposal_stage_in_graph_tables.md`,
`B_proposal_batch_result_staging.md`, `02_critique_redteam.md`)

## 1. Objective

Make graph extraction survive an interruption, so a source whose graph needs
more batches than one capacity window allows can converge across runs.

Concretely: source 45 (Hartley) needs **~87** batches and currently completes
**≤3 per capacity window**, discarding them all at the end of each. After this
change a batch that has validated once is never paid for again, and 87 batches
accumulate across as many windows as it takes.

## 2. Explicit Non-Goals

- **Not** changing what the graph contains, how entities dedupe, or how
  relations are scored. A resumed run must publish byte-identical graph rows to
  a clean run.
- **Not** making a failed batch retryable across the `agy` shell-out class
  (ROADMAP 5b) — that is a separate cause with a separate fix.
- **Not** touching `persist_graph_data`, the publish transaction, or the atomic
  flip. They already work; this plan feeds them the same input more cheaply.
- **Not** parallelising batches.

## 3. Strict Quality Conditions & Release Gates

- `scripts/backend-check pytest`, `ruff`, `mypy` clean before each phase ends.
- `npx vitest run -c ./plugin/vitest.config.ts` green (no plugin change expected;
  the gate stays because the version bump touches plugin manifests).
- A migration test proves an existing vault DB upgrades without data loss.
- **Live validation is a release gate, not optional.** The change is unfalsifiable
  by unit tests alone — see D2. Source 45 must show reuse across two runs.

## 4. Locked Design Decisions (Arena Consensus)

**D1 — Stage the batch payload in a side table, never in the graph tables.**
Proposal B. `graph_entities` is globally deduplicated under
`UNIQUE(canonical_name, entity_type)`; staging into it would mean UPDATEing rows
owned by other sources before the publish gate, which is the §26.3 violation the
current in-memory design exists to prevent. The graph tables, the unique index,
`persist_graph_data`, and every graph reader are untouched.

**D2 — The staging write commits in its OWN transaction, and the compile error
path must never delete it.** This is the exact failure that made v0.62.0
worthless on its own: `compile.py` deleted the staged rows, and all 19 unit tests
passed because none reached that handler. **The test for this must roll the outer
transaction back and then assert the row survives.** A test that only asserts
"the row was written" passes against the broken implementation.

**D3 — The resume key is `input_hash`, computed by the same `render_prompt` the
run uses.** `render.render_prompt(contract, input_obj)` is pure and already
returns `input_hash` (`render.py:78`), so the cache hit is provably the same
rendered prompt, not a heuristic match on batch index or content length.

**D4 — A cache miss is correct; a SILENT cache miss is the defect.** Batch
boundaries are cut at `client_optimal_chunk_chars`, so a provider failover
resizes every batch and misses all 87 keys. Unit ids can likewise shift if
v0.62.0's release-and-adopt fails. Both are legitimate misses that re-pay in
full. Every run therefore logs `reused N/M, extracted K`, and when staged rows
exist for the source but **none** matched, logs that explicitly with the chunk
size recorded at stage time versus the current one.

**D5 — Payloads round-trip through the pydantic model's own serializer.**
`model_dump_json()` / `model_validate_json()`, never hand-rolled dicts. A dropped
optional field would make a resumed run publish a different graph than a clean
one, with nothing to flag it. The round-trip test uses a fully populated
instance, not an empty one.

**D6 — Only validated results are staged, and staged rows are deleted on
publish.** The existing `result.ok and result.parsed is not None` gate decides
what is cacheable, so a refusal or a validation failure is never cached. Rows for
a source are deleted inside the publish transaction once the flip succeeds, and
when the source is removed.

## 5. Scope Exclusions & Stop Conditions

- **STOP if `input_hash` proves unstable across two consecutive clean runs of the
  same unpublished source.** Resume is worthless if the key moves on its own.
  Verify this FIRST, in P0, before any schema work — the same class of stop
  condition fired on plan 05 and cost a release.
- **STOP if staging measurably slows a clean run.** One indexed lookup and one
  insert per batch against ~87 batches must be lost in the noise of an 8–12 s
  provider round-trip; if it is not, the design is wrong.
- Out of scope: ROADMAP 5b (agy shell-out), ROADMAP 11 (workspace ingest scope).

## 6. Evidence Ledger

`.agents/plans/06_resumable_graph_evidence.md`, created immediately before P1
coding starts. Records the rollback anchor (`git rev-parse HEAD`), the current
`db.SCHEMA_VERSION`, the pre-change batch counts for source 45, and the post-
change reuse measurement.

## 7. Execution Phases (Follow TDD and CI at each phase)

**P0 — Prove the key is stable. DONE 2026-08-22, PASSED.** `render_prompt` is
pure, so this was verified with **zero provider calls**: rebuild the batches from
the live DB and compute `input_hash` per batch in two separate processes.

Landed on Hartley itself — `04_Resources/References/MultipleViewGeometryHartley
- .md`, **5,358 units, 8,905 spans, 72 batches** at the live 18,000-char chunk
size. All 72 hashes **identical across processes** and **72/72 distinct**, so the
key neither drifts nor collides.

Two corrections to the briefing from this measurement:

- The batch count is **72, not ~87**. The ROADMAP figure divided total prompt
  chars by chunk size; real batching packs whole units and does better.
- At ≤3 usable batches per capacity window, 72 still cannot converge in one run,
  so the conclusion is unchanged — only the arithmetic is.

**P1 — Schema and DB helpers.** `graph_batch_results` table + migration,
`db.get_graph_batch_result` / `put_graph_batch_result` / `delete_graph_batch_results`.
*Verify:* migration test on a pre-change DB; **D2's rollback-survival test**;
D5's round-trip test.

**P2 — Resume in `extract_graph_data`.** Lookup before `run_prompt`, stage after
a validated result, D4's logging.

**P2 must first add `, id` to `list_generation_units`' ORDER BY.** It orders by
`created_at` alone, and `created_at` has one-second granularity: measured on
source 45, **all 5,358 units sit in tie groups** (279 distinct timestamps,
largest group 57). Tie order is decided by SQLite's sorter rather than by the
query. It measured stable across a `generation_id` re-stamp and a `VACUUM`, but
SQLite does not document its sorter as stable, so the resume key currently rests
on an implementation detail. If the plan ever changes, batch boundaries move and
every hash from the first divergence onward misses — a silent full re-pay.
*Verify:* a test that interrupts after batch 2 of 4 and asserts the resumed run
issues exactly 2 provider calls and produces the same `GraphData` as an
uninterrupted run.

**P3 — Cleanup.** Delete on publish (inside the publish transaction) and on
source removal; `wiki` subcommand to clear one source's staged batches.
*Verify:* publish leaves zero rows; a cleared source re-extracts.

**P4 — Docs and specs.** `SCHEMA.md` (new table), `SYSTEM_BEHAVIOR.md` (resume
semantics), the guides, and their `_KR.md` counterparts. **0.62 → 0.63 changes
the minor line, so all four spec titles bump to `v0.63.x`** and
`test_spec_sync.py` must pass.
*Verify:* `scripts/backend-check pytest backend/tests/test_spec_sync.py`.

**P5 — Live validation (release gate).** Run source 45 across two capacity
windows. Record batches completed in run 1, batches reused in run 2, and confirm
the reuse count equals run 1's completed count.
*Verify:* `reused N/M` in the log matches the prior run's completions.
