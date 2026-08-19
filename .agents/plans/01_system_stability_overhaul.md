# System Stability Overhaul — Active Umbrella Plan

Updated: 2026-07-31
Status: ACTIVE — workstream 1 (release-chain integrity) is DONE: it was
`02_v032_regression_audit.md` P6–P10, which shipped through v0.40.1 with P8
recorded in CHANGELOG, and that plan has been deleted. Workstreams 2–4
(prompt architecture v2, safe decomposition, measured performance) remain
open and are why this file is still here. Completed diagnosis and shipped
releases removed; Git history
is the archive.

## Objective

Finish the remaining stability work with independently reviewable releases:
correctness first, then measured performance and existing-surface UX. Every
behavior change remains docs-first, TDD-first, and testbed-verified.

## Preserved Contracts

- `state.sqlite` remains authoritative; Collections markdown is derived.
- Retrieval remains DB-native FTS5/vector/RRF/rerank.
- Curator layers remain CTX/ATM/CON/SYN; EXH remains retired.
- No schema or public-contract change is implicit. Stop and re-plan as a Minor
  release if one becomes necessary.
- Production vaults and active testbeds are never debugging sandboxes.

## Remaining Workstreams

1. **Release-chain integrity**
   - Execute `.agents/plans/02_v032_regression_audit.md` P6–P10.

2. **Prompt architecture v2**
   - Establish golden fixtures and a cross-provider output-shape metric.
   - Version prompt profiles and normalize provider output at contract
     boundaries without merging Sidechat and Popover tool policies.

3. **Safe decomposition and exception hardening**
   - Characterize behavior before extracting remaining god-file ownership
     domains.
   - Replace silent broad catches only where a typed boundary outcome is
     defined and regression-tested.

4. **Measured performance**
   - Benchmark fixed RAG/DAG fixtures before optimization.
   - Accept changes only with a measured speedup and no quality regression.

5. **Existing-surface UX**
   - Address confirmed friction in chat, popover, diff, and dashboard surfaces.
   - Validate real plugin behavior in addition to unit tests.

## Release Gates

- `scripts/backend-check pytest`, `ruff`, and `mypy` when backend is touched.
- Full plugin Vitest, TypeScript, production build, and audit when plugin is
  touched.
- Relevant specs plus English guide, followed by faithful Korean guide sync.
- Isolated testbed and external Reference Mode smoke for affected paths.
- Version consistency and changelog for every code release.

## Stop Conditions

- DB schema or public contract change is required.
- A characterization test exposes disputed existing behavior.
- A deletion cannot be proven safe by a usage audit.
- The same validation gate fails three times without a new diagnosis.

## Completion

Close only when every remaining item is fixed or explicitly moved to Icebox
with a reason. Then delete this plan and its evidence ledger; Git retains the
history.
