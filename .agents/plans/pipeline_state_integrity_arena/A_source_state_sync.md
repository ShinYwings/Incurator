# Domain Analysis A: Source State and Cross-Device LWW

Date: 2026-07-03 | Domain: DB / synchronization

## Design Constraints

- `state.sqlite` is authoritative and remains device-local.
- JSONL snapshots merge canonical rows by LWW.
- Import must preserve the remote timestamp and remain idempotent.
- `sources.last_ingested` describes ingest progress; it is not a general row
  revision and must not be repurposed as one.
- Schema changes require migration coverage and a Minor release in 0.x.

## Alternatives and Trade-offs

1. Continue using `last_ingested`: no migration, but layer/status/path mutations
   remain invisible. Rejected because it is the confirmed root cause.
2. Always overwrite source rows on import: simple, but merge order determines
   the winner and peers can oscillate. Rejected.
3. Infer source recency from downstream artifact timestamps: cannot represent
   errors, retries, path rebinding, or status-only transitions. Rejected.
4. Add `sources.updated_at`: explicit and auditable. Requires schema v11 and
   careful timestamp/export-gate handling. Accepted.

## Final Decision

- Add schema-v11 `sources.updated_at`.
- Backfill it from the best existing source timestamp.
- Ensure every local source INSERT/UPDATE advances it. Prefer one guarded SQLite
  trigger for legacy/raw SQL update sites; imported `INSERT OR REPLACE` rows
  carry their remote value and must not be restamped.
- Use `sources.updated_at` for source LWW and export-change detection.
- Compare export-gate timestamps as parsed instants, not fragile mixed-format
  strings.
- Add tests proving L1→L4 status-only transitions export, import, and converge.

## Implementation Pseudocode

```text
migrate_v11:
  add sources.updated_at
  backfill normalized timestamp from last_ingested || added_at
  install guarded local-update timestamp trigger

set_source_layer_status(...):
  UPDATE sources SET layer_status=?, layer_error=? ...
  trigger advances updated_at

db_sync:
  _UPDATED_AT_COL["sources"] = "updated_at"
  remote source timestamp = row.updated_at
  export gate parses timestamp values before comparison
```
