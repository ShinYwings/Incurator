# compile_pipeline Proposal: Crash-Window And Terminal-Status Defects In The Staged Compile

Date: 2026-08-04 | Agent Persona: Compiler Integrity Engineer

Scope audited: `backend/src/curator/pipeline/compile.py`,
`pipeline/knowledge_units.py`, `pipeline/claim_support.py`,
`pipeline/projection.py`, `pipeline/synthesis.py`, `ingest_worker.py`,
plus the two collaborators the pipeline's contracts actually depend on
(`db/jobs.py::recover_stale_jobs`, `commands/common.py::_mark_clean_sync_status`).

Spec ranges read: SYSTEM_BEHAVIOR §4.1 (L210-271), §6/§6.1 (L368-468),
§26.3/§26.4 (L2248-2400), §27.8 (L2787-2817).

---

## 1. Core Logic & Implementation

### CP-1 [P2] `recover_stale_jobs` NULLs `layer_error`, destroying the post-publish projection marker

**Spec (§26.3, SYSTEM_BEHAVIOR.md:2336-2345):**

> "A materialization/filesystem failure does not discard or replace the already
> authoritative generation. It marks the source's L2 projection phase `error`;
> **a process interruption leaves the pending marker intact. The next retry
> deterministically cleans orphan CTX pages and performs a full DB-backed
> ATM/CON/SYN and search re-emit without calling the LLM or minting another
> generation** …"

The marker is stored in `sources.layer_error`. `compile_source_l2` writes it
**inside the publish transaction** (`pipeline/compile.py:447-454`):

```python
            # This marker commits atomically with the authoritative generation.
            # If the process exits before the post-commit projection phase can
            # report success or failure, the next attempt recovers from the DB
            # instead of invoking the LLM again.
            conn.execute(
                "UPDATE sources SET layer_error = ? WHERE id = ?",
                (_POST_PUBLISH_PROJECTION_PENDING, source_id),
            )
```

and reads it back on the next attempt (`pipeline/compile.py:295-312`):

```python
    projection_state = str(source.get("layer_error") or "")
    if (
        prior_generation is not None
        and (
            projection_state == _POST_PUBLISH_PROJECTION_PENDING
            ...
        return _recover_published_source(...)
```

During the whole post-publish projection phase the source's `l2_status` is still
`'running'` — it is set at `compile.py:318` and only changed at `compile.py:499`
after `_finalize_published_source` returns.

The crash-recovery routine that both workers run at startup unconditionally wipes
that column (`backend/src/curator/db/jobs.py:154-161`):

```python
        if source_ids:
            conn.execute(
                f"UPDATE sources SET l2_status = '{consts.STATUS_PENDING}', "
                "layer_error = NULL "
                f"WHERE l2_status = '{consts.STATUS_RUNNING}' "
                f"AND id IN ({','.join('?' * len(source_ids))})",
                source_ids,
            )
```

Reachable from both worker entry points: `ingest_worker.py:474`
(`IngestWorker.run` — the MCP-embedded worker and the daemon `wiki build` spawns)
and `commands/jobs.py:63` (`wiki jobs run`).

**Concrete failure interleaving**

1. `wiki build` enqueues an `l2_atoms` job; the worker claims it → `ingest_jobs.state='running'`,
   and `compile_source_l2` sets `sources.l2_status='running'`.
2. The staged generation passes the gate and the publish transaction **commits**:
   `gen_S` is authoritative, `layer_error='post-publish projection pending'`.
3. The process dies during `_finalize_published_source` (SIGKILL, laptop sleep,
   OOM, closing the terminal that owns the detached daemon) — i.e. while ATM
   markdown is being written or `materialize_search_documents` is running.
4. Restart. `recover_stale_jobs` matches this row exactly
   (`l2_status='running'` + a `running` job) and sets `l2_status='pending'`,
   **`layer_error=NULL`**.
5. The requeued job re-enters `compile_source_l2`. `projection_state` is now `""`,
   so neither the `_POST_PUBLISH_PROJECTION_PENDING` nor the
   `_POST_PUBLISH_PROJECTION_ERROR` branch matches and `_recover_published_source`
   is never called.
6. The compile re-runs the **full LLM extraction**, mints a **new `GEN-`**, re-runs
   graph extraction, and publishes it — retiring the generation that was already
   authoritative. Exactly the two things §26.3 says the retry must not do.

