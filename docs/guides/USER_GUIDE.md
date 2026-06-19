# 📖 User Guide: Master the Incurator

This guide provides technical details on how to operate the **Curator Engine** and manage your knowledge DAG. For the design philosophy and motivation behind the system, see [Project Philosophy](../philosophy/ABOUT.md). For a feature overview, see the [README](../README.md).

---

## 📋 Prerequisites

Before installing the system, ensure the following tools are installed:

1.  **Python 3.10+**: The core logic is written in Python.
2.  **Terminal**: All commands are executed within a CLI environment.
3.  **Note Editor (Obsidian Recommended)**: The primary tool for visualizing and editing your knowledge base. While any text editor that supports Markdown can be used, the system is optimized for Obsidian's link structure and plugin ecosystem.
4.  **Node.js**: Required for building the Obsidian plugin and plugin development tooling. (Note: `./setup.sh` handles the installation of Node.js, Ollama, and the backend package automatically, while `wiki init` handles the plugin installation.)
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
>   - Local search defaults use Qwen3 0.6B embedding and reranker GGUFs through `llama-cpp-python` (about 1.28GB of model files before runtime overhead). Incurator unloads configured Ollama LLM models before loading these search models to reduce VRAM pressure.
>   - **When using a Local Model (Ollama) for chat/curation**: Additional VRAM is required based on the model size (e.g., ~10GB total for an 8B model, a margin of at least 2GB over the model size is recommended).
>   - **When using a Cloud Model (Antigravity, Claude, etc.)**: local VRAM pressure is lower, but DB-native FTS5 search still runs locally.
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
-   **Integrity Verification**: Run `wiki sync` to verify structural and logical integrity and apply supported repairs. Do not manually edit generated files under `.curator/Collections/`; they are disposable projections, not an input channel for DB changes.
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
│       └── 04_Synthesis/   # [L4] Shared corpus-wide synthesis nodes (SYN-, derived projection)
├── .gitignore         # Git ignore rules (auto-generated)
└── .stignore          # Syncthing ignore rules (auto-generated)
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

### 4. Use Knowledge (Query) & Curation
When you ask a question, the system answers through the dynamic **Curation lens**
over the refined DAG (L1–L4). There is no per-workspace Exhibition file to
generate; the shared **L4 Synthesis** layer is built automatically by `wiki build`,
and curation selects/recombines L3/L4 nodes at query time (never stored).

