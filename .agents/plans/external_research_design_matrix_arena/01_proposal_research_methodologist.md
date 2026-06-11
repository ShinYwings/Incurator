# Research Methodology Proposal: Failure-First Comparative Evidence
Date: 2026-06-11 | Agent Persona: research_methodologist

## 1. Core Logic & Implementation

Use a failure-first evidence chain. Research starts from a reproduced Incurator
failure, not from a candidate framework.

### Research unit

Each research unit is one versioned dossier:

```yaml
candidate_id: CAND-...
failure_ids: [F1, F4]
primary_sources:
  - url: ...
    claim: ...
    verified_scope: ...
hypothesis: ...
baseline: current_incurator
spike:
  fixture_ids: [...]
  independent_variable: ...
  controlled_variables: [...]
metrics: [...]
decision: adopt | benchmark | reject
decision_scope: ...
downstream_contracts: [...]
```

### Mandatory source hierarchy

1. Paper and official implementation/documentation.
2. Reproducibility artifacts and official benchmark definitions.
3. Independent comparisons only as secondary context.
4. Blogs, summaries, and model-generated descriptions cannot establish a claim.

### Research sequence

1. Reproduce and classify the target failure.
2. Write a falsifiable hypothesis before reading candidate results deeply.
3. Extract the candidate's actual mechanism and assumptions.
4. Define the smallest disposable spike that isolates that mechanism.
5. Freeze fixtures and measurement protocol.
6. Compare against the unchanged current baseline and a simple control.
7. Record result, limitations, and confidence.
8. Decide at the narrowest valid scope.

### Decision semantics

- **Adopt**: accept a design contract or invariant for downstream specs. This
  does not authorize production implementation in this program.
- **Benchmark**: retain as a candidate requiring later implementation behind a
  controlled experiment or requiring Program-2 substrate first.
- **Reject**: prohibit as the default or reject for the measured failure. Revisit
  only if the stated trigger changes.

## 2. Pros & Cons

### Pros

- Prevents solution-led research and framework cargo culting.
- Makes negative results durable and avoids repeated spikes.
- Preserves separation between research approval and implementation approval.
- Produces traceable inputs for Program-2 and Program-3 specs.

### Cons

- Requires disciplined failure reproduction before exciting experiments.
- Some mechanisms cannot be isolated cleanly from full framework behavior.
- Negative results may be model-, fixture-, or scale-specific and need careful
  rejection scope.