**Why the existing test does not catch it.** `backend/tests/test_plan_b2_staging.py:400-441`
(`test_interrupted_post_publish_projection_recovers_without_llm`) asserts the
post-crash state is precisely `l2_status == "running"` and
`layer_error == "post-publish projection pending"` (lines 423-424), then re-invokes
`compile_source_l2` **in-process** with a `_NoCallClient()`. It never runs the real
restart path, so `recover_stale_jobs` never executes between the two halves. Insert
`db.recover_stale_jobs(vault.state_db)` between line 424 and line 426 and the test
fails: `_NoCallClient` would be called.

**Fix direction.** Make the recovery UPDATE marker-preserving, e.g.
`SET l2_status='pending', layer_error = CASE WHEN layer_error = 'post-publish projection pending' THEN layer_error ELSE NULL END`,
or (better) stop overloading `sources.layer_error` as a control-flow flag and give the
publish marker its own column / `compiler_generations.status='published_pending_projection'`
state that no status-reset path can clear. Add a regression test that calls
`recover_stale_jobs` between the crash and the retry and asserts the generation id is
unchanged and no LLM call happened.

---

### CP-2 [P2] Non-atomic wholesale L4 rebuild: `clear_synthesis_nodes` commits before the new nodes exist, and a partial rebuild is then frozen by the dependency-hash short-circuit

**Spec (§27.8, SYSTEM_BEHAVIOR.md:2808-2812):**

> "**Atomic graph/report publish.** Graph resolution, support aggregation,
> community construction, and report generation for a scope publish together or
> not at all, inside the publish transaction (extending §26.3). A failed graph
> audit discards the staged graph/report generation; the prior authoritative
> graph generation … remain untouched and continue serving."

`pipeline/synthesis.py:145-172`:

```python
    # Regenerated wholesale: drop the stale layer, then write the fresh one.
    db.clear_synthesis_nodes(paths.state_db)
    node_ids: list[str] = []
    parsed = cast(Any, result.parsed)
    for item in parsed.syntheses:
        item_spans = list(item.source_span_ids) or span_ids
        syn_id = db.upsert_synthesis_node(
            paths.state_db,
            ...
        )
        for span_id in item_spans:
            db.record_artifact_dependency(
                paths.state_db,
                ...
            )
        node_ids.append(syn_id)
```

Every one of those helpers opens and commits its **own** connection —
`db/_entities.py:3033-3036`:

```python
def clear_synthesis_nodes(db_path: Path) -> None:
    """Delete every synthesis node (the shared L4 layer is regenerated wholesale)."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM synthesis_nodes")
```

and `upsert_synthesis_node(db_path, *, ...)` (`db/_entities.py:2967`) takes no `conn`
parameter at all. So the L4 layer is destroyed and rebuilt across **N+1 independent
committed transactions**, with no staging and no rollback anchor. There is no
generation gate on this scope.

**Concrete failure scenario.** A 6-node synthesis is regenerated. `clear_synthesis_nodes`
commits (L4 is now empty on disk *and* in the DB). Nodes 1-3 are upserted, each with
`dependency_hash = dep_hash`. The process is killed (or `upsert_synthesis_node` raises
on a disk-full / constraint error) before node 4. The DB now holds a **truncated but
self-consistent-looking** L4.

The damage is then made permanent by the idempotency short-circuit at
`pipeline/synthesis.py:113-122`:

```python
    existing = db.list_synthesis_nodes(paths.state_db)
    if existing and all(n.get("dependency_hash") == dep_hash for n in existing):
        ...
        return [n["id"] for n in existing]
```

The 3 surviving nodes all carry the current `dep_hash`, so **every subsequent
`wiki build` returns them as complete and never regenerates the missing three**. The
vault silently serves a 50%-complete synthesis layer until the community-report corpus
changes enough to move `dep_hash`. Note that when `clear_synthesis_nodes` succeeds and
zero nodes are written the failure is self-healing (`existing` is empty → regenerate);
the *partial* case is the one that is durably wrong.

`backend/tests/test_synthesis.py` exercises the happy path and the unchanged-hash
no-op, but nothing injects a failure between the clear and the writes.

**Fix direction.** Pass a single caller-owned `conn` through `clear_synthesis_nodes` /
`upsert_synthesis_node` / `record_artifact_dependency` (the `db._maybe_conn` pattern
already used by `_retire_prior_generation_units` at `compile.py:832`) so the whole L4
swap is one transaction; or write the new nodes first under a staged marker and flip.
Additionally, make the short-circuit require the *count/ids* recorded with the hash to
match, not merely "all rows carry this hash", so a truncated layer can never present as
complete.

---

