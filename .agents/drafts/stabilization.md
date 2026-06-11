# Core RAG & Knowledge Distillation Stabilization Plan

## Context
We need to resolve the hallucination, edge loss, and prior knowledge mapping instabilities occurring in the current RAG search engine (Qwen3 Reranker + FTS5) and knowledge distillation pipeline. This is a core task that lays the foundation before developing the Knowledge Sync Bridge and PDF Annotation.

## Core Product Thesis (Clarified 2026-06-11)

Incurator must let an agent use a notes vault the way a coding agent uses a
codebase:

- inspect the whole repository/vault without loading everything into context;
- discover the right module/note, symbol/anchor, dependency/link, and exact source;
- compile raw files into reusable semantic prior knowledge;
- retrieve only the knowledge needed for the current task;
- progressively expand from an index/summary to exact evidence;
- verify every reused claim against source truth;
- preserve changes, contradictions, and human approvals over time.

The analogy is structural, not literal. Notes are not code and should not be
forced into a programming-language schema. The compiler must extract note-native
meaning such as claims, definitions, decisions, procedures, questions, examples,
equations, contradictions, authored wikilinks, headings, block references,
citations, and provenance.

The final consumers are:

1. external agents connected through MCP;
2. the Obsidian agent/sidebar/popover;
3. backend answer and exploration routes;
4. humans inspecting Sources & Trace.

The primary product is therefore **reusable, source-grounded prior knowledge and
bounded evidence packs**, not merely a better top-k search result or a larger
knowledge graph.

## Mandatory Work Order

This heart-of-system milestone must follow this order:

1. deeply diagnose the current RAG + DAG hybrid end to end;
2. deeply research how external systems solve each diagnosed failure;
3. write a detailed target architecture and implementation specification;
4. only then implement against frozen evaluation gates.

The current planning files are a research/program plan. They are not permission
to begin implementation and are not the final target architecture specification.

## Revised Three-Program Split

The earlier split by technical component (`retrieval / math / graph`) is rejected
because later compiler changes would invalidate earlier retrieval baselines.

1. **Truth Contract & Quality Observatory**
   - Produce the Failure Atlas, External Design Matrix, Evaluation Specification,
     and Target Architecture Specification.
   - Implement only the diagnostic/evaluation substrate and critical lineage/
     trace correctness needed to make later work measurable.
2. **Evidence Compiler Integrity**
   - Make note/PDF → L1-L4 compilation faithful, deterministic, incremental, and
     claim-level source-grounded.
   - Own note-native semantics, math preservation, entity/relation resolution,
     community hierarchy, invalidation, and reproducibility.
3. **Agentic Query Serving & Sensemaking**
   - Serve the trusted compiled knowledge to external and Obsidian agents through
     one bounded, progressive, freshness-aware context service.
   - Own adaptive hybrid retrieval, local/global/explore/source routes, context
     budgeting, evidence links, feedback lineage, and measured optimization.

Every program repeats focused research → approved implementation spec → TDD →
implementation → quality evaluation. Each program uses a separate branch/PR and
stops before the next begins.

## Planning Artifact Structure

`03_rag_knowledge_quality_stabilization.md` is the umbrella program plan. The
following are six independent component Master Plans, each produced through its
own Arena rather than being duplicate fragments of the umbrella plan:

| Plan | Dedicated Arena | Execution batch |
|---|---|---|
| A — Retrieval, provenance, and locator resolution | `rag_retrieval_provenance_arena/` | Batch 3 |
| B — Math extraction and claim-level distillation | `math_extraction_distillation_arena/` | Batch 2 |
| C — Graph resolution and community quality | `graph_quality_arena/` | Batch 2 |
| D — D1 diagnosis/baseline + D2 final specs/observatory | `current_system_failure_atlas_arena/` | Batch 1 |
| E — External research and comparative design matrix | `external_research_design_matrix_arena/` | Batch 1 |
| F — Unified agent context service, client links, and feedback | `agent_context_service_arena/` | Batch 3 |

The six plans are completed during planning, then executed only after the current
PR is merged. Batch 1 explicitly runs `D1 → E → D2`; other batches run `B → C`
and `A → F`. Each step is a separate merged release.

## Architecture Corrections Confirmed During 2026-06-11 Planning

- `qmd` is retired. Stabilization must improve the existing DB-native
  FTS5 + chunk-vector + RRF + configured-reranker engine; it must not restore a
  qmd dependency or use qmd parity as the new source of truth.
- Static `EXH-*` files and EXH reverse-parse backprop are retired. Provenance and
  correction behavior must follow the current DB-native L1-L4 model and durable
  `02_Wiki/` promotion contract.
- `state.sqlite` is authoritative; `.curator/Collections/` is a disposable
  projection and must not become load-bearing.

## Additional User Requirement Triaged 2026-06-11 (Preserved)

> `[[{문서명}#^{각주명}]]` is an Obsidian link form used heavily in the user's
> notes. The LLM and backend should actively use it when reading Markdown and
> building L1-L4/DB knowledge. Sidebar and popover answers should emit working
> links; current generated document links do not work.

This milestone therefore also owns block-reference-aware source anchors:

- parse and preserve Obsidian block references (`^block-id`) and heading anchors;
- store resolvable note/block provenance without replacing `source_span_ids`;
- include valid Obsidian wikilinks in answer evidence when a vault note anchor is
  known;
- make sidebar/popover link handling open note, heading, and block targets.

## Reference Plans (Must Read Before Implementation)
Agents must read the following past archive plans and understand the original design intent and RAG build history before starting stabilization.
- `Git History (v0.3.2 search_internalization)`: (Qwen3 + FTS5 RAG system build history)
- `Git History (2026-06-01_Generative_Backprop_Plan)`: (Generative Backprop structure)
- `Git History (2026-06-01_Math_RAG_Backprop_Plan)`: (Complex math/logic backprop processing)

