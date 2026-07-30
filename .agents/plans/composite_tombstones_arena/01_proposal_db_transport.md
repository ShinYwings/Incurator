# DB Transport Proposal: Versioned Canonical Composite Keys

Date: 2026-07-30 | Agent Persona: Lead Architect

## 1. Core Logic & Implementation

Keep the physical `deleted_records` table and existing single-key token format.
For composite targets, encode `{"key":{...},"v":1}` with compact sorted JSON.
A closed registry maps transport fields to physical PK fields and supplies the
source-sync-key adaptation. Import computes the same token for every row and
performs tombstone-versus-row LWW before upsert.

Hard deletes use a shared helper that captures target keys, executes the delete,
and records tombstones inside the caller's transaction. Source deletion gets an
explicit dependent cleanup path matching local removal semantics.

## 2. Pros & Cons

Pros:

- Minimum DDL churn.
- Inspectable and deterministic wire identity.
- One registry covers delete, resurrection prevention, and local emission.
- Existing scalar tombstones remain valid.

Cons:

- `record_id` now contains a structured token for composite rows.
- Each true hard-delete path must be audited and instrumented.
- v12 and v13 peer snapshots cannot interoperate.

