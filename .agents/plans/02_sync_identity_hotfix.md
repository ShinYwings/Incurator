# v0.32.1 Master Implementation Plan

Date: 2026-07-04
Status: APPROVED — user requested diagnosis and repair; Arena debate concluded.

## 1. Objective

Make macOS and Linux exchange distinct device snapshots and converge their
authoritative L1-L4 state without copying `state.sqlite`.

## 2. Explicit Non-Goals

- No promise to merge concurrent edits to the same source file or logical
  record. Concurrent reads and disjoint-file work remain supported.
- No SQLite schema or JSONL row-format change.
- No layer-count masking or Dashboard-only normalization.
- No rebuild of existing L2-L4 knowledge.
- No backward-compatible read of vault-local `sync_state.json`.

## 3. Strict Quality Conditions & Release Gates

- Separate backend caches always produce separate device ids.
- A synced/stale vault-local state file cannot affect device identity.
- Two devices with disjoint sources/KUs converge without row loss.
- Full backend/plugin CI and testbed autosync smoke pass.
- Production Mac DB remains backed up before recovery.

## 4. Locked Design Decisions

- Both backends may run concurrently. Distinct device snapshot filenames permit
  concurrent reads and disjoint-file work; existing LWW is a safety net for
  delivery order, not a promise to merge same-record concurrent edits.
- Bookkeeping path: `.cache/config/sync_state/<vault-hash>.json`.
- JSONL transport stays `.curator/sync/dev-<id>.jsonl`.
- Old `.curator/sync_state.json` is unsupported and ignored.
- Recovery retains `dev-0782dbcf0ff4.jsonl` until round-trip convergence.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: retired-device pruning and remote Linux shell automation.
- **Stop Conditions**: stop destructive recovery if SQLite integrity fails or
  if an import would delete existing live knowledge.

## 6. Evidence Ledger

See `.agents/plans/02_sync_identity_hotfix_evidence.md`.

## 7. Execution Phases

- **P0 — Baseline**: record DB/snapshot counts and collision evidence.
- **P1 — Contract Specification**: update system behavior and EN/KR guides.
- **P2 — TDD**: add cache-isolation and shared-id convergence regressions.
- **P3 — Core Logic**: move sync state helpers to backend cache.
- **P4 — Integration**: run backend/plugin checks and testbed autosync.
- **P5 — Production Recovery**: backup DB, deploy, autosync, wait for Linux
  round trip, verify both visible snapshots and Mac counts.
- **P6 — Release**: bump 0.32.1, changelog, delete plan files, push draft PR.
