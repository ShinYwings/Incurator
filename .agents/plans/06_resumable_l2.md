# v0.62.0 Master Implementation Plan — Resumable L2 Extraction

Date: 2026-08-21
Status: APPROVED (user, 2026-08-21). P0 complete — see
`06_resumable_l2_evidence.md`. D1 and D4 amended by P0 findings, marked inline.

Arena record: `.agents/plans/resumable_l2_arena/`
(`00_problem.md`, `01_proposal_lead_architect.md`, `02_critique_redteam.md`,
`03_defense_measured.md`). ROADMAP item 5.

## 1. Objective

An interrupted L2 extraction must not re-pay for batches it already completed.

**Definition of done**: source 45 (Hartley, 8,905 spans, 277 batches) is
interrupted mid-extraction, restarted, and the restarted run issues LLM calls
only for the batches that had not completed — verified by counting
`prompt_runs` rows for the second attempt. The published unit set is identical
to what an uninterrupted run produces.

The cost this removes is measured, not estimated: Hartley completed **all 277
batches twice** (08-19, 08-20) and lost both at the publish step to a 429. At the
measured median extract latency of **18,631 ms**, that is ~86 minutes of provider
work discarded per attempt.

## 2. Explicit Non-Goals

- **No staging table, and no new column.** §4 shows the resume key already
  exists in the schema.
- **No change to publish semantics.** §26.3 staging, the publish gate, the
  atomic flip, and `reconcile_source` are untouched.
- **No resume across a contract or configuration change.** A changed prompt
  template, contract version, or `curate_spec_hash` re-runs everything. That is
  correct, not a limitation.
- **No resume of an already-published source.** A forced recompile re-pays in
  full, exactly as today.
- **Not L3.** `run_l3_from_existing_atoms` has no per-step heartbeat; separate item.

## 3. Strict Quality Conditions & Release Gates

- A resumed run's published unit set is **identical** to an uninterrupted run's —
  asserted by test, not inspected by eye.
- Added persist cost stays within the measured envelope: **≤ 25 ms median per
  batch** (measured 8.9–17.9 ms), i.e. ≤ 0.15% of an 18.6 s batch.
- `run_compiler_audit` on the live DB returns a **byte-identical report**
  before and after the reader filters of P4. The filters must be provably inert
  today.
- `scripts/backend-check pytest`, `ruff`, `mypy` green; `npx vitest run -c
  ./plugin/vitest.config.ts` green.
- Testbed smoke: `VAULT_ROOT=testbed wiki add` → interrupt → re-run → `wiki lint`
  exits zero.

## 4. Locked Design Decisions (Arena Consensus)

**D1 — The resume key is `prompt_runs.input_hash`. No schema change.**
`input_hash` is `sha256(system + user messages)[:16]` of the fully rendered
prompt (`render.py:78`), so it covers the batch text *and* the template. It is
strictly stronger than the `_config_key` the proposal invented, which is why F3
is dissolved rather than answered.

Measured on the live DB across Hartley's three attempts:

| attempt | runs | distinct `input_hash` |
|---|---|---|
| 08-19 | 571 | **277** |
| 08-20 (clean) | 277 | **277** |
| 08-20 pm | 461 | **277** |

The three hash sets are **100% identical** (277 ∩ 277 ∩ 277 = 277). The batch
identity is stable across attempts; the surplus runs are retries of the same
277 batches.

> **AMENDED AT P0 (2026-08-21) — this was stated too strongly.** The stop
> condition fired: no other source reproduces identical hash sets. The cause is
> measured: `_spans_block` renders each span's **id** into the prompt, so
> `input_hash` depends on span identity, and an L1 re-run mints new ids. Source
> 45's own 08-18 → 08-19 pair fails too (14.7% span overlap → 12.7% hash
> overlap), so this is a property of span identity, not of Hartley.
>
> **Corrected D1**: `input_hash` is a stable batch identity **given an unchanged
> span set** — which is exactly the condition a resume runs under. Restricted to
> the 23 attempt pairs vault-wide that share an identical span set, **18 have
> identical hash sets and the other 5 are in a strict subset relation**, the
> extras being validation-split sub-batches. No pair crosses or is disjoint.
>
> A changed span set correctly re-runs everything. Note the sharp edge, measured
> on source 37: **99.7% span overlap still shares only 21.7% of hashes**, because
> one changed span shifts the packer and invalidates every batch after it.
> Partial span reuse buys nothing; this is correct for a changed source.
> Full detail in `06_resumable_l2_evidence.md` §6.

