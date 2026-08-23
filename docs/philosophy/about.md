# 💡 Why Incurator Exists

## The Evolution: From Naive RAG to LLM Wikis

When working with research papers, PDFs, and personal notes, traditional search and standard RAG (Retrieval-Augmented Generation) quickly fall short. Naive RAG breaks documents into arbitrary text chunks and searches them at query time, lacking a cohesive understanding of higher-level concepts across multiple documents.

To solve this, the **"LLM Wiki"** pattern emerged—compiling information into a structured, persistent collection of Markdown notes maintained by an AI agent rather than re-indexing raw chunks on every query.

However, existing open-source LLM Wiki implementations suffer from three critical architectural failure modes:

---

## The Three Traps of Existing LLM Wikis

### 1. Truth Decay & Hallucination Accumulation (The Silent Overwrite Trap)
In most LLM Wiki systems, the AI directly edits and updates markdown files in place. If the model makes a small hallucination or misinterprets a nuance, that mistake becomes permanent wiki text. In subsequent runs, the AI treats its own past hallucination as ground truth. Over time, the link to the original source is obscured, leading to systematic truth decay.

### 2. Context Window Overflow & Flat Sprawl (The Scalability Trap)
As a wiki grows beyond 150–200 flat pages, an agent can no longer fit the entire wiki structure in its context window. It begins creating duplicate pages, missing relevant cross-links, and hallucinating relationships. Flat wikilinks (`[[Topic]]`) cannot distinguish whether a paper *supports*, *contradicts*, or *refines* an existing theory.

### 3. Ingestion Cost Explosion (The FinOps Trap)
Running raw document parsing, fact extraction, and cross-linking entirely through commercial frontier models burns massive token budgets on basic preprocessing. Feeding whole PDFs into heavy reasoning models just to summarize them is unsustainable.

---

## The Incurator Solution: Architecture & Principles

Incurator is built from the ground up to solve these failure modes through strict architectural separation:

```
  [Raw Sources] (PDFs, Notes, Zotero) ── (Immutable Ground Truth)
       │
       ▼ (wiki add: Instant L1 / wiki build: Local SLM Compilation)
┌──────────────────────────────────────────────────────────────┐
│ 🏛️ The Curator (.curator/ & state.sqlite)                    │
│   L1 Contexts  →  L2 Atoms  →  L3 Concepts  →  L4 Synthesis  │
│   (Disposable, Rebuildable, Machine-Readable Knowledge DAG)   │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼ (Dynamic Curation Lens via curate.yml)
┌──────────────────────────────────────────────────────────────┐
│ 🎨 The Artist (Obsidian Sidebar & Universal MCP Server)      │
│   • In-line Selection Popovers & PDF Split-View Reading      │
│   • Interactive Diff Review on Markdown Notes (Cursor-style) │
│   • Deep Contradiction Detection & Multi-source Synthesis    │
│   • MCP Brain for External IDEs (Cursor / VSCode)            │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼ (Human Review & Explicit Promotion)
  [02_Wiki/] (Permanent, Verified Human Knowledge Base)
```

### 1. Two-Track Space: AI Storage vs. Durable Human Wiki
- **AI Space (`.curator/`)**: The machine-readable SQLite knowledge graph and disposable inspection projections. It can be wiped and completely recompiled from raw sources at any time.
- **Human Space (`02_Wiki/`)**: The permanent collection. AI never silently overwrites human notes. Only findings explicitly reviewed and promoted by a human become durable wiki artifacts. Source truth is always protected.

### 2. 4-Layer Hierarchical DAG (No Flat Sprawl)
Instead of hundreds of unstructured flat pages, knowledge is compiled into discrete, typed layers:
- **L1 Contexts**: Source structure, page/section locators, and provenance.
- **L2 Atoms**: Irreducible, source-grounded factual units.
- **L3 Concepts**: Multi-source thematic clusters and community reports.
- **L4 Synthesis**: Corpus-wide standing evidence nodes.

### 3. AI FinOps: Separation of Compilation and Reasoning
- **Compilation**: Structural parsing and fact atomization (`L1 → L2 → L3`) run automatically on local SLMs (e.g. Ollama) or fast background workers at zero or negligible cost.
- **Reasoning**: Interactive exploration, deep synthesis, and hypothesis debate are handled on-demand by high-reasoning frontier models paired with the human.

### 4. Active Reading Studio & Universal MCP Bridge
Knowledge must not be locked in a terminal CLI. Incurator provides:
- **Obsidian Studio**: Split-view PDF reading, instant in-line selection popovers, and in-editor interactive Diff Review for markdown notes.
- **Universal MCP Server**: Exposes the live knowledge graph to external coding agents (Cursor, VSCode, Claude Desktop), allowing your research vault to serve as the active context brain for coding and writing projects.

Knowledge is no longer a static archive—it becomes a living, self-correcting, and continuously incrementing ecosystem.
