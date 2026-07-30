# RELAY — ACTIVE

## Goal

Close every confirmed finding from the second whole-system review and audit the
release chain from v0.32.0 through current v0.39.0 for additional stability
regressions.

## Plan Reference

- Master plan: `.agents/plans/02_v032_regression_audit.md`
- Evidence ledger: `.agents/plans/02_v032_regression_evidence.md`
- Domain analyses:
  - `.agents/plans/A_v032_release_history_analysis.md`
  - `.agents/plans/B_integrity_lifecycle_analysis.md`
  - `.agents/plans/C_retrieval_provider_analysis.md`
  - `.agents/plans/D_plugin_persistence_analysis.md`
- Arena: `.agents/plans/v032_regression_audit_arena/`
- Umbrella: `.agents/plans/01_system_stability_overhaul.md`

## Analysis & Reasoning

- Current branch is unmerged `release/v0.39.0` at rollback anchor `b567427`;
  existing PR #101 CI is green.
- The v0.32.0+ range contains 19 merged PRs, 167 non-merge commits, and 216
  aggregate changed paths. Historical intent was read from deleted plans with
  `git show`.
- The second review confirmed 22 findings: two P0, fourteen P1, and six P2.
- PR #101 receives only direct authored-topology blockers: single-generation
  tombstone repair, audit membership, monotonic repair/retirement clocks,
  report invalidation, nested labels, and one-pass target decoding.
- Cross-system fixes ship as small v0.39.x patch releases by integrity boundary:
  source lifecycle/compiler recovery; durable persistence; provider/MCP process
  lifecycle; retrieval/prompt contracts.
- No schema change is currently required. A schema/public-contract change is a
  stop-and-replan condition.
- Audit closure requires historical-plan + merge-diff + current-contract
  triangulation and two consecutive dry passes per release.

## Progress Status

- User report captured and triaged into ROADMAP: complete.
- Historical release/plan inventory: complete.
- Current specs, implementation boundaries, and active testbed constraints:
  inspected.
- Arena proposal, red-team critique, defense, four domain analyses, master plan,
  and evidence ledger: complete.
- User approved the master plan on 2026-07-30.
- PR #101 has no GitHub-hosted review threads; the seven supplied in-session
  diff findings are the current-branch correction scope.
- P1 contracts/guides/changelog: complete.
- P2 red run: all seven direct defect oracles failed for the intended reasons.
- P3 implementation: complete; the seven oracles pass.
- Added and fixed a quiescence guard so healthy lone-generation reconciliation
  performs no write and cannot create replica sync ping-pong.
- Focused authored, sync/schema, graph/report/search, Failure Atlas, docs/spec,
  Ruff, and Mypy gates pass.
- D2 holdout was not rerun; its non-Q06 `_entities.py` drift evidence/hash is
  re-armed.
- Full backend: 1,358 passed, 6 skipped, 4 expected xfails.
- Plugin: 737 passed; TypeScript, production build, and npm audit (0
  vulnerabilities) pass.
- Isolated current-contract G9/Reference Mode smoke passes; the temporary vault
  and exact cache namespace were removed. Production `last_root` remains
  `/Users/shin/shinywings/second_brain`; active testbed was not mutated.
- Manifests remain synchronized at 0.39.0.
- Branch pushed at implementation head `4f3af29`; PR #101 description refreshed.
- Latest-head push and pull-request CI both pass Backend and Plugin tests;
  Version Consistency passes on push and is intentionally skipped on the PR
  event.
- Current phase: PR #101 is ready for human review and merge.

## Critical Context / Blockers

- Do not mutate production `second_brain` or the active ResNet testbed.
- Do not rerun the consumed D2 holdout. Update only permitted drift
  evidence/hashes if tracked implementation files change.
- The active ResNet scenario contains historical EXH-era assertions; use
  temporary current-contract fixtures rather than treating those phases as a
  valid release gate.
- Do not place source deletion, persistence, provider/MCP, and retrieval fixes
  into PR #101.
- Stop if current ownership/dependency data cannot close source deletion without
  a schema change or cannot distinguish shared graph state.

## Immediate Next Action

After PR #101 merges, fast-forward local `master`, preserve the active v0.32+
master plan, and begin P5 from the clean merged anchor. Do not branch the
cross-system source-lifecycle patch from `release/v0.39.0`.