### CP-3 [P2] `compile_global_l3` records `l4_status='skipped'` on a synthesis failure — §4.1 requires `error` — and immediately clobbers the real L3 error message

**Spec (§4.1, SYSTEM_BEHAVIOR.md:248-252):**

> "Sources whose L2 is done must also receive a terminal `l4_status`: `done` only
> when current shared synthesis nodes are grounded in L3 reports that cite that
> source's spans, `skipped` when that source has no eligible L4 contribution, or
> **`error` when report/synthesis generation fails**. They must not remain
> indefinitely `pending` after a completed build."

`pipeline/compile.py:1105-1132`:

```python
    error_msg = "; ".join(errors) if errors else None
    l4_error = "L3 prerequisite failed; synthesis not attempted" if errors else None
    ...
    for sid in l2_done_ids:
        l3_status = "error" if errors else (
            "done" if sid in report_source_ids else "skipped"
        )
        source_l4_status = "skipped" if errors else (
            "done" if sid in synthesis_source_ids else "skipped"
        )
        db.set_source_layer_status(
            paths.state_db, sid, "l3", l3_status, error=error_msg
        )
        db.set_source_layer_status(
            paths.state_db, sid, "l4", source_l4_status, error=l4_error
        )
```

Two distinct problems.

**(a) Status contradicts the spec, and a test pins the contradiction.**
`errors` is populated by exactly two things: per-report prose failures
(`compile.py:1076-1081`) and the L4 synthesis failure (`compile.py:1092-1096`) — i.e.
precisely the "report/synthesis generation fails" case the spec assigns `error`. The
code assigns `skipped`. `backend/tests/test_compile_pipeline.py:409-441`
(`test_compile_global_l3_failure_sets_l4_skipped_not_error`) deliberately asserts
`_layer_status(paths, 1, "l4") == "skipped"`. So spec and test disagree; per arena
ground rule 5 both are wrong until reconciled. The user-visible consequence of the
current choice: `source_tools.py:62` and the status surfaces cannot distinguish
"this source legitimately contributes nothing to L4" from "L4 generation blew up",
and `_mark_clean_sync_status` (see CP-4) will later flip the `skipped` to `done`.

**(b) The recorded diagnostic is overwritten and is factually false.**
`db.set_source_layer_status` always writes `layer_error` (`db/sources.py:523-527`):

```python
    with connect(db_path) as conn:
        conn.execute(
            f"UPDATE sources SET {column} = ?, layer_error = ? WHERE id = ?",
            (status, error, source_id),
        )
```

so the second call (l4) unconditionally overwrites the `error_msg` the first call (l3)
just stored. The real provider/validation message is lost and replaced by the constant
`"L3 prerequisite failed; synthesis not attempted"`. When the only entry in `errors`
came from the synthesis step, that string is doubly wrong: L3 prose did **not** fail,
and synthesis **was** attempted. A user debugging a failed build sees a message that
misdirects them to L3.

**Fix direction.** Decide the contract once: either amend §4.1 to say `skipped` (and
explain why), or set `l4_status='error'` here. Independently, stop clobbering: compose
one `layer_error` string covering both layers, or give `set_source_layer_status` an
`error=UNSET` sentinel so a status write can leave `layer_error` untouched.

---

### CP-4 [P2] `wiki sync` promotes `l3_status`/`l4_status` to `done` from mere file existence on disk

**Spec (§4.1, SYSTEM_BEHAVIOR.md:240-252):** `l3_status` is `done` "only when a live
community report is grounded in that source's spans"; `l4_status` is `done` "only when
current shared synthesis nodes are grounded in L3 reports that cite that source's
spans". **§26.3 (SYSTEM_BEHAVIOR.md:2297-2299):** "Markdown and search are disposable
projections and are **never promoted to authority merely because a file was written**."

`backend/src/curator/commands/common.py:717-731`:

```python
def _mark_clean_sync_status(paths: cfg.WikiPaths) -> None:
    """Clear stale layer errors once sync has verified the current graph."""
    with db.connect(paths.state_db) as conn:
        l2_done = [...]
        l3_done = [...]
    if l2_done and paths.concepts.exists() and any(paths.concepts.glob(f"{consts.PREFIX_L3}-*.md")):
        db.set_sources_layer_status(paths.state_db, l2_done, "l3", "done")
    if l3_done and paths.synthesis.exists() and any(paths.synthesis.glob(f"{consts.PREFIX_L4}-*.md")):
        db.set_sources_layer_status(paths.state_db, l3_done, "l4", "done")
```

