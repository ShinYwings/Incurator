# v0.62.0 Evidence Ledger — Resumable L2

Created at P0, before any implementation code. Plan: `06_resumable_l2.md`.

## 1. Rollback anchor

- Branch `release/v0.62.0`, cut from `master` at `96357ab`.
- **No destructive DB operation is planned.** The live vault DB
  (`.cache/vaults/13ed51f8b06cb88e/state.sqlite`, 233 MB) is never written by
  this work. All measurement runs against copies in the scratchpad
  (`f2.sqlite`, `audit_base.sqlite`).
- No schema migration (see §3), so there is nothing to roll back but code.

## 2. Dirty worktree at P0

`git status --short` clean at branch creation. Uncommitted work belonging to
other agents: none.

## 3. Schema reality (pre-fact-checked against the live DB)

`knowledge_units`: `id, unit_type, canonical_name, statement, source_span_ids,
source_id, confidence, truth_status, atom_node_id, prompt_run_id, created_at,
updated_at, semantic_hash, support_status, support_reason, formula_status,
retired_at, generation_id`. `formula_status` is `NOT NULL DEFAULT
'not_applicable'` (`db/schema.py:422`).

`prompt_runs`: `trace_id, prompt_id, prompt_version, family, role,
model_provider, model_name, input_hash, output_hash, validator_status,
validator_errors, retry_count, source_ids, source_span_ids, curate_spec_hash,
query_trace_id, latency_ms, created_at, finished_at`.

**No migration required.** Every field the design needs already exists. This is
the finding that makes the plan small, and it is why there is no P2 schema phase.

## 4. Live baseline

- 5,451 `knowledge_units`; 4,174 `claim_supports`; 11,461 `source_spans`.
- 1,811 `curator.knowledge_unit_extract` runs — latency **median 18,631 ms**,
  mean 22,747 ms, max 132,271 ms. All `antigravity-cli`, contract `v3`.
- Source 45 (Hartley): 8,905 spans, `l2_status='pending'`, 0 units, 277 batches.

## 5. Pre-change compiler audit (the P4 diff baseline)

`run_compiler_audit` on `scratchpad/audit_base.sqlite`, snapshot at
`scratchpad/audit_before.json`, **sha256
`f5de509f5855f73d87060649b6e214a6ef6ac49ee6c4d9f32a43c25ec9e45674`**:

| finding | count |
|---|---|
| unsupported_claims | 2508 |
| failed_claims | 892 |
| stale_claims | 0 |
| dangling_supports | 0 |
| formula_inconsistencies | 0 |
| staged_leftovers | 0 |
| duplicate_candidates | 49 |
| **publish_blocking** | **0** |

`publish_blocking = 0` **confirms the F1 defense empirically on real data**: the
live vault has 2,508 unsupported and 892 failed claims and still blocks nothing.
P4's three filters must leave this snapshot byte-identical.

## 6. P0 finding — the stop condition fired, and why the design survives

The plan's first stop condition was: *"the P0 baseline shows `input_hash` is not
stable for a source other than 45 → the design is wrong."* It fired. Across
attempt pairs on sources 37, 36, 34, 18, 12, 25, **no hash set was identical**
(Jaccard 0%–88%).

**Cause, measured, not guessed.** `_spans_block` renders each span's **id** into
the prompt, so `input_hash` depends on span identity. When L1 re-runs it mints
new span ids, and every batch hash changes. The correlation is direct:

| source | attempt pair | span ids same | hashes same |
|---|---|---|---|
| 45 | 08-18 → 08-19 | 14.7% | 12.7% |
| 45 | 08-19 → 08-20 | **100%** | **100%** |
| 45 | 08-20 → 08-20 | **100%** | **100%** |
| 37 | 08-05 → 08-08 | 99.7% | 21.7% |
| 36 | 08-04 → 08-05 | 39.2% | 23.4% |
| 34 | 08-02 → 08-18 | 53.3% | 25.7% |

Source 45's own first pair fails too — the same source, before and after its L1
re-run. So this is not a property of Hartley; it is a property of span identity.

A near-miss is instructive: source 37 at 99.7% span overlap still shares only
21.7% of hashes. **One changed span invalidates every batch after it**, because
the packer shifts. Partial span reuse buys almost nothing — which is correct
behavior for a changed source, not a defect.

**Restricting to attempt pairs with an identical span set** (23 pairs across the
vault): **18 of 23 have identical hash sets.** The 5 that do not are all one
pattern — validation-failure splits. `_split_batch_for_retry` halves a failed
batch by `_span_len` midpoint and recurses, recording each child as its own
prompt run:

| source | A batch sizes | B batch sizes | relation |
|---|---|---|---|
| 26 | [16, **24**, **33**, 57] | [16, 57] | B ⊆ A; 24+33 = the 57 split, both `repaired retry=1` |
| 11 | [29] | [**13**, **17**, 29] | A ⊆ B; 13+17 = the 29 split |
| 20 | [19] | [**10**, **11**, 19] | A ⊆ B |
| 12 | [11, **22**, **23**, 44, 52, 54] | [11, 44, 52, 54] | B ⊆ A |
| 34 | 17 runs | 15 runs | B ⊆ A |

