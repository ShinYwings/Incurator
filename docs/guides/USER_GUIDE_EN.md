# 📖 User Guide: Master the Incurator

This guide provides technical details on how to operate the **Curator Engine** and manage your knowledge DAG. For the design philosophy and motivation behind the system, see [Project Philosophy (about.md)](../philosophy/about_EN.md). For a feature overview, see the [README](../../README_EN.md).

---

## 📋 Prerequisites

Before installing the system, ensure the following tools are installed:

1.  **Python 3.10+**: The core logic is written in Python.
2.  **Terminal**: All commands are executed within a CLI environment.
3.  **Note Editor (Obsidian Recommended)**: The primary tool for visualizing and editing your knowledge base. While any text editor that supports Markdown can be used, the system is optimized for Obsidian's link structure and plugin ecosystem.
4.  **Node.js**: Required for building the search engine (QMD) and running the MCP server. (Note: `./install.sh` handles the installation of Node.js and Ollama automatically, so you don't need to prepare them separately.)
5.  **Curator Engine Backends**: At least one model backend is required, supporting both local and cloud providers.
    - **Local LLM (Ollama)**: Provides strong privacy and offline capabilities with no additional cost. (Requires VRAM)
    - **Subscription Services (Providers)**: Leverages external engines like Gemini, Claude, and OpenAI. These do not consume local VRAM and offer high reasoning performance. (Note: Standard universal models are sufficient for the curation phase; high-cost reasoning-only models are not strictly required.)
    - **Flexible Configuration**: You can configure either type as your **Primary** or **Fallback** engine. For example, you can use a local model as primary and a cloud model as failover, or vice versa.

> [!NOTE]
> **Verified Development Environment**
> This system has been fully tested and validated in the following environment:
> - **Interface**: A **CLI-only** engine. You can operate it directly in the terminal or leverage it within your **IDE (antigravity)** agent environment.
> - **Early Development Environment**: Incurator is in its early stages, and all experiments and validations were conducted by the developer using the **antigravity** agent environment. As a result, some internal logic may be unintentionally tailored to that specific environment. If you encounter issues in other agents or IDEs, we highly encourage contributions that generalize these environment-specific logic parts.
> - **Hardware**:
>   - **Linux**: NVIDIA GeForce RTX 4070 Ti 12GB, RAM 64GB
>   - **macOS**: Apple Silicon (8GB RAM environment tested)
> - **Minimum Specs & Hardware Performance**: 
>   - A **minimum of 2.5GB VRAM** is required to run the search engine (QMD).
>   - **When using a Local Model (Ollama)**: Additional VRAM is required based on the model size (e.g., ~10GB total for an 8B model, a margin of at least 2GB over the model size is recommended).
>   - **When using a Cloud Model (Gemini, Claude, etc.)**: No additional VRAM is consumed, making it possible to run the system with only the minimum VRAM required for QMD.
>   - While CPU+GPU offloading via Ollama is possible, it is extremely slow and may make practical curation difficult. We strongly recommend an environment where the entire model can fit into VRAM.

> [!TIP]
> **Multi-Device Synchronization**
> If you plan to use the same vault across multiple devices, we strongly recommend using **Syncthing**. Synchronizing the database (SQLite) files while they are being actively modified can lead to data corruption. You should use Syncthing's **Ignore** feature to exclude frequently changing DB files from synchronization. Refer to the [Sync Ignore Guide](./SYNC_IGNORE_GUIDE_EN.md) for detailed instructions.

---

## 🧭 Incurator Operational Principles

To maintain the powerful performance of Incurator and manage your knowledge safely, we recommend following these principles:

-   **Single Source of Truth**: Instead of running `wiki init` in multiple project directories to create small, fragmented knowledge bases, maintain **a single main vault** where all your knowledge is aggregated. Knowledge truly **Increments** and yields new insights only when it is concentrated and organically connected in one place.
-   **Respect the AI Space (AI-only Space)**: The `.curator/` folder is an 'AI-only space' designed exclusively for agents and the system. It is a high-density data network intentionally structured to be difficult for humans to read or edit. Manually modifying files here can break the integrity of your knowledge graph, so avoid touching it directly.
-   **Self-Healing & Integrity**: If you feel your knowledge graph is contaminated or links are broken, run the `wiki sync` command. Incurator has self-healing capabilities to trace errors and restore logical integrity automatically. **Crucially, if you manually edit any node files yourself (rather than via an agent), you must run `wiki sync` to propagate those changes through the entire graph.**
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

#### 📂 Vault Directory Structure
Running the `wiki init` command initializes the following structure for knowledge management. Following the philosophy that knowledge is most effective when stored in different forms for machines and humans, Incurator strictly separates human-readable spaces (Root) from the AI-only spaces (`.curator/`) via physical directory separation.

```text
<vault_root>/
├── .obsidian/         # Obsidian configuration and plugins
├── 00_System/         # User-defined folders (e.g., sandbox, inbox, daily, etc.)
├── 01_Workspaces/     # [Artist Space] Project-specific studios (See structure below)
├── 02_Wiki/           # [Human Space] Human-verified and promoted knowledge
├── 03_Notes/          # [Source] Original human notes (Immutable/Read-only)
├── 04_Resources/      # [Source] External references and literature (Immutable)
├── 05_Assets/         # Media assets (images, PDF attachments, etc.)
├── 06_Archives/       # Archives for deprecated or old sources
├── .curator/          # [AI Space] Core system data and SQLite DB (AI-only Space)
│   ├── config.yml     # LLM backends, models, and path configurations
│   ├── state.sqlite   # Deduplication hashes, provenance, run history
│   ├── index.md       # DAG routing table (Mapping of all node IDs)
│   ├── ledger.md      # History of HITL corrections and promotions
│   └── Collections/   # Knowledge Layer (DAG) Storage
│       ├── 01_Contexts/    # [L1] Summaries and refined metadata
│       ├── 02_Atoms/       # [L2] Atomic facts (Permanent Notes)
│       ├── 03_Concepts/    # [L3] Thematic groupings
│       └── 04_Exhibitions/ # [L4] Task-optimized agent exhibits
├── .gitignore         # Git ignore rules
└── .stignore          # Syncthing ignore rules
```

> [!NOTE]
> While `01_Workspaces/` is typically located inside the Vault, you can also connect and operate project directories physically located outside the Vault as workspaces.

> [!TIP]
> For detailed ignore patterns and synchronization best practices, refer to the [Sync Ignore Guide](./SYNC_IGNORE_GUIDE_EN.md).

### 3. Register Knowledge Sources
Send your raw files (PDF, Markdown, HTML, Text) to the Curator for registration.
```bash
wiki add <file>
```
This command performs **Knowledge Ingestion and Refinement (L1-L3)**: it parses raw data to generate L1 Contexts, L2 Atoms, and L3 Concepts.

### 4. Use Knowledge (Query) & L4 Curation
When you search for knowledge, the system automatically runs the final L4 pipeline if needed to synthesize Concepts into Exhibitions.

> [!IMPORTANT]
> **Trigger-based Auto-sync**:
> This automation is not a persistent background service. It is triggered at the **moment** you interact with an agent (`search_curator`) or run `wiki query` from a **registered workspace directory** (see [Initialization](#🏗️-creating-and-initializing-a-workspace)). The system checks for pending sources and processes them immediately when it detects your "intent" to use knowledge. This ensures the pipeline works organically without manual execution. See the [MCP User Guide](./MCP_USER_GUIDE_EN.md) for details.

To run it manually, use:
```bash
wiki curate
```
- **L4 Exhibitions**: Synthesizes high-level Concepts into task-optimized packages for agents.

---

---

## 📚 Knowledge Ingestion

Once your vault's physical structure is ready, it's time to inject your fragmented knowledge into the system.

Incurator's ingestion process consists of two stages: **Organizing files (Organize)** and **Summarizing and refining them into knowledge layers (L1–L3) (Ingest)**. The data collected here will later be processed into Exhibits (Exhibitions) within a workspace for actual use.

### Step 1: Organize Files
First, place your original files (PDF, Markdown, HTML, images, etc.) into the appropriate folders within the vault based on their nature.
- `03_Notes/`: Your own notes and thoughts.
- `04_Resources/`: External papers, articles, and literature.
- `05_Assets/`: Attached images or data files.

### Step 2: Extract and Register Knowledge (Ingest)
Once the files are organized, command the Curator to read them and refine them into the knowledge layers (L1–L3).

```bash
# Register a specific file within the vault
wiki add 03_Notes/my_note.md

# Omit the argument to scan the entire vault and register all changes at once
wiki add
```

With this command, the Curator parses the raw data to automatically perform **L1 Summary, L2 Atomic Fact Extraction, and L3 Concept Linking**. The results are stored in the AI-only space inside `.curator/`.

> [!TIP]
> If no file or directory path is specified for `wiki add`, the Curator scans all configured source directories (e.g., `03_Notes`, `04_Resources`) to automatically find and batch-process new or changed files.

- You can check the list of registered sources with `wiki sources list`.
- To recursively register all files within a specific folder, use the `-r` option.

Once your knowledge is safely registered in the vault, it's time to set up your own "Studio" to actually use it for specific projects.

---

## 🎨 Workspace Management

Workspaces are the **Studios** where the **Artist** (Human + Agent) performs actual project work.

> [!IMPORTANT]
> **Location Freedom**: A workspace does not have to be located inside the vault (`01_Workspaces/`). Any **project directory** on your filesystem can be turned into a workspace connected to the Curator by running `wiki workspace init`.

### 🏗️ Creating and Initializing a Workspace
When starting a new project or connecting an existing one to your knowledge base, run the initialization command in that directory. This process prepares the configuration files and agent-specific rules all at once.

> [!TIP]
> **How the System Detects the Workspace**:
> The Curator identifies the "current" workspace by searching for a `curate.yml` file in your **Current Working Directory (CWD)** or its parent directories. This means that as long as you run commands from within a project folder, the system automatically recognizes which project context to use.

#### 📁 Workspace Directory Structure
Once a workspace is initialized, the following structure is created within the project directory:

```text
<your_project_dir>/
├── curate.yml         # Knowledge Requirement Specification (Required)
├── .agents/           # Agent-specific workspace (Auto-generated)
└── <notes/scripts>    # Human artifacts related to this project
```

```bash
# Initialize a workspace in a specific directory
wiki workspace init <path/to/workspace> --agent antigravity
```
- `--agent`: Installs rules for your specific agent (e.g., antigravity, gemini-cli).
- `--project`: Sets a unique ID for the project. (Default: directory name)

### `curate.yml` (Knowledge Requirement Specification)
This file tells the Curator what knowledge to "stage" for the current project.
```yaml
project: "Gaussian Splatting Research"
scope: "concepts" # all | concepts | exhibitions
min_confidence: 0.8
boost_terms: ["depth distortion", "normal consistency"]
```
When an agent searches via MCP, the Curator uses this spec to filter and prioritize the most relevant information.

Both the vault and workspaces are now ready. Let's see how the Curator answers your questions and collaborates with agents.

---

## 🔍 Knowledge Utilization & Curation

Now you can obtain answers or perform the final synthesis for agent consumption.

### Querying and Auto-updates (Intent-based Curation)
This is the core operational mode of Incurator. You just need to ask or converse.

The system checks the `curate.yml` specification and **instantly activates the pipeline to synthesize the final answer** at the moment you run `wiki query` or interact with an agent (`search_curator`) in a workspace.

> [!TIP]
> **"Just use it. the system handles the rest."**
> Curation is triggered when an "intent" to use knowledge occurs, so you don't have to specify which workspace it is or manually run the pipeline every time. (The system automatically understands the context through the folder location where you run the command.)

### (Reference) Manual Forced Curation
Use this only for debugging or when a forced update is required.
```bash
wiki curate
```
- **Automatic Workspace Selection**: If a `curate.yml` exists in the current or parent directory, it follows that specification.
- **Default Fallback**: When running `wiki curate` without an active workspace, the Curator automatically creates a **default workspace** at `01_Workspaces/Curator Workspace` and performs curation on the entire knowledge base.
    - > [!WARNING]
    > **Scheduled for Removal**: This automatic creation feature is provided temporarily for convenience during the v0.1.0 development and debugging phase. In future versions, automatic synthesis without an explicit workspace (`curate.yml`) will be restricted to ensure clear knowledge management boundaries. We strongly recommend using `wiki workspace init` for formal setup.

---

## 🔄 Feedback Loop & Self-Healing (HITL & Sync)

Knowledge is refined incrementally through dialogue and correction.

1.  **Synthesis**: Derive new insights by engaging in dialogue with the agent in your workspace.
2.  **Feedback & Correction**: If you discover errors in prior knowledge, correct the nodes immediately using MCP tools.
3.  **Self-Healing**: When a node is updated, `wiki sync` runs automatically to trace the DAG backward (Backprop) and restore consistency. Run `wiki sync` manually to verify overall integrity.
4.  **Promotion**: Move finalized insights to `02_Wiki/` to promote them to human-readable wikis.
5.  **Loop**: Promoted wikis are recognized as new sources in the next cycle, allowing knowledge to grow **incrementally**.

This circular flow ensures that your knowledge never stays stagnant but keeps evolving through interaction and verification.

---

## 🧑‍🎨 Persona Setup

The persona is how Incurator understands your knowledge model. The system is a general-purpose curation engine, but the persona steers its behavior toward your domain and goals.

### Curator Persona

Configured automatically through a short interview during `wiki init`. The result is stored under the `persona:` key in `.curator/config.yml` and applied across `wiki sync` (verification context) and `wiki query` (synthesis context).

```bash
wiki persona              # Show the current Curator persona
wiki persona update       # Re-run the interview to update the Curator persona
```

If you skip the interview or have not configured one, a default STEM persona is applied.

### Artist Persona

Stored under the `persona:` key in each workspace's `curate.yml`, overriding the Curator persona for that project. It is created automatically on the first run of `wiki curate --workspace <name>` and can be updated later:

```bash
wiki persona update --workspace <name>   # Update the Artist persona
```

The Artist persona lets you set a project-specific `exhibition_intent` (researcher / engineer / learner), confidence thresholds, and disambiguation keywords, giving you fine-grained control over how knowledge is staged for each workspace.

---

## 🛠️ Core Commands (CLI Reference)

Summary of major commands following the user workflow.

### 1. Setup & Configuration
| Command | Description | When to use |
| :--- | :--- | :--- |
| `wiki init <path>` | Initializes a Curator vault. | First-time setup |
| `wiki config <key>` | Modifies model and environment settings. | Changing providers or preferences |
| `wiki status` | Checks vault health and statistics. | Checking overall system health |
| `wiki persona` | Show and update the vault persona. | Adjusting curation direction |

### 2. Knowledge Ingestion & Management
| Command | Description | When to use |
| :--- | :--- | :--- |
| `wiki add <file>` | Registers sources and builds L1-L3 layers. | Adding new information |
| `wiki sources list` | Lists all registered sources. | Checking collected data inventory |

### 3. Refinement & Optimization
| Command | Description | When to use |
| :--- | :--- | :--- |
| `wiki curate` | Synthesizes L4 Exhibitions. | Manually updating exhibits |
| `wiki sync` | Verifies integrity and performs self-healing. | Restoring consistency after edits |

### 4. Knowledge Utilization
| Command | Description | When to use |
| :--- | :--- | :--- |
| `wiki query "..."` | Gets refined answers to questions. | Using curated knowledge |
| `wiki workspace init` | Initializes a workspace. | Starting a new project |

### 5. Developer Tools (Developer Only)
| Command | Description | When to use |
| :--- | :--- | :--- |
| `wiki testbed init` | Builds a virtual test vault (`testbed/`). | When you want to safely validate new features |
| `wiki testbed list` | Lists available test scenarios. | When selecting a scenario for validation |

> [!CAUTION]
> **Testbed Notice**: These commands handle temporary, development-only storage, not your actual knowledge base. Do not use them during standard knowledge management or actual project execution.

---

## 🧩 Configuration Management

Incurator allows you to safely and conveniently manage all core settings via the `wiki config` command without having to manually edit the `.curator/config.yml` file.

### 1. Provider Configuration (`wiki config provider`)
Configure the LLM backends that power Incurator's intelligence. The system maintains two backend layers.

- **Primary Backend**: The main engine for all tasks. Choose the model that best fits your hardware specifications and budget.
- **Fallback Backend (Failover)**: A secondary engine that takes over if the primary engine fails due to network issues or API limits. Designating a different type (e.g., Cloud ↔ Local) from the primary engine further increases system stability.

> [!NOTE]
> `Primary` and `Fallback` share the same configuration options, and you can freely cross-select any of the providers listed below for either role.

#### Supported Provider List
| Provider | Type | Key Features |
| :--- | :--- | :--- |
| `ollama` | Local | Use local models like DeepSeek or Llama 3 (Free, offline capable) |
| `gemini-cli` | CLI | Inference via official Google `gemini` command (Fast, reliable free option) |
| `claude-code` | CLI | Inference via official Anthropic `claude` command |

```bash
# Set up both Primary and Fallback at once via the wizard
wiki config provider
```

### 2. Model Management (`wiki config models`)
View and change the specific models to be used by the current provider.

```bash
# View available models and the recommended list
wiki config models list

# Switch to a specific model immediately (Auto-downloads for Ollama if not present)
wiki config models use gemma2:9b
```

- `wiki config models list` recommends the best models suited for your system performance and provider characteristics.
- When you change a model via `wiki config models use`, the system instantly verifies the model's availability and reflects the change in the configuration file.

### 3. Status Verification (`wiki status`)
A comprehensive dashboard that provides a multi-dimensional diagnosis of your vault's health and the operational status of your AI engines. This is the first command you should check whenever you have questions during system operation.

```bash
wiki status
```

This command aggregates and outputs data from three main areas in real-time. Here is the meaning and practical use of each item:

#### ⚙️ System Configuration (Config)
Verifies if the system's 'brain' and 'eyes' are correctly set up.
-   **Primary / Fallback Models**: Shows the main LLM and the emergency fallback LLM currently responsible for knowledge extraction and synthesis. Ensure the intended models are active.
-   **Reranking**: Indicates whether the secondary verification process to improve search precision is enabled. This should be `on` for high-quality answers.
-   **QMD binary**: The status of the core search engine binary. If it's not `installed` or is `not found`, you may need to run `wiki reindex` or reinstall.

#### 📂 Knowledge Source Status (Sources)
Checks the 'entrance of the pipeline' where raw data is turned into knowledge.
-   **Raw source files**: The total number of files physically present in the vault folders.
-   **Sources summarized (L1)**: If this number is lower than the number of raw source files, it means there is new knowledge that the system hasn't read yet via `wiki add`.
-   **Ingest runs**: The total number of ingestion runs performed. A higher number indicates that the knowledge base has been updated frequently.

#### 🧠 Knowledge Density (Collections)
Shows the processing status at each pipeline stage. L1, L2, and L3 are all generated together in a single `wiki add` run. L4 is generated separately.

-   **L1 Contexts**: One summary per source. Should match the number of ingested sources.
-   **L2 Atoms**: Atomic facts extracted from each source. Multiple atoms are generated per source, so this count will be larger than L1.
-   **L3 Concepts**: Cross-source clusters formed from L2 atoms.
-   **L4 Exhibitions**: Exhibits synthesized per workspace spec (`curate.yml`). Starts at 0 until a workspace is initialized and `wiki curate` has been run.

> [!TIP]
> **Pipeline Status Diagnosis**: If L4 is 0, no workspace Exhibition has been generated yet. Calling `search_curator` via MCP will automatically trigger `wiki curate` and create L4. To generate manually, run `wiki curate` directly.
