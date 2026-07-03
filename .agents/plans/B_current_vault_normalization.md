# Domain Analysis B: Current Vault Normalization

## Design Constraints

- macOS `second_brain/.curator/state.sqlite` contains three legacy Zotero rows.
- All three already have stable attachment keys.
- The old release can convert them without adding generic root mappings.
- Production paths must be backed up and verified before mutation.

## Alternatives & Trade-offs

1. Delete and rebuild the DB: rejected because it discards device-local jobs and
   derived state unnecessarily.
2. Hand-edit SQL: rejected because the existing tested normalizer updates
   dependent relpaths and rebuilds the table.
3. Run the existing normalizer once, verify, then delete it from the product:
   selected.

## Final Decision

Before deploying v0.32.0, run the v0.31.0 dry-run and apply command against
`second_brain`, retain its timestamped backup, verify schema 11 and all three
Zotero identities, then ensure `wiki status` succeeds.

## Verification SQL

```sql
PRAGMA integrity_check;
PRAGMA foreign_key_check;
SELECT id, relpath, logical_source_id, external_ref
FROM sources
WHERE relpath LIKE '/%' OR external_ref LIKE '/%';
```
