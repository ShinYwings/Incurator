# Evidence Ledger — v0.58.1 latent defect fixes

Date: 2026-08-18
Plan: `.agents/plans/07_latent_defect_fixes.md`

## 1. Rollback anchor and worktree state

- Rollback anchor: `0c0ebeb` — `docs(agents): pre-implementation review of plan
  06; D7 reversed`. Identical to `origin/master` at branch creation.
- Worktree: `.claude/worktrees/focused-noyce-749aac`, clean (`git status
  --short` empty) before any edit.
- Branch: `fix/db-connect-commit-and-chunk-floor`, cut from `0c0ebeb`.
- Dev venv: `.venv-dev` created inside the worktree (the helper resolves
  `ROOT_DIR` from its own location, and the worktree had none), populated with
  `uv pip install -e './backend[dev,mcp]'`. `.venv` / `.venv-dev` are ignored;
  no `backend/.venv`, `backend/uv.lock`, or backend-local caches created.
- Concurrent work: `feature/v0.59.0-job-progress` exists locally and unpushed.
  No open PRs (`gh pr list --state open` empty).

## 2. Pre-fix reproduction — defect 1

Fresh temp DB, first-ever operation is a job claim:

```
call 1 -> OperationalError: cannot start a transaction within a transaction
call 2 -> OperationalError: cannot start a transaction within a transaction
call 3 -> OperationalError: cannot start a transaction within a transaction
schema_version rows after 3 failed calls: []
```

The last line is the never-heals proof: the `INSERT` in `_stamp_schema_version`
is rolled back by the raise, restoring exactly the precondition that produced
it.

Second DML branch — an existing DB whose stored version is stale:

```
claim on stale-version db -> OperationalError: cannot start a transaction within a transaction
version after -> [(1,)]
```

Same failure, same non-healing, reached through `UPDATE` rather than `INSERT`.
This is the branch that would bite an existing vault the first time a job is
claimed after a `SCHEMA_VERSION` bump.

## 3. Are the user-facing paths broken? No — and the reason is fragile

Both callers of `claim_next_job` call `db.recover_stale_jobs` first:

- `commands/jobs.py:65` in `jobs_run`
- `ingest_worker.py:516` in `IngestWorker.run`

`recover_stale_jobs` issues a `SELECT` and an `UPDATE` with no explicit `BEGIN`,
so it joins the open implicit transaction without error and its `yield`-exit
`conn.commit()` commits the schema stamp along with its own work. Measured on a
fresh DB:

```
recover_stale_jobs on fresh db -> 0
schema_version after -> [(13,)]
claim_next_job now -> None
```

So `wiki jobs run` is **not** currently broken. What is broken is
`db.claim_next_job` standalone — a member of the public DB API surface that
`test_db_public_api.py:41` asserts — protected only by an incidental ordering
that no test, comment, or spec records. Reordering those two lines, or adding a
third caller that claims first, re-arms the defect silently.

The changelog must say this accurately and must not claim `wiki jobs run` was
failing for users.

## 4. Pre-fix reproduction — defect 2

`extract_knowledge_units`'s own subdivision and batching loops, replayed against
eight 3,000-character sections with a client reporting `optimal_chunk_chars =
200`:

```
max_chars = 200 -> chunk_size passed to _chunk_text = -300
refined spans: 24000
BATCHES (= LLM calls): 3920
```

24,000 refined spans for 24,000 characters of input: one chunk per character,
produced by `_chunk_text`'s forward-progress guard absorbing the negative size.
The report measured 1,148 batches on a different document; the shape is the
same and scales with character count, not section count.

## 5. Production values that bound the floor

Every real `optimal_chunk_chars`, read from source:

| client | value | file |
|---|---|---|
| `OllamaClient` | `int(context * 0.8) * 4`; smallest tier = 4,096 tokens -> **13,107** | `llm.py:445` |
| `AntigravityCliClient` | 18,000 | `llm.py:928` |
| `ClaudeCliClient` | 12,000 | `llm.py:1103` |
| DeepSeek | 50,000 | `llm.py:1226` |
| helper default | 60,000 | `pipeline/chunking.py:8` |

`_MIN_SUBDIVISION_CHARS = 1000` sits an order of magnitude below the smallest of
these, so the floor cannot engage on any production configuration. That is the
property §5 of the plan makes a stop condition.

## 6. Schema and version reality

- No schema change; `SCHEMA_VERSION` stays 13, no migration.
- All four build manifests at `0.58.0` before the bump: `backend/pyproject.toml`,
  `plugin/package.json`, `plugin/manifest.json`, `plugin/package-lock.json`
  (both `version` and `packages[""].version`).
