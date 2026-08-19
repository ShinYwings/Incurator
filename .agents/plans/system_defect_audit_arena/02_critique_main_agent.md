# Critique on the v0.42.0 Arena Proposals — Main-Agent Verification Pass

Date: 2026-08-04 | Agent Persona: Red-team critic (main agent, standing in for
the failed per-domain critic agents)

## 0. Why this document exists

The arena run completed all four inspectors — every one of them wrote its
proposal to disk before returning — but **all four red-team critic agents and
the synthesizer died on a provider session limit** (resets 14:30 Asia/Seoul).
The structured results therefore came back marked `verdict: "undebated"`.

Undebated findings must not enter a plan. Rather than wait, the main agent ran
the critic role inline against the highest-severity claims. This document
records exactly which findings were independently re-verified and which were
NOT, so the coverage boundary is explicit rather than implied.

**Verification method:** every claim below was re-checked by reading the cited
`file:line` in the repository at `chore/system-defect-audit-arena` (master
`1ca26f0`, v0.42.0) — not by trusting the inspector's quoted excerpt — plus a
search for existing tests that would already pin the correct behavior.

## 1. Vulnerabilities & Flaws

### VERDICT: CONFIRMED — `sync_db-1` [P0] silent cross-device row loss

Independently re-verified, all three legs:

1. `db_sync.py:1416-1419` — `_do_insert` really does issue
   `INSERT OR IGNORE INTO {table} ...`.
2. `db_sync.py:1357-1360` — the caller returns `"inserted"` unconditionally
   after that statement; nothing inspects `rowcount`, so an ignored insert is
   indistinguishable from a real one.
3. `db/schema.py:290` (`idx_source_spans_source_hash`) and `db/schema.py:368`
   (`idx_graph_entities_name`) really are UNIQUE indexes over *natural*
   columns.

The leg the inspector needed and I checked separately: are the primary keys
actually device-random in the normal path? Yes. `db/_entities.py:34-36`
`_new_id()` returns `f"{prefix}-{uuid.uuid4().hex[:8]}"`, and
`upsert_graph_entity` (`db/_entities.py:830`) deduplicates only *locally*, by
`SELECT * FROM graph_entities WHERE canonical_name = ? AND entity_type = ?`,
minting a fresh random id when there is no local hit.

So two devices that each extract "Transformer" hold the same natural key under
different random PKs. On import the remote PK matches nothing locally, the
insert is attempted, SQLite silently swallows the UNIQUE violation, and the
pass reports `inserted`. **The peer's row is dropped and the counters say it
landed** — silent divergence between replicas that no surface reports.

This is the single most serious finding of the run and it directly affects a
multi-device vault, which is this repository's documented topology (§13.1).

### VERDICT: CONFIRMED — `compile_pipeline-1` [P2] crash recovery destroys the post-publish marker

Re-verified end to end:

- `pipeline/compile.py:451-454` writes `_POST_PUBLISH_PROJECTION_PENDING` into
  `sources.layer_error` *inside* the publish transaction.
- `pipeline/compile.py:295-299` requires exactly that marker value to take the
  cheap DB-backed recovery path.
- `pipeline/compile.py:318` sets `l2_status='running'` at the start and it is
  only replaced at `compile.py:499` — so while the marker exists, the source is
  still `running`.
- `db/jobs.py:154-160` unconditionally issues
  `UPDATE sources SET l2_status='pending', layer_error = NULL WHERE l2_status='running' AND id IN (...)`,
  where the ids come from `ingest_jobs` rows still in `running`.

Callers confirmed at `ingest_worker.py:474` and `commands/jobs.py:63`, i.e. both
worker startup and the CLI. So the documented "interruption leaves the pending
marker intact" (§26.3) does not survive the very restart it is designed for:
the marker is nulled, the cheap path is skipped, and the retry re-runs the LLM
and mints another generation — the two things §26.3 forbids.

Coverage gap confirmed: `grep` finds **no** call to `recover_stale_jobs` in
`backend/tests/test_plan_b2_staging.py`, so the test that asserts the marker
never exercises the recovery that erases it.

