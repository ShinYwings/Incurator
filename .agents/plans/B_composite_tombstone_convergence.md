# Domain Analysis B — Tombstone Migration And Convergence

Date: 2026-07-30

## Design constraints from the current codebase

- JSONL headers require exact `SCHEMA_VERSION` equality, so mixed v12/v13 peers
  are already rejected rather than silently partially imported.
- Import applies tombstones first, but `_lw_upsert()` never checks an existing
  tombstone. A later stale peer snapshot can therefore resurrect a deleted row.
- `_apply_tombstone()` compares the local row revision only for scalar-key
  tables. Composite rows currently have neither a local-revision guard nor a
  delete.
- Existing production tombstone call sites delete `sources` and `atoms`; no
  production call site currently emits a composite tombstone.
- A realistic source has non-cascading `ingest_runs`, `source_pages`, and
  `dag_edges` references. A remote source tombstone can fail even though a
  source tombstone without those dependents passes the current test.

## Alternatives and trade-offs

### Only teach `_apply_tombstone()` composite SQL

Rejected. It leaves stale-peer resurrection and local tombstone emission
unfixed, so the feature would pass one import test without converging.

### Database triggers for every synchronized table

Rejected for this slice. Triggers could capture all deletes but would duplicate
table-specific key encoding in SQL, complicate imported-delete timestamps, and
make delete/reinsert transactions hard to reason about.

### Explicit codec plus centralized deletion helpers

Selected. One registry owns identity. Import and local deletion use the same
encoder/decoder, and the existing finite set of hard-delete paths is made
explicit and testable.

## Final decision

### Migration boundary

- v13 JSONL files do not interoperate with v12 clients.
- Existing single-key `deleted_records` rows remain valid without rewriting.
- A pre-v13 raw token for a composite table is not decodable. Export/import
  validation must fail with the table and token identified; it must never guess,
  silently omit, or treat that record as applied.
- This fail-closed validation is the migration policy because historical
  production code did not create composite tombstones. A diagnostic test
  verifies that an unsupported manually-created row is preserved for operator
  review rather than destroyed.

### Delete-versus-update convergence

For every incoming row:

1. Encode its transport identity with the same registry used by tombstones.
2. Read the local tombstone, if any.
3. Compare the incoming row revision to `deleted_at`.
4. If `deleted_at >= row_revision`, skip the row.
5. If `row_revision > deleted_at`, remove the older tombstone and apply LWW.
6. For immutable rows without a revision clock, an existing tombstone wins.

For every incoming tombstone:

1. Decode and validate its full transport key.
2. Resolve source-scoped portable keys to local ids.
3. Compare the local target revision to `deleted_at`.
4. If the local row is newer, keep the row and do not replace its newer state
   with the tombstone.
5. Otherwise execute the full-key delete, record the tombstone, and increment
   deletion stats in one transaction. An already-absent row is a valid applied
   tombstone.

### Local emission

- Add one helper that snapshots the full key before a hard delete and records a
  tombstone in the caller's transaction.
- Instrument actual canonical removals for page-provenance replacements,
  claim-support reconciliation, and artifact-dependency invalidation.
- A delete followed by reinsertion of the same key in the same logical update
  must leave no tombstone for that live row.
- Source tombstone application uses the same dependent-cleanup semantics as
  local source removal so realistic imported deletes do not fail on
  non-cascading local tables.

## Test matrix

- All six composite tables: encode/decode/apply round trip.
- Strings containing commas, colons, quotes, Unicode, and path separators.
- Wrong version, missing key, extra key, wrong scalar type, unknown source key.
- Remote tombstone older/newer/equal to the local row.
- Stale third-peer row cannot resurrect a deleted scalar or composite row.
- Newer row legitimately supersedes an older tombstone.
- Realistic source deletion with `source_pages`, `ingest_runs`, and `dag_edges`.
- Dry-run reports changes without deleting or rewriting tombstones.
- Two devices converge and a third stale snapshot remains quiescent.

