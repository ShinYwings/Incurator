# v0.31.0 Evidence Ledger

Date: 2026-07-03
Status: VERIFIED

## Rollback Anchor

- Branch point: `3c3249abfe4d461877bbef8c12c8277ce7ccced4`.
- Production repair requires timestamped copies of `state.sqlite*`,
  `.curator/sync/`, and `.curator/sync_state.json`.
- No production file has been modified during diagnosis.
- Verified pre-change backup:
  `/home/shin/.cache/incurator/backups/second_brain-v0.31.0-pre-20260703T1645KST/`.
  SQLite backup SHA-256:
  `c8bd615dbee99f5b0cb472af0cd6cdca5020cd4e0574a5193e2517065cddb3d1`.
  `PRAGMA integrity_check` returned `ok`.

## Current Repository and Schema Reality

- Build version: v0.30.0.
- DB schema: v10.
- `sources` has no general `updated_at`.
- Source LWW clock: `COALESCE(last_ingested, added_at)`.
- Dashboard `layer_counts`: filesystem Markdown counts.
- Projection re-emission already defines serving DB sets for L2/L3/L4.

## Current Production Baseline (`second_brain`)

| Measure | Value |
| --- | ---: |
| sources total | 32 |
| L1 done | 31 |
| L1 error | 1 |
| CTX Markdown files | 65 |
| source spans | 1301 across 31 sources |
| serving/raw knowledge units observed | 1 |
| graph entities | 0 |
| active graph relations | 0 |
| live community reports | 0 |
| synthesis nodes | 0 |
| ATM Markdown files | 353 |

Source #5 is `zotero:PZBCB9LJ`, with no source spans and no current CTX file.

## Dirty Worktree

- User-owned untracked file:
  `.agents/drafts/sidechat_ui_regression_v0.29.0.md`.
- Planning files in this branch are intentional.
- Active testbed scenario: `gaussian_splatting` (Reference Mode + L1-L4 goals).

## Pre/Post Validation Matrix

| Gate | Pre | Required Post |
| --- | --- | --- |
| Dashboard L1 count | 65 | 31 from DB |
| Status source truth | filesystem | serving DB queries |
| Status-only sync | not reliably exportable | converges across two DBs |
| Imported timestamp | `last_ingested` proxy | remote `updated_at` preserved |
| Contradictory L1 retry | reproducible in source #5 | repaired or explicit unresolved-reference state |
| L3 readiness | 1 source done, 0 live reports | no false L3 done; source-grounded readiness |
| L4 readiness | 0 nodes; historical completion unverified | current-node truth; peer recovery or rebuild documented |
| Stale projections | 65 CTX / 353 ATM | safely re-emitted from DB |
| Backend tests | initial targeted failures captured | full pytest/ruff/mypy pass |
| Plugin tests | profile merge regression added | TypeScript + full vitest pass |
| Testbed | `gaussian_splatting` selected | Reference Mode/L1-L4 scenario pass |

## Final Evidence

- Backend: `1178 passed, 6 skipped, 5 xfailed`; ruff and mypy passed.
- Plugin: TypeScript no-emit passed; `665 passed`.
- `gaussian_splatting`: L1 3, serving L2 52, no eligible L3/L4; every source
  correctly showed terminal `skipped` instead of false L3 done. Structural
  scenario checks: 6 passed, 0 failed.
- Production `second_brain`: schema 11, `PRAGMA integrity_check=ok`, 32/32 L1,
  0 errors, 0 serving L2/L3/L4 artifacts, 32 CTX projections, no stale
  ATM/CON/SYN projections. One interrupted job was recovered to queued and its
  source layer reset from running to pending.
- Source #5 (`zotero:PZBCB9LJ`) resolved the emitted attachment key and rebuilt
  `CTX-8ace29c9`; implicit Tesseract OCR was disabled in favor of the explicit
  vision-model path.
