# Core RAG & Knowledge Distillation Stabilization Plan

## Context
We need to resolve the hallucination, edge loss, and prior knowledge mapping instabilities occurring in the current RAG search engine (Qwen3 Reranker + FTS5) and knowledge distillation pipeline. This is a core task that lays the foundation before developing the Knowledge Sync Bridge and PDF Annotation.

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

### GraphRAG-level Entity Resolution, Noise Filtering, and Vault Quota Architecture Design
- **Current Status**: Due to the structure of the current internal DB (graph_entities, graph_relations), there is a risk that synonyms or similar concepts will be fragmented and duplicated, or noise edges will multiply infinitely. If the .curator DB and markdown files are left alone, the computer disk space could explode.
- **Requirement 1 (Noise Filtering)**: Design a pipeline architecture to merge identical entities and precisely optimize edge weights using embedding similarities and LLMs before/after inserting extracted knowledge into the DB.
- **Requirement 2 (Capacity Management/Context Compat)**: Introduce the concept of a maximum vault capacity limit (Quota) (Default: 200GB) to prevent infinite multiplication.
- **Requirement 3 (UI/UX Visibility)**: Introduce a Claude Code style circular progress bar (Circle Bar) UI so users can intuitively recognize capacity pressure.
  - Obsidian Agent: Always displayed at the top of the chat window.
  - CLI: Display a text/emoji-based progress bar in the wiki status output.
  - Also explicitly guide and set capacity policies during wiki init.

### Hierarchical Clustering Algorithm Design Plan for Global Sensemaking
- **Current Status**: Lacks global summary or community-level summary capabilities that encompass hundreds of papers.
- **Requirement**: Write a plan to implement an advanced clustering logic that automatically clusters fragmented L2 (Atom) knowledge into L3 (Concept/Community) units mathematically, benchmarking algorithms like MS GraphRAG's Leiden algorithm.

### Additional System Integration Logic
- `backend/src/curator/retrieval/*.py`: Tune reranking weights and stabilize hybrid search referring to past RAG build plans.
- `backend/src/curator/pipeline/*.py`: Strengthen prompts and validation for the L2->L3->L4 promotion logic. (Normalize Generative Backprop logic)
- `testbed`: Add new scenarios in `tests/scenarios/` to reproduce instability and broken Backprop phenomena.