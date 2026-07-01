# v0.29.0 Portable Path Storage Evidence Ledger

Date: 2026-07-01
Status: PRE-IMPLEMENTATION BASELINE

## Rollback Anchor

- Base branch: `master`
- Base release: v0.28.5, PR #75 merged
- Working branch: `release/v0.29.0`
- Worktree was clean before planning changes.
- Before any production migration, copy DB and sync exports to ignored
  `<repo>/.cache/migrations/v0.29.0/<timestamp>/`.

## Current Schema Reality

- `SCHEMA_VERSION = 9`.
- `sources.relpath` is documented as vault-relative but production has one
  absolute reference row.
- `sources.external_path` and `sources.import_origin` are absolute-path columns.
- `db_sync._DEVICE_LOCAL_COLUMNS` protects `sources.external_path`.
- source resolution, evidence locators, status, rebind, and ingest query these
  columns directly.
- current sync exports contain the absolute values.

## Current Plugin Persistence Reality

- `externalPdfRegistry` localStorage persists `path`.
- external PDF view state persists `path`.
- Zotero view restore calls backend resolution first but then persists the
  returned absolute path and retains plugin-side `~/Zotero`/saved-path fallbacks.
- `data.json` currently stores `zoteroBasePath: ~/Zotero`.
- session structured context sanitizer strips absolute `filePath` and
  `backendStatus`, but opaque message/context prose contains path strings.

## Production Read-only Counts

- `sources.relpath`: 1 absolute row
- `sources.external_path`: 1 absolute row
- `sources.import_origin`: 1 absolute row
- `source_pdf_pages.relpath`: 20 absolute rows for that source

## Scenario Discovery

Available scenarios:

- `tests/scenarios/gaussian_splatting`
- `tests/scenarios/resnet_neural_ode`
- `tests/scenarios/testbed_template`

No active `testbed/` marker was found. After implementation approval, the
production COLMAP/Gaussian Splatting source context was used to select
`tests/scenarios/gaussian_splatting`; the generic template is not the active
scenario.

## Pre-validation

Planning phase used read-only code, file, JSON, and SQLite inspection. No
production vault data was modified.

## Post-validation

Pending implementation and approval.
