# Retrieval Quality Proposal: Measured Hybrid RAG+DAG Serving

Date: 2026-06-11 | Agent Persona: retrieval_architect
Status: DRAFT PROPOSAL

## 1. Core Logic & Implementation

### Baseline rule

Keep lexical/vector/RRF/rerank as the factual/local baseline until the frozen
Program 1/2 quality suite proves a candidate improves a reproduced failure.
Current constants and route heuristics are not tuned from anecdotes.

### Query-family policy

Evaluate and route separately:

- exact lexical and identifiers;
- Korean/CJK and substring-heavy queries;
- paraphrase/vector;
- formula/symbol;
- direct factual/local;
- source-scoped;
- associative/multi-hop;
- global synthesis;
- contradiction/verification;
- degraded providers.

### Candidate serving techniques

Benchmark, do not pre-adopt:

- deterministic context-enriched source chunks;
- graph-guided expansion/organization after hybrid seeds;
- passage/entity PPR for associative tasks;
- selected-community local/global/DRIFT-like flows;
- sufficiency-gated corrective retrieval;
- complexity-gated bounded iterative retrieval.

### Route constraints

- `local`: factual baseline; graph/agentic additions cannot reduce direct factual
  quality beyond approved tolerance.
- `source-section`: query-rank within scope and enforce a bounded result budget;
  exact source expansion remains available on demand.
- `global`: select query-relevant synthesis/reports; never load all standing
  global records blindly.
- `explore`: execute bounded follow-up retrieval only when complexity/sufficiency
  policy permits; record stop reason and all added evidence.

### Selection and budget

Candidate retrieval and final evidence selection are separate:

```text
retrieve broad bounded candidates
  -> enforce policy/freshness/truth
  -> diversify and score
  -> select within route/item/token budgets
  -> expose omissions and expansion handles
```

Every selected item records ranking contributions and why it survived policy and
budget selection.

### Required metrics

- Recall@1/3/5, MRR, nDCG@10;
- hard-negative outrank count;
- expected source-span and multi-hop path recall;
- route selection accuracy;
- context precision/recall per token;
- degraded-mode frequency;
- p50/p95 retrieval and pack latency;
- citation and end-to-end agent-task metrics.

## 2. Pros & Cons

### Pros

- Preserves strong factual retrieval while improving targeted complex tasks.
- Makes graph/agentic retrieval earn its complexity.
- Keeps global/source routes relevant and bounded.

### Cons

- Route-specific evaluation and tuning are expensive.
- Bounded iterative retrieval adds latency and stop-rule complexity.
- Some graph candidates may be rejected despite promising anecdotal results.
