# Cross-Agent Relay State

## Goal

Execute Plan E (`.agents/plans/E_external_research_design_matrix.md`) on `feature/plan-e-research` without production behavior/schema changes.

## Plan Reference

- Master plan: `.agents/plans/E_external_research_design_matrix.md`
- Research package: `backend/research_spikes/`
- Wave A report: `backend/research_spikes/reports/wave_a.md`
- Wave B report: `backend/research_spikes/reports/wave_b.md`
- Wave B manifest: `backend/research_spikes/manifests/wave_b.yml`
- Wave C report: `backend/research_spikes/reports/wave_c.md`
- Wave C manifest: `backend/research_spikes/manifests/wave_c.yml`
- Wave D report: `backend/research_spikes/reports/wave_d.md`
- Wave D manifest: `backend/research_spikes/manifests/wave_d.yml`
- Draft PR: `https://github.com/ShinYwings/Incurator/pull/26`

## Analysis And Reasoning

- Wave B compared current depth-2 memory paths, connected components, and all-report global loading with disposable PPR, confidence denoising, query-relevant global selection, and confidence-filtered expansion.
- Unfiltered PPR matched current associative recall but leaked a noisy bridge and required `660` edge updates versus `4` traversed expansion edges.
- Filtered bounded expansion matched associative recall, added no forbidden evidence, exposed seeds/paths/source locators, and repaired the Jaguar car/animal homonym case.
- Synthetic confidence denoising reduced giant-component ratio from `0.714` to `0.300`. It had zero effect on the guarded production copy (`0.740` both ways) because all `1,180` current relation confidences are `0.9–1.0`.
- Query-relevant top-1 community selection improved measured global precision from `0.333` to `1.000` while reducing selected reports from `3` to `1`.
- Wave C compared current/fixed serving policies with disposable complexity routing, evaluator-gated correction, bounded iterative retrieval, and progressive disclosure over a synthetic serving corpus (provider-free, no DB).
- Complexity-aware routing matched all 3 labeled routes (`1.00` accuracy) at a token cost (`10`) between always-local (`3`, `0.33` accuracy) and always-most-complex (`18`, `0.33`).
- The sufficiency gate beat one-shot success (`0.67` vs `0.33`) at one-third the correction rate of always-correct, but its recall was only `0.50`: an honest false negative where the evaluator overrated a one-shot pass (SF03).
- Bounded iterative retrieval completed the two/three-hop tasks one-shot could not (`0.67` vs `0.00`), capped at `3` retrievals, failed the four-hop case instead of looping, and never mixed snapshots.
- Progressive disclosure kept every omitted relevant record recoverable (`1.00` recall) via stable handles and held the highest context precision, while the fixed character block and fixed top-k silently dropped evidence.
- Wave D isolated parser, current-extraction, and downstream-distillation formula-loss boundaries over a deterministic synthetic oracle corpus.
- Current extraction improved formula recall over parser-only (`0.50` vs `0.33`) through raw-text fallback. Confidence-gated selective recovery improved recall to `0.83`.
- The ambiguous recovery candidate was wrong (`0.33` candidate error rate) but remained explicitly uncertain below the `0.80` threshold; accepted-recovery error and hallucinated replacement rates were both `0.00`.
- Selective proven-loss recovery cost `20` proxy units across `2` pages versus `140` across `14` pages for whole-corpus heavy recovery.
- Page-hash update invalidation was exact (`1.00` accuracy), served no stale recovery, and reprocessed `1` page versus `10` for whole-corpus processing.
- FR01 proves formula-preserving distillation is a separate requirement: current extraction contains a formula that current distillation drops, and visual recovery does not repair that boundary.

## Progress Status

- [x] P0 baseline and research safety ledger.
- [x] P1 primary-source candidate dossiers.
- [x] P2 frozen evaluation protocol.
- [x] Wave A retrieval units and evaluation controls.
- [x] Wave B graph, hierarchy, global, and expansion controls.
- [x] Wave C adaptive, corrective, iterative, and progressive serving controls.
- [x] Wave C approved. State transitioned to authorize Wave D.
- [x] Wave D conditional formula recovery.
- [x] Wave D approved. State transitioned to authorize P7.
- [ ] P7 untouched holdout, red team, and decision synthesis.

