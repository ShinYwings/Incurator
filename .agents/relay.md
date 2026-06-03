# Agent Relay Handoff

**Last Updated:** 2026-06-03
**Last Agent:** Claude Code (Opus 4.8)

## Goal

Implement the v0.3.1 curation-native rebuild per
`.agents/plans/2026-06_v0.3.1_curation_native_rebuild/`. The user authorized
implementation (not just planning), wants clean/efficient/maintainable code with
no shortcut hacks, and explicitly said **backward compatibility does not matter**
for this migration (do clean replacements, no wrappers/legacy paths/persona
auto-mapping). User chose: start at Phase 0 sequentially; agent bundles logical
units and decides commits.

## Plan Reference

- Master: `.agents/plans/2026-06_v0.3.1_curation_native_rebuild/00_MASTER_PLAN.md`
- Code blueprint (concrete sequencing):
  `.agents/plans/2026-06_v0.3.1_curation_native_rebuild/11_CODE_LEVEL_IMPLEMENTATION_BLUEPRINT.md`
  (but DIVERGE from its §13 backward-compat guidance per user instruction).
- Exhibition Review Plan: `.agents/plans/2026-06_exhibitions_persistence_review.md`

## Analysis & Reasoning

13-phase sequence. Phase 0 (specs/guides before code) is mandated by the repo
workflow. Spec-sync rule requires all three spec domains at the same active
version with the prior version archived.

Guide strategy decision: instead of writing all 8 guides (4 EN + 4 KR) upfront
for unimplemented commands, guides are updated **per-phase** as each feature
lands, so docs stay truly in sync with code (the higher-order repo rule). The
v0.3.1 specs already define target behavior authoritatively.

## Progress Status

DONE (Phase 0):
- Created synchronized v0.3.1 specs (additive, preserving v0.2.2 verbatim then
  appending v0.3.1 sections):
  - `docs/specs/curator_schema/SCHEMA_v0.3.1.md` (§11–§19: source_spans,
    knowledge_units, graph_entities/relations, community_reports, memory_paths,
    prompt_runs, curation_plans, insight_candidates, artifact_dependencies,
    upgraded L1/L2/L3/L4 frontmatter, curate.yml KRS shape, id/prefix registry,
    source-truth protection).
  - `docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.3.1.md` (§15–§21: prompt
    registry/trace/validators, curate.yml compilation + curation plan flow,
    query routing local/global/explore/exhibition/source-section, backprop
    classification lifecycle, source-truth protection, CLI/MCP/plugin surface,
    testbed validation).
  - `docs/specs/plugin_schema/PLUGIN_SCHEMA_v0.3.1.md` (§9–§11: local plugin
    commands, query result + trace payloads, trace panel rendering).
- Archived v0.2.2 specs to each domain's `archives/` (git mv).
- Bumped version 0.2.2 → 0.3.1: `backend/__init__.py`, `backend/pyproject.toml`,
  `mcp_server.py` (now reads `__version__`), `plugin/manifest.json`,
  `plugin/package.json`, `plugin/src/agent/incuratorClient.ts` default.
- Added `backend/tests/test_v031_spec_sync.py` (10 tests, passing): single active
  spec per domain, prior version archived, title declares version, backend
  version matches active spec line.
- Verified `test_runtime_state.py` + `test_mcp_version.py` still pass after bump.

DONE (Phase 2 — DB schema v4, done before prompts per blueprint §13.1):
- `backend/src/curator/db.py`: `SCHEMA_VERSION = 3 -> 4`. Appended 10 v0.3.1
  tables to `SCHEMA_SQL` (source_spans, knowledge_units, graph_entities,
  graph_relations, community_reports, memory_paths, prompt_runs, curation_plans,
  insight_candidates, artifact_dependencies) with indexes. `connect()` already
  self-heals via `executescript(SCHEMA_SQL)` so tables auto-create (IF NOT
  EXISTS); no separate migration needed.
