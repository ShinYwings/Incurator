# RAG Systemic Hardening — Master Implementation Plan

Date: 2026-06-20
Status: DRAFT — Arena debate concluded; **awaiting user approval before any code** (Universal Strict Workflow Step 4).
Arena: `.agents/plans/rag_systemic_hardening_arena/` (briefing + lead_architect proposal + red_team + schema_guardian critiques)
Version target: **Minor** (new edge kind, new CLI surface, new spec sections) — exact bump decided at Step 10.

## 1. Objective
Implement the four genuinely-unimplemented systemic audit findings (06, 03, 02, 01),
each behind its own TDD phase, reusing existing machinery wherever it exists:

- **06**: explore route grounds on `ContextService.context_fetch` — one trace/snapshot/budget contract, no divergent retrieval path.
- **03**: soft-snapshot auto-rebase for non-intersecting epoch changes + advisory async pipeline healing.
- **02**: `soft_alias` candidate edges (no auto-merge) + giant-component quarantine, both with hard caps.
- **01**: human-gated promotion of real failures into Atlas candidates + deterministic noise-injection eval.

**Definition of done**: every phase has `pytest`+`ruff`+`mypy` green, docs/specs synced EN→KR, testbed smoke pass; the six already-fixed findings (04,05,07,08,09,10) and their tests do not regress.

## 2. Explicit Non-Goals
- **No autonomous entity merging.** Soft-links are proposals only.
- **No hard deletion during healing.** Quarantine/flag only; deletion is out of scope.
- **No fail-open rebase.** If per-node change detection is not provable, P-03(a) ships as a no-op + measured spike, NOT a stale-serving optimization.
- **No re-touching** findings 04/05/07/08/09/10 — they are settled.
- **No new external search-binary dependencies.**
- Not changing the legacy `build_evidence` for non-explore routes beyond what 06 requires.

## 3. Strict Quality Conditions & Release Gates
- 100% of new + existing tests pass; `ruff` and `mypy` clean via `scripts/backend-check`.
- Explore emits exactly one `QTR-*` row with ordered `CTXA-*` actions and a `PACK-*`/`SNAP-*` identical in shape to local/global. (red_team: parity test on insight-candidate ids.)
- Factual routes (`local`/`source-section`/`global`) NEVER traverse `kind='soft_alias'` (asserted test).
- Soft-alias traversal under explore obeys a hard fanout/hop cap, not only a budget penalty.
- A non-intersecting epoch change no longer returns `snapshot_conflict`; an intersecting one still does (both asserted).
- `PRAGMA integrity_check = ok`, `schema_version` bumped, row-count preserved after the P-02 migration; unchanged-rebuild is idempotent (zero new soft-alias edges on an unchanged corpus).
- Noise-injection eval is seed-deterministic (no CI flap).
- **Spaghetti refactor pass (user-requested):** before the release commit, a
  dedicated cleanup pass refactors any spaghetti code touched/created by this
  milestone (long branchy functions, duplicated trace assembly, dead legacy paths).
  Behavior-preserving; gated by the full test suite staying green.
- **Full-workflow testbed verification (user-requested):** the update is not done
  until the end-to-end pipeline — `wiki add` → `wiki update` → `wiki sync` →
  query/explore → **backprop** (`curator_update_node` + dependent DAG repropagation)
  — is exercised on **several scenarios** (`complex_math_backprop` and
  `testbed_template` at minimum) against a real LLM (Ollama is up locally), with
  results reported. A blocker (LLM/dep) must be documented, not silently skipped.