### VERDICT: CONFIRMED (with a severity note) — `compile_pipeline-2` [P2] non-atomic L4 rebuild can freeze a partial layer permanently

Re-verified:

- `db/_entities.py:3033-3036` — `clear_synthesis_nodes` opens its **own**
  `with connect(db_path) as conn`, so the wholesale DELETE commits on its own,
  before any replacement row is written.
- `pipeline/synthesis.py:146-172` — each replacement node is then written by
  `db.upsert_synthesis_node(paths.state_db, ...)`, again per-call connections.
  The L4 swap is therefore N+1 independent transactions, not the single publish
  transaction §27.8 requires.
- `pipeline/synthesis.py:113-114` — the idempotency short-circuit accepts the
  existing set whenever `all(n["dependency_hash"] == dep_hash for n in existing)`.
  After a crash mid-loop every *surviving* row already carries the new hash, so
  the truncated layer satisfies the check and is returned as complete on every
  later build until the report corpus changes.

**Severity note the inspector did not make:** the crash window is narrower than
the proposal implies. `prompting.run_prompt` (synthesis.py:132) completes
*before* `clear_synthesis_nodes`, so the exposed span is pure DB writes, not an
LLM call. That lowers likelihood — but the consequence is permanent and silent
(the layer never self-heals), so P2 stands rather than being downgraded.

## 2. Suggested Alternatives

- **sync_db-1**: do not "fix" this by switching to `INSERT OR REPLACE` — that
  would trade a silent drop for a silent overwrite of the local row. The insert
  must detect the collision (check `rowcount`, or pre-resolve by natural key)
  and then take the *documented* LWW path against the colliding local row,
  reporting a real outcome (`updated`/`skipped`) instead of a fictional
  `inserted`. Any fix needs a two-replica regression test asserting both
  convergence and truthful counters.
- **compile_pipeline-1**: prefer giving the publish-pending phase its own column
  or a `compiler_generations` status over a `CASE WHEN` patch to the recovery
  UPDATE. `sources.layer_error` is currently overloaded as both a human error
  string and control flow, which is what made this collision possible at all
  (and see `compile_pipeline-3`, where the same overload causes an error-message
  clobber). The regression test must call `recover_stale_jobs` between the
  simulated crash and the retry.
- **compile_pipeline-2**: thread one caller-owned connection through
  clear/upsert/record via the existing `db._maybe_conn` pattern so the swap is
  atomic. Independently — and worth doing even if atomicity lands — make the
  short-circuit compare the recorded node id set, not merely "every surviving
  row carries this hash", so a truncated layer can never present as complete.

## 3. NOT VERIFIED — do not treat as findings yet

The following were produced by inspectors but have received **no** adversarial
verification from any agent, including me. They are hypotheses with cited
evidence, nothing more:

- `compile_pipeline-3` [P2] `l4_status='skipped'` where §4.1 requires `'error'`,
  plus an error-message clobber. Note this one explicitly conflicts with an
  existing green test (`test_compile_pipeline.py:409`), so it is a
  spec-vs-test reconciliation decision, not a straightforward fix.
- `compile_pipeline-4` [P2] `wiki sync` promoting `l3/l4_status` to `done` from
  a filesystem glob rather than per-source grounding.
- `compile_pipeline-5` (title not captured in the structured result).
- `retrieval_context-1..5` [5 findings] — returned structured, unverified.
- `plugin_lifecycle` F1 [P1] Quick Query cross-reference fetch not pinned to a
  document identity (claimed wrong-PDF page splicing), F2 [P2]
  `syncAgyMcpConfig` overwriting a malformed settings file non-atomically,
  F3/F4 [P3].
- `sync_db-2` [P2] device-local sync state written without the `durable_io`
  lock/fsync, `sync_db-3` [P2] export gate latching on peer clock skew.

`plugin_lifecycle` F1 [P1] is the highest-severity unverified claim and should
be the first target when critics can run again — it alleges wrong-document
evidence reaching an answer, which would be a correctness failure, not a
performance or hygiene one.
