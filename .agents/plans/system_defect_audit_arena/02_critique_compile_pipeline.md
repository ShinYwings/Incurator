# Critique on 01_proposal_compile_pipeline.md
Date: 2026-08-04 | Agent Persona: Red-team critic (Crash-Window Adversary)

Method: every cited `file:line` was re-read at HEAD of `chore/system-defect-audit-arena`.
Every spec quote was re-read from `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`.
Every claimed test was re-read. Findings survive only where my own re-derivation
reproduced the failure; where the inspector's reasoning was right but its framing,
spec anchor, or blast radius was wrong, I say so explicitly below.

**Verdict summary**

| ID | Inspector | My verdict | Final severity |
|---|---|---|---|
| CP-1 | P2 | **confirmed** | P2 |
| CP-2 | P2 | **confirmed** (spec anchor corrected, impact re-derived) | P2 |
| CP-3 | P2 | **confirmed** (a) + (b), one sub-claim corrected | P2 |
| CP-4 | P2 | **confirmed** (one detail corrected) | P2 |
| CP-5 | P3 | **confirmed** (dead code; the latent hazard is real too) | P3 |

Nothing was refuted outright. Three findings needed corrections that change the
fix, not the verdict.

---

## 1. Vulnerabilities & Flaws (per-finding re-verification)

### CP-1 — `recover_stale_jobs` NULLs the projection marker → **CONFIRMED (P2)**

**Attack 1 — is the code current?** Yes. `db/jobs.py:154-161` reads exactly
`UPDATE sources SET l2_status = '<pending>', layer_error = NULL WHERE l2_status =
'<running>' AND id IN (...)`. The `source_ids` list at `jobs.py:140-146` is
`SELECT DISTINCT source_id FROM ingest_jobs WHERE state='running' AND source_id>0`
— a source crashed mid-compile has exactly that row, so it is matched, not filtered.

**Attack 2 — is the crash window real?** Yes, and it is wider than the inspector
argued. `compile.py:451-454` writes the marker *inside* the publish transaction;
the projection phase runs at `compile.py:472-478`; `l2_status` is only moved off
`running` at `compile.py:499`. So the entire `_finalize_published_source` duration
(stable-id persistence, DAG edges, ATM markdown, `materialize_search_documents`)
is spent in the exact `(l2_status='running', layer_error='post-publish projection
pending')` state that `recover_stale_jobs` destroys. Note the failure needs no
`except`-escaping exception: an in-process exception is caught at `compile.py:479`
and *converts* the marker to the `_POST_PUBLISH_PROJECTION_ERROR` form, which the
recovery branch also accepts — but a **SIGKILL/power-loss** leaves the pending form,
and only that path also leaves the job `running`, which is precisely the input
`recover_stale_jobs` acts on. The two mechanisms line up perfectly.

**Attack 3 — is the recovery branch still gated on the marker?** Yes.
`compile.py:295-307` requires `projection_state == _POST_PUBLISH_PROJECTION_PENDING`
**or** (`l2_status == 'error'` **and** `projection_state.startswith(_ERROR)`).
After recovery, `l2_status='pending'` and `projection_state=''` — both disjuncts
fail. `_recover_published_source` is unreachable. Confirmed.

**Attack 4 — is a test already pinning this green?** No, and I found something the
inspector missed that *helps* the fix: `test_v031_pipeline_state.py:35-60`
(`test_recover_stale_job_resets_source_layer_to_pending`) asserts only
`job_state == 'queued'` and `l2_status == 'pending'` — it **never asserts
`layer_error`**. So the marker-preserving `CASE WHEN` patch is test-safe today; no
existing assertion has to be rewritten. `test_plan_b2_staging.py:400-432` is exactly
as described: it raises `KeyboardInterrupt` from `_finalize_published_source`
(deliberately escaping the broad `except Exception` at `compile.py:455`), asserts
the `running` + `pending` marker state at lines 423-424, then re-enters
`compile_source_l2` in-process with `_NoCallClient()`. `recover_stale_jobs` is never
called between the halves. The bug lives precisely in the untested seam.

**Attack 5 — is the spec really violated?** Yes, and the spec is *self-conflicting*,
which the inspector under-sold. §4.1 (L237-239) mandates the reset:
"Recovering a job left `running` by a crashed worker resets both the job to `queued`
and its source `l2_status` to `pending`". §26.3 (L2340-2343) mandates the opposite
for the marker: "a process interruption leaves the pending marker intact. The next
retry … without calling the LLM or minting another generation." Both clauses are
satisfiable simultaneously **only if the reset stops clearing `layer_error`** — the
current code satisfies §4.1 and breaks §26.3. The fix must therefore preserve the
`l2_status='pending'` reset (§4.1 is not negotiable) while preserving the marker.