- Spec titles read `(v0.58.0)`. `test_spec_sync.py::_active_line` compares only
  `MAJOR.MINOR`, so `0.58.1` satisfies them unchanged.

## 7. Post-fix validation

Filled in during P3–P5.

### 7.1 Defect 1 — after the fix

```
call 1 -> None
call 2 -> None
schema_version rows -> [(13,)]
stale-version claim -> None ; version after -> [(13,)]
enqueue then claim -> job 1 state=running
```

### 7.2 Defect 2 — after the fix

```
max_chars = 200 -> chunk_size passed to _chunk_text = 1000 (floored)
refined spans: 40   (was 24000)
BATCHES (= LLM calls): 40   (was 3920)
_chunk_text(chunk_size=-300) -> ValueError: chunk_size must be positive, got -300
```

40 batches for 8 sections x 3,000 chars: 5 sub-chunks per section (1,000-char
chunks advancing 500), each exceeding the 200-char batch budget on its own. The
count now scales with `document_length / floor`, not with `document_length`.

The `graph_index.py` site turned out to be worse than the plan assumed. Its
regression test uses a 211-character statement with the budget at 200, so the
old bound was `statement[:-300]` — the empty string. The unit reached the model
as literally `KNU-1 (claim) [SPAN-1]: ... [TRUNCATED]`, with the entire
statement gone. It is not only a tail-amputation defect; below the shortfall it
erases the content outright and still labels the result truncated.

### 7.3 Suite

- `scripts/backend-check pytest` — **1,598 passed, 6 skipped, 4 xfailed** in
  495s.
- `scripts/backend-check ruff` — clean (`backend/src/`, and the four touched
  test files checked explicitly). Eight pre-existing F401s elsewhere under
  `backend/tests/` are untouched and outside the helper's default target.
- `scripts/backend-check mypy` — clean, 128 source files.
- `npx vitest run -c ./plugin/vitest.config.ts` — **1,070 passed, 3 skipped**
  (plugin untouched; run as a no-regression check, with
  `plugin/src/generated/buildManifest.json` stubbed as CI does).
- The three tests that deliberately pass `optimal_chars=160`
  (`test_failed_late_batch_leaves_no_partial_units`,
  `test_property_chunk_budget_is_respected`,
  `test_provider_exception_leaves_no_partial_units`) pass **unmodified**, which
  is the plan's §3 gate distinguishing the chosen fix from the rejected clamp.

### 7.3a Unplanned: the D2 holdout drift tripwire fired

`backend/src/curator/db/schema.py` is one of the files pinned by content hash in
`docs/specs/failure_atlas/D2_HOLDOUT_RESULT.yml`, so the one-line commit
tripped `test_failure_atlas_d2.py::test_d2_holdout_result_is_single_run_frozen_and_fine_grained`
and `test_job_events.py::test_the_frozen_evaluated_files_are_untouched`. This
was not anticipated by the plan.

Handled by the procedure the file itself establishes — there are eleven prior
`*_rearm` records with the same shape. Added `v0581_connect_commits_schema_rearm`
carrying the prior hash, the date, and the non-impact argument, then updated the
recorded hash. The holdout is **not** re-run and **no new result is claimed**:
`run_count` is 3, `valid_run_count` 1, and every metric and frozen input is
untouched. The non-impact argument is mechanical — the harness is unchanged, it
uses exactly `connect`, `init_db`, and `upsert_search_document`, it issues no
explicit `BEGIN`, and the new commit covers only schema DDL and the
`schema_version` row, so no document, span, chunk, ranking input, citation, or
metric can differ.

### 7.4 Testbed smoke

Scenario: `testbed_template` (the only scenario present in this worktree; the
developer's custom scenarios are gitignored and absent here).

```
wiki testbed init testbed_template --force   -> ok
VAULT_ROOT=testbed wiki status               -> 2 raw sources, 0 tracked
VAULT_ROOT=testbed wiki jobs list            -> No background jobs.
VAULT_ROOT=testbed wiki jobs run             -> No queued jobs. + index rebuild
```

Then the defect's own scenario against the real resolved vault path, with the
repo-cache state DB deleted so a claim is genuinely the first operation:

```
state_db: .cache/vaults/78eb2566778d27f2/state.sqlite
exists before: False
first-ever op is a claim -> None
second claim -> None
schema_version: [(13,)]
enqueued 1 -> claimed 1 running
```

`wiki jobs run` was also re-run against the deleted DB and drained cleanly. Note
that this CLI path passed before the fix too, for the reason in §3 — it is a
coverage check, not the regression proof. The regression proof is the direct
`claim_next_job` sequence above and the four unit tests in `test_db_schema.py`.

No LLM-dependent smoke was attempted: neither defect is LLM-behavioural, and
both regression paths are exercised deterministically with fake clients.
