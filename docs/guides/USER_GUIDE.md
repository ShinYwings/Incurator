# 📖 User Guide: Master the Incurator

This guide provides technical details on how to operate the **Curator Engine** and manage your knowledge DAG. For the design philosophy and motivation behind the system, see [Project Philosophy (ABOUT_KR.md)](../philosophy/ABOUT.md). For a feature overview, see the [README](../../README.md).

---

## 📋 Prerequisites

Before installing the system, ensure the following tools are installed:

1.  **Python 3.10+**: The core logic is written in Python.
2.  **Terminal**: All commands are executed within a CLI environment.
3.  **Note Editor (Obsidian Recommended)**: The primary tool for visualizing and editing your knowledge base. While any text editor that supports Markdown can be used, the system is optimized for Obsidian's link structure and plugin ecosystem.
4.  **Node.js**: Required for building the search engine (QMD) and running the MCP server. (Note: `./setup.sh` handles the installation of Node.js, Ollama, and the backend package automatically, while `wiki init` handles the plugin installation.)
5.  **Curator Engine Backends**: At least one model backend is required, supporting both local and cloud providers.
    - **Local LLM (Ollama)**: Provides strong privacy and offline capabilities with no additional cost. (Requires VRAM)
    - **Subscription Services (Providers)**: Leverages external engines like Antigravity, Claude, and OpenAI. These do not consume local VRAM and offer high reasoning performance. (Note: Standard universal models are sufficient for the curation phase; high-cost reasoning-only models are not strictly required.)
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
>   - **When using a Cloud Model (Antigravity, Claude, etc.)**: No additional VRAM is consumed, making it possible to run the system with only the minimum VRAM required for QMD.
>   - While CPU+GPU offloading via Ollama is possible, it is extremely slow and may make practical curation difficult. We strongly recommend an environment where the entire model can fit into VRAM.

> [!TIP]
> **Multi-Device Synchronization**
> If you plan to use the same vault across multiple devices, we strongly recommend using **Syncthing**. Synchronizing the database (SQLite) files while they are being actively modified can lead to data corruption. You should use Syncthing's **Ignore** feature to exclude frequently changing DB files from synchronization. Refer to the [Sync Ignore Guide](./SYNC_IGNORE_GUIDE.md) for detailed instructions.

---

## 🧭 Incurator Operational Principles

To maintain the powerful performance of Incurator and manage your knowledge safely, we recommend following these principles:

-   **Single Source of Truth**: Instead of running `wiki init` in multiple project directories to create small, fragmented knowledge bases, maintain **a single main vault** where all your knowledge is aggregated. A dedicated **Curator** resides in every folder initialized with `wiki init`, and knowledge truly **Increments** and yields new insights only when it is concentrated and organically connected in one place.
-   **Persona-based Vault Segmentation**: Only operate separate vaults if the 'perspective' or 'expert persona' you want for your knowledge management is fundamentally different (e.g., a STEM expert vs. a Cooking expert). Since a single Incurator instance runs one Curator at a time, excessive fragmentation hinders knowledge connectivity.
-   **Respect the AI Space (AI-only Space)**: The `.curator/` folder is an 'AI-only space' designed exclusively for agents and the system. It is a high-density data network intentionally structured to be difficult for humans to read or edit. Manually modifying files here can break the integrity of your knowledge graph, so avoid touching it directly.
-   **Self-Healing & Integrity**: If you feel your knowledge graph is contaminated or links are broken, run the `wiki sync` command. Incurator has self-healing capabilities to trace errors and restore logical integrity automatically. **Crucially, if you manually edit any node files yourself (rather than via an agent), you must run `wiki sync` to propagate those changes through the entire graph.**
-   **Workspace Flexibility**: While your knowledge Library (Vault) should be centralized, your **Workspaces** (where you do the work) can be located anywhere. Connect any project folder or working directory to your central main Vault to consume its knowledge. The Curator lives in the "Library" (Vault), and the Artist lives in the "Studio" (Workspace). You have one Library but can have unlimited Studios.