- Added module-level `import json`, `import uuid`. Added ~25 accessor functions
  at end of db.py: upsert_source_span/list_source_spans/get_source_spans_by_ids,
  upsert_knowledge_unit/list_knowledge_units_for_source, upsert_graph_entity
  (dedup by name+type, unions spans/units on merge), upsert_graph_relation
  (validates endpoints exist + confidence 0..1), get_graph_entity/
  find_graph_entities/relation_neighborhood, upsert_community_report/
  list_community_reports/get_community_report, record_memory_path/
  list_memory_paths, record_prompt_run/finish_prompt_run/get_prompt_run/
  list_prompt_runs_for_query, record_curation_plan/get_curation_plan,
  create_insight_candidate/list_insight_candidates/get_insight_candidate/
  update_insight_candidate_status, record_artifact_dependency/dependents_of.
  JSON columns decoded back to lists/objects in `_decode_*_row` helpers.
- `backend/tests/test_v031_db_schema.py`: 9 tests, all pass. Full backend suite
  271 passed (no regressions from version bump + schema v4).
- DB tables are internal state; documented in SCHEMA_v0.3.1 §11 (no user guide
  needed for raw tables).

DONE (Phase 1 — Prompt subsystem, the most important area):
- New package `backend/src/curator/prompting/`:
  - `contracts.py` — PromptContract (frozen), RenderedPrompt, ValidationResult.
  - `registry.py` — PromptRegistry + global REGISTRY + register(); unique ids.
  - `render.py` — `{{ field }}` mustache renderer (safe w/ literal JSON braces),
    input/message hashing.
  - `validators.py` — VALIDATORS dispatch table: json_model, source_span_ids,
    requires_source_spans, no_unknown_wikilinks, no_source_truth_pollution,
    confidence_range, relation_endpoints, exhibition_frontmatter. Uniform
    signature (raw, parsed, ctx)->ValidationResult.
  - `trace.py` — start/finish_prompt_run wrapping db prompt_runs; provider_name
    map; output hashing.
  - `runner.py` — run_prompt(): render→trace→client.chat(json_mode)→parse→
    validate→one json_repair retry→finish trace. Self-contained extract_json
    (handles {} and []). Returns PromptRunResult(trace_id, raw, parsed,
    validation, retry_count).
  - `evals.py` — offline eval harness + 6 builtin fixtures (no LLM).
  - `families/*` — 13 contracts registered: source_map, knowledge_unit_extract,
    entity_relation_extract, community_report_write, curation_plan,
    exhibition_write, query_router, query_local_answer, query_global_reduce,
    query_explore_expand, backprop_classify, backprop_patch_plan,
    note_context_pack. Each has typed pydantic input/output models + templates +
    validators.
- Tests (34, all pass): test_v031_prompt_{registry,validators,trace,
  family_contracts,eval_fixtures}.py. Ruff clean. Full backend suite 305 passed.
- DESIGN NOTE: `prompts.py` (1350 lines, current pipeline) is intentionally left
  intact. Per the clean-rebuild plan, existing prompt text migrates into families
  and prompts.py funcs are DELETED in the phase that rebuilds each pipeline
  (Phase 4 = L1/L2 extraction prompts; Phase 6 = query.py SYNTHESIS_SYSTEM_PROMPT;
  Phase 7 = backprop prompts). This avoids double-work and keeps the working
  pipeline green until each piece is replaced. End state = SYSTEM_BEHAVIOR §15.1
  (no wrapper functions in prompts.py).

ARCHITECTURE LOCKED (user-confirmed 2026-06-03): derived-projection compile model.
See memory [[v031-compile-model]]. DB (state.sqlite) = single source of truth;
`.curator/Collections/` CTX/ATM/CON markdown = derived disposable qmd corpus
(emitted from DB, never authoritative, no drift); only L4 Exhibition is
human/agent-facing (02_Wiki) and is reverse-parsed back to DB. qmd retained.
Specs updated: SCHEMA §"Storage model" + SYSTEM_BEHAVIOR §22 + curator_propose_
correction in §20. L1 = deterministic structure (no LLM); refinement = LLM at
L2/L3.

DONE (Phase 3 — curate.yml KRS):
- `curate_yml.py`: added dataclasses CurateReferenceMode, CurateGoal,
  CurateKnowledge, CurateOutput, CurateReasoning, CurateVerification,
  CurateBackprop, CuratePrompts; extended CurateSpec with goal/knowledge/output/
  reasoning/verification/backprop/prompts/reference_mode (kept legacy persona/
  min_confidence for current pipeline until Phase 6). Added per-section parsers.
  Added frozen CurationPolicy + compile_curate_policy() (compiles from NEW
  sections, NOT persona) + validate_curate_spec() + curate_spec_hash() +
  workspace_id_for(). VALID_ROUTES/AUDIENCES/CONTRADICTION_POLICIES constants.
