# Cache Preservation Domain Analysis

## Constraints and invariants

The candidate path includes an authoritative DB and may contain unrelated logs,
backups or runtime ownership state. `db.get_stats` calls `db.connect`, which
commits SCHEMA_SQL and a version stamp before reading. It is not an inspector.
Zero sources does not imply no prompt/query/job history or sync tombstones.
The current namespace API writes a resolved `vault_root` marker and state.sqlite.

## Alternatives and trade-offs

Counting only SYNC_TABLES loses local job history. Counting all physical tables
rejects an initialized empty FTS database because shadow metadata has rows.
Ignoring names by prefix admits unrelated history. Use trusted expected table
definitions and PRAGMA table_list types to distinguish real shadow infrastructure.
Build this reference in memory once, never repair an examined database. Unknown
layouts stay; no new compatibility or schema migration layer is introduced.

Allowing arbitrary non-DB files makes recursive deletion an undocumented expiry.
Preserve everything beyond the marker and closed DB, including SQLite sidecars.
This intentionally leaves caches whose contents or activity need a separate policy.
An empty known DB remains collectible. Revalidation narrows stale-plan deletion
without pretending to hold an atomic lifecycle lease across every possible writer.

## Final decision and pseudocode

```
inspect(namespace):
  reject symlinks/nonregular members/unexpected file names
  read marker; resolve root; reject existing/non-temp/uncertain root
  if DB exists:
    open mode=ro; compare tables + table types with trusted memory schema
    require one matching schema_version
    reject any row in any non-infrastructure logical table
  return size, reason, filesystem identities, marker contents

discover(cache): inspect every real direct namespace
sweep(planned): inspect again; compare identities and marker; delete only match
```

Acceptance covers tombstones, prompt/query/job rows, unknown tables/files,
partial schemas unchanged, WAL/SHM retention, FTS populated/empty distinction,
canonical root, symlinks, changed marker, replaced namespace and late row insertion.
