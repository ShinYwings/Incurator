# Agent Relay Handoff

**Last Updated:** 2026-06-04
**Last Agent:** Claude Code (Opus 4.8)

## Goal

Implement the v0.3.1 curation-native rebuild. The backend module/interface layer
(Phases 0–9) is COMPLETE and green. We are now executing a **locked redesign** of
the curation/persistence model on top of it.

**Redesign (user-locked):**
- Curation = a **dynamic workspace-KRS-biased lens** over the refined DAG, NOT a
  frozen per-workspace Exhibition file. It is produced fresh per query and never
  stored.
- Concept/graph layers (L3: entities/relations/community_reports) are KEPT.
- Add an explicit **shared L4 Synthesis layer** (durable, workspace-independent,
  source-grounded — like the synthesis tier in other LLM wiki repos). The
  Curation lens sits ABOVE this layer and selects/recombines L3/L4 nodes.
- Two agent surfaces: `fetch_context` (evidence pack only, for reasoning agents
  with their own LLM) and `answer` (evidence + synthesis, for `wiki query` CLI).
- Backprop = correction-driven and EXH-independent. Memory = additive bias (KRS +
  insights), never a frozen package.
- NO backward compatibility (clean replacements). User performs all git commits.

## Plan Reference

- `.agents/plans/2026-06_curation_rethink.md` and
  `.agents/plans/2026-06_curation_persistence_redesign.md` (design proposals).
- Specs (all synchronized at v0.3.1):
  `docs/specs/curator_schema/SCHEMA_v0.3.1.md`,
  `docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.3.1.md`,
  `docs/specs/plugin_schema/PLUGIN_SCHEMA_v0.3.1.md`.

## Analysis & Reasoning

Compile model (locked): DB (`state.sqlite`) = single source of truth;
`.curator/Collections/` markdown = derived, disposable qmd corpus (emitted from
DB, never authoritative). L1 = deterministic (no LLM); refinement = LLM at L2/L3;
synthesis = LLM at L4. The synthesis layer is content-addressed by the whole
report corpus so it is skipped when nothing changed and regenerated wholesale on
any change.

## Progress Status

IN PROGRESS — REDESIGN R3 (remove frozen-Exhibition subsystem). User chose
"Full R3 now (backend + plugin)". Backend is currently GREEN (357 passed) and
importable. Engineering decision: keep `LAYER_L4`/`PREFIX_L4`/`TYPE_L4` +
`paths.exhibitions` as INERT legacy constants (many status/path helpers reference
them; the dir just stays empty) — removed the BEHAVIOR, not every constant.
- R3a DONE: removed exhibition route (ROUTES, evidence `_active_exhibition_item`,
  curate_yml VALID_ROUTES/allowed_modes defaults) + tests.
- R3b DONE: deleted `curator.exhibition_write` family, `exhibition_frontmatter`
  validator, eval case (→ synthesis), registry test, `Route` literal, curation_plan
  `active_exhibition_block`.
- R3c PARTIAL: removed callers (`wiki curate`/`wiki refresh` CLI commands, the
  `wiki build` L3→L4 forward-prop block, orphan cli helpers
  `_curate_spec_hash`/`_find_workspace_exhibition`). STILL TODO: delete the now-dead
  L4 functions in ingest_llm.py (`run_l4_scoped`, `_run_pass3_synthesis`,
  `_write_one_exhibition_plan`, `_enforce_exhibition_contract`,
  `_run_exhibition_refinement`, `find_workspace_exhibition`,
  `_get_scoped_concept_ids`, `_count_followup_sections`,
  `_extract_followup_questions`, `invalidate_exh_cache_for_concept`,
  SynthesisPlan/SynthesisPlanResult, `_stream_page` if orphaned) + prompts.py
  exhibition prompt text.
- R3d DONE: `query.run_query` is sessionless (no EXH save; removed
  `_save_curation_page`/`update_curation_page`/`_derive_core_concepts`/
  `_concept_paths_for_atom`/`_atom_ids_for_context`, `saved_path`/`on_saved`,
  pinned/ephemeral params, SYNTHESIS prompt EXH-authority text). plugin_api +
  mcp `curator_query` reworked: no cache/EXH file, return answer + trace
  (synthesis_node_ids/community_report_ids/trace_id/route). cli `query` command
  dropped `--save-as`/`--curate`, scope `exhibitions`→`synthesis`.