**Attack 6 — is severity inflated?** No, but it is not P1/P0 either. The re-compile
publishes a fresh correct generation, so no wrong knowledge is served and no data is
lost; the cost is a full LLM re-extraction (the §26.3-forbidden action) plus a
needless generation churn that retires an already-authoritative one. That is a
contract violation with a de-facto workaround (wait and pay) → **P2**.

**Correction to the inspector.** Its fix direction lists the schema-change option
("its own column / `compiler_generations` status") as "better". I disagree on
sequencing: the root cause is real but the schema route is a minor bump + migration
for a crash-window fix. The correct shape is the reverse order — land the
marker-preserving predicate now (see §2), and treat de-overloading `layer_error` as a
separate hygiene item, because a *second* consumer already exists that the inspector
did not connect: `set_source_layer_status` blanks `layer_error` on **every** status
write (`db/sources.py:523-527`), so any code path that touches l2 status between the
publish commit and the retry also erases the marker. That is the same root cause as
CP-3(b) and should be fixed once, jointly.

---

### CP-2 — Non-atomic wholesale L4 rebuild + dep-hash freeze → **CONFIRMED (P2), spec anchor corrected**

**Attack 1 — code current?** Yes. `synthesis.py:145-146` (`clear_synthesis_nodes`)
then the per-item loop at 149-172 calling `upsert_synthesis_node(paths.state_db, …)`
and `record_artifact_dependency(paths.state_db, …)`; `db/_entities.py:3033-3036`
confirms `clear_synthesis_nodes` opens its own `connect(...)` (which commits on clean
exit). Neither writer accepts a caller-owned `conn`. N+1 committed transactions:
confirmed.

