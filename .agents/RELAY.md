# Agent Relay State

## Status: ACTIVE — Program 1 / Plan D1 (Failure Atlas baseline release)

- **Goal**: Execute ROADMAP To-Do #1 Batch 1, first release: Plan D1
  (Current-System Failure Atlas diagnostic baseline + frozen oracle contract).
  User approved start via `/goal 다음 마일스톤 진행해` on 2026-06-12.
- **Branch**: `release/v0.6.0` (fresh from merged `master` @ `8458f65`).
- **Plan Reference**: `.agents/plans/D_current_system_failure_atlas.md`
  (phases P0–P4 + Intermission Gate; D2/P5/P6 deferred until Plan E merges).
  Umbrella: `.agents/plans/03_rag_knowledge_quality_stabilization.md`.
- **Active testbed scenario**: `complex_math_backprop` (named by the D plan's
  evidence ledger; `testbed_template` is only the blueprint). Current `testbed/`
  holds v0.5.6 smoke leftovers, not a scenario init.

## Progress Status

- [x] P0: approval granted, branch created, worktree clean at baseline
- [ ] P0: baseline snapshot + evidence ledger (`D1_roadmap_evidence.md`)
- [ ] P1: Failure Atlas case records F1–F13 + oracle/contract tests
- [ ] P2: deterministic reproduction fixtures
- [ ] P3: mutation/degradation/cross-client experiments
- [ ] P4: labels, holdout, baseline report, proposed thresholds
- [ ] Docs sync (specs + EN/KR guides), version 0.6.0, CHANGELOG, PR

## Critical Context / Blockers

- D1 is diagnosis-only: **no production behavior changes** before before-state
  evidence capture. Reproduction tests assert current (defective) behavior or
  are strict-xfail oracles.
- LLM-provider-dependent experiments must be run with configured providers or
  explicitly documented as blocked (deterministic provider-free gates separate).

## Immediate Next Action

Author `.agents/plans/D1_roadmap_evidence.md` with the baseline snapshot
(SHA, schema fingerprint, config hashes, scenario, rollback anchor), then
start P1 atlas records.
