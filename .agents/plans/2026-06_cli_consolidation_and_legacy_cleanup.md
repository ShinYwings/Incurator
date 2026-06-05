# System-Wide Deep Analysis: Senior Engineering Committee Report

## Executive Summary

This document is the master index for a **rigorous, code-level deep analysis** of the entire Incurator system. It was produced by an 8-person panel of senior engineers who read every critical source file line by line, cross-referenced the codebase against industry SOTA (Microsoft GraphRAG, HippoRAG, LlamaIndex, Argilla, LangGraph, Logseq DB), and debated architectural flaws until consensus was reached.

**This is an analysis-only document. No code has been modified.**

---

## Panel Members

| Role | Name | Domain |
|---|---|---|
| Chief Architect | Alice | DAG structure, state transitions, system-wide coherence |
| Data Engineer | Bob | Data pipelines, SQLite schema, CDC patterns |
| Security / HITL Lead | Charlie | RBAC, agent guardrails, human-in-the-loop enforcement |
| Documentation Specialist | Diana | Code ↔ docs alignment, spec fragmentation |
| Backend Specialist | Frank | Python core logic, DB transactions, performance |
| Plugin Specialist | Evan | Obsidian API, TypeScript, client-server integration |
| UI/UX Designer | Grace | Cognitive load, annotation UX, diff view design |
| QA Engineer | Hannah | Testability, edge cases, CI/CD pipeline stability |

---

## Critical Finding #0: The System Already Has GraphRAG — Nobody Realized It

**Alice (Chief Architect)**:
"Before we even begin the phase-by-phase breakdown, I need to flag something that changes everything. I read `db.py` line by line and discovered that the v0.3.1 schema already contains `graph_entities`, `graph_relations`, `community_reports`, `memory_paths`, and `synthesis_nodes` tables (lines 250-405). This is a near-complete implementation of **Microsoft's GraphRAG architecture** (entity extraction → community detection → hierarchical summarization) combined with **HippoRAG's associative memory paths** (Personalized PageRank over a knowledge graph).

The system is not a simple RAG pipeline. It is a hybrid GraphRAG + HippoRAG engine. But the panel's analysis revealed that this powerful foundation is undermined by legacy code, architectural contradictions, and missing guardrails across every layer."

---

## Phase Index

Each phase document contains:
1. **Exact code file references** with line numbers
2. **SOTA benchmarks** from peer-reviewed papers and production systems
3. **Verbatim debate transcripts** from the 8-person panel
4. **Consensus action items** categorized by `[Backend]`, `[Plugin]`, `[UX/UI]`, `[QA]`, `[Docs]`, `[Architecture]`, `[Security]`

### Philosophical Alignment
- **[Phase 0: Philosophical Alignment](2026-06_deep_analysis/Phase_0_Philosophical_Alignment.md)** — `README.md`, `docs/philosophy/ABOUT.md`
  - The Curator vs Artist separation: Why forcing L1-L3 into filesystem Markdown violates the Dual-Track mandate.
  - Spec-Driven Exhibition (Dynamic Lens): Why `wiki curate` and static syncs were deprecated in favor of dynamic queries.
  - Prior Knowledge Correction: Enforcing strict backpropagation rules.

### Core Engine & Data Layer
- **[Phase A: Core Engine](2026-06_deep_analysis/Phase_A_Core_Engine.md)** — `sync.py`, `db.py`, `insight_lifecycle.py`
  - The Logseq Paradox: Why writing Markdown files as a core data dependency is an anti-pattern that Logseq already abandoned.
  - Exact code paths: `promote_insight()` at `insight_lifecycle.py:99-131`, `sync.py:140-158` incremental sync.
  - Missing concurrency control in `db.py:561-576` (`connect()` context manager lacks transaction isolation).

### Retrieval & Query
- **[Phase B: Retrieval & Curation](2026-06_deep_analysis/Phase_B_Retrieval_Curation.md)** — `orchestrator.py`, `evidence.py`
  - The LlamaIndex Violation: `_run_explore()` at `orchestrator.py:179-190` silently writes `insight_candidates` to the DB during a read query.
  - HippoRAG benchmark: Our `memory_paths` implementation vs. the original HippoRAG paper's Personalized PageRank.
  - Session context loss in `evidence.py` — every query is stateless.

### APIs & CLI
- **[Phase C: Interaction APIs & CLI](2026-06_deep_analysis/Phase_C_Interaction_APIs.md)** — `mcp_server.py`, `cli.py`, `plugin_api.py`
  - LangGraph RBAC gap: Agents can bypass HITL via unconstrained CLI execution.
  - The "6 Pillars" CLI consolidation proposal with exact command mappings.