> [!IMPORTANT]
> **Trigger-based Auto-sync**:
> This automation is not a persistent background service. It is triggered at the **moment** you interact with an agent (`search_curator`) or run `wiki query` from a **registered workspace directory** (see [Initialization](#🏗️-creating-and-initializing-a-workspace)). The system checks for pending sources and processes them immediately when it detects your "intent" to use knowledge. This ensures the pipeline works organically without manual execution. See the [MCP User Guide](./MCP_USER_GUIDE.md) for details.

To refine the knowledge graph (L2 Atoms → L3 Concepts → shared L4 Synthesis):
```bash
wiki build
```
- **L4 Synthesis**: corpus-wide, cross-cutting insights distilled from the community reports — shared and workspace-independent.

> [!TIP]
> **One-shot update**: instead of running `wiki add`, `wiki build`, and
> `wiki sync` by hand, run `wiki update` to do the whole pipeline
> (discover → L1 → L2/L3 → vector embeddings → verification) synchronously in a
> single step.

---

---

## 📚 Knowledge Ingestion

Once your vault's physical structure is ready, it's time to inject your fragmented knowledge into the system.

Incurator's ingestion process consists of two stages: **Organizing files (Organize)** and **Summarizing and refining them into knowledge layers (L1–L4) (Ingest)**. The data collected here becomes shared Synthesis and is selected by the dynamic workspace/query lens when you use it.

### Step 1: Organize Files
First, place your original files (PDF, Markdown, HTML, images, etc.) into the appropriate folders within the vault based on their nature.
- `03_Notes/`: Your own notes and thoughts.
- `04_Resources/`: External papers, articles, and literature.
- `05_Assets/`: Attached images or data files.

### Step 2: Register Structural Knowledge (L1)
Once the files are organized, command the Curator to register their structural L1 context.

```bash
# Register a specific file within the vault
wiki add 03_Notes/my_note.md

# Omit the argument to scan the entire vault and register all changes at once
wiki add
```

With this command, the Curator parses the raw data and immediately records structural L1 state in `state.sqlite`. L1 adds an English `Source Guide` with section/page previews for quick recall, inlines raw `Source Sections` for small/medium documents, and uses on-demand raw-source reads for large documents. It also emits a derived CTX Markdown projection under `.curator/Collections/01_Contexts/` for inspection. That projection is disposable; the DB remains authoritative. Run `wiki build` separately to queue or compile L2 Atomic Facts and L3 Concepts.

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
- Re-referencing the same external document never creates a duplicate stub. The
  backend keys each reference by its stable `logical_source_id` (for Zotero,
  `zotero:<attachmentKey>`) and reuses the existing stub — even if the
  `state.sqlite` row was lost and only the stub file survives on disk, so you no
  longer see a `<name>-2.md` twin appear under `04_Resources/References/`.
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
# Controls how the Curator scopes and ranks dynamic curation for this project.
persona:
  domain: ""               # e.g. "computer-vision", "biochemistry"
  subdomain: ""            # more specific focus area
  goal: ""                 # 2-4 sentences describing the curation goal
  output_intent: "engineer"      # researcher | engineer | learner
  disambiguation_keywords: []    # workspace-specific terms to boost
  confidence:
    high_threshold: 0.85   # evidence above this → high confidence
    low_threshold: 0.55    # evidence below this → HITL review queue
  updated_at: ""

# Source selection — fnmatch globs relative to vault root.
# Empty include list = draw from all vault sources.
sources:
  include: []
  #  - "03_Notes/**"
  #  - "02_Wiki/my-topic/**"
  exclude: []

# Minimum confidence floor for curation/search results.
min_confidence: 0.60
```

> **v0.3.1**: the old anchor field was removed — there is no frozen
> per-workspace generated file. `curate.yml` now drives the dynamic Curation lens that
> biases query-time retrieval over the shared DAG.

**Key fields:**

| Field | Purpose |
| ----- | ------- |
| `persona.output_intent` | `researcher` — next hypotheses to validate; `engineer` — implementation steps; `learner` — concepts to review |
| `persona.confidence` | Per-workspace confidence thresholds, overriding vault-wide defaults |
| `sources.include` | Limit which vault files feed this workspace (empty = all) |
| `min_confidence` | Confidence floor applied by the curation lens / `search_curator` |

> [!TIP]
> The `persona:` block is generated automatically by the Artist persona wizard that runs during `wiki workspace init`. You can update it later with `wiki persona update --workspace <name>` or via the `curator_update_artist_persona` MCP tool.

Both the vault and workspaces are now ready. Let's see how the Curator answers your questions and collaborates with agents.

---

## 🔍 Knowledge Utilization & Curation

Now you can obtain answers or perform the final synthesis for agent consumption.

### Querying With The Dynamic Curation Lens
This is the core operational mode of Incurator. You just need to ask or converse.

Querying is **sessionless** and the same whether you are in a Workspace or the
Vault — it returns an answer + a `QTR-` trace and writes **no** vault file:
- **Workspace query**: when a `curate.yml` is in scope, its persona/KRS biases the
  Curation lens (which evidence is selected and how it is ranked).
- **Vault query**: a plain chat whose active note is not inside a workspace folder
  resolves to `default` with no KRS bias — it never binds an arbitrary project
  workspace you never opened.

**Per-request language**: The agent detects each question's language fresh (Korean, English, Chinese, Japanese, Russian, …) by Unicode script and answers in that same language, using English only as the internal search/reasoning language. The output language follows each message independently — an English question gets an English answer even if your previous question was in Korean. Language metadata is response/trace-only and is never persisted.

`wiki query` and `curator_query` read the currently compiled DAG and synthesize a sessionless answer with a `QTR-` trace. `search_curator` returns retrieval results without answer synthesis. Queries do not register sources, run pending L2/L3 jobs, or write a frozen Exhibition file; use `wiki add` and `wiki build` explicitly to update the compiled DAG.

> [!TIP]
> The active workspace path determines whether a `curate.yml` KRS biases the
> query. Outside a workspace, the query uses the `default` vault scope.

### Agent Context Packs (Plan F target)

For agents that perform their own reasoning, `curator_fetch_context` returns a
normalized context pack instead of an answer. The pack has one `QTR-*` root trace,
one attached `RTR-*` retrieval execution, a reproducible snapshot id, explicit
budget accounting, source locators, omission reasons, and expansion/verification
handles. Future `wiki query` synthesis uses the exact same pack rather than
running a separate retrieval path.

### Promoting an answer to durable knowledge
A query answer is not stored. To keep one, promote it into `02_Wiki/` (the
human-curated space) — via the plugin's promote action or the MCP
`curator_promote_insight` tool. Promotion writes only `02_Wiki/`; source truth
(`03_Notes/`, `04_Resources/`) is never touched.

---

## 🔄 Feedback Loop & Integrity Review (HITL & Sync)

Knowledge is refined incrementally through dialogue and correction.

1.  **Synthesis**: Derive new insights by engaging in dialogue with the agent in your workspace.
2.  **Feedback & Correction**: If you discover errors in prior knowledge, submit a classified correction proposal with MCP tools. Proposals do not overwrite generated nodes automatically.
3.  **Integrity Review**: Apply any approved follow-up change through its reviewed workflow, then run `wiki sync` to verify structural and logical integrity.
4.  **Promotion**: Move finalized insights to `02_Wiki/` to promote them to human-readable wikis.
5.  **Loop**: Promoted wikis are recognized as new sources in the next cycle, allowing knowledge to grow **incrementally**.

This circular flow ensures that your knowledge never stays stagnant but keeps evolving through interaction and verification.

---

## 🧾 Claim-Level Support & Compiler Integrity (v0.8.0)

From v0.8.0, every source-supported knowledge unit (L2 claim) carries an
explicit **support status** instead of being trusted just because it cites a
real span id:

| `support_status` | Meaning |
| :--- | :--- |
| `verified` | At least one verified minimal support record exists and its evidence hash matches the current source text. |
| `unchecked` | Built before v0.8.0 (or not yet validated). Visible to you, but no longer fed into new compilation until re-validated. |
| `failed` | Validation found the cited spans do not actually support the claim. Excluded from downstream knowledge. |
| `stale` | The source text behind the claim changed since verification. Excluded until re-validated. |

What this means in practice:

- **Upgrading is safe and honest**: the v0.8.0 migration marks all your
  existing claims `unchecked` — nothing is silently promoted to "verified".
  A normal `wiki build` re-compiles them under the new contract.
- **Formulas are first-class**: a claim that depends on a central formula
  either keeps the formula intact in its text or links the exact formula
  evidence. Distillation that silently drops a formula present in the source
  extraction is treated as a defect, not a summary choice.
- **No partial builds**: a compile that fails midway publishes nothing — your
  previous knowledge, projections, and search index keep serving untouched.
  Re-running an unchanged build does not duplicate or mutate anything.
- **Source edits clean up after themselves**: editing, deleting, or splitting
  a source retires the claims that lost their basis (they remain auditable but
  stop appearing in answers) instead of leaving stale duplicates behind.
- **`wiki lint` audits all of it**: lint gains a Compiler Integrity section
  reporting unsupported/failed/stale claims, evidence-hash mismatches, and
  formula-status problems, and exits non-zero on release-blocking findings.

---

## 🕸️ Graph Quality (v0.9.0)

v0.9.0 turns your verified claims into a trustworthy knowledge graph. It
distinguishes when two names are really the same thing, tracks how independently
a relationship is supported, and builds community summaries that stay grounded in
exact claims (specs: SCHEMA.md §21, SYSTEM_BEHAVIOR.md §27).

What this means in practice:

- **Merges are careful and reversible**: the system never silently fuses two
  entities because their names look alike. Synonyms and abbreviations merge only
  after safety checks; ambiguous names (homonyms) are left separate until
  decided. Any accepted merge can be undone exactly, restoring the original
  entities and every relationship.
- **Support is counted honestly**: a relationship backed by ten copies of the
  same source counts as one independent confirmation, not ten. Re-running a build
  accumulates genuine support instead of overwriting it.
- **Community reports need corroboration (≥2 independent sources)**: a
  relationship becomes *active* — eligible to ground a community report — only
  once **two genuinely independent sources** assert it. A claim found in just one
  source (however many times it is re-stated there) stays uncorroborated and does
  not yet build a community. In practice this means a vault with a single source
  per topic produces few or no community reports until a second independent source
  corroborates the same relationships; this is intentional — Plan C reports are
  grounded only on cross-source–confirmed facts.
- **Weak edges are quarantined, not hidden**: self-loops, contradictions,
  unsupported edges, and risky "bridge" links are set aside with a stated reason
  and a condition for re-admission — they never quietly shape your community
  summaries. Only fully supported relations build communities.
- **Stable, explainable communities**: the same graph produces the same
  community hierarchy every time. Community reports cite exact supporting claims;
  the old "summarize the whole cluster" fallback is gone, and outdated reports
  retire and regenerate when their inputs change.
- **`wiki lint` audits the graph too**: lint gains a Graph Quality section that
  flags references to merged-away entities, unsupported active relations,
  unresolved endpoints, ungrounded report findings, and any homonym false merge,
  exiting non-zero on release-blocking findings.

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

Set automatically by the `wiki workspace init` wizard and stored in the `persona:` block of `curate.yml`. It overrides the Curator persona for that specific project, letting you control `output_intent`, confidence thresholds, and disambiguation keywords per workspace.

```bash
wiki persona update --workspace <name>   # Update the Artist persona via interview
```

Or update it from within a chat session via the `curator_update_artist_persona` MCP tool.

→ For the full `persona:` field reference, see the [`curate.yml` section above](#curateyml--workspace-configuration-reference).

---

## 🐙 Git Integration

Incurator can inspect an already Git-managed vault from Obsidian and expose the
common Git workflow through sidechat. This is designed for vaults that already
use Git and may already have scheduled commits. It uses your existing local
`git` only — there is **no GitHub CLI (`gh`) dependency** and the plugin stores
no GitHub tokens. (If you push over HTTPS, your normal git credential helper
handles authentication, outside the plugin.) The plugin does not add a manual
Commit/Push button cluster.

### Conversational Git Sync (Sidechat)

Sidechat can run deterministic backend Git commands for the active vault:

- **Status**: ask *"Are there any unpushed changes?"* or *"What's the GitHub
  status?"* to summarize branch, upstream, ahead/behind, dirty files, and
  `.curator/` ignore warnings.
- **Push**: ask *"push해줘"* or *"Push this vault to GitHub."* The backend runs
  `git push` only when the branch has an upstream and is not behind/diverged.
- **History for selected text**: select Markdown text and ask *"이 내용 예전에
  어떻게 바뀌었는지 히스토리 찾아줘."* The backend searches git history for the
  selected text or a normalized excerpt in the active Markdown file and returns
  matching commits with capped patch snippets.
- **File history**: ask for the active Markdown file's history to get recent
  commits and summaries.

Scheduled commit jobs remain compatible with this flow. Incurator's sidechat
does not need to create commits before pushing when your scheduler already does
that. A guarded commit backend primitive may exist for explicit requests, but
the default conversational workflow is status/history/push.

> [!TIP]
> **.gitignore Best Practices**
> Git decides what is tracked. Incurator stages or inspects files according to
> `.gitignore`; ignored files are not added. `.curator/` should be ignored
> because it contains generated SQLite databases and vector/search indexes. If
> `.curator/` is not ignored, the Git status result warns you instead of
> silently editing `.gitignore`.

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
| `wiki update` | **One-shot pipeline**: runs `add` → `build --wait` → vector embeddings → `sync` synchronously, bringing the whole vault up to date in a single command. Use `--force` to rebuild existing layers and `--no-sync` to skip the final verification. | The everyday "just make it current" command |
| `wiki add <file>` | Registers sources and compiles instant L1 Contexts (structural, no LLM) directly into the database. | Adding new information |
| `wiki build` | Compiles L2 Atoms + L3 Concepts from registered L1 Contexts into the database. Uses the configured LLM for high-quality extraction and can fall back to deterministic L3 Concepts if the provider fails. By default it queues jobs and starts a detached background daemon; `--wait` runs synchronously. Build **always (re)generates vector embeddings** when it finishes — even when no atoms changed or the queue was already empty — so search converges to vector-ready without a separate `wiki reindex --embed`. (The queue is drained internally; the `jobs` command group still exists for the background worker but is hidden from `wiki --help`.) | Deep knowledge-graph construction |
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
| `wiki models ensure` | Install/refresh local search model dependencies and GGUF files. `setup.sh` runs this automatically unless `INCURATOR_SKIP_MODELS=1` is set. |
| `wiki models status` | Show local search model health, cache paths, and dependency status as JSON. |
| `wiki config get <key>` | Read a specific config value. (e.g. `wiki config get llm.primary`) |
| `wiki config set <key> <value>` | Update a specific config value. Machine-local keys such as `llm.*`, `search.*`, and `external.*` write to `.cache/config/config.yml`; pass `--local` only for portable vault-scoped keys that belong in `.curator/config.yml`. |
| `wiki config secret list/delete` | Inspect masked local encrypted backend secrets or delete a stored secret. |

### 3. Refinement & Optimization
| Command | Description | When to use |
| :--- | :--- | :--- |
| `wiki build` | Refines L2 Atoms, L3 Concepts, and the shared L4 Synthesis layer. | Building/refreshing the knowledge graph |
| `wiki sync` | Verifies integrity and performs self-healing. | Restoring consistency after edits |
| `wiki sync --reemit` | Re-emits the derived L2/L3/L4 markdown projection (ATM/CON/SYN) from the authoritative DB records and refreshes DB-native search rows. | Refreshing projections after DB-level corrections |
| `wiki reindex` | Rebuilds the DB-native search index (FTS5 + chunks) from the authoritative records. Add `--embed` to also (re)generate chunk vector embeddings. In normal use `wiki build` already embeds automatically, so `--embed` is mainly a manual recovery path after a model/embedder change. | After model/config changes, or if search drifts |

> **v0.3.1**: The frozen-staging commands were removed. L4 is now the shared
> **Synthesis** layer (built automatically by
> `wiki build`), and curation is a dynamic query-time lens (`wiki query`).
> Corrections flow through the MCP `curator_propose_correction` tool, not by
> editing a generated L4 file.

### 4. Knowledge Utilization
| Command | Description | When to use |
| :--- | :--- | :--- |
| `wiki query "..."` | Gets refined answers to questions. | Using curated knowledge |
| `wiki query "..." --route explore` | Routes through the v0.3.2 curation-native orchestrator (DB graph + DB-native hybrid search) with a query trace. | Discovering connections, scoped routing |
| `wiki inspect synthesis <SYN-…>` | Exports the L4-to-L1 evidence chain for a synthesis node. Add `--json` for machine-readable output. | Proving why a generated synthesis exists |
| `wiki inspect answer <QTR-…>` | Exports the evidence chain behind a recorded query trace. Add `--json` for machine-readable output. Orchestrated queries persist one authoritative QTR containing their retrieval trace. | Auditing an answer from Sources & Trace |
| `wiki workspace init` | Initializes a workspace. | Starting a new project |

#### v0.3.2 Curation-Native Query Routes

`wiki query "..." --route <route>` answers through the curation-native
`QueryOrchestrator`. Routes:

- `auto` — let the orchestrator choose (deterministic-first).
- `local` — precise entity/fact answers grounded in source spans.
- `global` — broad synthesis leading with the shared L4 Synthesis nodes, backed by community reports.
- `explore` — discover connections (memory paths) + provisional insight candidates.
- `source-section` — answer scoped to one source's spans.

Queries are **sessionless**: they return an answer + a `QTR-` trace and write no
vault file. Durable artifacts come only from an explicit promotion to `02_Wiki/`.
Every orchestrator query persists the `QTR-` trace so the answer can later be
audited with `wiki inspect answer <QTR-…>`.

Without `--route`, `auto` runs. Search is DB-native in v0.3.2: FTS5 lexical
retrieval, chunk-level vectors, typed query expansion (`lex`/`vec`/`hyde`), RRF,
and configured reranking over best chunks. `--mode` (hybrid|lex|vec) selects the
lower-level retrieval mode and is a separate axis from `--route`.

Tier-2 LLM/HyDE query expansion is enabled as a recovery mechanism by default:
Incurator first checks raw lexical/vector confidence, then uses configured
expansion only when lexical hits are thin or vector confidence is low. This keeps
high-confidence searches stable while still recovering paraphrase-heavy misses.

### 4-1. Prompts & Insights (v0.3.1)

| Command | Description |
| :--- | :--- |
| `wiki prompt list [--family F]` | List registered prompt contracts (id, version, family, purpose). |
| `wiki prompt show <PROMPT_ID>` | Show a prompt's templates, validators, and output model. |
| `wiki prompt trace <PTR-…>` | Inspect a recorded prompt run (model, validator status, hashes). |
| `wiki prompt eval` | Run the offline prompt-eval fixtures (no LLM). |
| `wiki inspect synthesis <SYN-…>` | Inspect a read-only audit report for one L4 Synthesis node, including community reports, graph entities/relations, source spans, prompt traces, and warnings. |
| `wiki inspect report <REP-…>` | Inspect the source support for one L3 community report. |
| `wiki inspect answer <QTR-…>` | Inspect the persisted route, selected evidence, prompt traces, and warnings for one query answer. |
| `wiki insight list [--workspace P] [--status pending]` | List provisional insight candidates. |
| `wiki insight show <INS-…>` | Show one insight candidate. |
| `wiki insight promote <INS-…>` | Promote a candidate to a durable `02_Wiki/` note (explicit, human-approved). |

Insight candidates are **provisional, not human truth**. Promotion writes only to
`02_Wiki/` and never edits source folders. The same capabilities are available to
external agents over MCP — see the [MCP User Guide](./MCP_USER_GUIDE.md) §3.6.

### 5. Developer Tools (Developer Only)
| Command | Description | When to use |
| :--- | :--- | :--- |
| `wiki testbed init` | Builds a virtual test vault (`testbed/`). | When you want to safely validate new features |
| `wiki testbed list` | Lists available test scenarios. | When selecting a scenario for validation |

> [!CAUTION]
> **Testbed Notice**: These commands handle temporary, development-only storage, not your actual knowledge base. Do not use them during standard knowledge management or actual project execution.

---

## 🔄 Cross-Device Knowledge Sync (`wiki db`)

Incurator stores all knowledge in `.curator/state.sqlite`. Because SQLite files cannot be safely merged by file-sync tools (Syncthing, iCloud, Dropbox), the `wiki db` commands provide a safe JSONL-based export/import pipeline for moving your knowledge between devices.

### How it works

1. **Export** your knowledge base on Device A → produces a `.jsonl` file
2. **Transfer** the file to Device B (scp, AirDrop, Syncthing, USB, etc.)
3. **Import** on Device B → records are merged using Last-Write-Wins; deleted records propagate via tombstones; `wiki reindex` runs automatically

### `wiki db export`

```bash
wiki db export                              # exports to .curator/export-YYYYMMDD.jsonl
wiki db export --out ~/Desktop/kb.jsonl     # custom output path
wiki db export --since 2026-01-01T00:00:00Z # incremental: only changed records
wiki db export --compress                   # gzip output (.jsonl.gz)
```

### `wiki db import`

```bash
wiki db import ~/Desktop/kb.jsonl          # import and auto-reindex
wiki db import ~/Desktop/kb.jsonl --dry-run # preview changes without writing
wiki db import ~/Desktop/kb.jsonl --skip-reindex  # import without reindexing
```

> [!NOTE]
> Device-local data (vector embeddings, background job state) is **never** included in export files. After import, `wiki reindex` rebuilds the local search index automatically.

### `wiki db autosync` — automatic sync over Syncthing

If you already sync your vault folder with **Syncthing**, `wiki db autosync` turns the manual export/import above into a hands-off, Zotero-grade flow.

```bash
wiki db autosync             # import peers, merge conflicts, export self if changed
wiki db autosync --dry-run   # preview without writing
```

How it stays safe across devices:

- **One file per device.** Each device writes only its own `.curator/sync/dev-<id>.jsonl` and reads everyone else's. Because no two devices write the same file, Syncthing never creates write-write conflicts.
- **Last-Write-Wins merge.** Records merge row-by-row by timestamp; deletes propagate via tombstones. Concurrent offline edits on two devices both survive — there is no whole-file overwrite.
- **No infinite loops** — without any fragile hash guard. A device never imports its own file, and it re-exports only when something actually changed.
- **Syncthing conflict files** (`*.sync-conflict-*`) are imported as ordinary peers (always data-safe) and archived under `.curator/runtime/sync_conflicts/`.

`.curator/state.sqlite` and `.curator/sync_state.json` stay device-local (excluded in `.stignore`); only the `.curator/sync/` JSONL files travel between devices. To have `wiki update` export automatically for CLI-only workflows, set `auto_sync.enabled: true` in `.curator/config.yml`. The Obsidian plugin drives `wiki db autosync` for you — see the Plugin Guide.

---

## 🧩 Configuration Management

Incurator allows you to safely and conveniently manage settings via the
`wiki config` command without manually editing YAML files. Machine-local blocks
such as `llm`, `search`, and `external` are stored in `.cache/config/config.yml`;
portable vault behavior remains in `.curator/config.yml`.

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

### 2-1. Search Model Provisioning (`wiki models`)
DB-native search uses separate local search models from the chat/curation LLM:
`llama-cpp::qwen3-embedding-0.6b` for chunk embeddings and
`llama-cpp::qwen3-reranker-0.6b` for answer-path reranking. `wiki models ensure`
downloads the configured GGUFs into `~/.cache/incurator/models/`, installs
`llama-cpp-python` when needed, and pins per-vault model paths when a vault is
available. `wiki models ensure --smoke` additionally runs a tiny live sanity
check that the embedding and reranker rank a relevant passage above an unrelated
one. Search remains usable in FTS5/RRF degraded mode if these models are missing.

You normally never run this by hand: `setup.sh` provisions on install/update, and
the Obsidian dashboard's **System** card shows the live embed/reranker model
identity + health — click the **Embed model** / **Reranker** rows to re-provision
(`wiki plugin models refresh`). To (re)build the vector index after the models are
healthy, run `wiki reindex --embed` (plain `wiki reindex` rebuilds FTS5/chunks only).
If you need a manual backend-only repair, run
`pip install -e './backend[rerank]'`. Do not run
`uv pip install -e .` from the repository root; the Python project lives in
`backend/`.

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
vault's source folders. It removes the tracking database (which includes the native search index), generated Collections,
dashboard/index/overview/ledger/log files, sync reports, transient staging files,
build trace canvases, device registry, and sidechat session state. Use this when
stale generated state, stale device metadata, or old chat context is causing the
backend or plugin to disagree with the current vault.

#### ⚙️ System Configuration (Config)
Verifies if the system's 'brain' and 'eyes' are correctly set up.
-   **Primary / Fallback Models**: Shows the main LLM and the emergency fallback LLM currently responsible for knowledge extraction and synthesis. Ensure the intended models are active.
-   **Reranking**: Indicates whether the configured search reranker is available. High-quality answers should use a real reranker/cross-encoder or validated search-fine-tuned model; RRF-only is a degraded fallback.
-   **Query expansion**: Indicates whether recovery-only Tier-2 expansion can run. If unavailable, deterministic lexical/vector expansion still runs and the trace records the degraded stage.
-   **Search readiness**: Shows DB-native FTS5 readiness, embedded chunk counts, vector readiness, provider/model, and any degraded stage.
-   **Search index degradation**: If embeddings, query expansion, or reranking are unavailable, lexical FTS5 search remains usable and the query trace records `vector_unavailable`, `query_expander_unavailable`, or `reranker_unavailable`. Run `wiki reindex` after fixing provider/model configuration to rebuild chunks and embeddings.

#### 📂 Knowledge Source Status (Sources)
Checks the 'entrance of the pipeline' where raw data is turned into knowledge.
-   **Raw source files**: The total number of files physically present in the vault folders.
-   **Sources summarized (L1)**: The number of sources with `l1_status=done`. `wiki add` creates a structural L1 Context immediately without an LLM call. The L1 page includes an English source guide for search plus size-aware source sections: raw text is inline for small/medium documents, while large documents keep previews and fetch exact evidence from the original source on demand. L2/L3 extraction is a separate step — run `wiki build` (queues jobs and automatically starts a detached background daemon to process them asynchronously, or `--wait` to run synchronously).
-   **Ingest runs**: The total number of ingestion runs performed. A higher number indicates that the knowledge base has been updated frequently.

#### 🧠 Knowledge Density (Collections)
Shows the processing status at each pipeline stage. L1 is created immediately; L2/L3 and the shared L4 Synthesis layer are processed by the MCP background worker, `wiki jobs run`, or `wiki build`. Use `wiki jobs cancel <id>` to cancel a queued job before a worker claims it, and `wiki jobs rerun <id>` to requeue a completed, failed, or cancelled job.

-   **L1 Contexts**: One source context record per source in the DB.
-   **L2 Atoms**: Atomic facts extracted from each source in the DB.
-   **Fallback Atoms**: DB records for low-confidence fallback atoms.
-   **L3 Concepts**: Cross-source clusters formed from L2 atoms, stored as DB relations.
-   **L4 Synthesis**: Shared corpus-wide cross-cutting insights distilled from the community reports (DB `synthesis_nodes`, projected to `04_Synthesis/SYN-*.md`).

> [!TIP]
> **Pipeline Status Diagnosis**: If L4 is 0, the shared Synthesis layer hasn't been built yet. Run `wiki build` (or let the background worker finish L3) to generate it.
