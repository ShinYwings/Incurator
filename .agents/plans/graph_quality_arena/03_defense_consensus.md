# Arena Defense And Consensus: Auditable Graph Quality

Date: 2026-06-11 | Agent Persona: system_synthesizer

## 1. Resolved Decisions

1. Plan C consumes only a fully published Plan B claim generation with verified
   or explicitly allowed support states.
2. Resolution separates aliases, ambiguous alias candidates, merge proposals,
   accepted merges, rejected decisions, and reversals.
3. Similarity never auto-merges. Exact/high-certainty aliasing still requires
   type/context/contradiction/`avoid_merges` guards.
4. Accepted merges preserve origin identity and downstream rewrite lineage so
   reversal can reconstruct the prior graph.
5. Relations aggregate claim-level support. Independent support is based on
   source lineage, not row count.
6. Unsupported/noisy/self-loop/bridge-risk relations become provisional or
   quarantined with reason codes and re-evaluation triggers.
7. Only active relations enter authoritative community construction.
8. Authored and extracted topology remain separate edge classes through
   weighting, auditing, and hierarchy construction.
9. Hierarchy selection is benchmark-driven and multi-metric. Seeded weighted
   Leiden is a candidate; filtered connected components is the explicit degraded
   fallback.
10. Community identity is content/config-derived, but correct restructuring wins
    over artificial id stability.
11. Community reports cite exact claim-level support and cannot fall back to the
    entire community span pool.
12. Quota is explicitly deferred. Artifact growth is measured only as duplicate
    amplification/compiler quality.

## 2. Required Implementation Contracts

- Static specs define resolution decision lifecycle, relation support lifecycle,
  edge classes/statuses, hierarchy config identity, report invalidation, and
  reversal behavior before code.
- Additive migration backfills current entities/relations as unresolved or
  unchecked; it does not infer accepted aliases or verified support.
- A graph audit proves endpoint integrity, support provenance, resolution
  lineage, quarantine reasons, hierarchy reproducibility, and report freshness.
- Adversarial fixtures cover synonyms, homonyms, multilingual names,
  abbreviations, copied-source support, contradictions, self-loops, noisy bridge
  edges, and one-source edit/delete.

## 3. Stop Conditions

- Stop if Plan B claim generations/support contracts are not merged.
- Stop if accepted merges cannot be reversed with complete lineage.
- Stop if hierarchy improves modularity while violating homonym, provenance,
  report-support, or giant-component gates.
- Stop if quota UI/limits enter the change.
- Stop after three repeated QA failures and return to planning through the
  rollback strategist.

## 4. Vulnerabilities & Flaws Resolved

- Prevented destructive similarity merges, support inflation, and noisy bridge
  edges from silently shaping communities.
- Made Plan-C graph/report broad-span fallback removal explicit.

## 5. Suggested Alternatives Adopted Or Rejected

- Adopted reversible resolution, quarantined topology, and measured hierarchy.
- Rejected unconditional Leiden adoption and quota scope creep.
