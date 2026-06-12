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
- Wave C report: `backend/research_spikes/reports/wave_c.md`
- Wave C manifest: `backend/research_spikes/manifests/wave_c.yml`
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
- Wave C compared current/fixed serving policies with disposable complexity
  routing, evaluator-gated correction, bounded iterative retrieval, and
  progressive disclosure over a synthetic serving corpus (provider-free, no DB).
- Complexity-aware routing matched all 3 labeled routes (`1.00` accuracy) at a
  token cost (`10`) between always-local (`3`, `0.33` accuracy) and
  always-most-complex (`18`, `0.33`).
- The sufficiency gate beat one-shot success (`0.67` vs `0.33`) at one-third the
  correction rate of always-correct, but its recall was only `0.50`: an honest
  false negative where the evaluator overrated a one-shot pass (SF03).
- Bounded iterative retrieval completed the two/three-hop tasks one-shot could
  not (`0.67` vs `0.00`), capped at `3` retrievals, failed the four-hop case
  instead of looping, and never mixed snapshots.
- Progressive disclosure kept every omitted relevant record recoverable
  (`1.00` recall) via stable handles and held the highest context precision,
  while the fixed character block and fixed top-k silently dropped evidence.

## Progress Status

- [x] P0 baseline and research safety ledger.
- [x] P1 primary-source candidate dossiers.
- [x] P2 frozen evaluation protocol.
- [x] Wave A retrieval units and evaluation controls.
- [x] Wave B graph, hierarchy, global, and expansion controls.
- [x] Peer review, schema guardian, QA, docs sync, and legacy sweep.
- [x] PM reviewed/approved Wave B; Wave C authorized on the same branch.
- [x] Wave C adaptive, corrective, iterative, and progressive serving controls.
- [ ] **STOP: PM review/approval required before Wave D (P6 formula recovery).**

## Scoped Wave B Decisions

- Unfiltered PPR: `reject-default` in the measured scope; `benchmark-later`
  only after Program 2 graph-quality gates.
- Denoised hierarchy / Leiden candidate: `benchmark-later`.
- Query-relevant bounded global selection: `adopt-contract` candidate pending
  P7 holdout/provenance audit.
- KG-guided expansion: `benchmark-later`; adopt only explainable
  seed/path/provenance/budget invariants as a contract candidate.

## Scoped Wave C Decisions

- Complexity-aware routing: `benchmark-later`; classifier is a trivial regex
  over synthetic labels with no measured overhead or query distribution.
- Retrieval sufficiency / corrective gate: `benchmark-later`; recall-limited by
  evaluator blind spots and bounded to vault-evidence, single-snapshot
  correction.
- Bounded iterative retrieval: `benchmark-later`; adopt only the explicit
  max-iteration/budget/stop-oracle/single-snapshot invariant as a contract
  candidate.
- Progressive context disclosure: `adopt-contract` candidate pending P7
  holdout/provenance audit — declare omissions and expose stable expansion
  handles; a silent fixed character cutoff is a rejected default.

## Verification

- Focused research spike suite (contract + waves A/B/C): `38 passed`.
- Full backend: `681 passed, 13 xfailed` (the `+9` over Wave B are the new Wave
  C tests).
- Research ruff (`src/`, `wave_c.py`, Wave C test): passed.
- Research mypy on `wave_c.py`: passed.
- Wave C is provider-free and reads no database; mutation guard holds by
  construction (no production/testbed state opened).
- Production/testbed authoritative DB hashes: unchanged (untouched this wave).
- Full production `mypy src/`: still the same 73 pre-existing errors in
  untouched files; `src/` was not modified.

## Critical Context And Blockers

- Do not start Wave D (P6 conditional formula recovery) until PM review/approval.
- Preserve the unrelated dirty `GEMINI.md` edit.
- Do not commit `backend/research_spikes/local/`; it contains ignored private
  SQLite copies and raw result output.
- No version bump/changelog is appropriate: Plan E remains research-only and
  explicitly forbids production versions, dependencies, schema, and behavior
  changes.
- Current production relation confidence is not discriminative, so hierarchy,
  PPR, and expansion mechanism conclusions remain gated on Program 2.

## Immediate Next Action

Wave C (Plan E P5) is in progress on this branch: deterministic, provider-free
comparisons for complexity-aware routing, retrieval sufficiency/corrective
gating, bounded iterative retrieval, and progressive context disclosure. After
the spike, manifest, and report land, STOP at the next PM review gate before
Wave D (P6 conditional formula recovery). The untouched holdout remains
inaccessible until P7.
