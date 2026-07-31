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

### Update (2026-07-31, Codex)

- Corrected the initial stale-runtime diagnosis: the active plugin is v0.39.1,
  its bundle matches disk, and the live bundle contains the v0.36.4 permission
  merge.
- Reproduced `수식 (10)이 본문이랑 완전 다른데?` against the live PDF while
  observing `agy` and its settings. The plugin atomically inserted
  `$read_file$()` before launch; one `agy` process ran; `agy` removed the rule
  again on exit as expected for 1.1.9.
- The prompt contained page 5 through equation (9), only header-only hits for
  page 6, and the external iCloud/Zotero PDF absolute path. The launch command
  exposed only `/Users/shin/shinywings/second_brain` through `--add-dir`, so the
  model's attempt to locate equation (10) by native `read_file` was denied.
- Started `hotfix/v0.39.2-equation-reference-context` from merged v0.39.1 anchor
  `bc61fab`. Plan and evidence are ready; no implementation code has been
  written.
- User approved implementation readiness but deferred execution until the next
  session because Antigravity quota is low. Do not repeat diagnosis or ask for
  plan approval.
- **Immediate next action (start here):**
  1. Update `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`,
     `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`, and the English/Korean
     plugin guides so latest-user PDF references receive the same
     `<resolved_cross_references>` precedence as selected pointers.
  2. Add the failing current-page-(9)/next-page-(10) test in the plugin context/
     sidebar test suite. It must prove bounded next-page fetching and that the
     page-(10) body is inserted before generic PDF context.
  3. Integrate `resolveSelectionReferencesBlockAsync()` into sidechat latest-user
     PDF context assembly. Fetch missing pages through the existing read-only
     `getPdfContext(pageNum, radius=0)` boundary; do not widen `--add-dir`, add
     `command`, or use `--dangerously-skip-permissions`.
  4. Run focused plugin tests and TypeScript/build before any live provider call.
     Use the live external-PDF replay only after local gates pass, conserving
     provider quota.
- Approved plan: `.agents/plans/03_v0392_equation_reference_context.md`.
- Evidence: `.agents/plans/03_v0392_equation_reference_evidence.md`.
- Domain analysis: `.agents/plans/A_v0392_equation_reference_analysis.md`.