**In every case the two sets are in a subset relation — never crossing, never
disjoint.** Every full-batch hash reproduces; the differences are strictly extra
sub-batch runs. And `_split_batch_for_retry` is itself deterministic, so a split
child's hash is reproducible too.

**Conclusion**: D1 was stated too strongly, not wrongly. The corrected statement
and the D4 refinement it forces are folded into the plan.

## 7. P5 live acceptance — FAILED. The feature does not save Hartley.

Run: `wiki jobs run` against the real vault, job 76, source 45, 2026-08-20
20:31→21:53 UTC. The branch code was live (editable install verified against the
working tree).

**What worked.** Per-batch persistence is real and was observed live: 45 units
were in `knowledge_units` after 4 batches, where the old code holds 0 until all
277 finish. Extraction then completed **277/277, every run `validator_status=ok`,
81.5 minutes of provider latency**.

**What happened next.** The staged compile hit `Antigravity capacity exhausted
(429)`. `compile.py:501` runs `_discard_staged_units(gen_id)`, which is
`DELETE FROM knowledge_units WHERE generation_id = ?`. Generation `GEN-d0f7ef93`
is `discarded` and **source 45 has 0 knowledge_units — deleted, not retired**.

So the 81 minutes were lost exactly as in the three previous attempts. A resume
finds nothing, because the rows a resume would adopt no longer exist.

**This is my design error, not an unlucky run.** The briefing for this Arena
said the sharpest case was *"not 'interrupted midway' but 'finished the
expensive part and threw it away'"* — and the design I wrote addresses only
interruption **during** extraction. `compile.py:421` stamps every extracted unit
with the staged `gen_id` before the publish gate; the failure handler then
deletes everything carrying that id. Per-batch persistence moves the work out of
memory and into rows that the very next failure handler removes.

**The plan's own §1 definition of done is therefore not met** for the case the
roadmap item exists for. The unit tests pass because they exercise
`extract_knowledge_units` directly and never reach `compile.py`'s discard.

**Precise scope of a fix.** In the except handler, rows matching
`generation_id = gen_id` are exactly this run's extraction output:
`compile.py:421` is the only writer of that id outside the publish transaction,
and `reconcile_source`'s carry-forward runs inside `with db.connect(...)`, which
rolls back before the handler runs. Resetting them to `generation_id = NULL`
instead of deleting them would leave precisely the rows the resume predicate
looks for.

**Why this is not being done unilaterally.** The approved plan's Explicit
Non-Goals say: *"No change to publish semantics. §26.3 staging, the publish gate,
the atomic flip, and `reconcile_source` are untouched."* Changing what a staged
discard does is a change to staging semantics. It needs the user's decision.

**Also affected: the CHANGELOG as written overclaims.** It cites the 277-batch
loss as the motivating measurement for a feature that does not prevent it. Either
the fix lands, or that entry must be rewritten to say the feature covers
interruption during extraction only.

## 8. P5 live acceptance — PASSED after the §7 fix

`_release_staged_units_for_resume` shipped, then the same job was run again
against the real vault.

**Cold run (2026-08-21 06:39→08:04 UTC).** 277 extraction calls, 85.0 minutes
wall, 85.0 minutes of provider latency, every run `ok`. The staged compile failed
again — a different error this time (see §9). **5,358 knowledge_units survived
with `generation_id IS NULL`**, all 5,358 matching the adoption predicate. Under
the deleted-rows behaviour of §7 this number was 0.

**Resume run.** `wiki jobs rerun 76` then `wiki jobs run`:

| | cold | resume |
|---|---|---|
| extraction calls | **277** | **0** |
| wall clock to 277/277 | **5,100 s** | **~120 s** |
| provider time | 85.0 min | 0 |

The call count was measured against a baseline snapshot taken immediately before
the resume: `prompt_runs` for `curator.knowledge_unit_extract` on source 45 was
**1941 before and 1941 after**. The plan's §1 definition of done — *"the
restarted run issues LLM calls only for the batches that had not completed"* —
is met exactly: none had.

For contrast, every cold attempt this source has ever made:

| window | calls | wall | provider |
|---|---|---|---|
| 08-20 11:30→12:56 | 277 | 85.8 m | 86.0 m |
| 08-20 16:19→18:47 | 461 | 147.8 m | 139.3 m |
| 08-20 20:31→21:52 | 277 | 81.4 m | 81.5 m |
| 08-21 06:39→08:04 | 277 | 85.0 m | 85.0 m |

## 9. Hartley is still unpublished, now behind a DIFFERENT blocker

Not a regression of this work, and not in scope for v0.62.0.

The staged compile now fails in graph extraction: `curator.entity_relation_extract@v2`,
2 of 5 calls `failed` with

> `Antigravity CLI exited 1: permission check failed for command "python3 -c '…
> transcript_full.jsonl … content.find("Knowledge units:") …'"`

The model tried to recover its own prompt input by reading the CLI's transcript
log from disk. This is the v0.60.0 failure class — the model computing an answer
instead of returning one — but **the schema is not the cause here**: checked
directly, `curator.entity_relation_extract`'s output model flattens cleanly and
`_schema_for` therefore sends it. Graph extraction is also already batched by
`client_optimal_chunk_chars`, so it is not an input-size overflow either.

What is left is the agy CLI model electing to shell out even under a structured-
output contract, with a denied command failing the entire compile. That is
ROADMAP "agy sandbox", which now has hard evidence.
