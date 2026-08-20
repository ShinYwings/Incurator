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
