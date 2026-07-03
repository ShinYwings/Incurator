# v0.32.0 Master Implementation Plan

Date: 2026-07-04
Status: APPROVED — the user explicitly requested removal of the path migration
command and related backward compatibility.

## 1. Objective

Remove the user-facing and internal compatibility layer for pre-v0.29 absolute
source paths. Preserve the current reference-key runtime behavior and make
`wiki status` work after one-time normalization of the current device DB.

## 2. Explicit Non-Goals

- Do not remove general DB schema evolution unrelated to portable paths.
- Do not remove current named-root or Zotero-key resolution.
- Do not refactor unrelated code labeled legacy or compatibility.
- Do not change plugin external-PDF persistence in this backend-only contract
  cleanup.

## 3. Strict Quality Conditions & Release Gates

- `wiki paths` is absent from CLI help and source.
- `portable_migration.py` and `_migrate_v10_portable_sources` are absent.
- Config no longer converts legacy external root arrays.
- Fresh schema-v11 DB tests, reference resolution tests, and full CI pass.
- Production DB has no absolute source locator, passes SQLite integrity checks,
  and `wiki status` succeeds.

## 4. Locked Design Decisions (Arena Consensus)

- Schema stays at 11 because the current stored contract does not change.
- v0.32.0 supports only current source columns and locator formats.
- Root-key mapping in `.cache/config/config.yml` remains current behavior.
- Production normalization happens before compatibility code deployment.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: unrelated legacy CLI aliases, plugin migrations, historical
  graph/compiler migrations, and system-stability refactors.
- **Stop Conditions**: stop production mutation if dry-run identities differ,
  backup creation fails, or SQLite integrity checks fail.

## 6. Evidence Ledger

See `.agents/plans/07_roadmap_evidence.md`.

## 7. Execution Phases

- **P0 — Research & Measured Baseline**: reproduce status failure and inspect
  the three legacy rows. Verify: dry-run output and clean worktree captured.
- **P1 — Contract Specification**: update specs and EN guides first, then KR
  guides. Verify: no docs instruct users to run `wiki paths`.
- **P2 — Failing Tests**: assert CLI/module/converter absence and current-only
  config behavior. Verify: targeted tests fail before implementation.
- **P3 — Current DB Normalization**: back up and normalize `second_brain` with
  v0.31.0. Verify: schema, identities, integrity, and status.
- **P4 — Compatibility Removal**: delete command/module/schema/config adapters.
  Verify: targeted pytest and ruff.
- **P5 — Testbed Smoke**: run status/add/sync/lint against the existing testbed
  without changing production config. Verify: reference resolution remains
  current-contract-only.
- **P6 — Full CI & Release**: run backend/plugin checks, bump 0.32.0, update all
  spec title lines and changelog, clean roadmap/plan state, commit, push, and
  open the PR.
