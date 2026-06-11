# Schema Guardian Proposal: Provenance, Resolution, And Quota Contracts

Date: 2026-06-11 | Agent Persona: schema_guardian

> **Reframing note:** The schema candidates remain inputs, but their sequencing
> follows the active three-program master plan. Program 1 owns reproducibility,
> trace, locator, and evaluation contracts. Program 2 owns Knowledge IR, entity,
> relation, hierarchy, and reconciliation contracts. Quota is deferred.

## 1. Core Logic & Implementation

### Preserve current authority boundaries

- `source_spans` remains the atomic evidence identity.
- Existing JSON `source_span_ids` fields remain valid and required.
- New locator metadata supplements span ids; it does not replace them.
- Search tables remain derived/device-local where currently specified.
- No migration may treat `.curator/Collections/` as authoritative input.

### Additive schema candidates

Program 1 may add structured locator metadata to `source_spans.metadata` first,
avoiding a schema bump if the access patterns remain simple. A normalized locator
table is justified only if block/heading lookup requires indexed queries.

Program 2 likely needs explicit, auditable records:

```sql
entity_aliases(
  alias_normalized TEXT,
  entity_id TEXT,
  alias_display TEXT,
  source_span_ids TEXT,
  confidence REAL,
  resolution_status TEXT,
  resolution_reason TEXT,
  PRIMARY KEY(alias_normalized, entity_id)
)

entity_merge_proposals(
  id TEXT PRIMARY KEY,
  source_entity_id TEXT,
  target_entity_id TEXT,
  similarity REAL,
  decision TEXT,
  rationale TEXT,
  created_at TEXT
)
```

Quota configuration belongs in user configuration, while measured usage belongs
in runtime status. Do not persist fast-changing byte counts into synced canonical
tables.

### Integrity gates

- Every non-source search document must carry at least one valid source span,
  unless its contract explicitly permits an ungrounded operational record.
- Every `source_span_id` referenced by L2-L4 and search provenance must exist.
- Every merged entity must preserve the union of source spans and knowledge units.
- Relation endpoints must resolve after entity merging.
- Migrations must be additive and forward-only; rollback uses DB backup/rebuild,
  not destructive down-migration.

## 2. Pros & Cons

### Pros

- Keeps existing DB/source-of-truth rules intact.
- Makes entity resolution reviewable and reversible.
- Avoids over-normalizing locators before query needs are proven.

### Cons

- JSON locator metadata is less query-efficient than a normalized table.
- Alias proposal records add lifecycle/status complexity.
- Integrity checks may reveal existing invalid rows requiring a migration report.
