# Hierarchy Proposal: Measured Deterministic Weighted Communities

Date: 2026-06-11 | Agent Persona: graph_hierarchy_architect

## 1. Core Logic & Implementation

Benchmark hierarchy methods only after accepted aliases and active weighted
relations are available. Leiden is a candidate, not a completion criterion.

### Input graph contract

- Canonical entity ids after accepted alias resolution.
- Active edges only.
- Deterministic weights from relation-support policy.
- Authored topology and extracted topology retain separate edge kinds/weights.
- Stable sorted input and explicit seed/config hash.

### Candidate methods

1. Current connected components as baseline/degraded fallback.
2. Seeded weighted Leiden or equivalent modular partition.
3. Deterministic recursive partition/roll-up only while quality improves and
   minimum support thresholds are met.

### Required metrics

- giant-component ratio;
- modularity/partition quality with caveats;
- seed/rebuild stability;
- synonym/homonym fixture correctness;
- relation/support provenance coverage;
- orphan/singleton handling;
- report claim-support correctness;
- edit/delete incremental invalidation precision;
- downstream global-query metrics deferred to Program 3.

### Identity and reports

Community identity derives from level, sorted canonical members, active edge
support hashes, and algorithm config hash. Reports depend on exact entities,
active relations, and claim-support records. A hierarchy change retires stale
reports before synthesis can consume them.

### Degraded fallback

If the chosen hierarchy dependency is unavailable or quality gates fail, use
filtered connected components and mark the hierarchy mode/degradation explicitly.

## 2. Pros & Cons

### Pros

- Prevents one noisy edge from defining the whole global knowledge structure.
- Makes hierarchy reproducible and dependency-aware.
- Retains a deterministic dependency-free fallback.

### Cons

- Community stability is inherently sensitive to small graph changes.
- A hierarchy can look mathematically strong while being semantically poor.
- New algorithm dependencies need packaging and runtime validation.