## 4. Locked Design Decisions (Arena Consensus)
1. **Sequencing 06 → 03 → 02 → 01**, increasing blast radius; each independently shippable/revertable.
2. **06**: admit `explore` to the fetch-grounding path; rewrite (not delete) `test_context_fetch_does_not_admit_explore_route` and update §31.8 in the same commit; `_run_explore` becomes a context-pack consumer; one trace via `_update_context_trace_after_synthesis` (`action_type:"explore"`).
3. **03(a) soft-rebase is GATED on proven per-node change detection.** P0 measures epoch granularity. If coarse, a per-source epoch column ships as P-03a-pre BEFORE any rebase. Rebase annotates `rebased_from`/`rebased_to` on the `CTXA-*` action. Fail-safe to strict conflict on any uncertainty.
4. **03(b) healing is advisory/dry-run by default** (`wiki integrity heal --report`); `--apply` is opt-in, quarantine-only, never hard-deletes, runs via the existing `ingest_jobs` queue, and refuses to mutate inside a snapshot cooldown.
5. **02**: new `graph_relations.kind` (`'semantic'|'soft_alias'`) via one forward-only `_migrate_vN_graph_soft_links` with `kind='semantic'` backfill + row-count-preservation test. Soft-alias generation is idempotent (content-hash guarded, `compiler_generations`-style). Traversal: factual skip; explore allowed with **hard hop/fanout cap + budget penalty**. Quarantine `giant_component_hub` is **advisory + de-prioritization first**, hard exclusion only behind a human-reviewed allow/deny list; threshold is vault-size-relative. `quarantine_reason` frozen-set widening is documented in `SCHEMA.md`.
6. **01**: promotion writes to `docs/specs/failure_atlas/cases/candidates/` (never auto-frozen); each candidate REQUIRES an independent expected-answer field, not just the failed transcript. Noise injection lives in `fixture_corpus.yml` `noise_profiles` with a pinned seed; adds a resilience-recall-floor metric.

## 5. Scope Exclusions & Stop Conditions
- **Exclusions**: real-time/streaming healing; cross-vault alias resolution; auto-freezing atlas candidates; LLM-confidence calibration beyond a labeled threshold.
- **Stop Conditions** (halt + ask the user):
  - P0 shows epoch granularity is coarse AND a per-source epoch column is non-trivial → confirm before schema work.
  - The P-02 migration cannot preserve row counts or fails `integrity_check`.
  - Quarantine threshold guts >X% of on-topic recall in testbed.
  - Any change would regress a pinned test for findings 04/05/07/08/09/10.

## 6. Evidence Ledger
See `.agents/plans/01_rag_systemic_hardening_evidence.md` (rollback anchor, schema reality, dirty-worktree check, pre/post validation). Created/refreshed immediately before P1 coding starts.

## 7. Execution Phases (TDD + CI at each phase; each phase blocks the next)
- **P0 — Research & Measured Baseline**
  - Measure epoch granularity (`_source_epoch`): per-source or vault-wide? Determines P-03a path.
  - Baseline current explore trace shape + insight-candidate ids for the parity test.
  - Measure current graph density / largest community share to calibrate the quarantine threshold.
  - Inventory Failure Atlas contract (`qrels.yml`, `support_labels.yml`, holdout) for promotion/noise hooks.
  - Verdict gate: confirm sequencing + any Stop Conditions with the user.
- **P1 — Contract Specification (docs-first; STOP for approval if schema changes)**
  - SYSTEM_BEHAVIOR §31.8 (explore admission), new §for healing/rebase, new §for soft-links/atlas; SCHEMA.md `graph_relations.kind`; guides + `_KR`.
- **P2 — P-06 Explore unification** (`orchestrator.py`, `context_service.py`). Verify: `pytest` parity test + rewritten admission test, `ruff`/`mypy`.
- **P3 — P-03 Soft-rebase + advisory healing** (gated by P0). Verify: intersecting/non-intersecting snapshot tests; healing dry-run test; `ingest_jobs` integration.
- **P4 — P-02 Soft-links + quarantine** (migration + generation + traversal). Verify: migration row-count + `integrity_check`; factual-skip + capped explore-traversal tests; idempotent-rebuild test.
- **P5 — P-01 Atlas promotion + noise injection** (eval harness). Verify: promotion writes candidate with expected-answer; seed-deterministic noise eval + recall floor.
- **P6 — Spaghetti refactor pass** (user-requested). Behavior-preserving cleanup of code this milestone touched; full suite stays green before/after.
- **P7 — Full-workflow testbed verification across several scenarios** (user-requested). Run `wiki add/update/sync` + query/explore + backprop on `complex_math_backprop` and `testbed_template` against the live Ollama backend; report per-scenario results; document any blocker.
- **P8 — EN→KR doc sync + version/changelog + release** per Universal Strict Workflow Steps 8–13.

> Each phase passes `scripts/backend-check {pytest,ruff,mypy}` + relevant `npx vitest` before the next begins. Plan file is deleted after ship (git history is the archive).