### Ingest & External Integrations
- **[Phase D: Ingest & Integrations](2026-06_deep_analysis/Phase_D_Ingest_Integrations.md)** — `ingest_raw.py`, Zotero
  - Zotero community standard violation: Absolute paths (`com~apple~CloudDocs/Zotero/...`) vs. `zotero://` URI scheme.
  - CI/CD breakage on GitHub Actions due to iCloud path dependencies.

### Frontend & Plugin
- **[Phase E: Frontend & Obsidian Plugin](2026-06_deep_analysis/Phase_E_Frontend_Plugin.md)** — `plugin/main.ts`, `plugin/src/**/*.ts`
  - Argilla/LangSmith HITL benchmark: Why our current "approve" button is fake HITL.
  - Obsidian community best practice: Svelte `ItemView` mounting pattern for interactive diff views.

### Search Engine Architecture
- **[Phase H: Search Index Paradox](2026-06_deep_analysis/Phase_H_Search_Index_Paradox.md)** — Eliminating `qmd` filesystem dependency for SQLite FTS5.
- **[Phase K: Lint & Sync Paradox](2026-06_deep_analysis/Phase_K_Lint_Sync_Paradox.md)** — `lint.py`, `sync.py`
  - The Markdown Parsing Bottleneck: Why `lint` and `sync` are parsing 10,000 files via regex instead of using `state.sqlite`.

### LLM Reliability & Prompts
- **[Phase I: LLM Resiliency](2026-06_deep_analysis/Phase_I_LLM_Resiliency_Concurrency.md)** — Circuit breakers, budget exhaustion, jitter backoff.
- **[Phase J: LLM Prompt Vulnerabilities](2026-06_deep_analysis/Phase_J_LLM_Prompt_Vulnerabilities.md)** — `prompts.py`
  - The YAML Hallucination Trap: Why asking the LLM to write raw YAML frontmatter in `FRAGMENT_PAGE_TEMPLATE` is a massive security and stability risk.
  - `llm.py:166-176` already detects capacity errors (`_is_capacity_error`) but lacks a circuit breaker to actually stop retries.
  - Budget Guardrail design based on the `ingest_jobs` table's existing `input_tokens`/`output_tokens`/`estimated_cost_usd` tracking (db.py lines 488-505).

---

## Cross-Cutting Themes

### 1. The System is More Advanced Than Its Documentation Claims

The codebase implements a sophisticated hybrid GraphRAG + HippoRAG architecture with `graph_entities`, `graph_relations`, `community_reports`, `memory_paths`, and `synthesis_nodes`. However, the documentation (`WORKFLOW_GUIDE.md`, `MCP_USER_GUIDE.md`) still describes a simple 4-layer DAG (CTX → ATM → CON → EXH) and references deprecated commands like `wiki sync --backward`. This disconnect will cause catastrophic agent hallucinations.

### 2. The Filesystem is a Liability, Not an Asset

Multiple phases (A, H) converge on the same conclusion: the system's dependency on Markdown files as a data flow participant (not just a presentation layer) is the root cause of flaky tests, sync conflicts, and the search index paradox.

### 3. HITL is Declared But Not Enforced

The `insight_lifecycle.py` code correctly models `ActionPlan.requires_human_review = True`, but there is no enforcement mechanism that prevents an agent from bypassing this flag via direct CLI execution or MCP tool abuse (Phase C, Phase E).

### 4. The Prompts Are World-Class, The Plumbing is Not

`prompts.py` contains exceptionally well-engineered LLM prompts (SUMMARY_INSTRUCTIONS, ATOM_COORDINATOR, CONCEPT_CLUSTERING). The prompt engineering is production-grade. But the infrastructure around these prompts (retry logic, budget limits, concurrency control) is fragile.

### 5. MCP Tool Surface Area is Too Large for Reliable Agent UX

With nearly 40 granular MCP tools exposed, LLM agents face significant cognitive overload, leading to tool selection hallucinations, context bloat, and fragile polling loops. The architecture must evolve toward:
- **Macro-Tools**: Abstracting low-level steps (e.g., validate → plan → explore → promote) into single high-level, intent-based tools.
- **Dynamic Tool Exposing**: Dynamically filtering the available tools based on the agent's active workflow to preserve the context window and reasoning capacity.

---

## Verification Plan

### Automated Tests
- After implementing any changes, run `uv run pytest` to verify no regressions.
- **ResNet & Neural ODE Scenario**: Restore the domain testbed scenario using `curator_propose_correction` to verify L1 correction propagation through the HITL workflow.

### Manual Verification
- Execute `wiki --help` to verify CLI consolidation.
- Plugin build (`npm run build`) and Obsidian load test.
