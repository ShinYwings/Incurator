# Briefing — v0.32.0+ Stability Regression Audit And Repair Chain

Date: 2026-07-30

## 1. Problem

The user requested implementation of every finding from the second
whole-system review and a careful audit of all patches since roughly v0.32.0.
The current branch is unmerged v0.39.0 PR #101. Twenty-two high-confidence
findings already span source deletion, authored topology, LWW clocks, compiler
publication, retrieval degradation, provider cancellation, MCP lifecycle, and
durable local/plugin state.

## 2. Measured Scope

- Baseline: merged PR #80 / v0.32.0.
- Current target: `release/v0.39.0` at `b567427`.
- 19 merged PRs, 167 non-merge commits, 216 changed paths.
- Largest risk-bearing releases: v0.32.1 identity/storage, v0.34.0 backend
  facade extraction, v0.36.0 plugin facade extraction, v0.37.0 tombstones, and
  v0.39.0 authored topology.

## 3. Constraints

- Do not mutate the production vault or active testbed.
- Do not rerun the consumed D2 holdout.
- Do not widen PR #101 into every cross-system fix.
- No schema change is currently justified; stop and re-plan if one becomes
  necessary.
- Every code change is docs-first and TDD-first.
- Historical plans are read through Git; Git history is the archive.
- Delivery remains sequential and single-agent for context coherence. Arena
  roles below are explicit review personas executed by the primary agent; no
  delegated implementation is used.

## 4. Required Outcome

1. Close PR #101-specific blockers before merge.
2. Audit every v0.32.0+ release against one fault-transition matrix.
3. Ship cross-system fixes as a small v0.39.x patch chain.
4. End with zero unresolved P0/P1 findings; every P2 is fixed or explicitly
   queued with evidence and owner.

