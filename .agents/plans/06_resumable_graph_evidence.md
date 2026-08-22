# Evidence Ledger — v0.63.0 resumable graph extraction

Master plan: `.agents/plans/06_resumable_graph_extraction.md`

## Rollback anchor

| | |
|---|---|
| branch | `release/v0.63.0` |
| base commit | `6907b3c` (master) |
| revert | `git checkout master && git branch -D release/v0.63.0` |

Nothing has been merged, so rollback is deleting the branch. Once a PR merges,
`git revert -m 1 <merge-sha>` per the repo's rollback procedure.

## Schema reality BEFORE the change

| | |
|---|---|
| `db.SCHEMA_VERSION` | **13** |
| graph tables | `graph_entities` (no `generation_id`), `graph_relations` (has one) |
| entity uniqueness | `UNIQUE(canonical_name, entity_type)` — globally deduplicated |
| staging mechanism | **none**; `extract_graph_data` holds everything in memory |
| `prompt_runs` | records `output_hash` only — the output itself is NOT recoverable |

Live counts on the reference vault (`.cache/vaults/13ed51f8b06cb88e/state.sqlite`):

| table | rows |
|---|---|
| `source_spans` | 11,461 |
| `knowledge_units` | 2,737 |
| `graph_entities` | 1,305 |
| `graph_relations` | 1,198 |
| `community_reports` | 255 |

## P0 — resume-key stability (PASSED on the SECOND attempt; the first measured the wrong input)

**The first P0 run verified something production does not do.** It ordered units
`ORDER BY id` and fed **all** of the source's units to the batcher.
`compile.py` feeds `list_generation_units`, which is
`WHERE generation_id = ? AND retired_at IS NULL AND support_status = 'verified'
ORDER BY created_at`. Different order, different unit set. The green result was
real but it was not evidence about the production path — the same class of
mistake as mutation-testing a handler the test never reaches.

### Corrected measurement

Run against a **copy** of the live DB, using the production filter and ordering,
re-stamped with a fresh `generation_id` between the two runs to imitate a resume:

| | |
|---|---|
| live units on source 45 | 5,358 — **3,322 `unchecked`, 1,958 `verified`, 78 `failed`** |
| units graph extraction actually sees | **1,958** (verified only) |
| prompt chars, verified only | 414,021 |
| **batches** | **24** |
| hashes stable across a NEW `generation_id` | **yes** |
| distinct hashes | **24 / 24** |

### The batch count, stated honestly this time

It has now been wrong twice: **~87 → 72 → 24**, because each figure measured a
different unit set. The defensible statement is a *range*, not a number:

- **24** is the count for the DB **as it stands**, where 3,322 units are
  `unchecked` — they belong to runs that died before `validate_claim_support`
  reached them.
- A run that completes validation would verify most of those. At the observed
  verified rate among *checked* units (1,958 / 2,036 ≈ 96%), a fully validated
  source 45 lands near **68** batches; all 5,358 units unfiltered would be 71.
- So the converged count is **between 24 and ~71**, and no single number should
  be quoted as measured until a run actually completes validation.

This does not change the design. It does change the urgency argument: at ≤3
usable batches per capacity window, 24 needs 8 windows and 68 needs 23 — still
unreachable in one run, which is the whole premise, but not by the margin the
ROADMAP claimed.

### Residual fragility found while measuring (fix in P2)

`list_generation_units` orders by `created_at` with **no `id` tiebreaker**, and
`created_at` has one-second granularity: **all 5,358 units sit in tie groups**
(279 distinct timestamps, largest group 57). Tie order is therefore decided by
SQLite's sorter, not by the query.

Measured stable across a re-stamp of `generation_id` and across `VACUUM`, and the
plan is `SEARCH … USING INDEX idx_knowledge_units_generation` + `USE TEMP B-TREE
FOR ORDER BY`. But SQLite does not document its sorter as stable, so this rests
on an implementation detail. If the plan ever changes, tie order shifts, batch
boundaries move, and **every hash from the first divergence onward misses** —
a silent full re-pay. Adding `, id` to the ORDER BY makes it deterministic by
construction. **P2 should do this before relying on the key.**

## P0 — original (superseded) measurement

Verified with **zero provider calls**: `render_prompt` is pure, so batches were
rebuilt from the live DB and hashed in two separate processes.

