# RELAY — ACTIVE

## Goal

Ship v0.40.1 as P7 of the stability regression audit: isolate request
cancellation, preserve non-streaming CLI model/PATH selection, make MCP tool
dispatch collision-free, settle shutdown requests, and bound backend processes.

## Plan Reference

- Branch: `release/v0.40.1`
- Master plan: `.agents/plans/02_v032_regression_audit.md` (P7)
- Evidence ledger: `.agents/plans/02_v032_regression_evidence.md`
- Domain analysis: `.agents/plans/C_retrieval_provider_analysis.md`

## Analysis & Reasoning

- P7 contains backward-compatible correctness and lifecycle fixes only; there
  is no new public command, setting, schema, or contract, so the release target
  is patch v0.40.1.
- Every request needs its own cancellation/process handle. A foreground pointer
  may select which request a UI cancel action targets, but cannot own all work.
- Model-facing MCP names may be sanitized, but dispatch must use an explicit
  exposed-name to original server/tool map rather than reverse parsing.
- Timeout/output policies must vary by command class so hung requests terminate
  without truncating legitimate build/update operations.

## Progress Status

- v0.40.0 merged in PR #105 as `066a158`; relay reset commit `57665c7` is the
  clean P7 rollback anchor.
- Inbox is empty; P7 is the next approved phase in the active audit plan.
- Created `release/v0.40.1` from clean `master`.
- Docs-first contracts now define per-surface cancellation, CLI model/PATH
  preservation, collision-free MCP dispatch, settled shutdown, and 2-minute /
  60-minute backend command classes with 16 MiB / 64 MiB output limits.
- Red phase reproduced 8 targeted failures. The root-cause implementation now
  passes TypeScript, 107 focused lifecycle tests, the latest 100-test focused
  set, all 769 plugin tests, and a production plugin build.
- Full backend gates pass (1386 passed / 6 skipped / 4 xfailed, Ruff, mypy), as
  do post-bump spec/version checks (10/10). Implementation commit: `033a4fd`.
- Release commit `d626a5d` is pushed in draft PR #106:
  `https://github.com/ShinYwings/Incurator/pull/106`.
- GitHub CI passed on release head `d626a5d` for backend, plugin, and version
  consistency. The delivery-note head changes only agent state; the PR is the
  live authority for its final check state.

## Critical Context / Blockers

- Production `second_brain` and active testbed state remain out of scope for
  provider/process unit and integration proofs.
- Stop and re-plan if a new public setting, command, persisted schema, or other
  user-facing contract becomes necessary.

## Immediate Next Action

1. Confirm the delivery-note head remains green in PR #106.
2. Human reviews and merges PR #106.
3. After merge, reset RELAY on updated `master`, then continue with P8.
