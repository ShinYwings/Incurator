# Domain B — Generation Ownership and Replica Reconciliation Review

Date: 2026-07-30
Status: LOCKED FOR REVIEW APPROVAL

## 1. Design Constraints from Code and Specs

- Schema v13 remains unchanged.
- At most one authoritative compiler generation may exist per source.
- Authored relation ids are deterministic but the row has only one
  `generation_id`; independent replicas generate different generation ids.
- Source LWW, generation publication time, and relation row `updated_at` can
  select different replica rows.

## 2. Alternatives and Trade-offs

- Pick the generation owning the LWW relation row: violates source-fingerprint
  authority and fails when a source changed links. Rejected.
- Reassign all loser-owned rows to the winner: resurrects stale loser-only
  structure. Rejected.
- Persist exact authored membership in generation audit and reconcile by that
  set: accepted.

## 3. Final Decision

- Add sorted `authored_relation_ids` to generation audit JSON.
- Winner membership reassigns existing matching ids to the winner generation,
  then uses shared lifecycle compilation.
- Loser-owned ids absent from winner membership retire with dependent reports.
- DB-only republish carries membership only when prior and current fingerprints
  match; otherwise it retires prior authored membership.

## 4. Implementation Pseudocode

```python
winner_ids = audit_ids(winner)
shared = existing_ids & winner_ids
update_generation(shared, winner.id)
for relation_id in shared:
    compile_relation_lifecycle(relation_id)
retire(loser_owned_ids - winner_ids)
```