- Tests (14): test_v031_curate_yml_krs.py, test_v031_curation_policy.py. Full
  backend suite 319 passed. My new code ruff-clean.
- NOTE: pre-existing dead `import fnmatch` in curate_yml.py trips ruff; left as-is
  per surgical rule (not introduced by me; present in committed HEAD).
- Guide for curate.yml fields deferred to Phase 8 (when `wiki curate validate/
  plan` surface them); spec §16 is authoritative meanwhile.

DONE (Phase 4 foundation — built + tested + green):
- New `backend/src/curator/pipeline/` package (compile-model stages):
  - `source_spans.py` — deterministic (NO LLM) span extraction:
    `spans_from_sections()` splits section dicts into paragraph/equation/code
    spans (preserves $$...$$ and ``` exactly), single-chunk → heading_section.
    `store_source_spans()` → db.upsert_source_span (idempotent by content hash).
  - `knowledge_units.py` — `extract_knowledge_units()` uses
    prompting.run_prompt(curator.knowledge_unit_extract) over in-memory spans
    (full text; DB stores only previews), persists units via db.upsert_knowledge_unit
    ONLY when the run validates (no partial writes). Returns KnowledgeUnitResult.
  - `projection.py` — `emit_atom_markdown(unit, atom_id)` renders the ATM page
    (derived qmd corpus) with source_span_ids/knowledge_unit_ids/prompt_trace_ids
    frontmatter. `new_atom_id()`.
  - `__init__.py` does NOT eagerly import submodules (keeps instant-L1 LLM-free).
- WIRED: `ingest_raw.generate_l1_structural_context()` now also extracts+stores
  source_spans to the DB during instant L1 (try/except guarded; CTX output
  unchanged so existing L1 tests stay green).
- Tests (14): test_v031_markdown_source_spans, test_v031_pdf_source_spans,
  test_v031_knowledge_unit_extraction, test_v031_atom_frontmatter_source_spans.
  Full backend suite 333 passed. New code ruff-clean.

PENDING — Phase 4/5 LEGACY CUTOVER (next focused pass, do together):
The legacy L2/L3 generation lives in `ingest_llm.py` + `ingest_orchestrator.py`
(writes `atoms`/`concepts` tables, ATM/CON pages, dag_edges) and powers many
existing tests (test_v021_*, integrity, etc.). The clean cutover = make
`wiki build` drive the new pipeline (knowledge_units + graph/communities +
emit ATM/CON projections), remove legacy atom/concept generation, move L1/L2/L3
prompt text from prompts.py into families and delete superseded funcs, then
update the dependent tests deliberately. This is a large, risky rewrite best done
as one focused pass spanning Phase 4 (units) + Phase 5 (graph/communities), since
both come from the same ingest_llm module. The new pipeline modules are ready and
tested to plug in.

PLAN SYNC (2026-06-03): Added AMENDMENT blocks to `00_MASTER_PLAN.md` and
`11_CODE_LEVEL_IMPLEMENTATION_BLUEPRINT.md` recording the two locked decisions
(no-backward-compat; derived-projection compile model) that override the original
plan text. Specs remain the authoritative source; plans are subordinate.

LEGACY-TEST POLICY (user-clarified): keeping the suite green is for regression
safety of UNTOUCHED code + tests-as-spec, NOT backward compat. For replaced
legacy L2/L3 behavior, DELETE or REWRITE its tests to the new model — do not add
shims to keep old tests passing.

DONE (Phase 5 modules — built + tested + green, additive):
- `pipeline/graph_index.py` — extract_entities_and_relations(): entity_relation_
  extract contract → db.upsert_graph_entity/relation (entities first so endpoints
  resolve; failed run persists nothing).
- `pipeline/community_reports.py` — detect_communities() (deterministic union-find
  connected components over graph_relations, NO LLM) + generate_community_report()
  (community_report_write contract → db.upsert_community_report). Content-addressed
  `_dependency_hash` (hashes entity/relation CONTENT, not timestamps, so staleness
  is detected at any resolution).
- `pipeline/memory_paths.py` — build_memory_paths() (deterministic bounded DFS over
  relations, linear-combo scoring per SCHEMA §11.6) + record_memory_paths() +
  query_hash(). No PPR (out of scope).
- `pipeline/projection.py` — added emit_concept_markdown()/new_concept_id() (CON
  page from a community_report).
- Tests (13): test_v031_entity_relation_extraction, test_v031_community_reports,
  test_v031_memory_paths, test_v031_concept_projection. Full suite 345 passed,
  ruff clean.

ALL NEW PIPELINE STAGE MODULES NOW EXIST + TESTED (additive, suite green):
  source_spans, knowledge_units, graph_index, community_reports, memory_paths,
  projection(atom/concept). They are NOT yet wired into `wiki build`.

DONE (Cutover step 1 — integrating orchestration built + tested, additive/green):
- `pipeline/compile.py`:
  - `compile_source_l2(paths, client, source_id)` — re-parses source → spans
    (stable ids) → knowledge_units (LLM) → emit ATM pages → graph entities/
    relations (LLM); writes CTX→ATM dag_edges + artifact_dependencies; sets
    l2_status done/error. Failed extraction sets l2 error + persists nothing.
  - `compile_global_l3(paths, client)` — detect_communities → generate reports →
    emit CON pages; sets l3_status done for L2-done sources.
  - Returns CompileResult (atom_ids, concept_ids, unit/entity ids, trace ids).
- Test test_v031_compile_pipeline.py (3, end-to-end with a DynamicFakeClient that
  cites runtime span ids from the prompt). Full suite 348 passed, ruff clean.

DONE (Cutover step 2a — BEHAVIORAL SWAP complete + green, 348 passed):
- `ingest_llm.run_l1_to_l3` rewritten: per source → `pipeline.compile.compile_source_l2`,
  then `pipeline.compile.compile_global_l3`; sets status curated; keeps finalize
  (rebuild_index, append_log_entry, _update_ledger, _update_overview). Dropped the
  legacy per-source ingest_source + global concept pass + atom-coordinator calls.
- `ingest_llm.run_l3_from_existing_atoms` rewritten to compile_global_l3 (kept —
  still used by backprop_agents + worker). Deletes old CON/EXH then re-emits.
- `ingest_worker.run_next_job` L2 now calls compile_source_l2 (was ingest_source);
  L3 still via run_l3_from_existing_atoms (compile-backed).
- Verified ALL live build paths use the new pipeline: cli `wiki build` (--wait via
  run_l1_to_l3; async via worker), MCP curator_build_source/all (→ worker), MCP
  curator_ingest_source (→ register + build_source, NOT legacy). Legacy
  `ingest_source` chain is now DEAD.
- Updated tests: test_v021_background_jobs.py repointed 7 patches from the removed
  ingest_source to `curator.pipeline.compile.compile_source_l2`; fixed fake-result
  shape (.ok/.error/.atom_ids) + pages_updated expectation. All 22 pass.
- callbacks_factory/mode kept in run_l1_to_l3 signature for caller compatibility
  (now unused → harmless Hint).

DONE (Cutover step 2b — LEGACY DELETION complete + green, 305 passed):
- Computed dead set via AST reachability (roots = ingest_llm symbols referenced
  cross-module + run_l1_to_l3/run_l3_from_existing_atoms/run_l4_scoped). Deleted
  43 dead functions from ingest_llm.py (2868 → 1315 lines): ingest_source + atom
  chain (_run_pass1_atoms/_run_sequential_atoms/_run_parallel_workers/
  _process_one_atom/_run_orchestrator_plan/_extract_atoms_for_task/
  _run_atom_coordinator/_find_existing_atom/_enforce_atom_contract), L3 legacy
  (_run_global_pass2_concepts/_run_pass2_concepts/clustering/concept-plan/
  fallback/_enforce_concept_contract), + orphaned helpers. KEPT L4 curate chain
  (run_l4_scoped → _run_pass3_synthesis → _write_one_exhibition_plan →
  _enforce_exhibition_contract → _stream_page) since L4 isn't rebuilt yet.
- ingest_orchestrator.py reduced 474 → 35 lines (kept only _expand_downstream_via_sql,
  used by sync).
- Fixed BROKEN live path: MCP curator_build_all called nonexistent
  ingest_llm.build_atoms/build_concepts (+ missing build_client import) → now calls
  run_l1_to_l3 with proper import.
- Deleted dead test files: test_v021_batch_extraction.py, test_v021_embedding_
  clustering.py. Removed 12 legacy methods from test_integrity.py (atom/concept
  contract, ingest_source, L3 clustering) — 573 lines; 12 valid tests kept.
- Full suite 305 passed. New pipeline files ruff-clean. (3 pre-existing E702
  semicolons remain in kept _extract_json — not mine, left per surgical rule.)
- prompts.py NOT pruned: still actively used by L4 curate / backprop / lint /
  persona (not yet rebuilt). Its now-dead L2/L3 constants will be pruned when those
  pipelines are rebuilt (Phases 6/7) to avoid removing still-referenced text.

>>> CUTOVER FULLY COMPLETE. The v0.3.1 curation-native compile pipeline now drives
>>> the entire L1→L3 build, legacy generation deleted, suite green (305).

DONE (Phase 6 core — retrieval/orchestrator, 318 passed):
- New `backend/src/curator/retrieval/` package:
  - models.py: QueryRequest, EvidenceItem, EvidencePack, GraphStatus,
    QueryResultV031, ROUTES.
  - router.py: graph_status() + deterministic choose_route() (explicit mode →
    source_key → explore signal → global signal → local; degrades to allowed
    routes; source-section always permitted).
  - evidence.py: build_evidence() per route — DB graph (entities/spans/reports/
    memory_paths) + qmd derived corpus (fallback, degrades w/ warning).
  - orchestrator.py: QueryOrchestrator.run() — resolve curate.yml policy → route
    → evidence → query family prompt via run_prompt (QTR query_trace_id groups
    prompt_runs) → QueryResultV031. explore route creates insight_candidates +
    records memory_paths.
- Tests (13): test_v031_query_router.py, test_v031_query_orchestrator.py
  (local/global/explore/source-section e2e with dynamic fake). ruff clean.
- NOT yet wired: legacy `query.run_query` (qmd+SYNTHESIS_SYSTEM_PROMPT) still
  powers cli/plugin/mcp query. Wiring run_query/CLI/MCP/plugin to QueryOrchestrator
  + retiring SYNTHESIS_SYSTEM_PROMPT is Phase 8. query family prompts already exist.

DONE (Phase 7 core — backprop classifier + insight lifecycle, 325 passed):
- backend/src/curator/backprop_classifier.py: BackpropEvent + classify_feedback()
  via curator.backprop_classify contract → BackpropClassification (traced PTR);
  invalid output → ambiguous/flag_review.
- backend/src/curator/insight_lifecycle.py: plan_action() maps classification →
  ActionPlan (correction→patch_generated, contradiction→flag+needs_review,
  derived_insight→create_insight_candidate, style_only→no_op, promotion_request→
  promote, ambiguous→flag_review); writes_source_truth invariant = False;
  patch_node_ids filters to generated prefixes only (ATM/CON/EXH/KNU/ENT/REL/REP).
  create_insight_from_classification() → db insight_candidates; promote_insight()
  writes ONLY 02_Wiki/ + sets status promoted (guards against source folders).
- Tests (7): test_v031_backprop_lifecycle.py (classify correction/invalid,
  plan never writes source, correction targets generated only, derived insight +
  contradiction candidates, promotion to 02_Wiki only). ruff clean.
- DEFERRED to Phase 8 (invoked via CLI/MCP): sync.py --backward wiring
  (classify→curator.backprop_patch_plan) + EXH markdown reverse-parse → DB +
  re-emit projection + curator_propose_correction MCP tool.

>>> BACKEND MODULE LAYER COMPLETE (Phases 1–7). All v0.3.1 subsystems built +
>>> tested + green (325): prompting, DB schema, curate.yml KRS, compile pipeline
>>> (live), graph/communities/memory, query orchestrator, backprop/insight.

NEXT — Phase 8 (INTERFACES — make new capabilities user-reachable):
- CLI (cli.py): `wiki prompt list|show|trace|eval`, `wiki curate plan|validate`,
  `wiki query --mode auto|local|global|explore|exhibition|source-section --trace`
  (wire to QueryOrchestrator), `wiki insight list|show|promote`.
- Wire query.run_query → retrieval.QueryOrchestrator (retire SYNTHESIS_SYSTEM_PROMPT,
  keep language bridge + EXH save), then prune prompts.py dead constants.
- MCP (mcp_server.py): curator_plan_workspace, curator_explore,
  curator_get_prompt_trace, curator_get_curation_plan, curator_list_insight_candidates,
  curator_promote_insight, curator_validate_curate_spec, curator_propose_correction.
- Hidden plugin cmds: wiki plugin curate plan / prompt trace / insight list / promote.
- Plugin TS (types.ts, incuratorClient.ts, incuratorQueryTrace.ts): trace payloads
  + panels (PLUGIN_SCHEMA_v0.3.1 §9–11). + Vitest.
- Guides: USER/WORKFLOW/MCP/PLUGIN (EN then KR) for the new surface.
NEXT — Phase 9: complex_math_backprop testbed smoke + prompt evals.

NEXT — Cutover step 2b (LEGACY DEAD-CODE DELETION, pure cleanup, no behavior change):
Dead chain to delete (verified only referenced within itself):
  ingest_llm: ingest_source, _run_pass1_atoms, and L2/L3 helpers only it used;
  ingest_orchestrator: run_l2_batch_extraction, _extract_atoms_from_chunk,
    _fallback_atoms_from_l1_candidates, _build_atom_page_from_data,
    _split_into_batches, _BATCH_EXTRACT_PROMPT, BatchAtomResult, etc.;
  ingest_llm: _run_global_pass2_concepts, cluster_atoms_by_embedding,
    _concept_plans_from_embedding_clusters, _run_atom_coordinator + concept-plan
    helpers; possibly SummaryData/AtomCandidate/ConceptPlan models IF unused.
  AUDIT each symbol for remaining refs (e.g. SummaryData used by CliIngestCallbacks/
  IngestCallbacks signatures, ConceptPlan elsewhere) BEFORE deleting.
Delete dead test files: test_v021_batch_extraction.py, test_v021_embedding_clustering.py
  (they test removed functions). Also move remaining L1/L2/L3 prompt text from
  prompts.py into prompting/families and delete superseded funcs. Keep suite green.
testbed smoke (LLM-gated): wiki add (instant L1, no LLM) works; full build needs LLM.

NEXT — Cutover step 2 (THE DESTRUCTIVE SWAP, do as its own focused pass):
1. Rewrite `ingest_llm.run_l1_to_l3` to drive the new pipeline: for each pending
   source call `pipeline.compile.compile_source_l2`, then once
   `pipeline.compile.compile_global_l3`; keep finalize (index rebuild, ledger,
   domain log). Remove its legacy per-source `ingest_source` L2 + global concept
   pass + atom-coordinator calls.
2. Point the worker (`ingest_worker.run_queued_jobs` / job processing) and any
   `--wait` path / MCP `curator_build_*` at the same compile flow.
3. DELETE now-dead legacy: ingest_llm L2/L3 internals (ingest_source atom path,
   _run_pass1_atoms, batch extraction in ingest_orchestrator, clustering,
   concept plans, atom coordinator, SummaryData/AtomCandidate if unused) and the
   `atoms`/`concepts` SQLite tables if nothing else uses them. Move any remaining
   prompt text from prompts.py into prompting/families and delete superseded funcs.
4. DELETE/REWRITE dependent legacy tests to the new model (test_v021_batch_
   extraction, test_v021_background_jobs, integrity, mcp tools reading atoms/
   concepts). Do NOT shim to keep old tests green (user-confirmed).
5. testbed smoke: `wiki add` / `wiki build` / `wiki status` / `wiki lint`.
This will turn the suite red transiently; budget a focused pass to land it green.

NEXT — THE CUTOVER (big integrating step, do as its own focused pass):
Rewrite `wiki build` (ingest_orchestrator.py 474L / ingest_worker.py 419L) to
drive the new pipeline end-to-end:
  add: parse → source_spans (already wired in instant L1)
  build: load spans → knowledge_units → graph_index → community_reports →
         emit CTX/ATM/CON projections from DB → qmd update/embed
Then DELETE legacy L2/L3 generation in ingest_llm.py (~2868L: atom coordinator,
clustering, concept plans, fallbacks) + the `atoms`/`concepts` SQLite tables if
unused, move remaining L1/L2/L3 prompt text from prompts.py into families and
delete superseded funcs, and DELETE/REWRITE the dependent legacy tests to assert
the new model (per user: do NOT shim to keep old tests green). Expect many
test_v021_*/integrity tests to be rewritten. Check: `wiki add/build/status/lint`
testbed smoke after cutover. This is destructive + large; confirmed acceptable by
user (no backward compat). The new modules are ready to plug in.
- Rewrite ingest to the compile model: parse source → write DB source_spans
  (deterministic, no LLM) → emit CTX projection md. Then LLM knowledge_unit_
  extract (use prompting.run_prompt + the registered contract) → DB
  knowledge_units → emit ATM projection md. Likely a new `pipeline/` package
  (source_map/knowledge_units stages) replacing the L1/L2 parts of ingest_raw.py
  /ingest_llm.py. Add deterministic markdown source-span extraction (headings/
  paragraphs/equations/code for md; pages for pdf). Move L1/L2 prompt text out of
  prompts.py into families (already have contracts) and delete superseded funcs.
  Tests: test_v031_markdown_source_spans, test_v031_pdf_source_spans,
  test_v031_knowledge_unit_extraction, test_v031_atom_frontmatter_source_spans.
  CAUTION: ingest_raw.py/ingest_llm.py are large & power many existing tests; plan
  the rewrite carefully to keep the suite green (or update tests deliberately).

PENDING — Antigravity Delegated Work (Validation Required):
Antigravity has committed the following changes (commits `daae083`, `2f42c10`, `6ae992b`, and `b73b2f8`), but Opus needs to verify and integrate them:
- Deprecated ephemeral Garbage Collection for Exhibitions (L4) in `lint.py` (now returns `[]`) to treat them as persistent living documents/memories.
- Updated related test suites (`test_lint_ephemeral_gc.py`, `test_query_exhibition.py`) to reflect deprecated GC behavior.
- Implemented In-Context Learning (ICL) `<selection>` tag injection in `chatSidebar.ts` & `systemPrompt.ts` to focus LLM context on selected text.
- Added real-time background job polling and status bar rendering in the plugin sidebar using `.curator/runtime/jobs.json`.
- Fixed streaming diff rendering race condition/bug by isolating markdown render targets in `diffViewer.ts` and `chatSidebar.ts`.
- Fixed sidebar text selection CSS bug so user chat messages can be copied.
- Changed sidebar AI edit workflow: edits/new files are now **auto-applied** directly to the vault when generation finishes. Diff blocks are hidden from the sidebar, replaced by a simple "✓ Applied / ✓ Created" status with a "✗ Revert" button to undo the change if rejected.
- **WARNING FOR BACKEND REBUILD (Workspace Path)**: The frontend plugin (`chatSidebar.ts`) was modified to always pass the global `vault` root path for chat sessions, removing the logic that locked the chat to the nearest `curate.yml` workspace.
  - **Opus Validation Request**: The documentation strictly states that `wiki query` and agent MCP tools expect a `curate.yml` workspace boundary. Since the frontend now defaults to the vault root, Opus MUST validate how the backend handles these vault-wide queries during the ongoing prompt/backend rebuild. Please check if this causes "curate.yml not found" errors on the backend, and reconcile the backend logic/docs with this new vault-wide UI behavior to prevent conflicts.
- Created architectural review plan `.agents/plans/2026-06_exhibitions_persistence_review.md` evaluating alternative models for user-memory consolidation. Opus needs to review this plan and decide on the persistence model (Option A vs B/C).

## Critical Context / Blockers

- All modified backend, plugin, and plan files have been committed to master (commits `daae083`, `2f42c10`, `0b10833`, `6ae992b`, and `b73b2f8`).
- pytest runs via `uv run pytest` from `backend/` (plain `python -m pytest` lacks
  pytest in the active interpreter). A benign VIRTUAL_ENV mismatch warning prints.

## Immediate Next Action

Begin Phase 1 prompt subsystem (TDD): scaffold `prompting/` package, write
failing tests for registry/contracts/trace/validators, then implement and move
existing prompt families out of `prompts.py`/`query.py`. Coordinate with Phase 2
DB schema for `prompt_runs` persistence.
