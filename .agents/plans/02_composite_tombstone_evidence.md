# v0.37.0 Composite Tombstone Evidence Ledger

Date: 2026-07-30
Status: BASELINE LOCKED — no application code changed; schema approval pending.

## Rollback anchor

- Branch: `release/v0.37.0`
- Merge-base / clean master: `831e01dd0a416c5caeaeb53842ec90f04cc7abef`
- Starting release manifests: `0.36.8`
- Starting DB schema: `SCHEMA_VERSION = 12`

## Current schema reality

Composite synchronized primary keys:

| Table | Physical primary key | Portable complication |
|---|---|---|
| `source_pages` | `(source_id, wiki_path, at)` | `source_id` is replica-local |
| `source_pdf_pages` | `(source_id, page_number)` | `source_id` is replica-local |
| `claim_supports` | `(knowledge_unit_id, source_span_id, support_role)` | none |
| `graph_relation_supports` | `(relation_id, knowledge_unit_id, support_hash)` | none |
| `entity_resolution_lineage` | `(decision_id, origin_entity_id)` | immutable/no clock |
| `artifact_dependencies` | `(artifact_id, depends_on_id, depends_on_type)` | none |

## Reproduced code-path evidence

- `_apply_tombstone()` has no composite delete. It logs, records, returns true,
  and causes the importer to increment `deleted`.
- `_lw_upsert()` resolves composite primary keys for row merge but never checks
  `deleted_records`, so a stale peer can resurrect a deleted row.
- Composite local hard deletes exist in page provenance, claim-support
  reconciliation, and artifact dependency invalidation, but production
  tombstone calls currently cover only sources and atoms.
- `source_pages`, `ingest_runs`, and `dag_edges` have non-cascading references to
  `sources`; the imported-source tombstone path does not run local dependent
  cleanup.
- The spec already promises full-key import identity and delete/update LWW, so
  current code violates the documented contract rather than lacking a product
  decision.

## Prior art

- RFC 8785 supports deterministic JSON property ordering as stable identity.
  The implementation will use only the necessary restricted string/integer
  subset and will not claim full JCS conformance.
- SQLite documents that composite foreign/primary keys are tuples; partial keys
  are not equivalent identities.

## Pre-validation

- Git worktree was clean on `master` before branch creation.
- Active testbed contains the ResNet Dynamics vault and an external/public PDF.
  It will not be reinitialized before the user confirms the active scenario.
- No application tests have been changed or run for this planning-only phase.

## Post-validation

Pending implementation approval.

