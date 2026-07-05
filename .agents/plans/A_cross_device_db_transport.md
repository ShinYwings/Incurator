# Domain Analysis: Cross-Device DB Transport

## Design Constraints

- SQLite integer primary keys are replica-local.
- `.curator/sync/dev-<device>.jsonl` is the only portable DB transport.
- Concurrent reads and edits to distinct source files are supported.
- No v11 transport compatibility path remains after schema v12.

## Alternatives

- Raw SQLite sync: rejected because WAL/SHM and whole-file overwrite are unsafe.
- Numeric-id LWW: rejected because independently allocated IDs collide.
- Content hash as source identity: rejected because identical documents may be
  distinct sources and source content changes over time.
- Portable `sync_key` plus FK remap: selected.

## Final Decision

Add `sources.sync_key`, preserve local integer IDs, remap synchronized child
`source_id` values, use source-key tombstones, add generation revision, validate
all imported tables/columns, and identify snapshots by `export_id`.

## Pseudocode

```text
for source row:
  local = SELECT id FROM sources WHERE sync_key = remote.sync_key
  if local: UPDATE fields except id
  else: INSERT fields except id
  source_id_map[remote.id] = local.id

for child row:
  if source_id exists: row.source_id = source_id_map[row.source_id]
  validated_lww_upsert(row)
```

