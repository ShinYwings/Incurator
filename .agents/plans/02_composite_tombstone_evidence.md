# v0.37.0 Composite Tombstone Evidence Ledger

Date: 2026-07-30
Status: RELEASE READY — implementation, review, CI, and testbed gates passed.

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

- Schema v13 uses the closed six-table composite-key registry and canonical
  `{"key":{...},"v":1}` tokens. Source-scoped keys resolve through portable
  `sources.sync_key`; malformed/legacy tokens fail closed.
- Exact full-key deletes, delete-wins-equal LWW, strictly newer mutable-row
  supersession, immutable-row blocking, source dependent cleanup, local
  delete/reinsert emission, and stale-third-peer convergence are covered.
- Code review found and fixed one additional edge case: a first-import dry-run
  had no local parent row from which to resolve a source-scoped key. Import now
  carries the already-validated remote source key through the source-id map;
  dry-run counts match the real pass and remain read-only. The unused
  `source_scoped` registry flag and stale “always upsert” comments were removed.
- Focused sync suite: `99 passed`.
- Full backend suite: `1303 passed, 6 skipped, 5 xfailed`.
- Ruff: all checks passed. Mypy: no issues in 125 source files.
- Plugin: 68 files / 721 tests passed; production build passed.
- ResNet testbed: the active repo-cache DB upgraded from schema 12 to 13;
  autosync applied `+0/~0/-0`, the second pass was quiescent with no export,
  and `wiki lint` scored 100/100 with 3 pages and 0 issues.
- The pre-v13 peer snapshot was skipped as incompatible rather than partially
  imported. The active v13 device snapshot declared schema 13.
- External/public PDF and Reference Mode assets were not copied, rewritten, or
  reinitialized during testbed validation.
