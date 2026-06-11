# Governance Proposal: Provenance, Cost, And Decision Safety
Date: 2026-06-11 | Agent Persona: provenance_and_risk_guardian

## 1. Core Logic & Implementation

Treat provenance, reproducibility, update behavior, and bounded resource use as
hard constraints, not secondary metrics.

### Candidate disqualification rules

Reject as a production default when a technique:

- cannot identify the exact evidence selected for an answer;
- silently merges source truth with generated context;
- requires unbounded traversal, summarization, or context;
- cannot define behavior after source edit/delete;
- improves aggregate score while materially regressing direct factual quality;
- depends on model-judge-only evaluation;
- introduces a framework/runtime dependency whose operational cost exceeds the
  measured benefit;
- cannot be reproduced under a pinned snapshot/config/model manifest.

### Decision record requirements

Every decision records:

- scope and confidence;
- reproduced failure addressed;
- evidence and counter-evidence;
- provenance and update implications;
- cost/latency/dependency impact;
- rejected alternatives;
- revisit trigger;
- downstream owner and specification location.

### Dependency policy

External code may be used in an isolated spike only after license, version,
runtime, and transitive-dependency review. Adoption of a mechanism does not imply
adoption of its reference framework.

## 2. Pros & Cons

### Pros

- Protects Incurator's source-truth and personal-vault constraints.
- Makes rejection decisions useful and revisitable.
- Prevents a benchmark win from silently becoming architecture authority.

### Cons

- Hard disqualification can reject high-performing but opaque techniques.
- Reproducibility requirements increase research overhead.
- Some provenance limitations may be mitigated only during later implementation.
