# 🧠 Incurator: Knowledge Compiler & Research Assistant for Multi-Agent Workspaces

**English** | [한국어](README_KR.md)

**"Feed your PDFs and notes to a local AI compiler. Ask questions grounded in your own knowledge. Edit notes like Cursor, and connect your vault to external IDEs via MCP."**

Incurator is an intelligent knowledge compilation engine and Obsidian assistant designed for researchers, engineers, and deep thinkers. It bridges the gap between raw documents (PDFs, Markdown notes, research papers) and high-reasoning AI agents, turning your Obsidian vault into a structured, continuously evolving Directed Acyclic Graph (DAG) without token waste, truth decay, or hallucinations.

> For the architectural design rationale and how Incurator solves the failure modes of traditional LLM Wikis, see [Project Philosophy](philosophy/about.md).

---

## 🚀 The Experience: How It Works

```
  [Raw Sources] (PDFs, Notes, Zotero)
       │
       ▼ (wiki add / wiki build)
┌──────────────────────────────────────────────────────────────┐
│ 🏛️ The Curator (.curator/ & state.sqlite)                    │
│   L1 Contexts  →  L2 Atoms  →  L3 Concepts  →  L4 Synthesis  │
│   (Zero-cost compilation on local SLMs / background workers) │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼ (Dynamic Curation Lens via curate.yml)
┌──────────────────────────────────────────────────────────────┐
│ 🎨 The Artist (Obsidian Sidebar & Universal MCP Server)      │
│   • Split-view PDF context & source badges                   │
│   • In-line text-selection popovers ("Ask Gemini" style)     │
│   • Cursor-style Interactive Diff Review on Markdown notes   │
│   • Multi-source hybrid search & cited answers with traces   │
│   • Real-time context provider for external coding IDEs      │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼ (wiki query "save" / Promote)
  [02_Wiki/] (Permanent, Human-Reviewed Knowledge Base)
```

1. **Drop & Register (`wiki add`)**: Add PDFs, papers, or markdown notes. Incurator instantly builds an L1 structural index without making an LLM call.
2. **Compile (`wiki build`)**: A lightweight background model (e.g., local Ollama SLM) extracts atomic facts (L2 Atoms) and clusters them into multi-source thematic topics (L3 Concepts).
3. **Active Reading & Popover (Obsidian Studio)**: Open PDFs in split-view, highlight text to trigger instant in-line Q&A popovers, or chat in the sidebar with direct citations and provenance traces.
4. **Interactive Note Editing (Diff Viewer)**: Apply AI suggestions to your notes with a Cursor-style in-editor Diff Viewer—review additions/deletions line by line and accept or reject individual chunks.
5. **Project-Scoped Curation (`curate.yml`)**: Scope your project's domain and target goals dynamically so agents only retrieve relevant, high-confidence evidence without cross-domain pollution.
6. **Universal MCP Access**: Ask Cursor or Claude Desktop to reference your entire Obsidian knowledge base while writing code or reports.

---

## 🌟 What Makes Incurator Unique: 6 Core Superpowers

### 1. Obsidian Studio: Active Reading & Cursor-Style Diff Editing
- **In-Line Popover ("Ask Gemini" style)**: Select any text or mathematical formula in a note or PDF, click the floating trigger, and ask targeted questions grounded in your vault's compiled knowledge. Full LaTeX formula rendering supported.
- **Interactive Diff Viewer**: AI edits are never dumped blindly into chat or silently overwritten. Incurator opens a CodeMirror 6 inline Diff Viewer directly inside your note, letting you review changes (`+` / `-`) and selectively accept or reject diff chunks.
- **Split-View PDF Reader**: Drag and drop PDFs into split-views, view real-time ingestion status badges, and click citations to jump straight to exact pages.

### 2. Hierarchical DAG vs. Flat Wiki Sprawl
Existing LLM Wikis dump hundreds of flat Markdown files, overflowing the AI's context window and causing truth decay. Incurator compiles knowledge into a **4-layer Directed Acyclic Graph (DAG)**:
- **L1 Contexts**: Source structure and page locators (0 LLM tokens).
- **L2 Atoms**: Irreducible, source-grounded factual claims.
- **L3 Concepts**: Multi-source thematic clusters and community reports.
- **L4 Synthesis**: Corpus-wide standing evidence nodes.
- **Deep Contradiction Detection**: Run `wiki lint --deep` to automatically detect factual contradictions across different papers in your vault.

