# 🧠 InCurator: Knowledge Compiler for Multi-Agent Workspaces

**English** | [한국어](README.md)

**"Increment your knowledge, don't just search it."**

InCurator is a cost-effective, multi-agent knowledge system that transforms fragmented data into a structured **Directed Acyclic Graph (DAG)**. It serves as a bridge between raw information and high-reasoning agents, enabling you to organically incubate and increment your knowledge while executing complex projects without token waste or hallucinations.

---

## 🏛️ The Core Metaphor: Curator & Artist

Most AI knowledge bases fail because they treat LLMs as simple search engines. We separate the process into two distinct roles:

### ⚙️ The Curator (Local SLM / Knowledge Compiler)
The Curator is your background engine (Local SLM like Ollama). It doesn't "think" deep thoughts; it **compiles**. It takes raw data and builds a 4-layer evidence chain:
1.  **L1 Contexts**: Metadata-rich summaries.
2.  **L2 Atoms**: Irreducible, atomic facts.
3.  **L3 Concepts**: Multi-source thematic structures.
4.  **L4 Exhibitions**: Task-ready "exhibits" staged for other agents.

### 🎨 The Artist (Reasoning Agent + Human)
The Artist lives in your **Workspace**. Instead of searching through massive raw texts (wasting tokens and losing focus), the Artist visits the **Exhibition** staged by the Curator. The Artist and Human collaborate to create new insights (**Synthesis**), which are then promoted to the official **Wiki**.

---

## 🌟 Why This System?

### 1. Knowledge Compiler & Learning Metaphor
Knowledge isn't just "found"; it's **compiled**. Our system treats your vault like a deep-learning model in training.
- **Forward Pass**: `wiki add` registers sources and builds L1-L3 layers (Contexts, Atoms, Concepts). `wiki curate` then synthesizes the final L4 Exhibition.
- **Loss Signal**: Human or agent edits and logical contradictions act as feedback, representing the "error" in the system's current state.
- **Backward Repair (Sync)**: `wiki sync` uses these signals to trace the DAG backward, repairing structural flaws and rewriting affected upstream nodes to restore logical integrity.

### 2. Token Optimization (FinOps for AI)
By offloading the "grunt work" of summarizing and atomizing to a **Local SLM**, we preserve the "heavy thinking" tokens for your high-reasoning models (Gemini, Claude) during the final synthesis phase.

### 3. Two-Track Architecture
- **`.curator/` (Machine Track)**: A high-density, machine-readable backend designed for Agent MCP tools.
- **`02_Wiki/` (Human Track)**: A beautiful, domain-organized Zettelkasten designed for human browsing and long-term ownership.

### 4. Dynamic Correction & Concreting
Knowledge is not a static past; it lives and evolves through the dialogue between agents and humans. Every correction or doubt raised during a task becomes a **feedback signal**, and the system uses the `wiki sync` feature to immediately resolve contradictions and restore logical integrity across the entire graph. These refined insights then harden into a new baseline (Concreting), fostering a self-healing ecosystem that grows more sophisticated and accurate the more you interact with it.

### 5. Knowledge Concentration & Growth
Knowledge only truly **Increments** when it is gathered in a **single, cohesive space** rather than being fragmented across decentralized silos. InCurator ensures that all insights are funneled into a single source of truth, allowing for higher-level synthesis and the organic growth of your intellectual capital.

---

## 🛠️ Getting Started

### 📋 Prerequisites
- **Python 3.10+**, **Obsidian**, **Node.js**
- (Optional) **Ollama & Subscription Account/ID**: Backends for the Curator Engine. You can easily connect via your **Subscription Service ID** or **Account Login**. Configuring both allows for automatic **Failover/Fallback** to local models if the cloud service encounters an issue.
- See [User Guide: Prerequisites](docs/guides/USER_GUIDE_EN.md#prerequisites) for details.

### 🚀 Quick Start
1.  **Install**: `./install.sh` (Attempts automatic installation of Ollama and Node.js)
2.  **Initialize**: `wiki init <path/to/your/obsidian-vault>`
    > [!IMPORTANT]
    > **Single Vault Principle**: Do not run `wiki init` in multiple scattered directories. InCurator achieves its most powerful **Increment** effect when all fragmented knowledge is gathered in one place. We strongly recommend designating **a single main vault** where all your personal knowledge is concentrated and running the system there.
3.  **Register (Compile)**: `wiki add <file>` (Auto-generates L1-L3 layers)
4.  **Use Knowledge (Query)**: `wiki query "question"` or MCP search (Includes auto-synthesis of L4)

Check the [User Guide](docs/guides/USER_GUIDE_EN.md) for more details.

---

## 🤝 Contributing

**"Better Tools, Smarter Agents."**

We are building a better way to refine knowledge for both humans and machines. Currently, we are tackling exciting challenges such as advancing pipeline orchestration, reducing model dependency, ensuring sync stability, and enhancing UI/UX.

From simple bug fixes to new feature proposals—your contributions increase the value of knowledge. Get started now with our [Contribution Guide](docs/guides/CONTRIBUTION_GUIDE.md)!

---

## 🔗 Connections
- [User Guide](docs/guides/USER_GUIDE_EN.md)
- [Contribution Guide](docs/guides/CONTRIBUTION_GUIDE_EN.md)
- [MCP Integration Guide](docs/guides/MCP_USER_GUIDE_EN.md)
- [Sync Ignore Guide](docs/guides/SYNC_IGNORE_GUIDE_EN.md)
- [Project Philosophy](docs/philosophy/about_EN.md)