---

## 🚀 Quick Start

### 1. Installation
Run the installation script to set up the environment and build the necessary components:
```bash
./setup.sh
```

### 2. Initialize a Vault
Choose a directory to serve as your knowledge vault and initialize it:
```bash
wiki init <path/to/your/obsidian-vault>
```

During init, a short interview sets up the **Curator persona** — the vault-wide expert identity that governs how knowledge is synthesized and verified. The wizard asks the first question immediately, labels single-select and multi-select questions, accepts comma-separated numbers on multi-select questions such as verification sources and artifact types, and exits as soon as the final persona JSON is saved. The result is saved to `.curator/config.yml` and applied automatically on every `wiki sync` and `wiki query`.

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
│       └── 04_Exhibitions/ # [L4] Task-optimized agent exhibits (Only generated markdown layer)
├── .gitignore         # Git ignore rules
└── .stignore          # Syncthing ignore rules
```

> [!NOTE]
> While `01_Workspaces/` is typically located inside the Vault, you can also connect and operate project directories physically located outside the Vault as workspaces.

> [!TIP]
> For detailed ignore patterns and synchronization best practices, refer to the [Sync Ignore Guide](./SYNC_IGNORE_GUIDE.md).

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
> This automation is not a persistent background service. It is triggered at the **moment** you interact with an agent (`search_curator`) or run `wiki query` from a **registered workspace directory** (see [Initialization](#🏗️-creating-and-initializing-a-workspace)). The system checks for pending sources and processes them immediately when it detects your "intent" to use knowledge. This ensures the pipeline works organically without manual execution. See the [MCP User Guide](./MCP_USER_GUIDE.md) for details.

For advanced debugging or workspace-agent recovery, the hidden manual command is:
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

With this command, the Curator parses the raw data and immediately extracts structural L1 Contexts into the `state.sqlite` database. L1 adds an English `Source Guide` with section/page previews for quick recall, inlines raw `Source Sections` for small/medium documents, and uses on-demand raw-source reads for large documents. L1-L3 are managed strictly as database records—no intermediate markdown files are written, preventing vault pollution. It queues L2 Atomic Fact Extraction plus L3 Concept Linking for the build worker. The results are stored in the AI-only database inside `.curator/state.sqlite`.

> [!TIP]
> If no file or directory path is specified for `wiki add`, the Curator scans all configured source directories (e.g., `03_Notes`, `04_Resources`) to automatically find and batch-process new or changed files.

- You can check the list of registered sources with `wiki source ls`.
- To recursively register all files within a specific folder, use the `-r` option.

Once your knowledge is safely registered in the vault, it's time to set up your own "Studio" to actually use it for specific projects.

---

## 📄 External PDFs And Reference Mode

External files such as research PDFs owned by Zotero, iCloud, Syncthing, or a browser download folder can be connected to Incurator in two ways.

### 1. Reference Mode

The file stays in its original location while the Incurator backend registers it
as a tracked source. This is the default for PDFs opened from Zotero, iCloud,
Syncthing, browser download folders, or other external locations.

- The backend calculates the content hash and records a source entry in
  `state.sqlite`.
- `04_Resources/` receives a small markdown reference stub, not a copied PDF.
- `external_path` is only a recoverable location hint. The durable identity is
  the content hash plus logical source identity.
- Automatically generated reference stubs do not include absolute PDF paths by
  default, so they can safely synchronize to another device whose external PDF
  library lives elsewhere.
- If iPad annotations or an external app change the PDF bytes, the backend
  should detect this as Hash Drift.
- If the file moves, the backend may rediscover it inside configured external
  roots, but final rebind must happen only after human approval.

### 2. Copy Import

Copy Import is an explicit exception for files that should become
vault-managed resources. The PDF is copied into `04_Resources/`.

- PDFs do not belong in `03_Notes/`. `03_Notes/` is for human-authored notes.
- If the active note is `03_Notes/Vision/Foo.md`, the default destination is `04_Resources/Vision/Foo/<pdf-file>.pdf`.
- If no linked note exists, the fallback destination is `04_Resources/Inbox/<pdf-file>.pdf`.
- Existing files are never overwritten. Same-hash files reuse the existing source; same-name but different-hash collisions require a suffix or a user-selected destination.

The Obsidian plugin may answer immediate questions about an open PDF using viewer context, but durable source tracking, page provenance, and long-term RAG belong to the Incurator backend.

---

## 🎨 Workspace Management

Workspaces are the **Studios** where the **Artist** (Human + Agent) performs actual project work.

> [!IMPORTANT]
> **Location Freedom**: A workspace does not have to be located inside the vault (`01_Workspaces/`). Any **project directory** on your filesystem can be turned into a workspace connected to the Curator by running `wiki workspace init`.

### 🏗️ Connecting Your Agent to Curator

Run the following command from any project directory to connect Curator to your agent:

```bash
wiki workspace init <path/to/workspace> --agent <agent>
```

Choose `--agent` based on your agent runtime:

| Agent               | `--agent` value | Rule file                  |
| ------------------- | --------------- | -------------------------- |
| Claude Code         | `claude-code`   | `CLAUDE.md`                |
| OpenAI Codex        | `codex`         | `AGENTS.md`                |
| Antigravity         | `antigravity`   | `AGENTS.md`                |
| No agent (CLI only) | `none`          | —                          |

`--project` sets a unique project slug (defaults to the directory name).

> [!TIP]
> **How the System Detects the Workspace**:
> The Curator identifies the "current" workspace by searching for a `curate.yml` file in your **Current Working Directory (CWD)** or its parent directories. You do not need to specify the workspace on every command.

---

### 🔄 What Happens at Init — Three Scenarios

`wiki workspace init` detects the current state of the target directory and adapts:

#### Scenario 1: Empty directory

Everything is created from scratch — `curate.yml`, agent rule file, and Curator-managed files under `.agents/curator/`.

#### Scenario 2: Existing agent setup (no Curator yet)
The directory already has agent rules (`CLAUDE.md`, `AGENTS.md`, etc.) but Curator is not wired in.

Incurator uses its own LLM to read your existing rule file and integrate the Curator hooks at the right places — session start, query loop, session end — while preserving all your existing rules.

```text
Found existing claude-code setup. Integrating Curator knowledge navigation...

