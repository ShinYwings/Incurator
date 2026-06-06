# Changelog

All notable changes to Incurator are documented here.

---

## [0.4.0] — 2026-06-06

### Added

- **Cross-device Knowledge Sync Bridge** (`wiki db export / wiki db import`)
  - Export the knowledge DB to a portable JSONL file (`wiki db export`)
  - Import a JSONL file into another device's DB with Last-Write-Wins merge (`wiki db import`)
  - `--dry-run` option to preview changes before writing
  - `--compress` option for gzip output (`.jsonl.gz`)
  - `--since <datetime>` for incremental (delta) exports
  - Post-import automatic `wiki reindex` (skippable with `--skip-reindex`)
  - Device-local tables (embeddings, job state, FTS5 indices) are automatically excluded from exports
- **Tombstone table** (`deleted_records`) — deleted records propagate to other devices on next import
- `db_sync.record_tombstone()` helper for future delete operations to call

### Changed

- `SCHEMA_VERSION` bumped from 6 → 7 (non-destructive; adds `deleted_records` table only)
- Existing vaults self-heal on next `wiki` invocation

### Documentation

- `docs/guides/USER_GUIDE.md` + `USER_GUIDE_KR.md`: new "Cross-Device Knowledge Sync" section
- `docs/specs/curator_schema/SCHEMA.md`: §11.17 `deleted_records` contract

---

## [0.3.3] — 2026-06-06

Initial release on `master` branch. Baseline for the v0.4.x series.
