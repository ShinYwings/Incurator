# 🧠 InCurator: Knowledge Compiler for Multi-Agent Workspaces

**English** | [한국어](README.md)

**"Increment your knowledge, don't just search it."**

InCurator is a cost-effective, multi-agent knowledge system that transforms fragmented data into a structured **Directed Acyclic Graph (DAG)**. It serves as a bridge between raw information and high-reasoning agents, enabling you to organically incubate and increment your knowledge while executing complex projects without token waste or hallucinations.

> For the problems this system addresses and the reasoning behind its design, see [Project Philosophy (about.md)](docs/philosophy/about_EN.md).

---

## 🏛️ The Core Metaphor: Curator & Artist

Most AI knowledge bases fail because they treat LLMs as simple search engines. We separate the process into two distinct roles:

### ⚙️ The Curator (Knowledge Refinement Engine)
The Curator is the background engine that handles knowledge refinement. It focuses on **summarizing and refining knowledge** rather than high-level "reasoning." It has been verified that the Curator performs reliably using standard universal models from cloud providers, without requiring high-cost reasoning-only models. It builds a 4-layer evidence chain and stages a tailored Exhibition based on the Artist's preferences in `curate.yml`. It supports both Local models (via Ollama) and Cloud models (Gemini, Claude, OpenAI), allowing you to choose the best engine based on your hardware and requirements.
1.  **L1 Contexts**: Metadata-rich summaries.
2.  **L2 Atoms**: Irreducible, atomic facts.
3.  **L3 Concepts**: Multi-source thematic structures.
4.  **L4 Exhibitions**: Tailored exhibits staged to the Artist's specification.

### 🎨 The Artist (Reasoning Agent + Human)
The Artist lives in your **Workspace**. They express their taste and project requirements to the Curator via `curate.yml`, then visit the **Exhibition** the Curator has prepared. From these curated exhibits the Artist draws new insights (**Synthesis**). When they spot errors or uncover new ideas, they feed that back to the Curator — who corrects the underlying knowledge accordingly. The more this dialogue repeats, the more precise the exhibitions become.

---

## 🌟 Why This System?

LLM Wikis broadly aim for a closed loop — ingest, process, retrieve, feed back. InCurator is an LLM Wiki too, but differentiates itself from others in two key ways.

### 1. Specification-Driven Exhibition

Generic LLM wikis retrieve knowledge as-is. InCurator's Curator does more. When a human defines their project goals and knowledge requirements in `curate.yml`, the Curator selects and synthesizes only the relevant material from the knowledge graph, staging a **tailored Exhibition** for that specific context. Agents and humans consult this curated output directly — no raw data spelunking required — allowing focus to stay on generating insight. And when a single vault holds knowledge across many different domains, spec-driven selection ensures that only relevant concepts surface, preventing contamination between unrelated fields.

### 2. Prior Knowledge Correction

When humans or agents spot an error in prior knowledge — or derive a new insight from an Exhibition — the feedback doesn't just get appended as a new note. The correction signal propagates backward through the knowledge graph, updating the affected Atoms and Concepts and restoring logical coherence across the entire graph. This mirrors deep-learning backpropagation: **the system grows more precise with use, and knowledge evolves rather than just accumulates.**

### 2. Token Optimization (FinOps for AI)
Offload **compilation** (summarizing and atomizing knowledge) to non-reasoning models and reserve **creative synthesis** (requiring complex calculation or sophisticated reasoning) for reasoning models. This strategic role separation minimizes costs while maximizing insight.

### 3. Dual-Track Structure for AI and Humans
Knowledge is most effective when managed in different forms for machines and humans. InCurator achieves this by maintaining a dual-track directory structure.
- **AI Space (`.curator/`)**: A machine-friendly backend designed for agents to instantly search and leverage knowledge.
- **Human Space (`02_Wiki/`)**: A beautiful knowledge library designed for users to read, manage, and own long-term.

### 4. Knowledge Concentration & Growth
Knowledge only truly **Increments** when it is gathered in a **single, cohesive space** rather than being fragmented across decentralized silos. InCurator ensures that all insights are funneled into a single source of truth, allowing for higher-level synthesis and the organic growth of your intellectual capital.

---

## 🛠️ Getting Started

### 📋 Prerequisites
- **Core Environment**: Python 3.10+, Terminal, Note Editor (Obsidian recommended)
- **Backend Accounts**: An API Key or subscription account is required for cloud models (Gemini, Claude, etc.).
- **Automation Note**: You don't need to install Ollama (local models) or Node.js (search engine) manually; `./install.sh` handles these automatically.
- See the [User Guide](docs/guides/USER_GUIDE_EN.md) for more details.

### 🚀 Quick Start
1.  **Install**: `./install.sh` (Automatically installs Ollama, Node.js, and the QMD search engine.)
2.  **Initialize**: `wiki init <path/to/your/obsidian-vault>`
    > **Single Vault Principle**: Do not run `wiki init` in multiple scattered directories. InCurator achieves its most powerful **Increment** effect when all fragmented knowledge is gathered in one place. We strongly recommend designating **a single main vault** where all your personal knowledge is concentrated and running the system there.
3.  **Set up Persona**: During `wiki init`, a short interview configures your knowledge domain. Run `wiki persona update` anytime to refine it.
4.  **Register Knowledge (Refine)**: `wiki add <file>` (Auto-generates L1-L3 layers)
5.  **Use Knowledge (Query)**: `wiki query "question"` or MCP search (Includes auto-synthesis of L4)

> [!NOTE]
> **Developer Only**: The `wiki testbed` command is a tool for scenario validation and system development. Do not use it for standard knowledge management tasks.

Check the [User Guide](docs/guides/USER_GUIDE_EN.md) for more details.

---

## 🤝 Contributing

If you encounter any issues or difficulties while using InCurator, please let us know. We especially welcome direct contributions—fixing a problem yourself helps ensure others don't face the same hurdle.

Check out our [Contribution Guide](docs/guides/CONTRIBUTION_GUIDE_EN.md) to get started with bug fixes or feature improvements!

---

## 🔗 Connections
- [User Guide](docs/guides/USER_GUIDE_EN.md)
- [Contribution Guide](docs/guides/CONTRIBUTION_GUIDE_EN.md)
- [MCP Integration Guide](docs/guides/MCP_USER_GUIDE_EN.md)
- [Sync Ignore Guide](docs/guides/SYNC_IGNORE_GUIDE_EN.md)
- [Project Philosophy](docs/philosophy/about_EN.md)
