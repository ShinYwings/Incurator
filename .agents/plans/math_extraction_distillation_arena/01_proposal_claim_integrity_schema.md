# Claim Integrity Schema Proposal: Minimal Support And Reconciliation

Date: 2026-06-11 | Agent Persona: schema_guardian

## 1. Core Logic & Implementation

Preserve `source_spans` as atomic evidence identity and `knowledge_units` as L2
semantic records. Add only fields/tables justified by compiler integrity.

### Candidate additive schema

```sql
ALTER TABLE knowledge_units ADD COLUMN semantic_hash TEXT;
ALTER TABLE knowledge_units ADD COLUMN support_status TEXT NOT NULL DEFAULT 'unchecked';
ALTER TABLE knowledge_units ADD COLUMN support_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE knowledge_units ADD COLUMN formula_status TEXT NOT NULL DEFAULT 'not_applicable';
ALTER TABLE knowledge_units ADD COLUMN retired_at TEXT;

CREATE INDEX idx_knowledge_units_semantic_hash
  ON knowledge_units(source_id, semantic_hash);

CREATE TABLE claim_supports (
  knowledge_unit_id TEXT NOT NULL,
  source_span_id TEXT NOT NULL,
  support_role TEXT NOT NULL,
  support_status TEXT NOT NULL,
  support_reason TEXT NOT NULL DEFAULT '',
  evidence_hash TEXT NOT NULL,
  validator_trace_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (knowledge_unit_id, source_span_id, support_role)
);
```

The final specification may choose a JSON column over `claim_supports` only if
Program 1 proves no indexed audit/reconciliation query is needed. The default
recommendation is normalized support rows because support is a lifecycle, not
decorative metadata.

### Support roles and statuses

- Roles: `minimal_primary`, `minimal_secondary`, `formula`, `contradiction`.
- Statuses: `verified`, `uncertain`, `unsupported`, `stale`.
- Formula statuses: `not_applicable`, `preserved`, `omitted_incidental`,
  `recovered_uncertain`, `missing_central`.

### Integrity rules

- `source_supported` requires at least one `verified` minimal support row.
- `derived_insight` may cite evidence but cannot be relabeled source-supported.
- A support row's `evidence_hash` must match the current source span hash.
- Retired units cannot feed new graph extraction or search materialization.
- Dependency rows must connect units to exact support rows/spans, not broad
  source-level sets.

### Migration

Add columns/tables first. Backfill existing units as `unchecked`, then run a
read-only audit. Do not automatically call existing citations `verified`.
Rebuild source-derived L2 records under the new contract only after backup and
measured migration rehearsal.

## 2. Pros & Cons

### Pros

- Makes wrong-but-real citations detectable.
- Supports precise invalidation and audit queries.
- Preserves current IDs until a controlled rebuild decides otherwise.
- Separates evidence existence from evidence entailment.

### Cons

- Adds support lifecycle complexity and sync/export surface changes.
- Existing records initially become visibly unchecked.
- A normalized table requires DB-sync and inspection updates.
