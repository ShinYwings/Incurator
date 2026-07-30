# Domain C — Report and Search Freshness Review

Date: 2026-07-30
Status: LOCKED FOR REVIEW APPROVAL

## 1. Design Constraints from Code and Specs

- Removed relations already retire reports through exact relation dependencies.
- A newly added edge has no dependency row in an old report, so pure additions
  require endpoint-based invalidation.
- Authored entities have no factual spans or units; an orphan authored entity
  must not become standalone authoritative search evidence.
- Search tables are derived and may be safely rematerialized from DB truth.

## 2. Alternatives and Trade-offs

- Rebuild all communities during every L2 compile: correct but invokes broader
  L3 behavior and unnecessary churn. Rejected.
- Retire every report on any new authored edge: safe but imprecise. Rejected.
- Retire reports containing either newly connected endpoint, then let the
  normal L3 rebuild regenerate them: accepted.

## 3. Final Decision

- Extend authored persistence results with newly asserted relation ids.
- After shared lifecycle compilation, retire non-retired reports whose
  `entity_ids` intersect endpoints of newly active relations.
- Materialize `vault_note`, `vault_asset`, and `tag` entities only when they are
  endpoints of active relations; extracted entity types retain current behavior.
- Explicit source removal rematerializes search after the DB transaction.

## 4. Implementation Pseudocode

```sql
UPDATE community_reports
SET retired_at = :now, updated_at = :now
WHERE retired_at IS NULL
  AND EXISTS (
    SELECT 1 FROM json_each(community_reports.entity_ids)
    WHERE value IN (:new_endpoint_ids)
  );
```
