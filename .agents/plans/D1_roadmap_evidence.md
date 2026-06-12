# D1 Evidence Ledger — Failure Atlas Diagnostic Baseline Release (v0.6.0)

Date: 2026-06-12
Plan: `.agents/plans/D_current_system_failure_atlas.md` (phases P0–P4 only)
Umbrella: `.agents/plans/03_rag_knowledge_quality_stabilization.md`
Approval: user `/goal 다음 마일스톤 진행해` (2026-06-12) — explicit start of the
next ROADMAP milestone (To-Do #1 Batch 1, first release).

## Rollback Anchor

- Branch base: `master` @ `8458f652d5481f377bd957ed1256240aaf470f54`
  (`chore: reset agent state post PR #23 merge (v0.5.6 shipped)`).
- Working branch: `release/v0.6.0` (fresh from merged `master`).
- Worktree at branch creation: **clean** (`git status --short --branch` showed
  no uncommitted changes — the "dirty worktree" note in the D plan is stale;
  PR #23 merged and the worktree was reset before this release started).
- Rollback: `git checkout master` — no shared-branch history is rewritten.

## Baseline Snapshot (P0)

| Identity | Value |
|---|---|
| Git SHA (base) | `8458f652d5481f377bd957ed1256240aaf470f54` |
| Version (pyproject/package/manifest) | `0.5.6` (all agree) |
| DB schema version | `6` (`schema_version` table, `testbed/.curator/state.sqlite`) |
| Testbed DB sha256 | `cfffd778763b12f98836130fe13fdf58c5e237f4e3a38d170e5e6ffc381674c6` |
| Testbed config sha256 | `fe0cf1053116fcf3e6ca17c579d2c600f5ae08ee345741b02f0217f642d1a861` |
| DB backup | `.agents/backups/state.sqlite.d1-baseline` (same sha256 as above, verified) |
| Active testbed scenario | `complex_math_backprop` (named by the D plan evidence ledger; `testbed_template` is the blueprint only) |
| Testbed init command | `wiki testbed init complex_math_backprop --force` |
| Current `testbed/` content | v0.5.6 smoke leftovers (`04_Resources/smoke_routed_paper.md`, `smoke_images_paper.md`; 2 sources, 206 spans/search_documents/search_chunks; L2–L4 tables empty) — **not** a scenario init |

Authoritative table counts at baseline (testbed DB): sources=2,
source_spans=206, knowledge_units=0, atoms=0, concepts=0, synthesis_nodes=0,
graph_entities=0, graph_relations=0, community_reports=0,
search_documents=206, search_chunks=206, query_traces=0, dag_edges=0,
memory_paths=0.

LLM-sensitive cases: no configured provider is assumed during D1. All D1
reproduction gates are deterministic and provider-free; provider-dependent
experiments are explicitly recorded as `blocked: provider` in the atlas
records (Strict Quality Condition: deterministic gates and configured-provider
benchmarks remain separate).

## Current Repository And Schema Reality (verified 2026-06-12, this SHA)

Each F-claim from the umbrella plan was re-verified against the working tree
before any test or doc was written. Exact boundaries:

- **F1** — `backend/src/curator/retrieval/evidence.py::_search_hits()`
  (lines ~52–59): builds `EvidenceItem(id, kind="search_hit", title, text,
  score)` and **omits `source_span_ids`** even though
  `search.query(..., hydrate=True)` hydrates them on each hit.
- **F2** — `QueryOrchestrator.fetch_context()` (orchestrator.py:83) and
  `.run()` (:127) each mint their own `QTR-` id, while
  `retrieval/engine.py:341` persists a separate `QTR-` trace inside
  `search.query(...)` invoked from `_search_hits` → one logical query can
  persist ≥2 disconnected `query_traces` rows with no parent/child link.
- **F3** — `QueryOrchestrator` resolves `CurationPolicy`
  (`_resolve_policy`, orchestrator.py:80/124) but calls
  `build_evidence(self.paths, request, route)` (:84/:129) — the signature
  (evidence.py:144) accepts no policy; KRS bias is not enforced in evidence
  assembly.
- **F4** — `route == "global"` loads **all** synthesis nodes (first 6) plus
  **all** community reports via `_report_items(db_path)` which never sees the
  query (evidence.py:98–112, 169–183); `route == "source-section"` loads
  **all** spans of the source unbounded (evidence.py:152–167).
- **F5** — `EvidencePack.evidence_block(max_chars=16000)`
  (retrieval/models.py:62–71): fixed character cutoff, silently drops items,
  no token budget, no explicit omission record.
- **F6** — `pipeline/synthesis.py:110`:
  `item_spans = list(item.source_span_ids) or span_ids` — a synthesis item
  with no model-provided spans is grounded to **all upstream spans**.
- **F7** — no test in `backend/tests/` proves unchanged-rebuild idempotency,
  atomic failed-batch behavior, or dependency-closure invalidation
  (`grep -rln "idempot" backend/tests/` → no compile-pipeline idempotency
  suite; `artifact_dependencies` rows carry no content hashes).
- **F8** — `pipeline/graph_index.py:23,130–136`: entity identity =
  exact `canonical_name` string; `pipeline/community_reports.py:59,76`:
  communities = connected components over relations (giant-component risk,
  no homonym protection).
- **F9** — `grep -rn wikilink backend/src/curator/pipeline/` → zero hits:
  authored wikilinks/embeds/tags/frontmatter refs are parsed elsewhere
  (page_writer/lint/sync) but never compiled into graph topology.
- **F10** — `pipeline/source_spans.py:22` `_PREVIEW_CHARS = 200`; span
  evidence text in packs uses `text_preview` (evidence.py:90,162) → searchable
  source evidence is capped at a 200-char preview.
- **F11** — `QueryOrchestrator._run_explore()` (orchestrator.py:208–250) is a
  single prompt pass; follow-up questions are rendered as text, never
  executed; no iteration, no sufficiency gate, no measured loop.
- **F12** — MCP `curator_fetch_context`/`curator_query`
  (mcp_server.py:3174–3207) delegate to `QueryOrchestrator`; the plugin's
  `plugin_api.curator_query` (plugin_api.py:678) is a separate code path with
  its own persona-boost and `l3_incomplete` fallback shape → no shared
  normalized context contract.
- **F13** — `tests/scenarios/complex_math_backprop/MASTER_PLAN.md` validates
  retired EXH-era behavior (`EXH-*.md`, `04_Exhibitions/`, `exhibition_id`
  assertions at lines 43–273) → the active scenario does not measure the
  current DB-native architecture.

## Pre-Validation (before any change)

- `git status --short --branch` → clean, `release/v0.6.0` only.
- Baseline backend CI at branch base (before any change): `pytest -q` →
  **526 passed**, `ruff check src/` → clean (2026-06-12).

## Validation Log (appended as phases complete)

- P0 (2026-06-12): branch created, DB backed up, snapshot captured — no
  production behavior changed.
- P1 (2026-06-12): Failure Atlas spec + 13 case records authored; contract
  tests (`test_failure_atlas_contract.py`) pass — schema, lifecycle
  transitions, snapshot identities, oracles, fixture resolution all enforced.
- P2 (2026-06-12): all 13 deterministic reproductions green on first run —
  every baseline assertion matched predicted defective behavior
  (`test_failure_atlas_repro.py`: 13 baselines pass, 13 oracles strict-xfail).
- P3 (2026-06-12): mutation/degradation/atomicity experiments pass
  (`test_failure_atlas_experiments.py`): L1/search unchanged-rebuild
  idempotent; rename duplicates spans; failed batch leaves partial graph
  state; hybrid search degrades to lexical with warnings.
- P4 (2026-06-12): frozen corpus + qrels validated; deterministic lexical
  baseline measured (direct-factual dev/regression Recall@1=1.0, adversarial
  0 hard-negative outranks, associative Recall@5=1.0); holdout enforced
  unmeasured (`test_failure_atlas_eval.py`).
- Release validation (2026-06-12): full backend `pytest -q` → **643 passed,
  13 xfailed** (baseline was 526); `ruff check src/` + new test files clean;
  plugin `vitest run` (from `plugin/`) → **361 passed (44 files)**;
  `tsc` covered by CI. Spec titles + `ACTIVE_VERSION` + 3 version manifests
  all at 0.6.0.
- Known pre-existing gaps (NOT introduced by D1, no `src/` file touched):
  `mypy src/` reports 73 pre-existing errors in 25 files on master; GitHub CI
  does not run mypy (ruff/pytest/vitest/tsc/version-consistency are the
  gates). `ruff check tests/` (beyond CI's `src/` scope) has 6 pre-existing
  findings in old test files. Both predate this branch and are out of D1's
  diagnosis-only scope.
- Testbed: D1 changes no CLI/MCP behavior; testbed left untouched at the
  v0.5.6 smoke state captured in the baseline snapshot (no config/path
  changes to revert). Scenario re-init is deferred to D2, which owns
  current-architecture scenarios (F13).