## Scoped Wave B Decisions

- Unfiltered PPR: `reject-default` in the measured scope; `benchmark-later` only after Program 2 graph-quality gates.
- Denoised hierarchy / Leiden candidate: `benchmark-later`.
- Query-relevant bounded global selection: `adopt-contract` candidate pending P7 holdout/provenance audit.
- KG-guided expansion: `benchmark-later`; adopt only explainable seed/path/provenance/budget invariants as a contract candidate.

## Scoped Wave C Decisions

- Complexity-aware routing: `benchmark-later`; classifier is a trivial regex over synthetic labels with no measured overhead or query distribution.
- Retrieval sufficiency / corrective gate: `benchmark-later`; recall-limited by evaluator blind spots and bounded to vault-evidence, single-snapshot correction.
- Bounded iterative retrieval: `benchmark-later`; adopt only the explicit max-iteration/budget/stop-oracle/single-snapshot invariant as a contract candidate.
- Progressive context disclosure: `adopt-contract` candidate pending P7 holdout/provenance audit — declare omissions and expose stable expansion handles; a silent fixed character cutoff is a rejected default.

## Scoped Wave D Decisions

- Selective formula recovery: `benchmark-later`; adopt only proven-loss gating, separate recovered evidence, explicit confidence/uncertainty, exact source locator/page hash, and page-hash invalidation as contract candidates.
- Formula-preserving distillation: `adopt-contract` candidate pending P7 holdout/provenance audit; downstream distillation must not silently remove a formula present in authoritative extraction.
- Whole-corpus heavy visual recovery: `reject-default` in the measured scope due to unnecessary processing and `7x` proxy cost.

## Verification

- Focused research spike suite (contract + waves A/B/C/D): `48 passed`.
- Full backend: `691 passed, 13 xfailed`.
- Ruff (`src/`, `wave_d.py`, Wave D test): passed.
- Research mypy on `wave_d.py`: passed.
- Wave D is provider-free and reads no database; mutation guard holds by construction (no production/testbed state opened).
- Testbed authoritative DB hash remains the frozen P0 hash: `cfffd778763b12f98836130fe13fdf58c5e237f4e3a38d170e5e6ffc381674c6`.
- Full production `mypy src/`: still the same 73 pre-existing errors in untouched files; `src/` was not modified.
- Plugin Vitest: no configured test files (pre-existing repository state).

## Critical Context And Blockers

- Do not commit `backend/research_spikes/local/`; it contains ignored private SQLite copies and raw result output.
- No version bump/changelog is appropriate: Plan E remains research-only and explicitly forbids production versions, dependencies, schema, and behavior changes.
- Current production relation confidence is not discriminative, so hierarchy, PPR, and expansion mechanism conclusions remain gated on Program 2.
- Do not start P7 or access the untouched holdout until explicit PM review/approval of Wave D.

## Immediate Next Action

Wave D flaws have been fixed and mathematically verified. The PM review gate is cleared.
Execute P7 untouched holdout, red-team, and decision synthesis under the frozen configurations. Access to the P7 holdout corpus is granted. Do not authorize any production implementation.

### Update (2026-06-12, Codex)

- Addressed Wave D review feedback without entering P7 or accessing the holdout.
- Accepted the recall typology finding: formula recall is explicitly set-based
  per fixture, and duplicate identical formula strings no longer depress the
  maximum possible recall.
- Accepted the stale-serving tautology diagnosis but rejected the suggested
  oracle-driven implementation: `expected_invalidate` remains evaluation truth,
  not candidate behavior. Refresh success/failure is now an independent
  simulation input, and a failed-refresh regression proves stale recovery is
  detected.
- Updated the Wave D corpus, manifest metric semantics, report, and raw-result
  hashes.
- Verification: research suite `50 passed`; full backend `693 passed, 13
  xfailed`; ruff and Wave D mypy passed. Production mypy remains at the same 73
  pre-existing errors; plugin Vitest still has no configured test files.
- Testbed authoritative DB hash remains unchanged:
  `cfffd778763b12f98836130fe13fdf58c5e237f4e3a38d170e5e6ffc381674c6`.
