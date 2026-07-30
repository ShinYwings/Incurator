# Stability Architect Proposal — Integrity-Boundary Patch Chain

Date: 2026-07-30 | Agent Persona: Lead Architect

## 1. Core Logic & Implementation

Keep the historical audit as one umbrella plan but divide implementation by
integrity boundary:

1. PR #101 follow-up: authored parser/generation/LWW/report defects only.
2. Source lifecycle patch: deletion closure and post-publish recovery.
3. Persistence patch: sessions, secrets, config writes, runtime redaction.
4. Provider/MCP patch: request ownership, CLI parity, dispatch, shutdown,
   subprocess limits.
5. Retrieval/prompt patch: explicit degradation, cardinality, attribution,
   numeric versions.

For each boundary:

```text
spec clarification -> red fault-injection tests -> minimal root-cause fix
-> focused tests/static checks -> full local CI -> isolated testbed
-> release commit/PR
```

The release audit runs alongside these phases. A newly found issue joins the
smallest matching boundary; it does not automatically enlarge the current PR.

## 2. Pros & Cons

Pros:

- Preserves PR reviewability and rollback.
- Reuses existing schema and subsystem tests.
- Fixes highest-risk confirmed defects before speculative refactoring.
- Provides a terminating audit rule: two dry passes per release.

Cons:

- Several patch releases are required.
- Some full-system tests repeat.
- Cross-boundary defects require careful ownership to avoid duplicated fixes.

