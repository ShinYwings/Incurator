# Cross-Agent Relay State

## Goal

Execute Plan E (`.agents/plans/E_external_research_design_matrix.md`) on `feature/plan-e-research` without production behavior/schema changes.

## Plan Reference

- Master plan: `.agents/plans/E_external_research_design_matrix.md`
- Research package: `backend/research_spikes/`
- Wave A report: `backend/research_spikes/reports/wave_a.md`
- Wave B report: `backend/research_spikes/reports/wave_b.md`
- Wave C report: `backend/research_spikes/reports/wave_c.md`
- Wave D report: `backend/research_spikes/reports/wave_d.md`
- P7 report: `backend/research_spikes/reports/p7.md`
- P7 manifest: `backend/research_spikes/manifests/p7.yml`
- Draft PR: `https://github.com/ShinYwings/Incurator/pull/26`

## Analysis And Reasoning

- P7 consumed the four research-spike holdout items exactly once under frozen Wave A-D configurations: `RUQ05`, `GQ07`, `HQ01`, `FR05`. Corpus hashes were verified identical before and after the run.
- The Failure Atlas qrels holdout (`Q06`) was NOT consumed: the qrels reserve it for a D2-approved evaluation procedure. P7 records that reservation explicitly.
- RUQ05 (blind probe): aggregate Recall@5 alone reports `1.00` while top-1 citation correctness (`0.00`) and hard-negative outranks (`2`) expose the failure — direct holdout proof of the fine-grained diagnostics contract.
- GQ07: memory walk `1.00`, unfiltered PPR `1.00` (but again surfaced noisy-bridge node N14 at 660 edge updates), filtered bounded expansion `0.50` — the true `N07→N08` ecology-link edge (confidence 0.25) sits below the frozen 0.5 filter. The threshold is a correctness/noise dial that cannot be set until Program 2 makes relation confidence discriminative.
- HQ01: frozen regex classifier routed the blind probe `local` correctly at token cost 1 vs 6.
- FR05 (proven loss, no recovery candidate): all policies recall `0.00`, nothing fabricated, loss remained explicit, selective cost 0 vs 10.
- All five red teams passed: provenance, benchmark leakage, framework bias, cost, update/delete.
- Final decisions (no production authorization): `adopt-contract` = fine-grained-rag-diagnostics (Plan D2), query-relevant-global (Program 3, coverage limitation recorded), progressive-context-disclosure (Program 3, coverage limitation recorded), formula-preserving-distillation (Program 2). `reject-default` = unfiltered passage-entity-ppr, whole-corpus heavy recovery. All others remain `benchmark-later` with revisit triggers in `reports/p7.md`.

## Progress Status

- [x] P0 baseline and research safety ledger.
- [x] P1 primary-source candidate dossiers.
- [x] P2 frozen evaluation protocol.
- [x] Wave A retrieval units and evaluation controls (approved).
- [x] Wave B graph, hierarchy, global, and expansion controls (approved).
- [x] Wave C adaptive, corrective, iterative, and progressive serving controls (approved).
- [x] Wave D conditional formula recovery (approved).
- [x] P7 untouched holdout, red team, and decision synthesis.
- [ ] P8 research validation and handoff (awaiting PM review of the P7 decision package).

## Verification

- Focused research spike suite (contract + waves A/B/C/D + P7): `60 passed`.
- Full backend: `701 passed, 1 failed (pre-existing env bug, see below), 2 skipped, 12 xfailed`.
- Ruff (`src/`, research runners, P7 test): passed. Research mypy on `p7_holdout.py`: clean.
- P7 is provider-free and reads no database; corpus hash guard verified identical before/after the run.
- Production `mypy src/`: `75` errors in untouched files. The previously recorded `73` was measured on the macOS environment; the delta is environment-only (different Python/stub versions) — `src/` was not modified on this branch.
- Plugin Vitest: no test files matched by the configured include pattern (pre-existing repository state).

## Critical Context And Blockers

- **Environment changed (2026-06-12): development moved from macOS (Apple Silicon, 8GB) to Ubuntu 24.04 (64GB RAM, 12GB VRAM).** Repo path here is `~/Workspace/Incurator` (macOS: `~/shinywings/Incurator`); active vault `~/Workspace/second_brain` (macOS: `~/shinywings/second_brain`). Both platforms remain supported targets. No runtime code hardcodes absolute paths (verified: only test fixtures contain them).
- **Testbed DB hash note:** the frozen P0 hash `cfffd778…` was recorded against the macOS machine's gitignored testbed copy. This Ubuntu machine's local `testbed/.curator/state.sqlite` is a different pre-existing copy (hash `4bb46326…`, mtime 2026-06-07) that P7 never opened or modified. The P0 mutation guard is satisfied by construction: P7 reads no SQLite at all.
- **New pre-existing bug captured in `.agents/USER_REPORT.md`:** `db.init_db` leaks its SQLite connection (sqlite3 context manager commits but does not close), leaving WAL sidecars; on Ubuntu/py3.11 this makes `tests/test_v021_status_stats.py::…bootstraps_when_db_file_exists_without_sources_table` fail with "database is locked". Not fixed here — Plan E forbids production changes; needs its own fix branch after triage.
- Do not commit `backend/research_spikes/local/`; it contains ignored private SQLite copies and raw result output. The official P7 raw-result hash is recorded in `manifests/p7.yml` (`sha256_at_recording`); do not re-run the CLI runner casually, as `latency_ms` fields change the file hash.
- No version bump/changelog: Plan E remains research-only and explicitly forbids production versions, dependencies, schema, and behavior changes.
- No P7 decision authorizes production implementation. Contracts land in Program 1/2/3 specifications during their own plans.

## Immediate Next Action

P7 is complete and pushed. Await PM review of the P7 decision package (`reports/p7.md`). On approval, execute P8: validate artifact completeness/link integrity, present the decision package, and hand specification requirements to the remaining Program-1 specification package. Stop after user approval — do not proceed into implementation under this plan.
