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

## P0 — resume-key stability (PASSED, 2026-08-22)

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
