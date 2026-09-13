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

2026-09-13: new tests first produced 20 expected failures and 6 compatible-path
passes on the old implementation. 2026-09-14: implementation passed all 46
test_db_schema tests; Ruff and mypy (134 files) and plugin TypeScript passed.
Full backend/plugin suites and independent review are running. No production
data or retention settings changed. All release manifests now declare 0.82.7.

Pending: complete suite results, independent review, GitHub CI, merge and pruning.

Full backend run: 2039 passed, 6 skipped, 4 xfailed, 3 subtests; two failures
were the same D2 evaluated-code hash tripwire. The record explicitly supports
re-arming on proven non-impact, without rerunning the consumed holdout. Private
old/new initialization comparison proves SCHEMA_SQL, TRIGGER_BODIES, all 141
sqlite_master objects and schema stamp identical. Only new rejection paths
change. Added a dated rationale and the new schema.py hash to the existing
record; no frozen inputs, metrics, run counts or harness changed.

Plugin Vitest 4.1.11: 1286 passed, 3 skipped (122 files passed, 1 skipped).
The mandated root npx command also passed but resolved Vitest 5, so the pinned
plugin-local tool was run separately. Independent five-lens available-agent
review found no actionable introduced defects at confidence >=80 on code/tests/
guides. Version/changelog and D2 re-arm follow-up review remain before shipping.

Follow-up review found one introduced P2 (confidence 90): SQLite allows a table
and trigger both named schema_version; insertion order made fetchone select the
trigger and reject a valid table. Added both entry points/order regressions,
observed 2 failures/2 passes, then preferred the table in the metadata read.
All 50 schema tests and Ruff now pass. D2 hash/rationale updated; final full
backend verification and review fix confirmation remain. Testbed status smoke
succeeded, and production last_root stayed /Users/shin/shinywings/second_brain.

Final verification: full backend 2045 passed, 6 skipped, 4 xfailed, 3 subtests
(75.20s). Ruff, mypy 134 files, TypeScript, pinned Vitest 1286 passed/3 skipped,
and isolated testbed status passed. Reviewer verified 0204c728 fixes the single
P2; no remaining actionable introduced finding >=80 across five lenses.
Only remote CI/merge and release cleanup remain for this prerequisite.
