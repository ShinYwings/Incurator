# 🧠 Incurator: Knowledge Compiler & Research Assistant for Multi-Agent Workspaces

**English** | [한국어](README_KR.md)

**"Feed your PDFs and notes to a local AI compiler. Ask questions grounded in your own knowledge. Edit notes like Cursor, and connect your vault to external IDEs via MCP."**

Incurator turns the PDFs and notes already in your Obsidian vault into a
knowledge graph your AI can actually use.

It compiles them once — locally, on small models, for close to nothing — and then
answers questions from that graph, citing the exact passage behind every claim.
Anything it cannot trace back to your own material, it does not say.

> For the architectural design rationale and how Incurator solves the failure modes of traditional LLM Wikis, see [Project Philosophy](philosophy/about.md).

---

## 🚀 The Experience: How It Works

```
  [Vault Sources] (03_Notes/, 04_Resources/, Zotero PDFs)
       │
       ▼ (wiki add / wiki build)
┌──────────────────────────────────────────────────────────────┐
│ 🏛️ The Curator (.curator/ & state.sqlite)                    │
│   L1 Contexts  →  L2 Atoms  →  L3 Concepts  →  L4 Synthesis  │
│   (Runs on local SLMs or background workers — your choice)   │
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
            ┌──────────────────┴──────────────────┐
            ▼ (Diff Review / Human Edit)          ▼ (wiki query "save" / Promote)
    [03_Notes/] (Updated Notes)            [02_Wiki/] (Permanent Wiki)
```

1. **Add** (`wiki add`) — drop PDFs or notes into `03_Notes/` / `04_Resources/`.
   A structural index is built immediately, with no LLM call.
2. **Compile** (`wiki build`) — a small local model extracts atomic facts and
   clusters them into cross-source themes. This is the slow, cheap part.
3. **Read and ask** — open a PDF in split view, select any text or formula for an
   in-line answer, or chat in the sidebar. Every answer carries its citations.
4. **Edit with review** — AI suggestions arrive as a diff inside your note. You
   accept or reject each chunk; nothing is overwritten silently.
5. **Scope it** (`curate.yml`) — tell a project what it cares about, so retrieval
   stays on-topic instead of dredging the whole vault.
6. **Use it elsewhere** — point Cursor or Claude Desktop at the vault over MCP.

---

## 🌟 How This Differs From Other LLM Wikis

Most LLM wikis read your documents and write a pile of Markdown about them. That
pile then becomes the problem: it is too large to fit in a context window, it
drifts from the sources it came from, and nothing tells you which parts you can
trust.

Incurator compiles instead of summarising, and refuses to state anything it
cannot trace back to your material.

| | Typical LLM wiki | Incurator |
|---|---|---|
| **What you get** | Hundreds of flat Markdown files | A 4-layer graph you *query*, not read |
| **Grounding** | The model summarises; sources drift over time | A finding that cannot cite its exact source spans **is not emitted at all** |
| **Your notes** | The AI rewrites them | Read-only to the machine. AI output lands in a separate space you promote from |
| **Scoping** | One global index for every question | `curate.yml` is a lens applied *at query time* — never a frozen, stale copy |
| **Cost** | A frontier model for everything | Small local models do the compiling; frontier models only for interactive reasoning |
| **Trust** | "Here is the answer" | Every answer carries its route, evidence and prompt traces (`wiki inspect answer`) |

The four layers exist so retrieval can be narrow: **L1** source structure (no LLM
tokens), **L2** irreducible factual claims, **L3** cross-source themes, **L4**
corpus-wide synthesis. A question touches the layer it needs instead of the whole
vault.

---

## 🧰 What You Actually Get

- **Obsidian studio** — split-view PDF reading with ingestion badges, in-line
  popovers on any selection or formula, and a CodeMirror diff viewer that lets you
  accept or reject AI edits chunk by chunk instead of having them overwritten.
- **Zotero without duplication** — reference external libraries in place. Annotate
  a PDF on iPad and the binary hash changes; Incurator tracks logical identity and
  text fingerprints so existing Atoms and Concepts survive.
- **An MCP server with 48 tools** — point Cursor, VS Code, Antigravity or Claude
  Desktop at your vault so a coding agent can pull your own papers and RFCs.
- **Contradiction detection** — `wiki lint --deep` finds claims from different
  papers that disagree.
- **Multi-device sync** — SQLite WAL checkpointing, relative paths and generated
  `.stignore` rules for conflict-free Syncthing/iCloud use across macOS, Linux and
  iPad.

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
