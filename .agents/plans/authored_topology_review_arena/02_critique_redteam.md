# Critique on the Compiler Proposal

Date: 2026-07-30 | Agent Persona: Red Team / Schema Guardian

## 1. Vulnerabilities & Flaws

- A hand-written Markdown scanner can accidentally become a partial general
  parser. It must not add reference links, plugin citation syntax, HTML parsing,
  or fuzzy destination recovery.
- Reassigning every loser-owned relation to the winner would resurrect
  loser-only stale links. The exact winner relation-id set is mandatory; source
  endpoint equality alone is insufficient.
- A generation audit from an older build may not contain
  `authored_relation_ids`. Treating a missing field as "all current rows" is an
  unsafe compatibility shim.
- Recompiling lifecycle after sync must preserve self-loop quarantine and must
  not directly force every winner relation to `active`.
- Report invalidation based only on removed relation dependencies misses pure
  additions. Invalidating all reports is safe but causes avoidable churn.
- Reindexing after source deletion removes retired relation documents, but
  orphan authored entities must also be excluded from authoritative search or
  they remain discoverable without active topology.
- The broader pre-existing source-delete closure for extracted KUs/supports is
  not small enough to smuggle into this PR. Mixing it with F9 review fixes would
  make rollback and review substantially harder.

## 2. Suggested Alternatives

- Parse only inline destinations necessary for the contract and expose scanner
  spans to both extraction and tag masking.
- Missing winner audit membership should fail closed by retiring loser-owned
  authored rows; it must never guess.
- After winner reassignment, call the shared lifecycle compiler.
- Retire reports whose stored `entity_ids` intersect endpoints of newly active
  topology; removed edges continue to use exact artifact dependencies.
- Materialize authored entity types only when they are endpoints of an active
  relation. Preserve all canonical extracted entity types.
- Queue the pre-existing full source-delete extracted closure as a separate
  System Stability item with its own plan.