## Multi-Agent Debate Topics (For Codex & Claude)
1. **`schema_guardian`**:
   - How should we supplement the SQL constraints to verify data integrity between `search_documents` and `knowledge_units`?
2. **`source_pair_analyst`**:
   - What is the cause of the bug where the trace back (Generative Backprop) to the original PDF Span (`source_spans`) is broken when generating L3 (Concepts) and L4 (Synthesis) layers? How can we bridge the gap between the archived Backprop plan specification and the current implementation?
3. **`cli_regression_runner`**:
   - How should we configure automated tests via the `testbed` script to catch pipeline collapses during complex RAG queries?

## Implementation Skeleton

### qmd/Search Engine Deep Analysis and Supplementation
- **Current Status**: Perform a deep analysis of the repository to understand how qmd works and supplement the shortcomings in the search engine.

### Resolve Math Formula Omission in PDFs and Distilled Knowledge (Atom, Concept)
- **Current Status**: Currently using pymupdf4llm as the default parser, but unlike preserving tables or text flow, block formulas in complex engineering/math papers are not perfectly reverse-transformed (OCR) into LaTeX code and are broken or omitted, meaning they are not fully reflected in L1. Furthermore, even if formulas are preserved in the Markdown original, the LLM evaporates the formulas without preserving them during the process of distilling knowledge into L2 (Atom) and L3 (Concept).
- **Fact-Check Required**: Before modifying the architecture, we must perform a specific fact-check and debugging on the L1 generated output to see whether pymupdf4llm fragments the formula areas into garbage text when converting to markdown, or if it skips them entirely.
- **Improvement Direction (Hybrid Pipeline)**: Depending on the fact-check results, consider introducing a hybrid extraction method where, instead of passing the entire page to a VLM, pymupdf4llm quickly grabs the text and skeleton, and only the areas identified as formulas are captured as images and passed to a backend VLM (Claude, Gemini, etc.) to be translated into LaTeX code. Additionally, the LLM knowledge extraction prompt itself must be strengthened to preserve formulas.

### Separate LLM Configuration for Knowledge Distillation and Query Expansion (HyDE) & Expose to UI/CLI
- **Current Status**: We need to clearly provide configuration options so that models can be selected independently based on the user's VRAM environment and purpose (heavy model for knowledge distillation vs. light and fast local model for query expansion).
- **Fact-Check Required**: Check how well the query_expander related structure is prepared inside the backend configuration (config.py), and verify if users can intuitively select these two models separately in the CLI (wiki config provider) and plugin dashboard UI. Supplement any deficiencies after fact-checking.
- **Reuse target (triaged 2026-06-11)**: The plugin's right-click "Convert to
  LaTeX" feature also needs to target this light/fast model instead of the main
  model (recommended Ollama default `qwen2.5:0.5b`). Build the light-model config
  plumbing here once and let the Convert-to-LaTeX setting in
  `.agents/drafts/minor_quick_wins.md` consume it.

> Scope correction: provider-management UI and Convert-to-LaTeX reuse are not
> quality-stabilization gates. Keep them in a separate provider-management /
> quick-win milestone. This program may define task-class model requirements, but
> must not absorb unrelated settings UI work.

### GraphRAG-level Entity Resolution, Noise Filtering, and Vault Quota Architecture Design
- **Current Status**: Due to the structure of the current internal DB (graph_entities, graph_relations), there is a risk that synonyms or similar concepts will be fragmented and duplicated, or noise edges will multiply infinitely. If the .curator DB and markdown files are left alone, the computer disk space could explode.
- **Requirement 1 (Noise Filtering)**: Design a pipeline architecture to merge identical entities and precisely optimize edge weights using embedding similarities and LLMs before/after inserting extracted knowledge into the DB.
- **Requirement 2 (Capacity Management/Context Compat)**: Introduce the concept of a maximum vault capacity limit (Quota) (Default: 200GB) to prevent infinite multiplication.
- **Requirement 3 (UI/UX Visibility)**: Introduce a Claude Code style circular progress bar (Circle Bar) UI so users can intuitively recognize capacity pressure.
  - Obsidian Agent: Always displayed at the top of the chat window.
  - CLI: Display a text/emoji-based progress bar in the wiki status output.
  - Also explicitly guide and set capacity policies during wiki init.

> Scope correction: entity/relation resolution belongs to Evidence Compiler
> Integrity because it determines what compiled knowledge exists. Vault quota and
> circular storage UI belong to a separate storage-governance milestone; disk
> limits do not prove RAG/DAG quality. Preserved scope:
> `.agents/drafts/vault_storage_governance.md`.

### Hierarchical Clustering Algorithm Design Plan for Global Sensemaking
- **Current Status**: Lacks global summary or community-level summary capabilities that encompass hundreds of papers.
- **Requirement**: Write a plan to implement an advanced clustering logic that automatically clusters fragmented L2 (Atom) knowledge into L3 (Concept/Community) units mathematically, benchmarking algorithms like MS GraphRAG's Leiden algorithm.

### Additional System Integration Logic
- `backend/src/curator/retrieval/*.py`: Tune reranking weights and stabilize hybrid search referring to past RAG build plans.
- `backend/src/curator/pipeline/*.py`: Strengthen prompts and validation for the L2->L3->L4 promotion logic. (Normalize Generative Backprop logic)
- `testbed`: Add new scenarios in `tests/scenarios/` to reproduce instability and broken Backprop phenomena.