**D2 — Resume is keyed on the batch, never on the span or the batch index.**
Both alternatives were measured and both are wrong:
- *batch index* — `optimal_chunk_chars` changes the batch count
  (60000→12, 32000→23, 16000→46, 8000→93), so an index means nothing across a
  provider change (§5a of the briefing).
- *span coverage* — in Hartley's clean 277-batch run, **1,790 of 8,692 spans
  (20.6%) legitimately appear in more than one batch**, with 0 duplicate input
  hashes. A span-keyed resume would have skipped real work. `input_hash` is
  immune to this because it hashes the batch, not its members.

**D3 — Persist each batch as it completes.** `_persist_units` moves inside the
loop. Measured on a copy of the live 233 MB DB at Hartley's real shape: 8.9 ms
median (32 units/batch) to 17.9 ms (93 units/batch), against an 18.6 s median
LLM call — **0.05–0.1%**. Whole-run: 2.5–5.0 s added to an 86-minute phase.
Lock granularity improves (277 × ~9 ms instead of one × 0.5–1.3 s).

**D4 — The skip predicate.** Before issuing batch *B*, render it and look for a
prior run with: `input_hash = H(B)`, `prompt_id||'@'||prompt_version =
PROMPT_CONTRACT_VERSION`, `curate_spec_hash =` current, **`validator_status IN ('ok','repaired')`**,
whose knowledge_units are still present with **`generation_id IS NULL AND
retired_at IS NULL`**. If found, skip the LLM call and adopt those unit ids.

The `generation_id IS NULL` clause is what makes a published source
non-resumable (D-non-goal 4): published units belong to the authoritative
generation and must never be re-adopted into a new one.

> **REFINED AT P0.** The check goes at the top of **`_run_batch_with_retry`**,
> not at the top of the batch loop. P0 found that the five same-span attempt
> pairs whose hash sets differ do so only because of validation splits — a batch
> that failed and succeeded as two halves records the children as their own
> prompt runs, and the failed parent is not `ok`. Checking only at the loop level
> would re-pay every such batch in full. `_split_batch_for_retry` is
> deterministic (midpoint by `_span_len`), so a child's `input_hash` is
> reproducible exactly like its parent's, and one predicate placed at the
> recursion entry covers both.
>
> **`repaired` counts as success.** `finish_prompt_run` writes `ok` only when
> `retry_count == 0` and `repaired` when a JSON-repair retry was used — both are
> validated output. The live vault has 57 `repaired` extract runs carrying **687
> knowledge units**; a predicate keyed on `'ok'` alone would re-pay every one of
> them. The predicate is `validator_status IN ('ok','repaired')`.

**D5 — What a resumed run returns.** `extract_knowledge_units` returns the union
of adopted ids and newly persisted ids, accumulated **in the loop**, exactly as
today. It never queries "staged units for this source."

This is the specific defect that killed the v0.51.1 mechanism: its resume path
returned `list_staged_unit_ids_for_source`, which filters `generation_id IS NULL`
and is therefore empty after a successful publish — a resumed run would have
attributed zero units to a fresh generation and retired the source's entire
authoritative set under §26.3. Accumulating in the loop cannot reproduce it.

**D6 — `_discard_unpublished_units` becomes conditional, not unconditional.**
Today it deletes every `generation_id IS NULL` unit for the source at the top of
`extract_knowledge_units`. It must instead keep the units that D4 can adopt and
delete the rest — those whose prompt run does not match the current contract or
`curate_spec_hash`, and those citing spans that no longer exist. The deletion
order (claim_supports first, then units) is already correct and stays.

**D7 — Three reader filters, because partials now persist by design.**
The F1 audit (27 reads; 15 unfiltered) found the exposure is telemetry-only —
partials are **not** publish-blocking, verified three ways in
`03_defense_measured.md` — but three table-wide scans do surface them:

| site | fix |
|---|---|
| `claim_support.py:490` (`active`) | add `generation_id IS NOT NULL` |
| `claim_support.py:520` (`semantic_hash` dedup) | add `generation_id IS NOT NULL` |
| `synthesis_audit.py:159` (`SELECT * FROM knowledge_units`, no filter at all) | add `generation_id IS NOT NULL` |

Without D7, an interrupted Hartley emits ~25,000 INFO lines from `wiki lint` —
a usability failure, not a correctness one, but the whole point of this feature
is that interruption stops being exceptional.

**D8 — `reconcile_source` and `materializer` are NOT changed.** Both are already
safe and the reason is ordering, not luck: `compile.py:418` stamps every
returned unit with the staged `gen_id` *before* `reconcile_source` runs at `:449`,
and `materializer.py:269` joins `compiler_generations` on `generation_id`, so a
NULL cannot match. **The search corpus cannot see a partial.** Touching either is
out of scope and would be the riskiest possible edit.

