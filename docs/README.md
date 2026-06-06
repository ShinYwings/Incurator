# 🧠 Incurator: Knowledge Compiler for Multi-Agent Workspaces

**English** | [한국어](README_KR.md)

**"Increment your knowledge, don't just search it."**

Incurator is a cost-effective, multi-agent knowledge system that transforms fragmented data into a structured **Directed Acyclic Graph (DAG)**. It serves as a bridge between raw information and high-reasoning agents, enabling you to organically incubate and increment your knowledge while executing complex projects without token waste or hallucinations.

> For the problems this system addresses and the reasoning behind its design, see [Project Philosophy (ABOUT_KR.md)](docs/philosophy/ABOUT.md).

---

## 🏛️ The Core Metaphor: Curator & Artist

Most AI knowledge bases fail because they treat LLMs as simple search engines. We separate the process into two distinct roles:

### ⚙️ The Curator (Manager of the Vault)
The Curator is the background engine that resides in the **Vault** to handle knowledge refinement. It focuses on **summarizing and refining knowledge** rather than high-level "reasoning." It has been verified that the Curator performs reliably using standard universal models from cloud providers, without requiring high-cost reasoning-only models. It builds a 4-layer evidence chain and stages a tailored Exhibition based on the Artist's preferences in `curate.yml`. It supports both Local models (via Ollama) and Cloud models (Antigravity, Claude, OpenAI), allowing you to choose the best engine based on your hardware and requirements.
1.  **L1 Contexts**: Metadata-rich summaries (Managed solely as high-speed DB records).
2.  **L2 Atoms**: Irreducible, atomic facts (Managed solely as high-speed DB records).
3.  **L3 Concepts**: Multi-source thematic structures (Managed solely as high-speed DB records).
4.  **L4 Exhibitions**: **Special Exhibitions** tailored to the Artist's specific project context. These are the **only** layer generated as Markdown files for human and agent interaction.

### 🎨 The Artist (Owner of the Workspace)
The Artist resides in the **Workspace**, their personal studio. They express their taste and project requirements to the Curator via `curate.yml`, then visit the **Exhibition** the Curator has prepared. From these curated exhibits the Artist draws new insights (**Synthesis**). When they spot errors or uncover new ideas, they feed that back to the Curator — who corrects the underlying knowledge accordingly. The more this dialogue repeats, the more precise the exhibitions become.

---

## 🌟 Why This System?

Incurators broadly aim for a closed loop — ingest, process, retrieve, feed back. Incurator is an Incurator too, but differentiates itself from others in two key ways.

### 1. Specification-Driven Exhibition

Generic Incurators retrieve knowledge as-is. Incurator's Curator does more. When a human defines their project goals and knowledge requirements in `curate.yml`, the Curator selects and synthesizes only the relevant material from the knowledge graph, staging a **tailored Exhibition** for that specific context. Agents and humans consult this curated output directly — no raw data spelunking required — allowing focus to stay on generating insight. And when a single vault holds knowledge across many different domains, spec-driven selection ensures that only relevant concepts surface, preventing contamination between unrelated fields.

### 2. Prior Knowledge Correction

When humans or agents spot an error in prior knowledge — or derive a new insight from an Exhibition — the feedback doesn't just get appended as a new note. The correction signal propagates backward through the knowledge graph, updating the affected Atoms and Concepts and restoring logical coherence across the entire graph. This mirrors deep-learning backpropagation: **the system grows more precise with use, and knowledge evolves rather than just accumulates.**

### 3. Token Optimization (FinOps for AI)
Offload **compilation** (summarizing and atomizing knowledge) to non-reasoning models and reserve **creative synthesis** (requiring complex calculation or sophisticated reasoning) for reasoning models. This strategic role separation minimizes costs while maximizing insight.

