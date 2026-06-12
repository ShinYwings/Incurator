# Plan E Wave C Report

Date: 2026-06-12
Status: Completed; awaiting PM review before Wave D

## Scope

Wave C (Plan E P5) compared current and fixed-policy serving controls with
disposable, deterministic adaptive-serving mechanisms over the synthetic
serving stress corpus:

- the current deterministic router signals versus complexity-aware route
  selection, against always-local and always-most-complex controls;
- one-shot retrieval versus an evaluator-gated bounded correction, against an
  always-run-one-correction control;
- one-shot retrieval versus bounded iterative retrieval, against a single
  deterministic follow-up control;
- the fixed character block (`EvidencePack.evidence_block(max_chars=16000)`)
  versus budgeted progressive disclosure, against a fixed top-k control.

Every metric is hand-computable from frozen oracle labels. No provider, model
judge, production state, holdout partition, or network call was used. The runner
(`wave_c.py`) reads only the committed corpus and never opens any database.

## Results

### Complexity-Aware Routing

| Policy | Route accuracy | Task success | Total route tokens |
|---|---:|---:|---:|
| Complexity-aware | 1.00 | 1.00 | 10 |
| Always-local | 0.33 | 0.33 | 3 |
| Always-most-complex | 0.33 | 0.33 | 18 |

The deterministic classifier (broad-synthesis → `global`, multi-hop/chaining →
`iterative`, otherwise `local`) selected the correct route on all three measured
cases. Always-local was cheapest but wrong on the global and multi-hop queries;
always-most-complex was both wrong on the simple/global queries and the most
expensive policy. Complexity-aware routing matched every route at a token cost
between the two fixed controls.

This proves only that an explicit route policy over fixed routes can beat naive
fixed policies on a labeled set; the classifier here is a trivial regex, not a
learned model, and the labels are synthetic.

### Retrieval Sufficiency / Corrective Gate

| Policy | Task success | Correction rate |
|---|---:|---:|
| One-shot | 0.33 | 0.00 |
| Sufficiency-gated | 0.67 | 0.33 |
| Always-correct | 1.00 | 1.00 |

Gate quality against the independent `needs_correction` oracle: precision
`1.00`, recall `0.50`.

The gate corrected only the case its evaluator scored below the `0.5`
threshold (SF02), beating one-shot task success (`0.67` vs `0.33`) at one-third
the correction cost of always-correct. The adversarial case SF03 is an honest
false negative: the retrieval evaluator scored a one-shot pass at `0.8` while
the oracle marks it as needing correction (a contradicting span the evaluator
overrated), so the gate skipped the needed correction and the task failed. The
gate therefore did not match always-correct task success. Always-correct reached
`1.00` success but paid a correction on every query, including the one that did
not need it.

### Bounded Iterative Retrieval

| Case | One-shot success | One follow-up success | Bounded success | Bounded iterations |
|---|---:|---:|---:|---:|
| IT01 two-hop | no | yes | yes | 2 |
| IT02 three-hop | no | no | yes | 3 |
| IT03 four-hop (over budget) | no | no | no | 3 |

| Policy | Task success |
|---|---:|
| One-shot | 0.00 |
| One deterministic follow-up | 0.33 |
| Bounded iterative | 0.67 |

Bounded iterative retrieval completed the two- and three-hop tasks that one-shot
and a single follow-up could not, while never exceeding `1 + max_followups = 3`
retrievals. The four-hop adversarial case IT03 stopped at the iteration cap and
failed rather than looping unbounded — the intended bounded-failure behavior. A
single frozen snapshot per case kept `snapshot_consistent` true on every case;
no iteration mixed snapshots.

### Progressive Context Disclosure

| Case | Fixed-block recoverable recall | Fixed top-k recoverable recall | Progressive recoverable recall |
|---|---:|---:|---:|
| DC01 filler before relevant | 0.33 | 0.33 | 1.00 |
| DC02 filler then relevant | 1.00 | 0.50 | 1.00 |
| DC03 budget below corpus | 0.33 | 0.67 | 1.00 |

| Policy | Mean context precision | Mean recoverable recall | Task success |
|---|---:|---:|---:|
| Fixed character block | 0.63 | 0.56 | 0.33 |
| Fixed top-k | 0.58 | 0.50 | 0.00 |
| Progressive disclosure | 0.86 | 1.00 | 1.00 |