| | |
|---|---|
| source | `04_Resources/References/MultipleViewGeometryHartley - .md` |
| units | 5,358 |
| spans | 8,905 |
| chunk size | 18,000 chars |
| **batches** | **72** (the ROADMAP's "~87" divided total chars by chunk size and overcounted) |
| hashes identical across processes | **yes** |
| distinct hashes | **72 / 72** |

The key neither drifts nor collides. First three: `b0e9892e9d4c30ef`,
`c4400dfa200bdc66`, `92714df22e148187`.

## P1 — schema and DB helpers

**Changed**

- `db/schema.py` — new `graph_batch_results` table + unique index on
  `(source_id, input_hash)`, `FOREIGN KEY … ON DELETE CASCADE`.
  `SCHEMA_VERSION` **13 → 14**.
- `db/_entities.py` — `put_graph_batch_result`, `get_graph_batch_result`,
  `count_graph_batch_results`, `delete_graph_batch_results`.

**Migration**: additive only. `SCHEMA_SQL` is re-executed by both `init_db` and
`connect`, so an existing vault gains the table on the next connection with no
data movement. Covered by
`test_the_table_appears_on_a_database_that_predates_it`.

**Asymmetric connection handling, on purpose.** `put_…` takes **no** `conn`
parameter — joining a caller's transaction would roll the row back with the
failure it exists to survive. `delete_…` **does** take one, because deletion must
happen inside the publish transaction so staged rows disappear exactly when the
generation becomes authoritative.

### Validation

`backend/tests/test_graph_batch_results.py` — **12 passed**.

**Mutation-checked.** Replacing the committing `connect()` with a raw connection
that never commits was caught by **7 tests**, including both D2 tests
(`test_the_write_is_committed_immediately`,
`test_a_staged_batch_survives_the_compiles_rollback`). The tests are load-bearing,
not decorative.

**Gap recorded honestly:** D2 has two halves. Half (a) — the write must not join
the caller's transaction — is tested and mutation-verified here. Half (b) — *the
compile's error handler must not DELETE the rows*, which is what made v0.62.0
worthless — **cannot be tested yet**, because the compile integration does not
exist until P2/P3. A test that rolls back the real compile path is a P3
deliverable and must not be skipped there.

`ruff` clean, `mypy` clean (130 source files).

### The version bump had consequences worth recording

`SCHEMA_VERSION` 13 → 14 broke **7 tests** that the P1 unit tests did not touch.
The bump is nonetheless correct, checked against the spec rather than assumed:
`SCHEMA.md`'s version history bumps for **any** DDL change, not only for changes
to the export format — v6 bumped for search tables that are excluded from export,
and v13 bumped while stating "the SQLite table shape is unchanged".

Consequence, recorded because it is real: `db_sync.py:974` **rejects an export
whose `schema_version` differs from local**. Devices that upgrade at different
times stop syncing until both are on v14. The export *format* is unchanged —
`graph_batch_results` is absent from the `SYNC_TABLES` allowlist — so this is a
version-stamp break, not a shape break.

What the 7 failures were:

| test | what it was |
|---|---|
| `test_schema_version_is_13` | the intentional pin — renamed, now asserts 14 |
| `test_spec_declares_matching_schema_version` | fixed by updating `SCHEMA.md` |
| `test_schema_v13_is_the_composite_tombstone_boundary` | a **redundant** second pin of the same integer; changed to assert the floor (`>= 13`) and renamed, since an additive table has no business failing a tombstone test |
| `test_v12_database_is_stamped_v13_…` | incidental literal → `db.SCHEMA_VERSION` |
| `test_fresh_v13_sources_schema_…` | incidental pin removed; the test is about portable columns |
| `test_the_frozen_evaluated_files_are_untouched` | the D2 drift tripwire |
| `test_d2_holdout_result_is_single_run_frozen_…` | same |

**The D2 tripwire was re-armed, not silenced.** `D2_HOLDOUT_RESULT.yml` freezes a
retrieval evaluation against content hashes of the code that produced it, with a
documented `*_rearm` procedure: record the prior hash and argue the change cannot
affect the metric. Only `db/schema.py` and `db/_entities.py` drifted; all seven
files the holdout actually exercises still match, as do `db/__init__.py`,
`db/jobs.py`, `db/sources.py`. The new table is absent from the search
projection, so the FTS5 corpus is byte-identical.

### Dead code noticed, not touched

`db_sync.EXCLUDE_TABLES` (`db_sync.py:71`) is referenced **nowhere** in the
backend. It reads as the denylist a new machine-local table should be added to,
but the exporter uses the `SYNC_TABLES` allowlist instead, so adding to it would
accomplish nothing. Left alone per the surgical-changes rule; worth a separate
cleanup.


## P2 — resume inside `extract_graph_data`

**Changed**

- `db/_entities.py` — `list_generation_units` now orders by `created_at, id`.
- `pipeline/graph_index.py` — `extract_graph_data` looks a batch up by
  `input_hash` before calling the provider, stages a validated result
  immediately, and logs what it reused. New `_parse_staged_payload` rebuilds a
  staged batch through the contract's own `output_model`.

**The source id is DERIVED, not passed.** Every unit row already carries
`source_id`, and a generation belongs to exactly one source, so a parameter would
only add a way to pass the wrong one. Units spanning several sources disable
resume with a warning; units with no `source_id` — the back-compat wrapper and
older tests — simply do not stage.

**Staging is best-effort and never fails a good extraction.** If the cache write
throws, the run continues and logs it: the cost of losing the row is one re-paid
batch next time, not a failed compile.

**An unreadable staged payload re-extracts rather than publishing.** A row
written under an older contract shape would otherwise put a graph into the
publish transaction that nothing can account for.

### The ordering fix was not cosmetic

`list_generation_units` ordered by `created_at` alone, and every one of source
45's 5,358 units sits in a tie group (279 distinct timestamps, largest 57).
Tie order was decided by SQLite's sorter. A unit test with three units sharing one
timestamp returned them in **insertion order** before the fix — so the hazard is
real, not theoretical, and a reorder would move every batch boundary and miss
every cached batch from the first divergence onward.

### Validation

`backend/tests/test_graph_resume.py` — **7 passed**; 30 passed across the three
related files.

| behavior | measurement |
|---|---|
| a fully staged source | **0 provider calls** on the second run |
| interrupted after batch 1 of 2 | resumed run makes **exactly 1** call |
| a refused batch | **not** staged (D6) |
| a validated batch | staged as it completes |

**Mutation-checked.** Disabling the cache hit (`if cached is not None` →
`if False`) fails the two resume tests; removing the total-miss warning fails the
loud-miss test. `ruff` and `mypy` clean.

### D2's second half — still open, and now checked

`compile.py`'s failure path releases staged **units** only
(`_release_staged_units_for_resume`); nothing deletes `graph_batch_results`. So
the rows survive a failed compile today. **P3 adds delete-on-publish, which is
the code that could over-delete**, and the test that rolls the real compile back
and asserts the staged batches survive belongs there. Do not skip it.


## P3 — cleanup, and D2's second half

**Changed**

- `pipeline/compile.py` — `db.delete_graph_batch_results(..., conn=conn)` inside
  the publish transaction, immediately after `_publish_generation`.
- `commands/sources.py` — `wiki source clear-graph-cache <id>`.

### `conn=conn` is load-bearing for TWO reasons, one of them measured

Semantically, a delete that committed on its own would destroy the resume that a
rolled-back publish still needs. **Mechanically, the publish transaction holds
the write lock**: dropping `conn=conn` was measured to fail **12 tests on SQLite
busy-timeouts** — an 86-second run — not on a wrong result. The comment records
both, because the second is invisible from reading the code.

### D2's second half is now tested, not just asserted

The plan flagged this as the thing not to skip, because it is exactly what made
v0.62.0 worthless: that release moved L2 extraction into rows and the compile's
failure handler deleted those rows, with all 19 unit tests passing because none
reached the handler.

`test_a_failed_publish_keeps_the_staged_graph_batches` drives the **real
compile**, fails it at the publish gate — after extraction has staged — and
asserts the rows survive. It passed on the first run, confirming the failure path
(`_release_staged_units_for_resume`) touches units only. It stays as the
regression guard now that a delete exists to be misplaced.

### The escape hatch closes a real trap

Only validated results are staged, so a refusal cannot be cached. The remaining
case is a batch that **validates but extracts nonsense**: it is cached and
replayed forever, and **re-ingesting does not clear it** — `wiki add --force`
releases and re-adopts the same unit rows, so unit ids and therefore batch hashes
are unchanged. Without the command the only recovery is editing SQLite by hand.

### Validation

| test | result |
|---|---|
| publish clears the staged batches | passes; failed before the delete existed |
| a failed publish keeps them | passes |
| delete joins the caller's transaction | passes; rows survive a rollback |
| `clear-graph-cache` (3 cases) | passes |

Mutation-checked: removing the delete fails the publish-clears test; dropping
`conn=conn` fails 12.

## P4 — docs and specs

- `SCHEMA.md` §11.13 (the table), `SYSTEM_BEHAVIOR.md` §L2 item 4 (resume
  semantics, extended rather than renumbered), `USER_GUIDE.md` + `_KR.md` (the
  new command).
- Version 0.62.5 → **0.63.0** across all four build manifests; all four spec
  titles bumped to `v0.63.0`. `test_spec_sync.py` passes.

**Recorded for users, not buried:** `SCHEMA_VERSION` 13 → 14 means devices that
upgrade at different times stop syncing until both are on v14. The export format
is unchanged — the version stamp is what `db_sync` rejects on.

### A doc inaccuracy noticed, not fixed

`CLAUDE.md` documents `wiki sources list|show|rm`. The CLI group is `source`,
singular — `wiki sources` is not a command. Pre-existing and out of scope here.