### 4. Monorepo and Dual-Track Structure for AI and Humans
The Incurator repository provides the Python backend daemon (`backend/`) and Obsidian plugin client (`plugin/`) in a **single repository (monorepo)**. Knowledge is most effective when managed in different forms for machines and humans:
- **AI Space (`.curator/`)**: The **Archive/Storage**. A machine-friendly backend designed for agents to instantly search and leverage knowledge. It operates as a high-speed database (`state.sqlite`) where all L1-L3 knowledge is stored as records without polluting the vault with intermediary markdown files.
- **Human Space (`02_Wiki/`)**: The **Permanent Collection**. A beautiful knowledge library designed for users to read, manage, and own long-term. Only the final synthesized L4 Exhibitions are output as Markdown for direct interaction.
- **Client Space (`incurator-obsidian-agent`)**: The Obsidian client handles open-PDF context, split-view chips, chat UI, provider selection, and import/rebind approval. Durable source registry and RAG provenance belong to the backend.

### 5. Lossless External Resource Integration (Reference Mode & Hash Drift Defense)
The system is designed to support **Reference Mode** for external reference PDFs such as Zotero files, avoiding forced duplication into the vault. If a user wants a vault-managed copy, the backend imports it into an approved `04_Resources/` destination. If the user wants the original location preserved, the backend tracks content hash and logical source identity. Even if the file hash drifts due to iPad Apple Pencil annotations or the physical path changes, the link can be healed through a human-in-the-loop confirmation process.

### 6. Knowledge Concentration & Growth
Knowledge only truly **Increments** when it is gathered in a **single, cohesive space** rather than being fragmented across decentralized silos. Incurator ensures that all insights are funneled into a single source of truth, providing an environment where information is organically connected and synthesized.

As such, splitting your knowledge into multiple vaults solely for administrative organization is not recommended. However, if you require fundamentally different **Curator Personas** (e.g., a STEM specialist vs. a Cooking specialist) to maintain your knowledge, operating separate vaults allows each Curator to refine information through their own expert lens.

---

## 🛠️ Getting Started

### 📋 Prerequisites
- **Core Environment**: Python 3.10+, Terminal, Note Editor (Obsidian recommended)
- **Backend Accounts**: An API Key or subscription account is required for cloud models (Antigravity, Claude, etc.).
- **Automation Note**: Installing Ollama (local models) and Node.js (search engine), along with building the monorepo backend package and plugin, is automatically handled all at once by running `./setup.sh` in the root directory.
- See the [User Guide](docs/guides/USER_GUIDE.md) for more details.

### 🚀 Quick Start
1.  **Install**: `./setup.sh` (Automatically installs the backend package, builds the plugin, and installs Ollama, Node.js, etc.)
2.  **Initialize**: `wiki init <path/to/your/obsidian-vault>`
    > **Single Vault Principle**: Every folder initialized with `wiki init` has its own resident **Curator**. Since Incurator runs one Curator at a time, we strongly recommend maintaining **a single main vault** to maximize knowledge connectivity and growth.
    >
    > **Exception (Persona Segmentation)**: If you want to maintain knowledge through completely different "expert perspectives" (e.g., a STEM vault vs. a Cooking vault), create separate vaults. Each vault's Curator will refine knowledge according to their unique worldview.
3.  **Set up Persona**: During `wiki init`, a short interview configures your knowledge domain. Run `wiki persona update` anytime to refine it.
4.  **Register Knowledge (Refine)**: `wiki add <file>` (Auto-compiles raw sources into L1-L3 database records)
5.  **Use Knowledge (Query)**: `wiki query "question"` or MCP search (Includes auto-synthesis of L4)

> [!NOTE]
> **Developer Only**: The `wiki testbed` command is a tool for scenario validation and system development. Do not use it for standard knowledge management tasks.
 
Check the [User Guide](docs/guides/USER_GUIDE.md) for more details.

---

## 🤝 Contributing

If you encounter any issues or difficulties while using Incurator, please let us know. We especially welcome direct contributions—fixing a problem yourself helps ensure others don't face the same hurdle.

Check out our [Contribution Guide](docs/guides/CONTRIBUTION_GUIDE.md) to get started with bug fixes or feature improvements!

---

## 🔗 Connections
- [User Guide](docs/guides/USER_GUIDE.md)
- [Contribution Guide](docs/guides/CONTRIBUTION_GUIDE.md)
- [MCP Integration Guide](docs/guides/MCP_USER_GUIDE.md)
- [Sync Ignore Guide](docs/guides/SYNC_IGNORE_GUIDE.md)
- [Project Philosophy](docs/philosophy/ABOUT.md)