The predicate is `any(...glob("CON-*.md"))` — the existence of *any one* concept file
anywhere in the collection — not "a live community report grounded in **this** source's
spans". `compile_global_l3` computes the correct per-source grounding sets
(`report_source_ids` / `synthesis_source_ids`, `compile.py:1108-1118`) and correctly
assigns `skipped`; this function then overwrites that computed answer with a blanket
`done` for **every** `l2_status='done'` source.

**Concrete failure scenario.** A vault has 10 sources. Only 3 of them have spans cited
by any live community report, so `compile_global_l3` correctly leaves the other 7 at
`l3_status='skipped'` and `l4_status='skipped'`. The user runs `wiki sync`; it finds no
structural issues and no gaps, so line 686 calls `_mark_clean_sync_status`. All 10
sources are flipped to `l3_status='done'`, and all sources already at `l3='done'` are
flipped to `l4='done'` because one `SYN-*.md` file exists — including sources whose L4
contribution is genuinely empty and, after CP-3, sources whose L4 actually errored. The
per-source status surface (`wiki status`, `wiki sources show`, the plugin dashboard,
`source_tools.py:56-62`) now reports full L1-L4 completion for sources that contribute
to neither layer. A stale leftover `SYN-*.md` from a prior run — which `reemit_synthesis`
deletes only when it runs — is sufficient to trigger the L4 branch.

Both calls also blank `layer_error` (same `set_sources_layer_status` overwrite as CP-3b,
`db/sources.py:544-548`).

**Fix direction.** Reuse the grounding sets: `_mark_clean_sync_status` should recompute
`report_source_ids` / `synthesis_source_ids` (the helper `_source_ids_for_span_ids`
already exists at `compile.py:124`) and promote only the sources actually grounded,
leaving the rest at `skipped`. Filesystem globs must not be an input to a layer status.

---

### CP-5 [P3] The L2 checkpoint-resume path is unreachable: checkpoints are only written by the branch that requires checkpoints to already exist

`pipeline/compile.py:313-341` gates resume purely on the presence of checkpoint rows:

```python
    # Resume from checkpoint when interrupted batches were already persisted —
    # check DB directly so callers that reset l2_status before dispatching still
    # trigger resume correctly (e.g. `wiki sources retry` sets l2_status='pending').
    resume_ku = db.has_l2_checkpoints(paths.state_db, source_id)
    ...
    ku_result = knowledge_units.extract_knowledge_units(
        ..., resume=resume_ku,
    )
```

But the only `insert_l2_checkpoint` call in the entire backend sits **inside the
`if resume:` branch** (`pipeline/knowledge_units.py:378-402`):

```python
    if resume:
        # Checkpoint-resume: skip batches already persisted by a previous interrupted run.
        ...
        for index, batch in enumerate(batches, start=1):
            ...
            _persist_units(db_path, source_id=source_id, pending_units=result.units)
            db.insert_l2_checkpoint(db_path, source_id, _batch_hash(batch))
```

The default (`resume=False`) branch at `knowledge_units.py:418-419` accumulates in
memory and bulk-persists — it writes **no** checkpoints. Verified call graph:
`extract_knowledge_units` has exactly one production call site (`compile.py:334`);
`insert_l2_checkpoint` has exactly one call site (`knowledge_units.py:402`);
`l2_checkpoints` rows are otherwise only *deleted* (`knowledge_units.py:155`,
`db/sources.py:488`) and the table is not carried by `db_sync`. Therefore
`has_l2_checkpoints` is always false in production and `resume=True` can never occur.

**Concrete consequence.** A 40-batch PDF whose L2 build is interrupted at batch 38
restarts from batch 1 on the next `wiki build` / `wiki sources retry`, re-paying ~38
provider round-trips (8-12 s each per the baseline note = 5-8 wasted minutes per retry),
which is exactly the cost the checkpoint mechanism was written to avoid.

**Why the tests are green.** `backend/tests/test_knowledge_unit_extraction.py:293-400`
calls `extract_knowledge_units(..., resume=True)` **directly**, bypassing the
`has_l2_checkpoints` gate, so all four resume tests pass against code that production
can never enter.

Secondary observation (latent, currently unreachable, worth guarding when CP-5 is
fixed): if checkpoints ever do exist and every batch hash matches, the resume branch
returns `all_unit_ids = db.list_staged_unit_ids_for_source(...)`, which filters
`generation_id IS NULL` — after a successful publish that list is **empty**, and
`compile_source_l2` would then attribute zero units to a fresh generation and publish
it, retiring the source's entire authoritative unit set under the §26.3 "no zero-unit
publish guard" rule. Any fix that makes resume reachable must clear checkpoints on
successful publish and must not let an all-skipped resume masquerade as a zero-unit
extraction.

