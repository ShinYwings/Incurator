# Cross-Agent Relay State

## Goal

Execute Plan E (`.agents/plans/E_external_research_design_matrix.md`) on
`feature/plan-e-research` without production behavior/schema changes.

## Plan Reference

- Master plan: `.agents/plans/E_external_research_design_matrix.md`
- Research package: `backend/research_spikes/`
- Wave A report: `backend/research_spikes/reports/wave_a.md`
- Wave B report: `backend/research_spikes/reports/wave_b.md`
- Wave B manifest: `backend/research_spikes/manifests/wave_b.yml`
- Draft PR: `https://github.com/ShinYwings/Incurator/pull/26`

## Analysis And Reasoning

- Wave B compared current depth-2 memory paths, connected components, and
  all-report global loading with disposable PPR, confidence denoising,
  query-relevant global selection, and confidence-filtered expansion.
- Unfiltered PPR matched current associative recall but leaked a noisy bridge
  and required `660` edge updates versus `4` traversed expansion edges.
- Filtered bounded expansion matched associative recall, added no forbidden
  evidence, exposed seeds/paths/source locators, and repaired the Jaguar
  car/animal homonym case.
- Synthetic confidence denoising reduced giant-component ratio from `0.714` to
  `0.300`. It had zero effect on the guarded production copy (`0.740` both
  ways) because all `1,180` current relation confidences are `0.9–1.0`.
- Query-relevant top-1 community selection improved measured global precision
  from `0.333` to `1.000` while reducing selected reports from `3` to `1`.

## Progress Status

- [x] P0 baseline and research safety ledger.
- [x] P1 primary-source candidate dossiers.
- [x] P2 frozen evaluation protocol.
- [x] Wave A retrieval units and evaluation controls.
- [x] Wave B graph, hierarchy, global, and expansion controls.
- [x] Peer review, schema guardian, QA, docs sync, and legacy sweep.
- [ ] **STOP: PM review/approval required before Wave C.**

## Scoped Wave B Decisions

- Unfiltered PPR: `reject-default` in the measured scope; `benchmark-later`
  only after Program 2 graph-quality gates.
- Denoised hierarchy / Leiden candidate: `benchmark-later`.
- Query-relevant bounded global selection: `adopt-contract` candidate pending
  P7 holdout/provenance audit.
- KG-guided expansion: `benchmark-later`; adopt only explainable
  seed/path/provenance/budget invariants as a contract candidate.

## Verification

- Focused research/atlas: `142 passed, 13 xfailed`.
- Full backend: `672 passed, 13 xfailed`.
- Plugin from `plugin/`: `44 files / 361 tests passed`.
- Research ruff and mypy: passed.
- Wave B primary/official source links: reachable or access-controlled.
- Production/testbed authoritative DB hashes: unchanged.
- Full production `mypy src/`: still fails with the same 73 pre-existing
  errors in untouched files.

## Critical Context And Blockers

- Do not start Wave C until PM review/approval.
- Preserve the unrelated dirty `GEMINI.md` edit.
- Do not commit `backend/research_spikes/local/`; it contains ignored private
  SQLite copies and raw result output.
- No version bump/changelog is appropriate: Plan E remains research-only and
  explicitly forbids production versions, dependencies, schema, and behavior
  changes.
- Current production relation confidence is not discriminative, so hierarchy,
  PPR, and expansion mechanism conclusions remain gated on Program 2.

## Immediate Next Action

PM reviews `backend/research_spikes/reports/wave_b.md`. After explicit approval,
continue with Plan E Wave C on the same branch.
