# Lead Architect Proposal: Staged Evidence Compiler Boundary

Date: 2026-06-11 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

Plan B must establish one source-pair compiler boundary:

```text
immutable source evidence
  -> candidate claims/formulas
  -> minimal-support validation
  -> staged generation
  -> atomic publish/reconciliation
```

The compiler publishes only after every required claim/support/dependency check
passes. It owns source-pair/L2 and non-graph generated-claim fallbacks. Graph and
community-report fallbacks are explicitly handed to Plan C.

## 2. Pros & Cons

Pros: gives Plan C a stable claim/support substrate and makes failed builds
rollbackable. Cons: requires additive generation/support state and delays visible
formula recovery until baseline and migration contracts are approved.
