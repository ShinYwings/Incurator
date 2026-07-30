# v0.36.8 Master Implementation Plan

Date: 2026-07-30
Status: APPROVED — user requested the proposed follow-up; Arena debate concluded.

## 1. Objective

Complete PR #96 so Convert-to-LaTeX selects the exact configured model, uses
low effort only when supported, and never relies on invalid catalogue slugs or
duplicated hidden inference. Ensure the plugin's Antigravity chat selector also
passes its chosen model to the CLI.

## 2. Explicit Non-Goals

- No redesign of the general provider/failover architecture.
- No change to full-page PDF ingest effort.
- No new user setting for extraction effort.
- No changes to output normalization beyond the existing transcription contract.

## 3. Strict Quality Conditions & Release Gates

- Failing tests first for each dispatch defect.
- Exact Antigravity model IDs match installed `agy 1.1.8`.
- Explicit extraction slots pass `low` only if declared; otherwise omit effort.
- Main-client fallback retains its configured effort.
- Backend pytest/ruff/mypy and plugin vitest/build pass.
- English docs/specs are updated before Korean guide synchronization.

## 4. Locked Design Decisions (Arena Consensus)

- Capability facts live in `models.json`; task policy lives in
  `_resolve_extract_client`; transport lives in client command builders.
- `make_client_for` accepts a keyword-only effort and performs no implicit
  task-policy selection.
- The extraction resolver picks the first explicit slot once. It does not call
  the ingest resolver because their effort policies differ.
- Fixed-thinking Antigravity Claude variants expose no selectable effort.
- Plugin Antigravity commands always include the selected nonempty model.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: Provider authentication setup and installing missing Ollama
  vision models.
- **Stop Conditions**: Stop only if the live CLI no longer exposes the measured
  model IDs or if the public fallback contract conflicts with current specs.

## 6. Evidence Ledger

- **Current Repository Reality**: PR #96 is draft and green at
  `0b82d8a`; plugin Antigravity args omit `--model`; backend independent extract
  clients omit effort; catalogue Opus slug is stale.
- **Current Dirty Worktree**: Clean before capturing this review report.
- **Rollback Requirements**: Non-destructive code/config edits only. Rollback
  anchor is `0b82d8a0aa74b09f2157e0c848b53b13ad90aa54`.

## 7. Execution Phases (Follow TDD and CI at each phase)

- **P0 — Research & Measured Baseline**: Compare PR patch, current command
  builders, catalogue, and live CLI model list.
- **P1 — Contract Specification**: Update plugin/system specs and EN/KR guides
  with task-specific effort and exact model dispatch.
- **P2 — Tests**: Add failing backend catalogue/resolver tests and plugin CLI
  command test.
- **P3 — Core Logic**: Implement backend lookup/factory/resolver changes and
  plugin `--model`; run focused pytest/vitest plus ruff.
- **P4 — Integration**: Run full backend/plugin validation and live
  Antigravity transcription smoke.
- **P5 — PR Review**: Review the complete `origin/master...HEAD` diff, delete
  completed plan artifacts, update relay/changelog/PR, push, and wait for CI.

