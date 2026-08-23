# 🧠 Incurator: Knowledge Compiler for Multi-Agent Workspaces

**English** | [한국어](README_KR.md)

**"Feed your PDFs and notes to a local AI compiler. Ask questions grounded in your own knowledge. Keep only what matters."**

Incurator is an intelligent knowledge compilation engine and Obsidian assistant designed for researchers, engineers, and deep thinkers. It transforms your raw documents (PDFs, Markdown notes, research papers) into a structured Directed Acyclic Graph (DAG), enabling you to explore, query, and synthesize insights without token waste or hallucinations.

> For the core philosophy and design rationale behind this system, see [Project Philosophy](philosophy/about.md).

---

## 🚀 The Experience: How It Works

```
  [Raw Files] (PDFs, Notes)
       │
       ▼ (wiki add / wiki build)
┌─────────────────────────────────────────────────────────┐
│ 🏛️ The Curator (.curator/)                              │
│   L1 Contexts  →  L2 Atoms  →  L3 Concepts  →  L4 Syn   │
│   (Compiled on local SLMs / cheap background workers)   │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼ (Dynamic Curation Lens via curate.yml)
┌─────────────────────────────────────────────────────────┐
│ 🎨 The Artist (Obsidian Sidebar & MCP Agent)            │
│   • Split-view PDF context & source badges              │
│   • Multi-source hybrid search & cited answers          │
│   • Interactive reasoning & hypothesis synthesis        │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼ (wiki query "save" / Promote)
  [02_Wiki/] (Permanent, Human-Reviewed Knowledge)
```

1. **Drop & Register (`wiki add`)**: Add PDFs, papers, or markdown notes. Incurator instantly builds an L1 structural index without requiring an LLM.
2. **Compile (`wiki build`)**: A lightweight background model (e.g., local Ollama SLM) extracts atomic facts (L2 Atoms) and clusters them into multi-source thematic topics (L3 Concepts).
3. **Explore & Chat (Obsidian Sidebar & MCP)**: Open notes and PDFs with an intelligent sidebar. Ask questions grounded in your compiled evidence, complete with direct page citations and provenance traces.
4. **Curate & Synthesize (`curate.yml`)**: Scope your project’s domain and knowledge requirements dynamically so agents only retrieve relevant, high-confidence evidence.
5. **Promote (`02_Wiki/`)**: Save verified insights and synthesized answers into your permanent vault wiki with a single click or command.

---

## 🏛️ Architecture: The Curator & The Artist

Incurator divides knowledge work into two distinct roles:

### ⚙️ The Curator (Manager of the Vault)
The background engine residing in `.curator/`. The Curator focuses on **knowledge compilation and structural organization**, not creative reasoning:
- **L1 Contexts**: Source structure, section/page locators, and provenance tracking.
- **L2 Atoms**: Irreducible, source-grounded factual units.
- **L3 Concepts**: Multi-source thematic structures and community clusters.
- **L4 Synthesis**: Shared, corpus-wide standing evidence nodes.
- **Authoritative State**: Stored in `state.sqlite`; generated Markdown files in `.curator/Collections/` serve as disposable inspection projections.

### 🎨 The Artist (Resident of the Workspace: Human + Agent)
The creative partner in the workspace (Obsidian Sidebar or external agents via MCP):
- **Dynamic Curation Lens**: Applies project requirements defined in `curate.yml` at query time over the live DAG without freezing stale subsets.
- **Sessionless Queries**: Asking questions never pollutes the DAG. Every query returns a cited answer or evidence pack backed by a full trace.
- **Explicit Promotion**: High-value findings become permanent vault knowledge only when explicitly approved and promoted to `02_Wiki/`.

---

## 🌟 Key Differentiators

### 1. Specification-Driven Dynamic Curation
Unlike traditional RAG systems that retrieve static chunks or freeze fixed subsets, Incurator applies workspace-level knowledge specifications (`curate.yml`) as a dynamic lens over the live graph. Queries retrieve precisely scoped evidence without domain contamination.

### 2. Prior Knowledge Correction & Auditability
When you or your agent spot an error in compiled knowledge, corrections are submitted as auditable proposals. Source ground truth is never silently overwritten, maintaining an immutable line of provenance between source documents, generated structures, and human-verified notes.

### 3. Token Optimization (AI FinOps)
Heavy data parsing and fact compilation (`Summary → Atoms → Concepts`) run on local SLMs (via Ollama) or lightweight models. Frontier reasoning models (Claude, OpenAI) are reserved exclusively for interactive dialogue and deep synthesis, cutting token costs by up to 90%.

### 4. Dual-Track Monorepo Architecture
Incurator unifies a Python backend daemon (`backend/`) and an Obsidian plugin (`plugin/`) in a single repository:
- **AI Space (`.curator/`)**: Machine-readable SQLite graph and disposable inspection projections.
- **Human Space (`02_Wiki/`)**: Clean, human-readable Markdown wiki notes.
- **Client Space (`Obsidian Sidebar`)**: Split-view PDF context, source state badges, and multi-model chat.

### 5. Dual Persona System
- **Curator Persona (Global)**: Configured during `wiki init`, defines the expert lens and domain verification standards for your entire vault.
- **Artist Persona (Workspace)**: Configured in `curate.yml`, tailors tone, goal, and domain focus for specific sub-projects.

### 6. Lossless External Reference Mode (Zotero Integration)
Directly reference external PDFs (e.g., Zotero libraries) without forced copying. The backend tracks content hashes and logical identities, automatically handling path changes and Apple Pencil annotation hash drift through human-in-the-loop verification.

### 7. Knowledge Concentration Principle
Knowledge compounds fastest when connected in a single, unified vault. Incurator recommends operating a single primary vault, creating separate vaults only when you need fundamentally different expert personas (e.g., STEM Research vs. Creative Writing).

---

## 🛠️ Getting Started

### 📋 Prerequisites
- **Python 3.10+**
- **Obsidian** (recommended for interactive UI)
- **Local / Cloud LLM**: Ollama for local models, or API keys for Cloud providers (Claude, OpenAI, Gemini).

### 🚀 Quick Start
1. **Install & Build Everything**:
   ```bash
   ./setup.sh
   ```
   *Installs Python dependencies, builds the Obsidian plugin, and sets up local tools.*

2. **Initialize Your Vault**:
   ```bash
   wiki init /path/to/your/obsidian-vault
   ```
   *Runs a quick interview to configure your vault's Curator Persona.*

3. **Register Sources**:
   ```bash
   wiki add /path/to/document.pdf
   ```
   *Creates instant L1 structural contexts without LLM cost.*

4. **Build Knowledge Layers**:
   ```bash
   wiki build
   ```
   *Extracts L2 Atoms and clusters L3 Concepts in the background.*

5. **Ask Questions**:
   ```bash
   wiki query "What are the core findings in the uploaded papers?"
   ```
   *Or open the Obsidian sidebar to interactively chat with your notes and PDFs.*

---

## 🔌 Integrations & Guides

- [User Guide](guides/USER_GUIDE.md) — Comprehensive CLI and workflow manual
- [Plugin Guide](guides/PLUGIN_GUIDE.md) — Obsidian plugin setup, features, and troubleshooting
- [MCP Integration Guide](guides/MCP_USER_GUIDE.md) — Connect Incurator to Cursor, Claude Desktop, and other MCP clients
- [Project Philosophy](philosophy/about.md) — In-depth architectural design decisions
- [Sync Ignore Guide](guides/SYNC_IGNORE_GUIDE.md) — Multi-device synchronization guide (Syncthing/iCloud)
