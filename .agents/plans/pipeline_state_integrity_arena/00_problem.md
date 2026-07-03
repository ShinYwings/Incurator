# v0.31.0 Pipeline State Integrity Briefing

Date: 2026-07-03

## User Report

The currently connected `second_brain` vault should show 31 completed L1
sources, but the dashboard shows 65. Some sources known to have completed
through L4 now appear as L1-only, and at least one source reports an L1 error.

## Measured Production Evidence

- Authoritative DB: 32 `sources` rows; 31 have `l1_status='done'`.
- Derived projection directory: 65 `CTX-*.md` files.
- Source #5 (`logical_source_id=zotero:PZBCB9LJ`) has:
  `l1=error, l2=done, l3=done, l4=skipped`, `layer_error=summary_failed`,
  no source spans, and no current `CTX-8ace29c9.md`.
- DB-native artifact reality: 1 knowledge unit, 0 graph entities, 0 synthesis
  nodes. The 353 ATM Markdown files are stale projections, not recoverable truth.

## Code Findings

1. `runtime_state.build_status_snapshot()` computes `layer_counts` by counting
   Markdown files, contradicting the DB-authoritative storage contract.
2. `db_sync` uses `COALESCE(last_ingested, added_at)` as the source-row LWW
   timestamp. Layer-status updates do not mutate that timestamp.
3. Missing-CTX smart healing retries L1 for curated sources. Failure changes
   `l1_status` to error while leaving prior downstream states untouched.
4. Reference stubs emit `zotero_attachment_key`, but the direct L1 resolver only
   checks `zotero_key` before falling back to indirect resolution.
5. `compile_global_l3()` sets `l3_status='done'` for every L2-complete source
   whenever no exception was raised, even if it produced no live community
   reports. This exposes `l3_ready` while concept-grounded answers are unavailable.

## Required Outcome

The dashboard must report authoritative DB counts; every source-state mutation
must participate in deterministic cross-device LWW; L1 projection repair must
not corrupt valid pipeline state; Reference Mode must resolve the portable key
that the system itself emits; L3/L4 readiness must require real serving
artifacts; and production repair must never reverse-import stale Markdown
projections.
