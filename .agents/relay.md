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

NEXT — Phase 4 (in progress): Source spans + knowledge units.
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

## Critical Context / Blockers

- Working tree has ~113 changed files from PRIOR sessions (unrelated to this
  Phase 0 work); my version-bump target files were already dirty before I edited
  them. A clean isolated commit of Phase 0 is therefore entangled. **No commit
  made yet** — awaiting user direction on how to handle the pre-existing dirty
  tree (commit Phase 0 selectively vs. leave uncommitted).
- pytest runs via `uv run pytest` from `backend/` (plain `python -m pytest` lacks
  pytest in the active interpreter). A benign VIRTUAL_ENV mismatch warning prints.

## Immediate Next Action

Begin Phase 1 prompt subsystem (TDD): scaffold `prompting/` package, write
failing tests for registry/contracts/trace/validators, then implement and move
existing prompt families out of `prompts.py`/`query.py`. Coordinate with Phase 2
DB schema for `prompt_runs` persistence.
