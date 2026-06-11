# Service Architecture Proposal: One Context Transaction Core
Date: 2026-06-11 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

Introduce one backend application service that owns context requests:

```text
MCP / CLI / plugin / backend synthesis
  -> ContextService
  -> normalize request + resolve snapshot/policy/budget
  -> route + retrieve + assemble + validate + pack
  -> persist one QTR transaction
  -> return normalized pack
```

### Operations

```python
class ContextService:
    def manifest(request: ManifestRequest) -> ContextManifest: ...
    def fetch(request: ContextRequest) -> ContextPack: ...
    def expand(request: ExpansionRequest) -> ContextPackDelta: ...
    def verify(request: VerificationRequest) -> VerificationResult: ...
    def feedback(request: FeedbackRequest) -> FeedbackReceipt: ...
```

`curator_query` calls `fetch`, then optional synthesis over the exact returned
pack using the same `trace_id`. `curator_fetch_context` returns the pack without
synthesis. Raw search remains a diagnostic surface but must use shared policy and
transaction primitives when exposed as agent context.

### Transaction stages

1. Normalize request and validate purpose/scope.
2. Resolve workspace, KRS policy, source scope, and authority/freshness policy.
3. Capture snapshot identity.
4. Resolve tokenizer and budget.
5. Route and retrieve candidates.
6. Assemble bounded evidence items.
7. Validate provenance, locators, policy, budget, and snapshot.
8. Persist one authoritative trace.
9. Return pack and expansion handles.

## 2. Pros & Cons

### Pros

- Eliminates client-specific retrieval truth and disconnected traces.
- Gives synthesis and evidence-only clients the same grounding primitive.
- Centralizes enforcement and testing.

### Cons

- Migration touches MCP, CLI, backend query, and plugin integration.
- A central service can become overly broad without strict internal boundaries.
- Existing query/search return shapes require an explicit compatibility plan.