## 5. Scope Exclusions & Stop Conditions

**Exclusions**: L3 heartbeat; the `wiki add --help` text still claiming L1 runs
without an LLM call; ROADMAP 1/2 (formula recovery and re-derivation).

**Stop conditions — halt and ask:**
- The P0 baseline shows `input_hash` is *not* stable for a source other than 45.
  D1 rests on one source measured three times; if a second source disagrees, the
  design is wrong.
- The P4 before/after audit reports differ on the live DB. The filters are
  asserted inert; a difference means an assumption in §4/D7 is false.
- Any change appears necessary in `reconcile_source`, `_run_publish_gate`, or
  `materializer`. That contradicts D8 and means the analysis was wrong.
- `_discard_unpublished_units` (D6) would delete a unit the skip predicate would
  have adopted, or vice versa.

## 6. Evidence Ledger

Recorded before any code is written; the full ledger lands in
`.agents/plans/06_resumable_l2_evidence.md` at P0.

- **Rollback anchor**: `master` at the commit preceding branch
  `release/v0.62.0`. No destructive DB operation is planned; the live DB is
  never written by this work — all measurement runs against
  `scratchpad/f2.sqlite`, a copy.
- **Schema reality**: `knowledge_units` carries `generation_id`, `retired_at`,
  `prompt_run_id`, `semantic_hash`, `formula_status NOT NULL DEFAULT
  'not_applicable'`. `prompt_runs` carries `input_hash`, `prompt_id`,
  `prompt_version`, `curate_spec_hash`, `validator_status`, `latency_ms`. **No
  migration is required** — this is the finding that makes the plan small.
- **Live baseline** (`.cache/vaults/13ed51f8b06cb88e/state.sqlite`, 233 MB):
  5,451 knowledge_units, 4,174 claim_supports, 11,461 source_spans, 1,811
  `knowledge_unit_extract` runs (median 18,631 ms / mean 22,747 / max 132,271).
  Source 45: 8,905 spans, `l2_status='pending'`, 0 units.
- **Dirty worktree**: `.agents/` only at time of writing; verify again at P0.

## 7. Execution Phases

- **P0 — Research & measured baseline. DONE.** D1 did **not** reproduce
  naively; the stop condition fired and the cause was measured rather than
  guessed (span identity, not Hartley). D1 restated and D4 refined above;
  evidence in `06_resumable_l2_evidence.md`. Audit baseline captured at
  `scratchpad/audit_before.json`, sha256 `f5de509f…e45674`, **publish_blocking =
  0 on the live vault** — the F1 defense confirmed on real data.
- **P1 — Contract specification (docs-first).** `SYSTEM_BEHAVIOR.md` gains the
  resume predicate (D4) and the return-value rule (D5); `SCHEMA.md` records that
  `generation_id IS NULL` now denotes a *durable* in-progress extraction and
  names the three filtered readers. Then the `_KR.md` guides. **No schema
  change, so no separate approval stop here** — but P1 lands before P2.
- **P2 — Failing tests (TDD).** (a) a resumed run issues LLM calls only for
  incomplete batches; (b) resumed and uninterrupted runs publish identical unit
  sets; (c) a changed prompt template re-runs every batch; (d) an
  already-published source is not resumed; (e) D6 keeps adoptable units and
  deletes the rest. Test (a) must interrupt with `KeyboardInterrupt` — a
  per-page `except Exception` let an earlier resume test pass against unfixed
  code. *Verify: all five fail for the right reason.*
- **P3 — Core logic.** Per-batch persist (D3), the skip predicate (D4),
  conditional discard (D6). *Verify: P2 green; `ruff`; `mypy`.*
- **P4 — Reader filters (D7).** Three filters plus one structural test asserting
  no table-wide read of `knowledge_units` outside the ingest path omits
  `generation_id`, in the manner of `test_workspace_hygiene.py`. *Verify:
  before/after `run_compiler_audit` reports are byte-identical.*
- **P5 — Testbed smoke + live acceptance.** `VAULT_ROOT=testbed wiki add`,
  interrupt, re-run, `wiki lint`. Then the real target: **run Hartley and let it
  resume.** *Verify: second attempt's `prompt_runs` count < 277.*
- **P6 — Release.** Version bump to **0.62.0** across `pyproject.toml`,
  `package.json`, `manifest.json`, `package-lock.json` (both version fields),
  and the **four spec titles** to `v0.62` — the minor line changes, so
  `test_spec_sync.py` requires it. `CHANGELOG.md`. Delete this plan. PR.

**Version rationale**: new user-facing capability (an interrupted ingest now
resumes), so Minor under the 0.x criteria — not Patch, despite touching no
schema.
