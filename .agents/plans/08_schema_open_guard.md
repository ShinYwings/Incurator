# v0.82.7 Master Implementation Plan

Date: 2026-09-13
Status: APPROVED — existing lifetime Arena identified the prerequisite;
independent schema review is recorded in prompt_lifetime_arena/06_schema_guard_review.md.

## 1. Objective

Refuse a database whose declared schema is newer than this runtime before either
`init_db` or `connect` executes application schema changes, refreshes triggers,
changes journal mode, or rewrites the schema stamp. This independently useful
patch precedes the schema-changing prompt-lifetime release. Completion means a
future database retains its data, installed schema, version and journal policy
after either entry point refuses it, with a useful upgrade instruction.

## 2. Explicit Non-Goals

No schema version change, migration, prompt lifetime implementation, chat format
change, GC policy change, or production mutation. This does not retrofit already
installed older binaries, nor make a live schema migration safe while callers
retain previously opened connections. Upgrade/quiesce known writers before the
later migration. SQLite may manage its own read/lock sidecars while opening a DB;
this patch does not promise a byte-identical filesystem inspection API.

## 3. Strict Quality Conditions & Release Gates

- Test both public connection entry points against future schema in DELETE and
  WAL journal modes, preserving data, custom schema/triggers and version.
- Refuse malformed or multiple version rows without attempting repair.
- Preserve fresh/empty initialization and compatible older-stamp behavior.
- Preserve caller-outside-transaction semantics and queued-job claims.
- Run required backend pytest/Ruff/mypy and plugin Vitest/TypeScript checks.
- Review before CI using the user-authorized available-agent substitution if
  the actual Claude review remains unavailable. Record what actually ran.
- Synchronize all release manifests at 0.82.7 and update CHANGELOG.

## 4. Locked Design Decisions (Arena Consensus)

A private `_check_schema_version` helper reads the existing schema-version
relation through the actual connection before setup. A missing relation or
empty table retains current initialization behavior. A present stamp must be
exactly one positive SQLite integer; a greater version raises a ValueError
naming both stored/runtime versions and asking for a compatible backend.
Malformed stamps raise an actionable consistency error instead of restamping.
Both `init_db` and `connect` use the helper inside their existing try/finally
connection lifetime. Compatible schema setup and its separate commit remain.

No private-copy preflight is used: it cannot atomically certify the subsequent
connection and can omit uncheckpointed WAL state. Checking the actual connection
sees committed WAL state. Migration remains a quiescent operation; this patch
does not add a new cross-process migration-lock contract.

## 5. Scope Exclusions & Stop Conditions

Excluded: producer reservations, retention markers, session ownership and all
other B1/B2 behavior, which remain in the active prompt-lifetime Arena.
Stop before applying a production migration or recovery operation. No such
action is needed to build or verify this patch. A failing relevant regression
returns to the design; do not silently weaken the rejection contract.

## 6. Evidence Ledger

See `08_schema_open_guard_evidence.md` and domain analysis
`prompt_lifetime_arena/B_schema_open_guard.md`. Rollback anchor is master
`d0171b47`, v0.82.6. Current `_stamp_schema_version` updates any unequal version
after executescript; both entry points currently refresh schema before checking.
Existing tests require compatible older stamps to upgrade and connections to
yield outside transactions. Only agent bookkeeping was dirty before this plan.

## 7. Execution Phases (Follow TDD and CI at each phase)

- P0 — Record current source/spec boundary and independent adversarial review.
- P1 — Update schema/system specification and English user guide, then Korean.
- P2 — Add behavioral regressions and demonstrate future/malformed rejection
  fails on current code. Implement the small shared guard; run focused tests
  and Ruff before continuing.
- P3 — Run required local checks and an isolated DB/job smoke path; retain all
  production settings and paths.
- P4 — Version/changelog, PR, independent review, green CI, merge and cleanup.
  Remove this completed plan/domain/evidence after merge; resume lifetime work.
