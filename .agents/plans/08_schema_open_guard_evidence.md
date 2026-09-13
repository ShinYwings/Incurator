# v0.82.7 Evidence Ledger

Date: 2026-09-13

## Before implementation

- Rollback anchor: d0171b47 / v0.82.6; PR #207 already merged.
- Existing schema: 14. No release migration is needed for the guard.
- Dirty paths: RELAY, ROADMAP and prompt_lifetime_arena documentation only.
- Defect: both entry points execute schema/journal setup before the unconditional
  unequal-version stamp update, permitting a newer DB to be restamped downward.
- Existing transaction tests: test_db_schema.py covers new, stale-stamp, queued
  job and connection-close behavior. Preserve them.
- Production configuration is not part of this patch; no production DB opened
  through a mutating application connection for investigation or validation.

## Verification

Pending: failing regression, focused pass, full local checks, independent review,
GitHub CI, merge and pruning. Record actual results as execution proceeds.
