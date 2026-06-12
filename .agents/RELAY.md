# Cross-Agent Relay State

## Goal

Execute Plan E (`.agents/plans/E_external_research_design_matrix.md`) on
`feature/plan-e-research` without production behavior/schema changes.

## Plan Reference

- Master plan: `.agents/plans/E_external_research_design_matrix.md`
- P0/P1/P2 artifacts: `backend/research_spikes/`
- Wave A report: `backend/research_spikes/reports/wave_a.md`
- Wave A manifest: `backend/research_spikes/manifests/wave_a.yml`

## Analysis And Reasoning

- The D1 Failure Atlas is tier 1; a synthetic graph stress corpus is tier 2;
  ignored read-only SQLite copies are tier 3.
- The active `complex_math_backprop` testbed and production vault snapshots are
  schema version 6 while current code is schema version 7. They are guarded
  copied diagnostics/scale inputs, not the comparison baseline.
- Wave A tested raw chunks, deterministic heading context, and explicitly
  generated context across lexical, deterministic vector, and hybrid controls.
- Generated context beat heading context on the frozen source-scoped cases,
  preserved direct-factual retrieval and exact source-span linkage, but added
  125% indexed characters. This supports a scoped contract candidate only.

## Progress Status

- [x] P0 baseline and research safety ledger.
- [x] P1 eleven primary-source candidate dossiers and claim-to-spike mapping.
- [x] P2 frozen evaluation protocol, metric unit tests, and holdout guard.
- [x] Wave A retrieval-unit and fine-grained diagnostic comparison.
- [x] Peer review, schema guardian, QA, docs sync, and legacy sweep.
- [ ] **STOP: PM review/approval required before Wave B.**

## Verification

- Focused research/atlas: `129 passed, 13 xfailed`.
- Full backend: `659 passed, 13 xfailed`.
- Plugin from `plugin/`: `44 files / 361 tests passed`.
- Research ruff and mypy: passed.
- Production/testbed authoritative DB hashes: unchanged.
- Full production `mypy src/`: still fails with 73 pre-existing errors in
  untouched files.
- Mandated root-level Vitest command finds no tests because the config include
  path is plugin-relative; running from `plugin/` passes.

## Critical Context And Blockers

- Do not start Wave B until the PM reviews Wave A.
- Do not commit `backend/research_spikes/local/`; it contains ignored private
  SQLite copies and raw result output.
- Existing qmd references found by the legacy sweep belong to the separate
  queued purge milestone and were not changed.
- No version bump/changelog is appropriate: Plan E explicitly forbids
  production versions, dependencies, schema, and behavior changes.

## Immediate Next Action

PM reviews `backend/research_spikes/reports/wave_a.md`. After explicit approval,
continue with Plan E Wave B on the same branch.