- R3h PARTIAL: deleted `curator_curate_workspace` tool; `search_curator` stripped of
  proactive-curate/ws_exh/update_curation_page. STILL TODO: `promote_exhibition`
  (mcp+plugin_api) is now inert (reads empty dir) — rework to promote answer→02_Wiki;
  `curator_check_workspace` still reports exhibition status (degraded, harmless).
- EXH tests: deleted test_query_exhibition.py; rewrote test_plugin_query_language.py
  (sessionless); fixed test_plugin_cli.py (curate/refresh removed).
- R3c DONE: deleted the dead L4 generation chain from ingest_llm.py (run_l4_scoped,
  _run_pass3_synthesis, _write_one_exhibition_plan, _enforce_exhibition_contract,
  _run_exhibition_refinement, _get_scoped_concept_ids, _count/_extract_followup,
  invalidate_exh_cache_for_concept, _stream_page, _strip_embedded_frontmatter,
  _strip_out_of_scope_curator_links, _is_llm_refusal, _concept_atom_ids,
  SynthesisPlan/SynthesisPlanResult) ~530 lines. Kept find_workspace_exhibition
  (used by mcp curator_check_workspace, returns None on empty dir). EXH-cache test
  now auto-skips (try/except import guard). ingest_raw docstring updated.
- R3k SPECS DONE: SCHEMA §5 (Exhibition lifecycle removed), §15 (rewritten →
  "L4 Synthesis Layer And The Dynamic Curation Lens"), §1/§11 (synthesis from R1);
  SYSTEM_BEHAVIOR §9 (rewritten → "Sessionless Query Behavior"), §22.2 (backprop
  EXH-independent), prompt list (-exhibition_write), MCP tools list
  (-promote_exhibition +curator_fetch_context), §"hidden commands" (wiki
  curate/refresh removed).

**Backend GREEN: 353 passed, 4 skipped (from `backend/` cwd). Imports clean.**
(The 3 test_plugin_pdf_context_identity failures only appear from repo-root cwd —
pre-existing path interaction, pass standalone + from backend/.)

STILL TODO (remaining R3 — each non-breaking; backend is green now):
- R3e sync.py: EXH propagate/regenerate/find_dirty helpers are now inert no-ops
  on the empty 04_Exhibitions dir; `wiki sync` Mode A still references EXH. Rework
  to DAG-integrity + reemit only (or delete the inert EXH helpers).
- R3f lint.py: gc_ephemeral_exhibitions already returns []; EXH lint rules are
  inert no-ops on empty dir. Optionally relabel L4→Synthesis.
- R3i curate_yml: `exhibition`/`exhibition_intent` fields + write_exhibition_to_spec
  still parsed but unused; remove. (LAYER_L4/PREFIX_L4/TYPE_L4/paths.exhibitions
  KEPT as inert legacy by design — many status/path helpers reference them.)
- mcp promote_exhibition + plugin_api.promote_exhibition: now read the empty EXH
  dir (return not-found); rework promotion to answer→02_Wiki, OR rely on
  curator_promote_insight. cli plugin promote command (5792) calls it.
- overview/ledger + status tables still print "L4 Exhibitions | 0" → relabel to
  "L4 Synthesis" (ingest_llm _update_overview/_update_ledger; cli status; sync).
- R3j PLUGIN TS (NOT STARTED): remove exhibition commands/types/UI in plugin/src
  (curator_curate_workspace calls, exhibition_id handling, promote-exhibition
  button → promote answer, trace panel exhibition refs) + vitest. Large separate
  surface; do as its own focused pass.
- R3k GUIDES (NOT DONE): USER_GUIDE / WORKFLOW_GUIDE / MCP_USER_GUIDE / PLUGIN_GUIDE
  EN+KR — remove wiki curate/refresh, query --save-as/--curate, curator_curate_workspace,
  ephemeral/promoted Exhibition; describe sessionless query + synthesis layer +
  curation lens. (WORKFLOW + MCP guides already partly updated in R1/R2.)

DONE — REDESIGN R2 (Curation lens uses L4 synthesis):
- models.py: `EvidenceItem.synthesis_node_id`, `EvidencePack.synthesis_node_ids`,
  `QueryResultV031.synthesis_node_ids`.