Proposed changes to CLAUDE.md:
  ## My Existing Rules            ← preserved
+ ## Curator Knowledge Navigation  ← added by LLM
+
+ **Session start** — call curator_check_workspace() ...
  ...

Apply Curator integration to CLAUDE.md? [Y/n]:
```

- **Y**: file is rewritten with Curator hooks integrated.
- **N**: a copy-paste prompt is printed instead, which you can give to your agent to do the integration manually.

If the LLM is unavailable, the copy-paste prompt is printed automatically and a Curator block is prepended to the rule file as a fallback.

#### Scenario 3: Curator already connected (restore / update)

`curate.yml` and the Curator runtime files already exist. The owned files under `.agents/curator/` are overwritten with the latest templates (picking up any Incurator updates), and the managed block in the agent rule file is replaced in-place. Your content outside the managed block is never touched.

---

### 📁 Files Created by Init

```text
<your_project_dir>/
├── curate.yml                           # Knowledge Requirement Specification
├── CLAUDE.md (or AGENTS.md) # Agent rule file — managed block injected
└── .agents/curator/
    ├── shared/rules.md                  # Full Curator behavioral rules
    ├── shared/sync.md                   # Sync workflow guide
    ├── runtime/<agent>.md               # Agent-specific runtime notes
    └── workflows/
        ├── workspace_loop.md            # Session workflow
        └── session_closeout.md          # End-of-session checklist
