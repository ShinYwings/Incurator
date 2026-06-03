# Incurator v0.3.1 Curation-Native Rebuild Master Plan

## 0. Planning-Only Scope

This directory is a planning and documentation suite for v0.3.1. It is not an
implementation patch.

The work in this phase is complete only when the master plan and child plans
define, in implementation-ready detail, how Incurator should evolve. Backend
code, plugin code, database migrations, generated prompts, and runtime behavior
must not be changed as part of this planning pass.

The immediate goal is to preserve and deepen Incurator's identity:

- `curate.yml` is the workspace Knowledge Requirement Specification, not a
  minor search-boost file.
- Exhibition staging is the defining interaction between the vault Curator and
  workspace Artist.
- Backpropagation is not a legacy side feature; it is the feedback mechanism that
  lets human and agent discoveries refine generated knowledge.
- Source truth remains immutable unless a human explicitly writes or promotes
  new knowledge through the proper workflow.
- Modern RAG systems should inform Incurator, but they must be absorbed into the
  Curator/Artist/Exhibition model instead of replacing it with a generic
  standalone RAG product.

## 1. Why v0.3.1 Exists

v0.2.x solved important operational problems: backend ownership, source
registration, Reference Mode, instant L1, async L2/L3, query-generated
Exhibitions, plugin/backend separation, and external-agent MCP support. However,
the current system still behaves too much like a search-plus-synthesis pipeline
in critical places.

The main v0.3.1 problem is not the absence of another retrieval store. The
problem is that curation, retrieval, prompt orchestration, query routing,
insight lifecycle, and backprop are not yet one coherent compiler.

Current weaknesses that motivate the rebuild:

- `curate.yml` influences retrieval too weakly. It should drive source policy,
  desired output, verification style, contradiction handling, exploration depth,
  and prompt selection.
- Prompt logic is scattered across `prompts.py`, `query.py`, plugin system
  prompts, lint/backprop utilities, and workspace provisioning. Prompt version,
  expected schema, validation, retry behavior, and trace are not first-class.
- Query behavior uses qmd search and synthesis, but does not yet perform
  GraphRAG-style community reasoning, memory-path retrieval, or DRIFT-like
  exploration as curation-native operations.
- L4 Exhibitions are sometimes treated as answer artifacts instead of carefully
  staged workspace context packages.
- Backprop exists as a system identity, but the future lifecycle for
  corrections, contradictions, and new derived insights needs a clearer schema
  and prompt plan.

## 2. Non-Goals

This plan explicitly rejects the following in v0.3.1 planning:

- Do not create a separate greenfield `.curator/notebase/` product that bypasses
  `curate.yml`, Exhibition staging, or backprop.
- Do not replace Incurator's curation metaphor with a generic vector database,
  GraphRAG clone, or LlamaIndex wrapper.
- Do not treat existing L1-L4 as automatically obsolete. Their names and exact
  storage shape may evolve, but their staged compilation role remains central.
- Do not implement code during this planning phase.
- Do not compress existing architecture documents into short summaries. Preserve
  prior detail and add more detail where the design has become concrete.

## 3. Documentation Suite Index

This directory is intentionally split into focused documents:

1. `01_INCURATOR_LINEAGE_ANALYSIS.md`
   - Recovers the system direction from existing `.agents/plans/` and docs.
   - Locks the principles v0.3.1 must preserve.
2. `02_EXTERNAL_RAG_SYSTEMS_REVIEW.md`
   - Reviews current external RAG/GraphRAG/memory/indexing systems.
   - Extracts adopt/reject lessons for Incurator.
3. `03_COMPARATIVE_ANALYSIS.md`
   - Compares external systems and current Incurator across design dimensions.
4. `04_CURATION_NATIVE_ARCHITECTURE.md`
   - Defines the v0.3.1 curation-native architecture.
   - Keeps `curate.yml`, Exhibition, and backprop at the center.
5. `05_PROMPT_SYSTEM_REBUILD.md`
   - Defines the prompt-system rebuild. This is the most important technical
     plan in the suite.
6. `06_CURATE_YML_SPEC_EVOLUTION.md`
   - Evolves `curate.yml` into a full Knowledge Requirement Specification.
7. `07_BACKPROP_AND_INSIGHT_LIFECYCLE.md`
   - Defines correction, contradiction, new insight, promotion, and source truth
     protection.
8. `08_INTERFACES_CLI_MCP_PLUGIN.md`
   - Plans CLI, MCP, plugin JSON, trace payload, and prompt-trace interfaces.
9. `09_DOCS_AND_TEST_STRATEGY.md`
   - Defines the docs/spec update order and test strategy for future
     implementation.
10. `10_DEEP_RESEARCH_IMPLEMENTATION_NOTES.md`
   - Re-analyzes external RAG systems at implementation-mechanics level.
   - Maps GraphRAG/LightRAG/HippoRAG/RAPTOR/LlamaIndex/Cursor mechanisms to
     concrete Incurator modules, schema gaps, and rejected shortcuts.
11. `11_CODE_LEVEL_IMPLEMENTATION_BLUEPRINT.md`
   - Defines file-by-file and function-by-function implementation guidance.
   - Names the new backend packages, prompt contracts, DB tables, CLI/MCP/plugin
     commands, TypeScript payloads, and test files needed for v0.3.1.

## 4. Source Documents To Respect

This plan suite is subordinate to current source-of-truth docs until the
v0.3.1 specs are written and approved. The following documents are required
context:

- `.agents/plans/2024-05_v0.2.0_system_build/INCURATOR_SYSTEM_BUILD.md`
- `.agents/plans/2024-05_v0.2.0_system_build/INCURATOR_SYSTEM_BUILD_EVIDENCE.md`
- `.agents/plans/2024-05_v0.2.1_update/v0.2.1_specs/00_Master_Plan.md`
- `.agents/plans/2024-05_v0.2.1_update/v0.2.1_specs/01_Architecture_Analysis.md`
- `.agents/plans/2024-05_v0.2.1_update/v0.2.1_specs/03_Autoencoder_DAG_Compiler.md`
- `.agents/plans/2024-05_v0.2.1_update/v0.2.1_specs/05_Sync_Backprop.md`
- `.agents/plans/2024-05_v0.2.1_update/v0.2.1_specs/09_Visualization_and_Observability.md`
- `.agents/plans/2024-05_v0.2.1_update/reference_mode_rag_plan.md`
- `.agents/plans/2026-06-01_Math_RAG_Backprop_Plan.md`
- `.agents/plans/2026-06-01_Generative_Backprop_Plan.md`
- `.agents/plans/2026-06-02_plugin_backend_ipc_plan.md`
- `.agents/plans/2026-06-02_zotero_backend_plugin_redesign_plan.md`
- `.agents/plans/2026-06_notebase_rag_plan.md`
- `docs/philosophy/ABOUT.md`
- `docs/guides/USER_GUIDE.md`
- `docs/guides/WORKFLOW_GUIDE.md`
- `docs/guides/MCP_USER_GUIDE.md`
- `docs/guides/PLUGIN_GUIDE.md`
- `docs/specs/curator_schema/SCHEMA_v0.2.2.md`
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.2.2.md`
- `docs/specs/plugin_schema/PLUGIN_SCHEMA_v0.2.2.md`

## 5. External References

The external-system review should cite and analyze these references:

- Microsoft GraphRAG indexing:
  <https://microsoft.github.io/graphrag/index/overview/>
- Microsoft GraphRAG query overview:
  <https://microsoft.github.io/graphrag/query/overview/>
- Microsoft GraphRAG local search:
  <https://microsoft.github.io/graphrag/query/local_search/>
- Microsoft GraphRAG global search:
  <https://microsoft.github.io/graphrag/query/global_search/>
- Microsoft GraphRAG DRIFT search:
  <https://microsoft.github.io/graphrag/query/drift_search/>
- LightRAG:
  <https://arxiv.org/abs/2410.05779>
- HippoRAG:
  <https://arxiv.org/abs/2405.14831>
- HippoRAG 2:
  <https://arxiv.org/abs/2502.14802>
- RAPTOR:
  <https://arxiv.org/abs/2401.18059>
- LlamaIndex Property Graph Index:
  <https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/>
- Cursor secure codebase indexing:
  <https://cursor.com/blog/secure-codebase-indexing>

## 5.1 Research Depth Requirement Added After Review

The first pass of this planning suite was too high-level. v0.3.1 planning must
be implementation-ready, not merely directionally correct. The child plans
therefore now include code-level research and implementation guidance:

- external systems are analyzed not only by concept but by pipeline shape,
  output artifacts, update strategy, and prompt/orchestration design;
- current Incurator modules are named directly;
- future code files, dataclasses, SQL tables, functions, CLI commands, MCP
  tools, plugin payloads, and tests are specified;
- `prompts.py`, `query.py`, `db.py`, `curate_yml.py`, `ingest_llm.py`,
  `plugin_api.py`, `mcp_server.py`, and plugin TypeScript files have explicit
  migration roles.

Any future implementation agent should treat `11_CODE_LEVEL_IMPLEMENTATION_BLUEPRINT.md`
as the concrete sequencing document after v0.3.1 specs/guides are approved.

## 6. Target v0.3.1 Thesis

The v0.3.1 thesis is:

Incurator should become a curation-native graph/memory compiler. The Curator
does not merely retrieve chunks. It reads a workspace's `curate.yml`, builds a
curation plan, chooses retrieval and synthesis strategies, stages an Exhibition,
records prompt and evidence traces, and accepts human/agent feedback as a
backpropagation signal. Modern RAG components such as community reports,
entity-relation graphs, recursive summaries, associative graph walks, and
incremental chunk caches are tools inside that compiler.

## 7. Future Implementation Order

After this planning suite is approved, the future implementation should proceed
in this order:

1. Create synchronized v0.3.1 specs in all three spec domains.
2. Update English user/developer guides, then Korean guides.
3. Implement prompt registry/contracts/tracing first, before changing retrieval.
4. Extend `curate.yml` parsing and workspace curation planning.
5. Add graph/community/report structures to the existing Curator pipeline.
6. Upgrade query routing and Exhibition synthesis.
7. Upgrade backprop and derived-insight lifecycle.
8. Wire CLI/MCP/plugin JSON interfaces over shared backend services.
9. Add testbed validation and prompt evals.

## 8. Acceptance Criteria For This Planning Suite

The planning suite is complete when:

- This directory contains the master and child plans listed above.
- The child documents provide long-form implementation reasoning.
- The prompt-system rebuild is detailed enough to implement without inventing
  major architecture.
- Incurator's identity around `curate.yml`, Exhibition, source truth, and
  backprop is preserved.
- The suite explicitly avoids backend/plugin code implementation in this phase.