### 3. Lossless Zotero Integration & Apple Pencil Hash Drift Defense
- **Reference Mode**: Directly integrate external Zotero libraries and PDFs without forced duplication into your vault.
- **Hash Drift Defense**: When you annotate a PDF on iPad via Apple Pencil, the binary hash changes. Incurator tracks logical source identities and textual fingerprints, seamlessly healing links and preserving existing Atoms and Concepts without re-indexing from scratch.

### 4. Universal MCP Server: An External Brain for Your Coding IDE
Incurator includes a full-featured Model Context Protocol (MCP) server with **48+ tools**:
- Connect your vault directly to **Cursor, VSCode, Antigravity IDE, or Claude Desktop**.
- When writing code, your agent can call `curator_fetch_context` or `curator_traverse_evidence` to pull prior research papers, architectural RFCs, and API documentation directly from your Obsidian vault.

### 5. AI FinOps: Zero-Cost Compilation + Reasoning Freedom
- **Local Background Worker**: Repetitive preprocessing and knowledge structuring (`L1 → L2 → L3`) run locally on Ollama (SLMs) or lightweight models for $0.
- **Frontier Reasoning**: Commercial reasoning models (Claude, OpenAI, Gemini) are used strictly on-demand for interactive exploration, reducing overall token costs by over 90%.

### 6. Seamless Multi-Device Sync (Syncthing & iCloud)
- Engineered with SQLite WAL checkpointing, deterministic relative paths, and automated `.stignore` rules to ensure conflict-free synchronization across macOS, Linux, and iPad.

---

## 🏛️ System Architecture: The Curator & The Artist

Incurator enforces a strict separation of concerns:

### ⚙️ The Curator (Manager of the Vault)
The background engine residing in `.curator/`. The Curator focuses on **structural compilation, indexing, and health checks**, not creative reasoning:
- Authoritative state stored in `state.sqlite`.
- Generated Markdown files in `.curator/Collections/` serve as disposable inspection projections that can be safely deleted and recompiled at any time.

### 🎨 The Artist (Resident of the Workspace: Human + Agent)
The creative partner operating in the workspace (Obsidian Sidebar or MCP clients):
- **Dynamic Curation Lens**: Applies project requirements defined in `curate.yml` at query time over the live DAG without freezing stale subsets.
- **Sessionless Queries**: Asking questions never pollutes the DAG. Every query returns a cited answer backed by a full provenance trace.
- **Explicit Promotion**: High-value findings become permanent vault knowledge only when explicitly approved and promoted to `02_Wiki/`.

---

## 🛠️ Getting Started

### 📋 Prerequisites
- **Python 3.10+**
- **Obsidian** (for the full interactive UI experience)
- **Local / Cloud LLM**: Ollama for local models, or API keys for Cloud providers (Claude, OpenAI, Gemini).

### 🚀 Quick Start
1. **Install & Build Monorepo**:
   ```bash
   ./setup.sh
   ```
   *Installs Python backend dependencies, builds the Obsidian plugin, and configures local tools.*

2. **Initialize Your Vault**:
   ```bash
   wiki init /path/to/your/obsidian-vault
   ```
   *Configures your vault topology and runs a short interview to establish your Curator Persona.*

3. **Register Sources**:
   ```bash
   wiki add /path/to/document.pdf
   ```
   *Creates instant L1 structural contexts without LLM cost.*

4. **Compile Knowledge Layers**:
   ```bash
   wiki build
   ```
   *Extracts L2 Atoms and clusters L3 Concepts in the background.*

5. **Ask Questions**:
   ```bash
   wiki query "What are the core findings across the uploaded papers?"
   ```
   *Or open Obsidian to explore your notes and PDFs with the sidebar and in-line popovers.*

---

## 🔌 Integrations & Guides

- [User Guide](guides/USER_GUIDE.md) — Comprehensive CLI and workflow manual
- [Plugin Guide](guides/PLUGIN_GUIDE.md) — Obsidian plugin setup, features, and shortcuts
- [MCP Integration Guide](guides/MCP_USER_GUIDE.md) — Connect Incurator to Cursor, Claude Desktop, and IDE agents
- [Project Philosophy](philosophy/about.md) — Architectural design rationale and LLM Wiki comparison
- [Sync Ignore Guide](guides/SYNC_IGNORE_GUIDE.md) — Multi-device synchronization guide (Syncthing/iCloud)