```

Files under `.agents/curator/` are **owned by Incurator** and overwritten on every init/sync to propagate template updates. Your content outside the managed block in the top-level rule file is never modified.

---

### Via MCP (no CLI required)

If your agent already has the MCP server connected, you can initialize a workspace directly from within a chat session:

```text
curator_workspace_init(
  workspace_path="/absolute/path/to/project",
  project="my-project",
  description="What this workspace is about"
)
```

The MCP tool auto-detects the connecting agent runtime and applies the same three-scenario logic. If the workspace already has agent rules, it attempts LLM integration automatically and returns an `integration_prompt` if the LLM is unavailable for the agent to use.

See the [MCP User Guide](./MCP_USER_GUIDE.md) for the full tool reference.

---

### `curate.yml` — Workspace Configuration Reference

`curate.yml` is the workspace-level configuration file. It tells the Curator what knowledge to stage and how to present it, and embeds the **Artist persona** that controls curation style for this project.

```yaml
project: "my-project"
description: "Knowledge workspace for my-project"

# Artist Persona — auto-generated by wiki workspace init wizard.
# Controls how the Curator scopes and ranks Exhibitions for this project.
persona:
  domain: ""               # e.g. "computer-vision", "biochemistry"
  subdomain: ""            # more specific focus area
  goal: ""                 # 2-4 sentences describing the curation goal
  exhibition_intent: "engineer"  # researcher | engineer | learner
  disambiguation_keywords: []    # workspace-specific terms to boost
  confidence:
    high_threshold: 0.85   # Exhibitions above this → high confidence
    low_threshold: 0.55    # Exhibitions below this → HITL review queue
  updated_at: ""

# Source selection — fnmatch globs relative to vault root.
# Empty include list = draw from all vault sources.
sources:
  include: []
  #  - "03_Notes/**"
  #  - "02_Wiki/my-topic/**"
  exclude: []

# Minimum confidence floor for search_curator results.
min_confidence: 0.60