**Attack 2 — the spec citation is wrong, and I am striking it.** §27.8 L2808-2812
reads "Graph resolution, support aggregation, community construction, and **report
generation** for a scope publish together or not at all". That enumeration is the
L3 graph/report pipeline. §27.8 mentions L4 exactly once more, and only about the LWW
clock ("Re-emitting unchanged L4 synthesis concept links is a no-op for
`synthesis_nodes.updated_at`"). **§27.8 does not place `synthesis_nodes` writes inside
a publish transaction.** Nor does §26.3, whose generation machinery is explicitly
"every Plan-B-owned compile" (L2294) — synthesis has no `GEN-` at all, as the
inspector itself notes ("There is no generation gate on this scope"). So the
"§27.8 atomicity violation" framing is **refuted**: the L4 layer is by design outside
the staged-generation contract today, and ENH-01 in the briefing already records
wholesale regen as an *enhancement*, not a defect.

**Attack 3 — but the freeze is a genuine, independently-grounded defect.** The
short-circuit at `synthesis.py:113-122` is verbatim as quoted:
`if existing and all(n.get("dependency_hash") == dep_hash for n in existing): … return
[n["id"] for n in existing]`. `all()` over a truncated set is vacuously satisfied by
the survivors. Any partial write (SQLITE_FULL, SQLITE_BUSY on a synced vault with a
concurrent worker, SIGKILL) therefore produces a permanently-frozen partial L4 that
every subsequent `wiki build` reports as complete. This needs no §27.8: it fails
§4.1's own `l4_status` definition ("`done` only when **current** shared synthesis
nodes are grounded in L3 reports that cite that source's spans") — sources whose
grounding lived in the three lost nodes keep `l4='done'`. That is silent degradation
→ **P2** stands, on the freeze, not on the atomicity.

**Attack 4 — I re-derived the blast radius and the inspector got it partly wrong.**
Its claim "L4 is now empty on disk *and* in the DB" after `clear_synthesis_nodes` is
**false**. `reemit_synthesis` (which deletes `SYN-*.md`, `synthesis.py:186-187`) runs
only at line 174, *after* the loop. So on a mid-loop failure the vault is left with
the **full previous SYN-*.md set on disk** and a **truncated node set in the DB** —
and `reemit_synthesis` never runs on that path, nor on the subsequent short-circuited
builds (line 121 re-emits only when concept links differ). The durable end state is
therefore worse than described: stale orphan L4 markdown that outlives its DB rows,
diverging from DB-native search forever. This *strengthens* the finding and changes
the fix (a repair must also force a re-emit, not just unfreeze).

**Attack 5 — already tested?** No. `test_synthesis.py` touches
`clear_synthesis_nodes` only at line 140 as direct setup, and exercises the happy
path plus the unchanged-hash no-op. No fault is injected between the clear and the
writes. Not pinned.

---

### CP-3 — `l4_status='skipped'` on synthesis failure + `layer_error` clobber → **CONFIRMED (P2)**

**Attack 1 — code and test current?** Both. `compile.py:1105-1132` matches the quote
exactly, `errors` is fed only by `compile.py:1081` (report prose) and
`compile.py:1096` (synthesis), and
`test_compile_pipeline.py:409-441` is real, is named
`test_compile_global_l3_failure_sets_l4_skipped_not_error`, and carries an explicit
intent comment: "L4 must NOT be 'error' — synthesis was the failure, and L4 was never
completed."

**Attack 2 — does §4.1 really promise `error`?** Yes, verbatim at L248-252:
"`skipped` when that source has no eligible L4 contribution, or **`error` when
report/synthesis generation fails**." The test's own scenario (`SynthesisFailClient`)
is literally "synthesis generation fails". This is a three-way divergence
(spec ↔ code ↔ deliberate test), i.e. exactly arena ground rule 5. Not refutable.

**Attack 3 — is the failure silent?** Partially, and the inspector overstated it.
`compile.py:1134-1135` raises `RuntimeError(f"L3 global clustering encountered errors:
{error_msg}")` — the **true** provider message *is* surfaced to the live caller
(`ingest_llm.py:575`/`613` do not swallow it). So the claim "a user debugging a failed
build sees a message that misdirects them to L3" is only true **after the process
exits**: what persists in `sources.layer_error` — i.e. what `wiki sources show`, the
MCP status tools, and the plugin dashboard read later — is the false constant
"L3 prerequisite failed; synthesis not attempted". I re-verified the clobber
mechanism at `db/sources.py:523-527`: `UPDATE sources SET {column} = ?, layer_error =
? WHERE id = ?` writes `layer_error` unconditionally, so the second (l4) call in the
loop overwrites the `error_msg` the first (l3) call stored, for every source, on every
iteration. Confirmed, with the impact narrowed to the persisted/asynchronous surface.

**Attack 4 — bonus divergence the inspector missed.** §4.1's *L3* clause (L240-243)
admits only `done` or `skipped` — it never sanctions `l3_status='error'`, yet
`compile.py:1121` writes exactly that (and the test pins it at line 437). Whichever
way the reconciliation goes, §4.1 needs the `error` state spelled out for **both**
layers, not just L4. Fold this into the same spec edit.

**Attack 5 — severity.** I considered downgrading to P3 since no served content is
wrong. I am not downgrading: the rubric puts "contract violation" flatly at P2, and
this one is compounded — the false `skipped` is then laundered into `done` by CP-4,
so the end state is a source reporting full L1-L4 completion after its L4 blew up.
**P2**, and CP-3+CP-4 must be fixed in the same batch or the fix is incomplete.

---

### CP-4 — clean-sync promotes L3/L4 to `done` from a filesystem glob → **CONFIRMED (P2)**

**Attack 1 — code current?** Yes, `commands/common.py:717-731` verbatim, reached from
line 686 (`elif not structural_issues: _mark_clean_sync_status(paths)`) — i.e. the
*normal* clean-sync path, not an edge case.

**Attack 2 — one factual correction.** The inspector says "every `l3_status='done'`
source" is flipped to `l4='done'`. Precisely: `l3_done` is snapshotted at lines
724-727 **before** the L3 promotion at line 729, so the L4 branch applies to the
*pre-promotion* `l3='done'` set, not to the newly promoted ones. This narrows the
first sync's blast radius by one round — but the very next clean `wiki sync` picks up
the newly-promoted set and completes the laundering. The defect stands; the "one run"
framing is wrong.

**Attack 3 — spec.** §4.1 L240-252 conditions both statuses on per-source grounding
("`done` only when a live community report is grounded in that source's spans" /
"only when current shared synthesis nodes are grounded in L3 reports that cite that
source's spans"). §26.3 L2296-2299 says projections "are never promoted to authority
merely because a file was written". A `glob("CON-*.md")` truthiness test is the
canonical instance of both violations. Confirmed.

**Attack 4 — already tested?** No. `grep -rn "_mark_clean_sync_status" backend/tests/`
returns nothing; no test exercises the promotion at all. Unpinned in both directions,
so the fix is free to change behavior.

**Attack 5 — reachability.** Requires ≥1 source correctly at `skipped` plus a clean
sync. `compile_global_l3:1118` sets `synthesis_source_ids = report_source_ids if
synthesis_ids else set()`, so **any** vault where synthesis produced nothing (empty
report corpus, unchanged-hash no-op returning `[]` from `synthesis.py:107`) leaves
*every* source at `l4='skipped'` — and one leftover `SYN-*.md` then flips all of them
to `done`. This is the common case, not a corner. If anything CP-4 is the most
frequently-triggered of the five.

**Attack 6 — severity.** Status surfaces lie about layer completion, and
`set_sources_layer_status` simultaneously blanks `layer_error` (`db/sources.py:544-548`),
erasing the real diagnostic. No knowledge is mis-served, so not P1/P0 → **P2**.

---

### CP-5 — L2 checkpoint-resume is unreachable dead code → **CONFIRMED (P3)**

**Attack 1 — call graph.** Re-grepped the whole backend:
`insert_l2_checkpoint` has exactly one call site, `knowledge_units.py:402`, and I
confirmed by reading `knowledge_units.py:378-416` that it sits **inside** `if resume:`.
The default branch begins at `knowledge_units.py:418` ("Default (non-resume):
accumulate in memory, bulk-persist on full success") and writes no checkpoint.
`extract_knowledge_units` has exactly one production call site (`compile.py:334`),
whose `resume=` comes solely from `has_l2_checkpoints` (`compile.py:316`). The
bootstrap is genuinely impossible: `resume=True` requires rows that only `resume=True`
can create.

**Attack 2 — could a legacy vault seed the table?** I checked
`git log -S insert_l2_checkpoint -- backend/src/curator/pipeline/knowledge_units.py`
and found a single commit (`0846f57 fix(pipeline): correct checkpoint-resume skip
logic…`); nothing indicates a historical unconditional-write version, and the table is
not carried by `db_sync`. So no realistic legacy seeding path. The dead-code verdict
holds.

**Attack 3 — is P3 right?** Yes. Nothing breaks; the cost is an unrealized
optimization plus four tests asserting behavior production cannot reach. I checked the
inspector's cost estimate against the briefing's measured facts (8.2–12.2 s per CLI
provider round-trip): the "5-8 wasted minutes on a 38-batch retry" figure is sound but
it is *unrealized savings*, not a regression. **P3** confirmed — but see §2: this must
be scheduled as *delete* or *complete*, never left half-alive, because the completion
route carries the zero-unit hazard below.

**Attack 4 — the secondary hazard is real and I am upgrading its prominence.**
`knowledge_units.py:411` returns `db.list_staged_unit_ids_for_source(...)` on the
all-batches-skipped path. Those ids filter `generation_id IS NULL`; after a successful
publish that set is empty. Combined with §26.3's "No zero-unit publish guard"
(L2345-2349: a successful extraction yielding zero units "MUST publish — retiring the
prior authoritative units"), a naive "make resume reachable" change would let an
all-skipped resume masquerade as a legitimate empty extraction and **retire a source's
entire authoritative unit set**. That is a latent P0 gated behind an unreachable
branch. It does not raise CP-5's severity today, but it is a hard stop-condition on
the fix.

---

## 2. Suggested Alternatives (better fix directions)

**CP-1 — fix the eraser, not just the one call site.** Two writers erase the marker:
`db/jobs.py:156-157` explicitly, and `db/sources.py:525` implicitly on every status
write. Do both in one change:
1. `recover_stale_jobs`: `SET l2_status='pending', layer_error = CASE WHEN layer_error
   LIKE 'post-publish projection%' THEN layer_error ELSE NULL END` — the `LIKE` (not
   `=`) also preserves the `_POST_PUBLISH_PROJECTION_ERROR` prefix form that
   `compile.py:302` accepts. Keep the `l2_status='pending'` reset: §4.1 L237-239
   requires it, and `compile.py:296-307`'s pending-marker disjunct does not test
   `l2_status`, so recovery still fires.
2. Give `set_source_layer_status` an `UNSET` sentinel default so a status-only write
   leaves `layer_error` untouched (this is also CP-3(b)'s fix — one change, two
   findings).
Regression test: extend `test_plan_b2_staging.py:400` with
`db.recover_stale_jobs(vault.state_db)` inserted at line 425, asserting the generation
id is unchanged and `_NoCallClient` is never called. Defer the dedicated
column / `compiler_generations.status='published_pending_projection'` de-overloading to
a follow-up — it is a migration and a minor bump for a one-line crash-window fix.

**CP-2 — decouple the two halves; ship the cheap one first.** The freeze
(`synthesis.py:113-122`) is a 3-line fix with no API churn and is where the durable
damage lives: record the node-set fingerprint alongside the hash (e.g. require
`len(existing) == expected_count` persisted with the dep_hash, or store the dep_hash on
a single `synthesis_manifest` row written *after* the loop and short-circuit on that
row, not on the per-node column). A manifest row written last is strictly better than a
count: it is a natural commit marker, it makes the "partial" state self-identifying,
and it needs no `conn` threading. Only then consider the transactional swap — and note
my Attack 4: whatever the fix, it must also **force `reemit_synthesis` on unfreeze**,
because the failure leaves the *old full* `SYN-*.md` on disk against a truncated DB, so
merely unfreezing the DB rebuild would still leave orphan markdown behind. The
inspector's `conn`-threading proposal is correct but is the expensive half (touches
three `db/_entities.py` signatures pinned by `test_db_public_api.py`) and does not by
itself repair an already-frozen vault.

**CP-3 — reconcile the spec toward the code, not the code toward the spec.** The
test's intent comment is defensible engineering: on a synthesis failure the source has
no L4 output, and `l4='error'` would be indistinguishable from a per-source L4 failure
that does not exist as a concept (L4 is global). The cheaper, more honest fix is to
amend §4.1 (+ `SYSTEM_BEHAVIOR` KR guide) to define the global-failure case as
`l3='error'` + `l4='skipped'`, and to spell out `error` as a legal `l3_status`
(my Attack 4). If instead the user wants the spec to win, `compile.py:1124` becomes
`"error" if errors else …` and `test_compile_pipeline.py:409` is renamed and inverted.
Either way, **the clobber must be fixed regardless of which side wins** — reuse the
`UNSET` sentinel from CP-1, or compose a single per-source message
(`f"l3: {error_msg}"` / `f"l4: {l4_error}"`) and stop asserting "synthesis not
attempted" when `errors` came from `compile.py:1096`, where it demonstrably was.

**CP-4 — delete the promotion, do not reimplement the grounding.** The inspector wants
`_mark_clean_sync_status` to recompute `report_source_ids`/`synthesis_source_ids` via a
shared `_source_ids_for_span_ids` helper. That duplicates compile-time policy into the
sync command and creates a second place where §4.1 can drift. Prefer the smaller,
safer shape matching the function's own docstring ("Clear stale layer errors once sync
has verified the current graph"): **clear `layer_error` only**, and leave `l3_status`/
`l4_status` alone — they are already terminal and correct from `compile_global_l3`. If
a `skipped→done` promotion is genuinely needed after a repair, it belongs in
`compile_global_l3`'s own re-run, not in `wiki sync`. This also removes the last
filesystem glob from status computation, which is the actual §26.3 requirement. Note
this needs a `layer_error`-only writer (a third consumer of the CP-1/CP-3 sentinel
work) — three findings, one primitive.

**CP-5 — decide, then act; do not "make it reachable" casually.** Recommend
**delete**: remove the `if resume:` branch, the `resume` parameter, `has_l2_checkpoints`
/ `insert_l2_checkpoint` / `get_l2_checkpoint_hashes`, the `l2_checkpoints` table
(migration), and the four bypassing tests
(`test_knowledge_unit_extraction.py:293-400`) — the staged-generation model already
makes an interrupted L2 safe, just not cheap. If the user instead wants the cost
saving, the completion route has three hard preconditions, all of which must land
together: (a) write checkpoints from the default batch loop, (b) `clear_l2_checkpoints`
inside the publish transaction (`compile.py:406-454`), not after it, and (c) a guard
that an all-skipped resume returning an empty `list_staged_unit_ids_for_source` is
treated as "already published, recover" and **never** as a zero-unit extraction —
otherwise §26.3's no-zero-unit-publish guard retires the source's entire authoritative
unit set. Half-completing this is worse than the dead code.

**Batching recommendation for the synthesizer.** CP-1, CP-3(b) and CP-4 all reduce to
one primitive — *`layer_error` is overloaded and every status writer clobbers it*.
Fix that primitive once (`UNSET` sentinel + marker-preserving recovery predicate +
error-only writer) and all three collapse into a single coherent change. CP-3(a) is a
spec decision that needs the user, not code. CP-2's freeze half is independent and
cheap; its atomicity half should be merged into ENH-01 rather than shipped as a defect
fix. CP-5 is a scheduling decision (delete vs. complete), not a bug fix.
