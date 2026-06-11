# Quality Observatory Proposal: Reproducible Measurement Substrate

Date: 2026-06-11 | Agent Persona: observability_architect
Status: DRAFT PROPOSAL

## 1. Core Logic & Implementation

### Observatory boundary

The observatory records and compares system behavior. It must not silently
repair, rerank, rewrite, or reinterpret production output.

### Required identities

Every diagnostic run needs:

- `run_id`;
- `case_id` and oracle version;
- source/corpus snapshot id;
- DB schema and authoritative-state fingerprint;
- search index epoch/fingerprint;
- KRS/config hash;
- provider/model/prompt fingerprints;
- request identity and route;
- authoritative query transaction id when available.

### Required measurements

**Compiler and provenance**

- valid-span rate;
- claim support correctness/completeness;
- stale/duplicate authoritative record rate;
- unchanged rebuild idempotency;
- mutation invalidation precision/recall;
- failed-build partial-state count;
- authored-structure preservation;
- long-source exact-evidence recall.

**Retrieval**

- Recall@1/3/5;
- MRR and nDCG@10;
- hard-negative outrank count;
- expected source-span/path recall;
- route selection accuracy;
- context precision/recall per token;
- degradation frequency.

**Answer and clients**

- citation correctness/completeness;
- unsupported and contradictory claim rates;
- locator-resolution success;
- normalized evidence parity;
- agent task success;
- p50/p95 latency, token use, and model cost.

### Report shape

Reports must be split by query/task family and execution mode:

```text
deterministic provider-free
full-quality configured providers
explicit degraded modes
human-reviewed semantic sample
```

No aggregate-only "quality improved" claim is admissible.

### Minimum Program-1 implementation candidates

After specification approval, Program 1 may implement only substrate needed to
make later changes measurable:

- one authoritative end-to-end query transaction or an explicit parent/child
  trace contract;
- stable snapshot/config/model identities;
- structured trace export;
- evaluation runner and frozen holdout support;
- normalized cross-client trace/evidence inspection;
- critical provenance adapter repair only if measurement is otherwise invalid.

These are candidates, not pre-approved code changes. The Failure Atlas must show
why each is necessary.

### Retention and privacy

- Evidence bundles must default to local testbed data.
- Live-vault excerpts require explicit approval and redaction rules.
- Large binary/source copies do not belong in metric reports.
- Exact evidence may be referenced by stable local identities and hashes.

## 2. Pros & Cons

### Pros

- Gives Programs 2 and 3 a shared regression oracle.
- Makes quality claims comparable across providers and releases.
- Makes degraded behavior visible rather than silently accepted.

### Cons

- Trace/schema additions can become invasive if not tightly scoped.
- Model/provider fingerprints do not guarantee perfectly repeatable outputs.
- Metric volume can obscure critical failures without a concise classification
  layer.
