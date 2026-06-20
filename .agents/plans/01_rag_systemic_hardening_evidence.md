# Evidence Ledger — RAG Systemic Hardening

Date: 2026-06-20 | Plan: `.agents/plans/01_rag_systemic_hardening.md`
Status: PRE-CODE. Refresh the validation rows immediately before P1 coding begins.

## Rollback Anchor
- Branch: `feature/rag-hardening` (from `master`).
- Clean HEAD before plan: `0d13304` (most recent: milestone init `b541d62` per session start — re-verify at code start).
- Safe revert: each phase is its own commit set; `git revert` per phase. P-02 migration (v10) is the only destructive step — back up `state.sqlite` before running it in testbed.

## Current Dirty Worktree
- `?? .agents/plans/` — this plan + Arena folder only. No source files modified. No competing in-flight work.

## Current Repository & Schema Reality (verified this session)
- **Findings already shipped (do NOT re-touch):** 04, 05, 07*, 08, 09, 10 — each pinned by a named regression test (see `00_problem.md` table). *07 is intentional/tested behavior, not a bug.
- **Latest DB migration: v9** (`_migrate_v9_graph_quality`, `db.py:1074`). The P-02 soft-link migration is **v10**.
- **`graph_relations`** (`db.py:358`): has `quarantine_reason` (frozen reason codes, `db.py:40`) + `lifecycle_status` (added in v9). **No `kind` column yet** — P-02 must add it (forward-only, backfill `'semantic'`).
- **`graph_entities`** (`db.py:339`): UNIQUE `(canonical_name, entity_type)` — soft-aliases must NOT be inserted as entity rows.
- **Snapshot/epoch**: `_source_epoch` (`context_service.py:153`), `_snapshot` (`:172`), `_conflict_response` (`:497`). P0 MUST measure whether the epoch is per-source or vault-wide — gates P-03(a).
- **Route admission**: `_ADMITTED_ROUTES = {local, source-section, global}` (`context_service.py:29`) excludes explore by design (§31.8). `test_context_fetch_does_not_admit_explore_route` pins this.
- **Explore path**: `orchestrator.py:119` (`route != "explore"` fork) → `:145` `build_evidence` → `:280` `_run_explore`.
- **Integrity surface**: `compiler_integrity` (`lint.py:1332`, §26.5) on-demand. P-03(b) reuses it via the `ingest_jobs`/`job_events` queue.
- **Failure Atlas**: `docs/specs/failure_atlas/` — `FAILURE_ATLAS.md`, `cases/F01..F13.yml`, `qrels.yml`, `support_labels.yml`, `fixture_corpus.yml`, `D2_HOLDOUT_RESULT.yml`; harness `backend/scripts/failure_atlas_holdout.py` + `backend/tests/test_failure_atlas_*`.
- **Feedback loop (P-01 source)**: `context_feedback` (`context_service.py:905`), FBK types incl. `irrelevant`/`incorrect`/`insufficient` (`:59`).

## Rollback Requirements
- Back up `state.sqlite` (testbed + any dev vault) before the P-02 v10 migration.
- After P-02 migration: assert `PRAGMA integrity_check = ok`, `schema_version = 10`, `graph_relations` row count unchanged vs. pre-migration snapshot.
- Stop + ask the user if row-count preservation or `integrity_check` fails (Stop Condition).

## Pre/Post Validation (fill at code time)
- [ ] P0 measurements recorded (epoch granularity, baseline explore trace, graph density, atlas contract).
- [ ] Per-phase `scripts/backend-check {pytest,ruff,mypy}` + `npx vitest` results.
- [ ] Testbed smoke (`VAULT_ROOT=testbed wiki add/sync/query`) per phase touching runtime.
- [ ] EN→KR doc sync confirmed per phase.