---

## 2. Pros & Cons

### What I judged clean (verified, not assumed)

- **Staged-generation visibility is genuinely write-time gated.**
  `retrieval/materializer.py:231-241` joins `compiler_generations` and filters
  `g.status = 'authoritative' AND ku.retired_at IS NULL AND ku.support_status='verified'`,
  so a staged or discarded generation's units cannot reach search even though
  `materialize_search_documents` is called on the L2-failure path (`compile.py:345`).
  §26.3's "Served = authoritative ∧ verified ∧ not retired" holds.
- **The L2 publish transaction really is one transaction.** `db.connect`
  (`db/schema.py:891-909`) commits only on clean exit of the `with` block and closes
  without committing on exception; every helper called inside the publish block at
  `compile.py:406-454` receives `conn=conn` and routes through `db._maybe_conn`
  (`db/schema.py:912-921`), which explicitly does not commit when the caller owns the
  transaction. Reconcile → graph persist → authored topology → generation flip →
  relation lifecycle → pending marker all commit or roll back together.
- **Graph LLM extraction is correctly behind the gate.** `graph_index.extract_graph_data`
  runs in memory during staging (`compile.py:390-397`) and only
  `persist_graph_data` runs inside the publish transaction — matching §26.3
  "copy-on-stage" for the generation-id-less `graph_*` tables.
- **Generation-less leftovers are discarded before a fresh extraction.**
  `_discard_unpublished_units` (`knowledge_units.py:137-155`) deletes
  `generation_id IS NULL AND retired_at IS NULL` units plus their `claim_supports`,
  and preserves retired rows as audit history — exactly §6.1 #3's wording.
- **§27.8's LWW clause is honored.** `synthesis.py:115-121` only rewrites
  `concept_ids`/`updated_at` when the concept links actually differ, so an unchanged
  re-emit is a no-op for `synthesis_nodes.updated_at`.

### What I could NOT verify (limits of this pass)

- I did not execute anything. Every finding is static reading; the crash windows in
  CP-1 and CP-2 are argued from control flow and committed-transaction boundaries, not
  from a reproduced kill test. CP-1 has a directly adjacent test
  (`test_plan_b2_staging.py:400`) that can be turned into the reproduction with a
  one-line insertion; CP-2 needs a fault-injected `upsert_synthesis_node`.
- I did not read `claim_support.py::reconcile_source` (lines 606+) or
  `pipeline/projection.py` in depth, so the §26.4 temp→stable id rewrite of *all four*
  downstream reference tables (`graph_*.knowledge_unit_ids`, `claim_supports`,
  `artifact_dependencies`, `dag_edges`) is unverified. That is the single highest-value
  remaining target for a follow-up inspector.
- I did not verify the §4.1 "batches of at most 900 parameters" rule in the
  community-report provenance lookups, nor the `_recover_published_source` orphan-CTX
  cleanup / hash-baseline rules from §26.3 (`_persist_source_projection_state`,
  `compile.py:551-720` — read only its call sites).
- CP-3 and CP-4 concern *terminal status semantics*, which are load-bearing for user
  trust but not for served content; a red-teamer may reasonably argue CP-3 down to P3
  on the status half (the layer_error clobber half stands on its own).
- CP-5's severity depends on how often L2 builds are interrupted mid-source in practice;
  it is dead code today, so it cannot *break* anything — the cost is the absent benefit
  plus four tests that assert behavior production never reaches.

### Cons of the fixes proposed above

- CP-1's cleanest fix (a dedicated publish-phase column or generation status) is a
  schema change and therefore a minor-version bump with a migration; the
  `CASE WHEN` patch to `recover_stale_jobs` is a one-line, migration-free stopgap but
  keeps `layer_error` overloaded as control flow, which is the root cause.
- CP-2's fix requires threading `conn` through three `db/_entities.py` helpers that
  currently take only `db_path`; that touches the public DB API surface pinned by
  `backend/tests/test_db_public_api.py` (signature-compatible additions only).
- CP-3 forces a spec-vs-test reconciliation: whichever way it is decided, either
  `SYSTEM_BEHAVIOR.md:248-252` or `test_compile_pipeline.py:409` must change, and the
  Korean guide pair must follow.
- CP-4's fix moves grounding computation into the sync command, which risks duplicating
  `compile_global_l3` logic; the correct shape is probably to extract one shared helper
  rather than to reimplement `_source_ids_for_span_ids` consumers twice.