# Active Exhibition anchor — auto-set by wiki curate.
# Leave empty for auto-detection; pin a specific ID to lock context.
exhibition: ""
```

**Key fields:**

| Field | Purpose |
| ----- | ------- |
| `persona.exhibition_intent` | `researcher` — next hypotheses to validate; `engineer` — implementation steps; `learner` — concepts to review |
| `persona.confidence` | Per-workspace confidence thresholds, overriding vault-wide defaults |
| `sources.include` | Limit which vault files feed this workspace (empty = all) |
| `min_confidence` | Exhibitions below this score are excluded from `search_curator` results |
| `exhibition` | Pinned Exhibition ID used as the primary context anchor in every session |

> [!TIP]
> The `persona:` block is generated automatically by the Artist persona wizard that runs during `wiki workspace init`. You can update it later with `wiki persona update --workspace <name>` or via the `curator_update_artist_persona` MCP tool.

Both the vault and workspaces are now ready. Let's see how the Curator answers your questions and collaborates with agents.

---

## 🔍 Knowledge Utilization & Curation

Now you can obtain answers or perform the final synthesis for agent consumption.

### Querying and Auto-updates (Intent-based Curation)
This is the core operational mode of Incurator. You just need to ask or converse.

The system uses a **Dual Architecture** for querying, depending on whether you are in a Workspace or Vault:
- **Workspace Agent**: If a workspace is specified, it uses the **Pinned Exhibition** and persona defined in `curate.yml` without generating ephemeral files.
- **Vault Agent**: When querying from a general Vault session, it dynamically generates an **Ephemeral L4 Exhibition** per chat session, using a global fallback persona. A plain chat whose active note is not inside a workspace folder is treated as a Vault session: its ephemeral Exhibition is scoped to `default`, not to an arbitrary project workspace you never opened.

**Per-request language**: The agent detects each question's language fresh (Korean, English, Chinese, Japanese, Russian, …) by Unicode script and answers in that same language, using English only as the internal search/reasoning language. The output language follows each message independently — an English question gets an English answer even if your previous question was in Korean. Language metadata is not stored in the generated Exhibition file, and the answer cache is keyed by output language so you never get a stale-language cached answer.

**L3 Constraints & Garbage Collection (GC)**:
- An L4 Exhibition is **only generated** if there are matching **L3 Concepts**. If no L3 Concepts match the query, the system skips L4 generation and returns an immediate answer.
- Ephemeral L4 Exhibitions generated during Vault sessions are marked with `ephemeral: true` and are automatically deleted (Garbage Collected) by `wiki lint` after 24 hours to prevent vault pollution.

The system **instantly activates the pipeline to synthesize the final answer** at the moment you run `wiki query` or interact with an agent (`curator_query` / `search_curator`).

> [!TIP]
> **"Just use it. the system handles the rest."**
> Curation is triggered when an "intent" to use knowledge occurs, so you don't have to specify which workspace it is or manually run the pipeline every time. (The system automatically understands the context through the folder location where you run the command.)

### (Reference) Advanced Manual Forced Curation
Use this only for debugging, workspace-agent recovery, or when a forced update is required. `wiki curate` remains directly callable but is hidden from the default `wiki --help` surface because normal users should usually query or use the workspace agent instead of manually generating L4 Exhibitions.
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

Incurator has two persona layers, each operating at a different level of the system.

### Curator Persona — Vault Level

Set during `wiki init` through a short interview. Stored in `.curator/config.yml` and applied globally across `wiki sync` and `wiki query`.
The interview labels whether each question is single-select or multi-select.
Verification sources and artifact types may be answered with comma-separated
numbers; the saved persona keeps canonical English fields.

```bash
wiki persona              # Show the current Curator persona
wiki persona update       # Re-run the interview to update it
```

If you skip the interview, a default STEM persona is applied.

> [!IMPORTANT]
> **The Curator persona defines the vault's expert identity.** If you want a fundamentally different expert perspective (e.g., STEM researcher vs. Chef), create a separate vault rather than changing the Curator persona.

### Artist Persona — Workspace Level

Set automatically by the `wiki workspace init` wizard and stored in the `persona:` block of `curate.yml`. It overrides the Curator persona for that specific project, letting you control `exhibition_intent`, confidence thresholds, and disambiguation keywords per workspace.

```bash
wiki persona update --workspace <name>   # Update the Artist persona via interview
```

Or update it from within a chat session via the `curator_update_artist_persona` MCP tool.

→ For the full `persona:` field reference, see the [`curate.yml` section above](#curateyml--workspace-configuration-reference).

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
| `wiki add <file>` | Registers sources and compiles instant L1 Contexts (structural, no LLM) directly into the database. | Adding new information |
| `wiki build` | Compiles L2 Atoms + L3 Concepts from registered L1 Contexts into the database. Uses the configured LLM for high-quality extraction and can fall back to deterministic L3 Concepts if the provider fails. Queues to the background worker by default; `--wait` runs now. | Deep knowledge-graph construction |
| `wiki source ls` | Lists all registered sources. | Checking collected data inventory |
| `wiki source show <id>` | Shows details and processing status for a specific source. | Diagnosing source errors |
| `wiki source rm <id>` | Removes a source registration and its generated L1 nodes. | Removing an incorrect source |
| `wiki source retry <id>` | Reprocesses a failed source. | Retrying after a processing failure |

### 2-1. Settings & LLM Backend Management

| Command | Description |
| :--- | :--- |
| `wiki config provider` | Interactively configure the LLM backend (Ollama / Claude Code / Antigravity / Codex / DeepSeek) and model. |
| `wiki config models list` | Show available models for the current backend. |
| `wiki config models use <tag>` | Directly set the model to use. |
| `wiki config get <key>` | Read a specific config value. (e.g. `wiki config get llm.primary`) |
| `wiki config set <key> <value>` | Update a specific config value. (e.g. `wiki config set llm.model gemini-3.5-flash`) |
| `wiki config secret list/delete` | Inspect masked local encrypted backend secrets or delete a stored secret. |

### 3. Refinement & Optimization
| Command | Description | When to use |
| :--- | :--- | :--- |
| `wiki curate` | Synthesizes L4 Exhibitions. Hidden from default help. | Advanced/debug workspace curation |
| `wiki sync` | Verifies integrity and performs self-healing. | Restoring consistency after edits |
| `wiki refresh` | Refreshes L4 Exhibitions from updated L3 Concepts without replacing human/agent edits. | Propagating new Concepts into existing Exhibitions |

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

> [!TIP]
> When a provider reports quota, rate-limit, or capacity exhaustion, Incurator surfaces the error explicitly and fails over to the configured Fallback backend instead of accepting an empty LLM answer. The Obsidian sidechat also renders these failures as quota/capacity messages so you can switch provider/model or wait for reset.

#### Supported Provider List
| Provider | Type | Key Features |
| :--- | :--- | :--- |
| `ollama` | Local | Use local models like DeepSeek or Llama 3 (Free, offline capable) |
| `antigravity-cli` | CLI | Inference via Google Antigravity CLI (`agy`) (Fast, reliable free option). Also exposes Claude / GPT-OSS models alongside Gemini 3.5 Flash / 3.1 Pro |
| `claude-code` | CLI | Inference via official Anthropic `claude` command (Sonnet 4.6 / Opus 4.7 / Haiku 4.5) |
| `codex-cli` | CLI | Inference via official OpenAI `codex` command (GPT-5.5 / 5.4 / 5.4-mini / 5.3-codex / 5.2) |
| `deepseek-api` | API key | Inference via DeepSeek's OpenAI-compatible API (`DEEPSEEK_API_KEY` or an encrypted local backend secret; current models `deepseek-v4-flash` / `deepseek-v4-pro`) |

```bash
# Set up both Primary and Fallback at once via the wizard
wiki config provider
```

#### Reasoning Effort

After choosing a model you can also pick a **reasoning effort**, which maps 1:1 to each CLI's thinking-depth option:

- `claude-code` → `claude --effort <low|medium|high|xhigh|max>`
- `codex-cli` → `codex -c model_reasoning_effort=<low|medium|high|xhigh>`
- `antigravity-cli` → `agy` has no flag, so the chosen effort is passed as a prompt hint (best-effort).

The wizard only shows the efforts a model actually supports (e.g. Gemini 3.1 Pro offers `low`/`high`); models with a single effort are auto-selected. You can also set it directly:

```bash
# Set Primary to GPT-5.5 with high effort
wiki config provider --primary codex-cli --model gpt-5.5 --effort high
wiki config provider --primary deepseek-api --model deepseek-v4-flash
wiki config provider --primary deepseek-api --model deepseek-v4-pro --api-key-env DEEPSEEK_API_KEY
```

For DeepSeek, `--api-key-env` must be an environment variable name (for example
`DEEPSEEK_API_KEY`), not the raw `sk-...` key value.
Passing `--api-key sk-...` stores the key in the backend's encrypted local
secret store outside the shared vault and writes only a secret reference into
config.

The choice is stored as `llm.primary_effort` / `llm.fallback_effort` in `.curator/config.yml`; leaving it empty uses each CLI's default effort.

CLI-backed providers (`antigravity-cli`, `claude-code`, `codex-cli`) use the
account currently logged into that CLI on the machine running the backend.
If you need a different account, switch it in the provider CLI itself
(`agy`, `claude`, or `codex login`). DeepSeek is different: it uses an API key
from `DEEPSEEK_API_KEY`, an encrypted local `llm.deepseek-api.api_key_secret`,
or a legacy plaintext `llm.deepseek-api.api_key`, so account selection is
controlled by the key rather than a browser-login CLI session. Newly stored keys
should use the encrypted local secret path to avoid syncing secrets through the
vault.

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

If the latest sync report has findings, `wiki status` may ask whether to show
review details. Those details are integrity findings to inspect or repair; they
are not a runtime error from the status command itself.
If the state DB file exists but is missing base tables, `wiki status` now
bootstraps the schema automatically before reading stats.

This command aggregates and outputs data from three main areas in real-time. Here is the meaning and practical use of each item:

### 3-1. Reset Generated State (`wiki reset`)

```bash
wiki reset
wiki reset --force
```

Resets generated Curator state while preserving `.curator/config.yml` and the
vault's source folders. It removes the tracking database, generated Collections,
dashboard/index/overview/ledger/log files, sync reports, transient staging files,
build trace canvases, device registry, and sidechat session state. Use this when
stale generated state, stale device metadata, or old chat context is causing the
backend or plugin to disagree with the current vault.

#### ⚙️ System Configuration (Config)
Verifies if the system's 'brain' and 'eyes' are correctly set up.
-   **Primary / Fallback Models**: Shows the main LLM and the emergency fallback LLM currently responsible for knowledge extraction and synthesis. Ensure the intended models are active.
-   **Reranking**: Indicates whether the secondary verification process to improve search precision is enabled. This should be `on` for high-quality answers.
-   **QMD binary**: The status of the core search engine binary. If it's not `installed` or is `not found`, you may need to run `wiki reindex` or reinstall.
-   **Search index degradation**: `wiki reindex` first updates the BM25 index, then attempts vector embeddings. If embeddings fail, BM25 search remains current while vector search is marked stale; run `qmd doctor` and retry `wiki reindex` after embedding support is healthy.

#### 📂 Knowledge Source Status (Sources)
Checks the 'entrance of the pipeline' where raw data is turned into knowledge.
-   **Raw source files**: The total number of files physically present in the vault folders.
-   **Sources summarized (L1)**: The number of sources with `l1_status=done`. `wiki add` creates a structural L1 Context immediately without an LLM call. The L1 page includes an English source guide for search plus size-aware source sections: raw text is inline for small/medium documents, while large documents keep previews and fetch exact evidence from the original source on demand. L2/L3 extraction is a separate step — run `wiki build` (queues to the background worker by default, or `--wait` to run synchronously).
-   **Ingest runs**: The total number of ingestion runs performed. A higher number indicates that the knowledge base has been updated frequently.

#### 🧠 Knowledge Density (Collections)
Shows the processing status at each pipeline stage. In the v0.2.1 default flow, L1 is created immediately, L2/L3 are processed by the MCP background worker or `wiki jobs run`, and L4 is generated by workspace-agent flows or the hidden advanced `wiki curate` command. Use `wiki jobs cancel <id>` to cancel a queued job before a worker claims it, and `wiki jobs rerun <id>` to requeue a completed, failed, or cancelled job.

-   **L1 Contexts**: One source context record per source in the DB.
-   **L2 Atoms**: Atomic facts extracted from each source in the DB.
-   **Fallback Atoms**: DB records for low-confidence fallback atoms.
-   **L3 Concepts**: Cross-source clusters formed from L2 atoms, stored as DB relations.
-   **L4 Exhibitions**: Exhibits synthesized per workspace spec (`curate.yml`) and generated as Markdown files.

> [!TIP]
> **Pipeline Status Diagnosis**: If L4 is 0, no workspace Exhibition has been generated yet. Calling `search_curator` via MCP can trigger workspace curation and create L4. Manual `wiki curate` remains available for advanced/debug use, but it is hidden from the default help surface.