Progressive disclosure filled the budget by relevance and emitted a stable
expansion handle for every omitted item, so every expected relevant record
stayed recoverable (`1.00` recall) on all three cases. The fixed character block
greedily filled in retrieval order and broke silently on overflow, dropping
relevant records with no omission signal (DC01, DC03). Fixed top-k truncated to
the first two items and never reported what it cut. Progressive disclosure also
held the highest mean context precision because it preferred relevant records
over filler within the same budget.

The budget is a hand-computable proxy; it maps to the production
`evidence_block` `16000`-character default but was scaled to small synthetic
records so the arithmetic is checkable by hand.

## Scoped Decision Posture

### Complexity-Aware Routing

`benchmark-later`.

- Evidence: an explicit route policy matched all labeled routes and avoided the
  most expensive fixed policy, but the classifier is a trivial deterministic
  regex over synthetic labels with no measured classifier overhead or
  representative query distribution.
- Downstream owner: Program 3.
- Revisit trigger: rerun with a learned/calibrated complexity classifier, real
  route/task labels, measured classifier latency, and a representative query mix
  before adopting any routing change.

### Retrieval Sufficiency / Corrective Gate

`benchmark-later`.

- Evidence: the gate beat one-shot success at a lower correction rate than
  always-correct, but its recall was only `0.50` because a retrieval evaluator
  can overrate a one-shot pass (SF03). Web-fallback correction is also outside
  Incurator's vault-evidence contract and was not modeled.
- Downstream owner: Program 3.
- Revisit trigger: calibrate the evaluator against labeled sufficiency examples,
  bound the correction action to vault evidence and a single snapshot, and prove
  the gate matches always-correct task success at materially lower cost without
  harming direct-factual tasks.

### Bounded Iterative Retrieval

`benchmark-later`; adopt only the explicit-bound invariant as a downstream
contract candidate.

- Contract candidate: any executed follow-up retrieval must have an explicit
  maximum iteration count, a per-iteration budget, a success/stop oracle, and a
  single stable snapshot across all iterations; rendered-but-unexecuted
  follow-ups do not count as iteration.
- Evidence: bounded iteration completed multi-step tasks one-shot could not,
  stayed within the `3`-retrieval cap, failed the over-budget case instead of
  looping, and never mixed snapshots.
- Downstream owner: Program 3.
- Revisit trigger: run on a trusted substrate with real follow-up generation
  (an LLM forms the follow-up query) and measure generated-query drift, repeated
  evidence, and cost against a deterministic follow-up control.

### Progressive Context Disclosure

`adopt-contract` candidate, pending P7 holdout/provenance audit.

- Contract candidate: bounded context serving must declare omissions and expose
  stable expansion handles that resolve to exact evidence within one snapshot; a
  silent fixed character cutoff that drops relevant evidence is a rejected
  default.
- Evidence: progressive disclosure kept every omitted relevant record
  recoverable (`1.00` recall) and held the highest context precision per token,
  while the fixed block and fixed top-k silently dropped relevant evidence.
- Downstream owner: Program 3 (`F_agent_context_service.md`).
- Revisit trigger: validate handle resolution and omission accuracy against
  source-edited and deleted snapshots, and confirm the bounded disclosure
  invariant holds on the untouched holdout in P7.

## Rejected Defaults

- Always routing to the most complex (or always the cheapest) fixed route.
- Treating an uncalibrated retrieval-evaluator score as a sufficient sufficiency
  signal.
- Always running a correction pass regardless of evidence quality.
- Any unbounded follow-up loop, or counting a rendered-but-unexecuted follow-up
  as an iteration.
- A fixed context character cutoff that drops relevant evidence with no omission
  signal or recovery handle.
- Interpreting these synthetic-label serving results as production approval.

## Limitations

- The serving stress corpus is synthetic and small; the untouched holdout
  (`HQ01`) remains inaccessible until P7.
- The routing classifier and sufficiency evaluator are deterministic stand-ins,
  not learned or calibrated models; classifier/evaluator overhead and real query
  distributions are unmeasured.
- Follow-up queries in the iterative comparison are pre-seeded hops, not
  LLM-generated; generated-query drift and repeated-evidence risk are untested.
- Token and character counts are hand-computation proxies, not real tokenizer or
  provider costs; latency was not measured because no provider was called.
- Snapshot consistency was enforced by construction (one frozen snapshot per
  case); cross-snapshot invalidation under live source edits/deletes remains
  unmeasured and blocks mechanism adoption.
