# RELAY — ACTIVE

## Goal

Close every confirmed finding from the second whole-system review and complete
the release-chain audit from v0.32.0 through merged v0.39.0.

## Plan Reference

- Master plan: `.agents/plans/02_v032_regression_audit.md`
- Evidence ledger: `.agents/plans/02_v032_regression_evidence.md`
- Domain analyses:
  - `.agents/plans/A_v032_release_history_analysis.md`
  - `.agents/plans/B_integrity_lifecycle_analysis.md`
  - `.agents/plans/C_retrieval_provider_analysis.md`
  - `.agents/plans/D_plugin_persistence_analysis.md`
- Umbrella: `.agents/plans/01_system_stability_overhaul.md`

## Analysis & Reasoning

- P5 started from merged v0.39.0 commit `d8d1e39` on
  `release/v0.39.1`.
- Two historical passes cover PRs #80–#86 and #98. They confirmed F01/F07 and
  added F23–F24: future-clock local reinsert and malformed current peer-header
  handling.
- Source deletion now closes canonical and device-local dependencies
  transactionally while preserving independently supported shared graph state.
- Post-publish failure or interruption recovers stable projections from the
  authoritative DB without another LLM call or generation. Re-emit updates only
  regenerated ATM/CON/SYN hashes and deleted orphan CTX hashes.
- No schema or public API/CLI contract change was required.

## Progress Status

- P1–P5: complete.
- Release commits:
  - `da57809` — source lifecycle/projection implementation and tests;
  - `17c96fc` — audit plan/evidence;
  - `c3f20c8` — v0.39.1 release metadata.
- Full backend: 1,373 passed, 6 skipped, 4 expected xfails.
- Plugin: 68 files / 737 tests passed.
- Ruff, Mypy (126 files), TypeScript, production build, docs/spec parity, and
  npm audit (0 vulnerabilities): passed.
- Isolated source deletion, lint 100/100, no-deep sync, and external Zotero
  Reference Mode smoke: passed.
- D2 was not rerun; exact non-Q06 drift hashes and rationale are re-armed.
- Production `last_root` and MCP pointers resolve to
  `/Users/shin/shinywings/second_brain`; active testbed was not mutated.
- `release/v0.39.1` is pushed and draft PR #102 is open.
- Latest-head push and pull-request CI both pass Backend and Plugin tests.
  Version Consistency passes on push and is intentionally skipped on the PR
  event.

## Critical Context / Blockers

- Human merge of PR #102 is the only remaining P5 action.
- Do not mutate production `second_brain`, the active ResNet testbed, or the
  consumed D2 holdout.
- P6 durable-state persistence work must start from clean merged `master`, not
  from the v0.39.1 release branch.

## Immediate Next Action

After PR #102 merges, fast-forward local `master`, remove the merged release
branch, and begin P6 from the clean merged anchor.
