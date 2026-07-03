# RELAY — v0.31.0 Release PR Pending

## Goal

Ship the verified pipeline-state integrity and sync-hardening release.

## Current State

- Branch: `release/v0.31.0`
- Planning commit: `ca03880`
- Implementation commit: `659e7b3`
- Release commit: `chore(release): v0.31.0`
- Draft PR: https://github.com/ShinYwings/Incurator/pull/79
- Version: 0.31.0 / schema 11

## Verified Results

- Backend: 1178 passed, 6 skipped, 5 xfailed; ruff and mypy passed.
- Plugin: TypeScript passed; 665 tests passed.
- Testbed `gaussian_splatting`: real L1/L2 build completed; empty L3/L4 correctly
  reported `skipped`; structural verification 6/6.
- Production `second_brain`: backup at
  `/home/shin/.cache/incurator/backups/second_brain-v0.31.0-pre-20260703T1645KST/`;
  schema 11; integrity ok; 32/32 L1; zero errors; DB-serving L2/L3/L4 counts
  truthful; orphan projections removed; stale running job recovered to queued.
- Plugin 0.31.0 and backend runtime deployed via `setup.sh`.

## Critical Context

- The 30 queued L2 jobs are real pending work and were not auto-run as part of
  this display-integrity fix.
- No peer JSONL retaining the previously claimed L4 canonical rows was present;
  stale Markdown was not reverse-imported.
- Preserve user-owned untracked
  `.agents/drafts/sidechat_ui_regression_v0.29.0.md`.

## Immediate Next Action

Review and merge draft PR #79. The 30 queued L2 jobs remain user-controlled
pending work and are not part of the display-integrity release.

### Update (2026-07-03, Codex) — PR #79 review follow-up

- Addressed all seven unresolved reviewer findings without replying to or
  resolving the GitHub threads.
- Migrated and fresh `sources.updated_at` now converge on the same
  `NOT NULL DEFAULT strftime(...)` contract; legacy import timestamps are
  validated and receive a current UTC-millisecond fallback when invalid.
- Global L3 and projection re-emit share a 900-variable chunked span-provenance
  resolver.
- Zotero profile merging normalizes missing arrays before merging.
- Verification: backend 1184 passed / 6 skipped / 5 xfailed; plugin 666 passed;
  ruff, mypy, TypeScript passed. Testbed schema constraint/default, integrity,
  and foreign keys verified.
