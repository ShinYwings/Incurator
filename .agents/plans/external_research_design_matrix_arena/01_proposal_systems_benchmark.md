# Systems Benchmark Proposal: Disposable Mechanism Spikes
Date: 2026-06-11 | Agent Persona: retrieval_systems_engineer

## 1. Core Logic & Implementation

Build disposable, isolated spikes outside production paths. A spike may read a
frozen exported fixture and emit evaluation artifacts, but it may not mutate
`state.sqlite`, production specs, plugin behavior, or runtime configuration.

### Spike waves

**Wave A — Retrieval-unit and evaluation controls**

- contextual chunks versus current chunks and deterministic heading-context
  control;
- current hybrid baseline versus lexical-only and vector-only controls;
- RAGChecker/ALCE/KILT-inspired diagnostics adapted to exact vault evidence.

**Wave B — Graph and hierarchy mechanisms**

- current depth-two memory paths versus passage/entity PPR;
- current connected components versus denoised/seeded hierarchy candidates;
- current global route versus query-relevant community selection;
- seed retrieval versus graph-guided expansion/organization.

**Wave C — Adaptive and agentic serving**

- fixed route versus measured complexity routing;
- one-shot retrieval versus sufficiency-gated corrective retrieval;
- one-shot retrieval versus bounded iterative retrieval;
- fixed context block versus progressive disclosure simulation.

**Wave D — Conditional document understanding**

- current formula extraction versus selective recovery on proven-loss fixtures;
- reject whole-corpus heavy recovery unless measured benefits justify it.

### Spike artifact contract

Each spike emits:

- immutable fixture manifest and hashes;
- exact baseline and candidate configuration;
- command/environment manifest;
- raw per-query results;
- metric summary by family;
- cost/latency/update report;
- provenance audit;
- failure analysis and decision recommendation.

## 2. Pros & Cons

### Pros

- Isolates mechanisms without importing entire frameworks.
- Keeps research reversible and production paths untouched.
- Makes later implementation choices evidence-based.

### Cons

- Isolation may understate integration benefits or operational costs.
- Disposable code can drift from production semantics.
- Graph candidates may require trusted Program-2 graph inputs before final
  conclusions.
