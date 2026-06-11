# Relation Quality Proposal: Independent Support And Quarantined Topology

Date: 2026-06-11 | Agent Persona: source_pair_analyst / graph_quality_specialist

## 1. Core Logic & Implementation

Treat a relation as a proposition with one or more claim-level support records,
not a mutable edge whose latest extraction overwrites prior evidence.

### Relation lifecycle

- Normalize endpoints through accepted aliases.
- Reject unresolved endpoints from authoritative topology.
- Collapse exact proposition duplicates while preserving each independent
  support record.
- Keep `source_states`, `system_infers`, and `workspace_derives` distinct.
- Compute topology weight from support quality, independence, assertion source,
  confidence calibration, and quarantine penalties.
- Quarantine unsupported, contradictory, self-loop, or giant-component-causing
  bridge candidates until they pass policy.

### Candidate schema

```sql
CREATE TABLE graph_relation_supports (
  relation_id TEXT NOT NULL,
  knowledge_unit_id TEXT NOT NULL,
  source_span_ids TEXT NOT NULL,
  assertion_source TEXT NOT NULL,
  confidence REAL NOT NULL,
  support_status TEXT NOT NULL,
  support_hash TEXT NOT NULL,
  PRIMARY KEY (relation_id, knowledge_unit_id, support_hash)
);
```

Add relation status/weight fields only after metric definitions are frozen:
`active`, `provisional`, `quarantined`, `retired`.

### Edge policy

Only `active` edges enter authoritative community construction. Provisional and
quarantined edges remain inspectable and searchable as labeled generated
records, but cannot silently join communities or support source-grounded claims.

## 2. Pros & Cons

### Pros

- Prevents latest-write evidence loss.
- Makes relation confidence explainable.
- Isolates noisy bridges before they corrupt hierarchy/global synthesis.

### Cons

- Independence is difficult to define when sources repeat one another.
- Quarantine thresholds can suppress useful weak ties.
- Adds lifecycle/invalidation complexity.
