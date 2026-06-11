# Retrieval Proposal: Progressive Evidence Under Explicit Budgets
Date: 2026-06-11 | Agent Persona: retrieval_and_performance_architect

## 1. Core Logic & Implementation

Use four disclosure levels:

1. `manifest`: vault/source/layer/index health and compact topology.
2. `index`: ranked evidence cards with compact claims and locators.
3. `excerpt`: bounded supporting excerpts and nearby context.
4. `source`: exact raw source span/page/block and full provenance.

### Budget policy

- Resolve the target model tokenizer when available.
- Otherwise use a conservative estimator and mark `estimation_mode`.
- Reserve expansion tokens before initial packing.
- Enforce total, item-count, per-item, route, and optional source-diversity caps.
- Preserve the minimal support necessary for any included claim.
- Report omitted item count/reasons and issue expansion handles.
- Never cut a locator, provenance id, formula, code block, or citation boundary
  into a misleading fragment.

### Adaptive serving boundary

Complexity routing, corrective retrieval, graph expansion, and iterative
retrieval are internal strategies behind the same service contract. Each has
explicit maximum iterations, budgets, stop reasons, and degradation warnings.

## 2. Pros & Cons

### Pros

- Improves context precision per token and agent control.
- Allows agents to inspect compact evidence before paying for raw source.
- Keeps advanced retrieval strategies bounded and observable.

### Cons

- Token estimates vary across providers.
- Progressive calls add latency and client complexity.
- Bad omission/expansion ranking can hide critical evidence despite explicit
  reporting.
