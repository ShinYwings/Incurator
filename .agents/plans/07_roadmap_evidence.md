# v0.32.1 Cross-Device Integrity Evidence Ledger

Date: 2026-07-05

## Rollback Anchor

- Branch HEAD before expansion: `23a6d2cf2124689c5313880517c8cd832f3a2e60`
- Branch: `hotfix/v0.32.1-sync-device-identity`
- Worktree: clean
- Production DB backup:
  `.cache/migrations/v0.32.1/20260704T042823Z/`

## Current Schema Reality

- Package/plugin: v0.32.1
- SQLite schema: v11
- `sources` transport PK: local integer `id`
- `compiler_generations`: no `updated_at`
- `deleted_records`: present, but source deletion callers do not record it
- importer validation: target-table existence only, no sync allowlist
- peer high-water identity: filesystem mtime

## Reproduced Pre-Change Failures

- Distinct id-1 source replicas converged to one source.
- A deleted source remained on the peer with zero tombstones.
- A stale staged generation replaced authoritative status.
- Crafted JSONL inserted a row into local-only `schema_version`.

## Storage Inventory

Machine-local files currently under the vault include `state.sqlite`,
`runtime/`, `staging/`, `dashboard.md`, `sync-report.json`, PDF page cache,
plugin PDF crops, and plugin CLI fallback files.

## Post-Change Results

Pending implementation and validation.

