# Arena Defense And Consensus: Trusted Evidence, Bounded Serving

Date: 2026-06-11 | Agent Persona: system_synthesizer
Status: DRAFT CONSENSUS - awaiting user approval after Programs 1 and 2

## 1. Responses To Red-Team Critique

### Service migration

Accepted. ContextService is introduced through delegated operations and parity
gates. Existing surfaces are removed or reduced to compatibility adapters only
after tests prove equivalent behavior.

### Compiler trust

Accepted. Serving cannot upgrade unsupported or stale compiler output. It rejects
or explicitly labels it and points back to Program 2 audit status.

### Snapshot and budgets

Accepted. Snapshot conflict tracks evidence-relevant DB/search/policy epochs, not
unrelated UI changes. Refresh returns a new pack. Budgets record estimator/model
identity, safety margin, actual known use where available, and omissions.

### Graph/agentic retrieval

Accepted. Direct factual/local retrieval is the protected baseline.
Associative/global/iterative additions are route-specific, bounded, and adopted
only when Program 1/2 holdouts improve without prohibited factual regression.

### Locators and clients

Accepted. Device/vault-dependent locator resolution has explicit exact,
fallback, stale, duplicate, and unavailable states. Backend normalized parity is
measured before client-specific immediate context and final packing.

### Pack persistence and compatibility

Accepted. Transactions persist compact identities, selection metadata, and
lineage. Exact content is read from authoritative records/snapshots when
possible. Compatibility surfaces receive explicit removal gates.

## 2. Locked Consensus

1. Plan A belongs to Program 3 and starts only after merged
   Program 1 observability and Program 2 compiler trust.
2. One retrieval coordinator and one authoritative `RTR-*` retrieval execution
   govern route/candidate/ranking/evidence selection under the Program-1
   root-QTR/snapshot substrate. Plan F owns ContextService root lifecycle and
   public/client transactions.
3. Plan A emits a transport-neutral retrieval result consumed by Plan F without
   launching a second retrieval path.
4. Every route enforces KRS, scope, truth/freshness, boundedness, and explicit
   degradation.
5. Retrieval routes use explicit candidate/evidence bounds and omissions. Plan F
   owns model-aware pack budgets and progressive expansion.
7. Structured locators supplement source-span ids and are rendered only at
   interface boundaries.
8. Invalid/stale/duplicate anchors never become working-looking links; fallback
   is broader but valid and warned.
9. Direct factual quality is protected. Graph/global/iterative retrieval is
   measured, bounded, and route-specific.
10. Cross-client parity, client-specific immediate context, and final provider
    budgets belong to Plan F.
11. Serving transactions do not become a new knowledge source of truth or a
    frozen answer cache.
12. Plan F consumes Plan A's selected evidence, transaction details, warnings,
    and locators through one explicit handoff contract.

## 3. Required Entry Evidence

Before Plan A implementation:

- Program 1 failure atlas, evaluation spec, qrels, holdouts, transaction and
  observability contract are merged;
- Program 2 compiler audit passes claim support, freshness, identity,
  reconciliation, and locator gates;
- current serving baseline is measured on the trusted Program 2 corpus;
- exact schema/API/migration/rollback specifications are approved;
- a fresh Program 3 branch starts from merged Program 2 `master`.

## 4. Vulnerabilities & Flaws Resolved

- Resolved disconnected-root risk with one Plan-A `RTR-*` child under the
  Program-1 root-QTR/snapshot substrate.
- Removed ContextService, client integration, progressive packs, and feedback
  from Plan A ownership.

## 5. Suggested Alternatives Adopted Or Rejected

- Adopted a transport-neutral retrieval-result/locator handoff to Plan F.
- Rejected a second retrieval implementation inside ContextService.