- evidence.py: `_synthesis_items()`; **global** route leads with synthesis nodes
  then community reports; **explore** primer includes synthesis nodes.
- orchestrator.py: `run` + `fetch_context` propagate `synthesis_node_ids` (and a
  `synthesis_node_id` per evidence item in fetch_context).
- query.py `QueryResult.synthesis_node_ids`; mcp_server curator_explore returns it.
- Tests: test_v031_query_orchestrator.py +2 (global surfaces synthesis;
  fetch_context includes synthesis). Suite **364 green**, retrieval files ruff-clean.
- Spec SYSTEM_BEHAVIOR §17 (global/explore + trace + fetch_context). Guides
  MCP_USER_GUIDE EN/KR (documented curator_fetch_context, updated curator_explore).

DONE — REDESIGN R1 (shared L4 Synthesis layer):
- DB: `SCHEMA_VERSION` 4 → **5**; `synthesis_nodes` table (SYN-) + accessors
  `upsert_synthesis_node` / `list_synthesis_nodes` / `get_synthesis_node` /
  `clear_synthesis_nodes` / `_decode_synthesis_row` (db.py).
- Prompt: `curator.synthesis_write` family (prompting/families/synthesis.py),
  registered in families/__init__.py; validators source_span_ids / confidence_range
  / no_source_truth_pollution.
- Pipeline: `pipeline/synthesis.py` — `generate_synthesis()` (community reports →
  cross-cutting SYN nodes, source-grounded, skip-when-unchanged, wholesale
  regenerate), `reemit_synthesis()`, `corpus_dependency_hash()`.
- Projection: `projection.emit_synthesis_markdown()` + `new_synthesis_id()` →
  `.curator/Collections/04_Synthesis/SYN-*.md`. Constants `LAYER_SYN`/`TYPE_SYN`/
  `PREFIX_SYN`; `WikiPaths.synthesis` path property.
- Wiring: `compile.compile_global_l3()` calls `generate_synthesis()` after reports;
  `compile.reemit_projections()` now also re-emits SYN (returns synthesis count).
- Tests: test_v031_synthesis.py (4) + updated test_v031_db_schema.py (version 5,
  table, spec-drift guard), test_v031_reemit_projections.py, test_v031_prompt_registry.py.
- Specs: SCHEMA §1 topology + §11 header (v5 + SYN row) + new §11.11 synthesis_nodes;
  SYSTEM_BEHAVIOR §22.1 forward flow + §15 prompt list.
- Guides: WORKFLOW_GUIDE.md + WORKFLOW_GUIDE_KR.md 4-layer DAG section updated
  (L4 Synthesis + Curation lens).
- `orchestrator.fetch_context()` + MCP `curator_fetch_context` (evidence-pack
  surface) were added earlier and are green.
- **Full backend suite: 362 passed** (canonical run from `backend/` via
  `uv run pytest`). Ruff clean on all R1 files.

## Critical Context / Blockers

- pytest must run from `backend/` (`uv run pytest`). Running from repo root
  collects with a different cwd and 3 unrelated `test_plugin_pdf_context_identity`
  tests fail due to a pre-existing path/cwd interaction — they pass standalone and
  in the canonical backend/ run. NOT an R1 regression.
- ~49 pre-existing ruff errors live in OTHER modules (unused imports, etc.); none
  in files I touched. Left per surgical rule.
- The old frozen-Exhibition machinery (04_Exhibitions, lint GC, EXH reverse-parse,
  exhibition_write prompt, `wiki curate`) still co-exists; it is removed in R3.
- User does ALL git commits. R1 is an uncommitted logical unit ready to commit.

## Immediate Next Action

**REDESIGN R2 — Curation lens.** Make the orchestrator's global/explore routes draw
on the L4 `synthesis_nodes` as evidence (alongside community_reports), so the
dynamic lens actually surfaces the synthesis layer. `fetch_context` (done) is the
evidence-only agent surface; `answer` (run) is the synthesis surface for
`wiki query`. Add evidence builder support for SYN nodes + tests. Then R3 removes
the frozen-EXH machinery (ephemeral EXH files, lint.gc_ephemeral_exhibitions,
backprop_sync EXH reverse-parse), makes sessionless Q&A return answer+trace (no
file), optional DB query_cache TTL keyed on curate_spec_hash + DAG version, and
reconciles specs (§15/§9) + guides EN/KR.
