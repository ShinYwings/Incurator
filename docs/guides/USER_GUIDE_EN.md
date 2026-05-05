# 📖 User Guide: Master the InCurator

This guide provides technical details on how to operate the **Curator Engine** and manage your knowledge DAG. For a high-level overview of the philosophy, see the [README](../../README_EN.md).

---

## 📋 Prerequisites

Before installing the system, ensure the following tools are installed:

1.  **Python 3.10+**: The core logic is written in Python.
2.  **Obsidian (Essential)**: The primary tool for visualizing and editing your knowledge base.
3.  **Node.js**: Required for building the search engine (QMD) and running the MCP server. (Automatic installation is attempted during `./install.sh`.)
4.  **Ollama (Optional)**: Recommended if you intend to use local SLMs (e.g., DeepSeek) as background curators. (Automatic installation is attempted during `./install.sh`.)
5.  **Subscription LLM Services (Optional)**: You can integrate services like Gemini, Claude, and OpenAI for more sophisticated knowledge synthesis and reasoning. An **API Key** or **Login ID** for the respective service is required for CLI usage.

> [!NOTE]
> **Verified Development Environment**
> This system has been fully tested and validated in the following environment:
> - **OS**: Linux (Ubuntu 24.04), macOS
> - **Hardware**:
>   - **Linux**: NVIDIA GeForce RTX 4070 Ti 12GB, RAM 64GB
>   - **macOS**: Apple Silicon (8GB RAM environment tested)
> - **Agent**: Validated within the **antigravity** agent environment
> - **Minimum Specs & Local Performance**: 
>   - A **minimum of 2.5GB VRAM** is required for the search engine (QMD), plus additional VRAM equivalent to the size of your chosen LLM model.
>   - When using an **8B parameter model** (e.g., DeepSeek-R1 8B), the system occupies **over 10GB of VRAM** in total (a 12GB VRAM environment is recommended).
>   - While CPU+GPU offloading via Ollama is possible, it is extremely slow and may make practical curation difficult. We strongly recommend an environment where the entire model can fit into VRAM.

> [!TIP]
> **Multi-Device Synchronization**
> If you plan to use the same vault across multiple devices, we strongly recommend using **Syncthing**. Synchronizing the database (SQLite) files while they are being actively modified can lead to data corruption. You should use Syncthing's **Ignore** feature to exclude frequently changing DB files from synchronization. Refer to the [Sync Ignore Guide](./SYNC_IGNORE_GUIDE_EN.md) for detailed instructions.

---

## 🧭 InCurator Operational Principles

To maintain the powerful performance of InCurator and manage your knowledge safely, we recommend following these principles:

-   **Single Source of Truth**: Instead of running `wiki init` in multiple project directories to create small, fragmented knowledge bases, maintain **a single main vault** where all your knowledge is aggregated. Knowledge truly **Increments** and yields new insights only when it is concentrated and organically connected in one place.
-   **Hands-off `.curator`**: The `.curator/` folder is a 'machine-only space' designed exclusively for agents and the system. It is intentionally structured to be difficult for humans to read or edit. Manually modifying files here can break the integrity of your knowledge graph, so avoid touching it directly.
-   **Self-Healing & Integrity**: If you feel your knowledge graph is contaminated or links are broken, don't try to fix it manually. Simply run the `wiki sync` command. InCurator has self-healing capabilities to trace errors and restore logical integrity automatically.
-   **Workspace Flexibility**: While your knowledge Library (Vault) should be centralized, your **Workspaces** (where you do the work) can be located anywhere. Connect any project folder or working directory to your central main Vault to consume its knowledge. You have one "Library" but can have unlimited "Studios."

---

## 🚀 Quick Start

### 1. Installation
Run the installation script to set up the environment and build the necessary components:
```bash
./install.sh
```

### 2. Initialize a Vault
Choose a directory to serve as your knowledge vault and initialize it:
```bash
wiki init <path/to/your/obsidian-vault>
```

### 3. Register Knowledge Sources
Send your raw files (PDF, Markdown, HTML, Text) to the Curator for registration.
```bash
wiki add <file>
```
This command performs **Knowledge Registration and Compilation (L1-L3)**: it parses raw data to generate L1 Contexts, L2 Atoms, and L3 Concepts.

### 4. Use Knowledge (Query) & L4 Curation
When you search for knowledge, the system automatically runs the final L4 pipeline if needed to synthesize Concepts into Exhibitions. To run it manually, use:
```bash
wiki curate
```
- **L4 Exhibitions**: Synthesizes high-level Concepts into task-optimized packages for agents.

---

## 🛠️ Essential Commands

| Command | Description | When to use |
| :--- | :--- | :--- |
| `wiki add <file>` | Registers new sources and builds L1-L3 layers. | When you have new raw information |
| `wiki curate` | Runs the L3 ➡️ L4 LLM pipeline. | To manually build or update Exhibitions |
| `wiki sync` | Verify integrity and repair the DAG. | If links are broken or nodes seem out of sync. |
| `wiki query "..."` | Search and synthesize an answer. | When you need a quick RAG-based answer. |
| `wiki status` | Show vault health and statistics. | To check the state of your knowledge ecosystem. |
| `wiki reindex` | Rebuild the search index. | After manual edits to ensure they are searchable. |

---

## 📂 Understanding the Layers

The Curator builds a **Directed Acyclic Graph (DAG)** to ensure every claim has evidence.

1.  **01_Contexts (L1)**: Summaries that preserve the original intent and metadata of a source.
2.  **02_Atoms (L2)**: Atomic, independent claims. The "Permanent Notes" of our system.
3.  **03_Concepts (L3)**: High-level thematic groupings that connect Atoms across multiple sources.
4.  **04_Exhibitions (L4)**: Final "Exhibits" staged for agents. These are task-specific and grounded in evidence.

---

## 🎨 Managing Workspaces

Workspaces (`01_Workspaces/`) are where the **Artist** (Human + Agent) works. Each workspace has a `curate.yml` file.

### `curate.yml` (Knowledge Requirement Specification)
This file tells the Curator what knowledge to "stage" for the agent:
```yaml
project: "Gaussian Splatting Research"
scope: "concepts" # all | concepts | exhibitions
min_confidence: 0.8
boost_terms: ["depth distortion", "normal consistency"]
```
When an agent searches via MCP, the Curator uses this spec to filter and prioritize the most relevant "Exhibits."

---

## 🔄 The Feedback Loop (HITL)

1.  **Forward Pass**: Use `wiki curate` to build up.
2.  **Synthesis**: Naturally engage in dialogue with the agent in your workspace to derive new insights. During this conversational flow, any errors in prior knowledge can be naturally discovered and corrected immediately using MCP tools.
3.  **Backpropagation**: When a node is updated, `wiki sync` runs to trace the DAG backward and automatically rewrite affected upstream nodes to maintain integrity.
4.  **Promotion**: Move finalized insights to `02_Wiki/`.
5.  **Loop**: The Curator will automatically ingest `02_Wiki/` items as new sources in the next cycle, making your knowledge **Incremental** and hardened (**Concreting**).

---

## 🧩 Advanced Configuration

Edit `.curator/config.yml` to change your LLM backends:
- **Primary**: High-reasoning (Gemini, Claude) for Synthesis.
- **Background**: Local SLM (Ollama, DeepSeek) for Curation (L1-L3).
