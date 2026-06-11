# Evaluation Proposal: Frozen Multi-Layer Benchmark Contract
Date: 2026-06-11 | Agent Persona: evaluation_architect

## 1. Core Logic & Implementation

Evaluate techniques at the layer they claim to improve and at end-to-end task
level. Aggregate-only wins are invalid.

### Benchmark partitions

- Development fixtures for spike iteration.
- Frozen validation fixtures for decision making.
- Holdout fixtures not inspected during technique tuning.
- Adversarial fixtures for hard negatives, contradictions, homonyms, stale
  anchors, source changes, formulas, Korean queries, and provider degradation.

### Query/task families

- direct factual;
- source-scoped factual;
- associative/multi-hop;
- broad/global synthesis;
- contradiction/verification;
- agent task requiring progressive retrieval;
- update/delete/freshness;
- cross-client parity.

### Metrics

Retrieval:

- Recall@1/3/5, MRR, nDCG@10;
- hard-negative outrank count;
- expected span and multi-hop path recall;
- context precision/recall per token.

Evidence and answer:

- claim-level citation correctness and completeness;
- unsupported-claim and contradiction rate;
- exact locator resolution;
- selected evidence provenance completeness.

Operations:

- p50/p95 latency;
- tokens and model cost;
- index/build/update cost;
- stale-output behavior;
- deterministic repeatability.

### Controls

Every spike compares:

1. current unchanged baseline;
2. simplest plausible control;
3. candidate mechanism;
4. candidate with its claimed supporting components only when necessary.

Confidence intervals, run count, random seeds, model/provider versions, and
hardware/environment are recorded. Model judges are secondary and calibrated
against human-labeled samples.

## 2. Pros & Cons

### Pros

- Separates factual, associative, global, and agentic performance.
- Detects gains bought by provenance, cost, or direct-factual regressions.
- Creates reusable release gates for later programs.

### Cons

- Gold labels and human review are expensive.
- A private-vault benchmark cannot establish broad external generality.
- Some latency/cost comparisons vary by provider and need normalized reporting.
