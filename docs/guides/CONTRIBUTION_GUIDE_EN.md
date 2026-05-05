# 🛠 InCurator Contribution & Development Guide

This guide is for developers intending to contribute to the InCurator project. it describes the technical challenges currently facing the project and how to set up a development environment (Testbed) to address them safely.

---

## 1. Current Architecture: Curator as Compiler

InCurator treats a personal knowledge base as a verifiable knowledge DAG, not just a folder of searchable files. From the beginning, this DAG was designed less as human-facing prose and more as an **LLM-readable intermediate representation (IR)** that models can parse, traverse, and reason over consistently. Today, Curator is a **compiler-inspired pipeline**: it builds the L1-L4 DAG from source truth and agent conversations, then uses `wiki sync` to trace structural and logical consistency backward.

- **LLM-readable IR**: Context, Atom, Concept, and Exhibition are layered IR for LLM reasoning. Each layer prioritizes stable frontmatter, relations, and provenance over human-facing prose.
- **Forward pass**: `wiki add` and `wiki curate` build the L1-L4 DAG from source and workspace inputs.
- **Backward pass**: `wiki sync` verifies the generated DAG in reverse, detects structural gaps, grounding gaps, and logical gaps, and repairs safe items.
- **Feedback signal**: Human edits to Contexts, Concepts, Exhibitions, or new requirements from agent dialogue become signals for sync and regeneration.

This structure evolved from a specific constraint: model output can vary, knowledge nodes depend on one another, and human edits need to propagate back into the DAG. Curator is therefore designed as a compiler-inspired pipeline, not a plain markdown generator.

- **Stable IR**: Layer schema, relations, and provenance are separated so model output variance does not pollute the entire DAG.
- **Sync as verification pass**: `wiki sync` reports structural errors like a type checker and traces grounding/logical gaps backward.
- **Affected subgraph rebuild**: When a specific L2/L3/L4 node changes, Curator focuses verification on the connected subgraph instead of blindly rebuilding everything.
- **Human feedback loop**: Human-edited Contexts, Concepts, Exhibitions, and agent dialogue become feedback signals for the next sync/curate cycle.

## 2. Project Roadmap & Current Challenges

The core challenge is to make Curator closer to a real compiler: the LLM-generated knowledge DAG should become an artifact that can be checked, optimized, incrementally rebuilt, and realigned from feedback.

The following items are the primary Future Work identified during the development of this project.

### 🔥 Top Priority
-   **`wiki add` Performance Optimization**: Currently, the speed of source registration and layer generation (L1-L3) is very slow. Revolutionizing this process—either through parallelization or prompt optimization—to drastically reduce document generation time is the most urgent priority.

### 🧠 Intelligence & Pipeline Quality
- **Model benchmarking**: The system should curate well even with smaller models, so each layer needs measured reasoning requirements and fallback strategies.
- **Prompt and verification separation**: Generation prompts should produce rich candidates; sync prompts should strictly verify equivalence, contradiction, merge candidates, and grounding.
- **Advanced orchestration**: L1-L4 generation, sync backprop, workspace curation, and query sessions need a coherent execution policy.

### 🏗 Architecture & State
- **Unified knowledge engine**: The `qmd` search index and Curator DB need to cooperate more consistently. Search results, DAG provenance, and sync reports should not disagree about the state of truth.
- **Sync-friendly state management**: SQLite (`state.sqlite`) is vulnerable to file locking and conflicts. Excluding DB files from sync is recommended for now, but a more sync-friendly state layer is a long-term need.
- **Reproducible testbed validation**: Private fixtures should repeatedly validate `wiki add`, `wiki sync`, `wiki curate`, and MCP flows.

### 🛠 User Experience & Tooling
- **Workspace provisioning automation**: Writing `curate.yml` and provisioning agent rules should become easier.
- **Better visibility**: Users should understand whether each layer is `clean`, `fixed`, or `review_needed` from `wiki status` and sync reports.
- **Lowering the learning curve**: Compiler-like pipeline concepts, forward/backward passes, and layer status need clearer CLI and documentation support.

### 📂 Input Coverage
- **Parser support expansion**: Images, PDFs, research artifacts, and specialized formats need reliable paths into L1 Contexts.

---

## 3. Development & Validation Environment: The Testbed Pattern

A testbed is a self-contained, reproducible environment used to validate InCurator behavior, agent performance, and curation logic without affecting your primary knowledge base.

### 📂 Private Fixture Pattern
Testbed source material often contains private notes, workspace instructions, research files, or unpublished agent transcripts. Keep that material outside public commits. A good private testbed setup separates these roles:

- **Creation script**: recreates a local testbed vault from private fixtures.
- **Stage fixture**: source corpus copied into the testbed, such as notes, references, assets, and workspace files.
- **Dialogue scripts**: repeatable MCP/query/curation flows that exercise expected behavior.
- **Fixture workspace rules**: dev-only agent rules for the private testbed workspace.
- **Master plan**: a short private document describing the testbed purpose, source corpus, and acceptance checks.

### Core Philosophy: The Private Stage Fixture
Instead of starting with an empty vault, a testbed should be seeded with a **private stage fixture**—a curated set of source files (L0) that represent a specific domain or problem set. The fixture itself may be ignored by Git, while the abstract testbed pattern and reusable helper code can remain public.

#### Success Criteria
- **Reproducible**: Running the creation script results in the exact same vault state every time.
- **Isolated**: Uses `WIKI_ROOT` environment variable to prevent cross-talk with the main vault.
- **Verifiable**: Contains enough complexity to test L1→L3 transitions and cross-source concept merging.

> [!TIP]
> **Real-world Validation Examples & Workflows**
> During development, the system can be validated with private cases like these:
> - **Domain Isolation & Merging**: We input a pair of related concepts (e.g., a PDF paper + its manual analysis note) and one unrelated piece of knowledge. We then verified whether the system naturally merged the related items into a **Concept (L3)** while strictly isolating the unrelated topic.
> - **Live Workspace Verification**: Integrate a workspace from an active project into the testbed to simulate a real environment. For example, intentionally remove a key insight from the raw data and then query the system about it via the MCP server. We used this to verify if the system could detect the knowledge gap and correctly update the Curator DAG to fix or supplement the missing information.

---

## 4. Abstract Directory Structure

A robust testbed follows the standard Curator topology but focuses on the `01_Workspaces`, `03_Notes`, and `04_Resources` directories as the primary "inputs."

```text
testbed/
├── 01_Workspaces/       # Agent-specific rules and workspace contexts
│   └── <Workspace_Name>/
│       ├── .agents/      # Rules for general coding agents
│       └── .antigravity/ # Rules for Antigravity/Gemini agents
├── 02_Wiki/             # (Optional) Pre-promoted human knowledge
├── 03_Notes/             # Human-authored source truth (The primary input)
│   ├── Papers/          # Summaries and notes on research
│   └── <Topic>/         # Domain-specific categorizations (Math, Vision, etc.)
├── 04_Resources/         # External reference metadata (e.g., Zotero exports)
├── 05_Assets/            # Images, PDFs, and binary data
└── .curator/             # Internal machine state (Initialized via CLI)
    ├── Collections/      # The generated DAG (L1-L4)
    ├── config.yml        # Testbed-specific LLM & path config
    └── state.sqlite      # Provenance and hash tracking
```

---

## 5. Implementation Workflow

To create a testbed, follow this automated 3-step pipeline:

### Step 1: Stage Scaffolding
Copy a private stage fixture directory into the testbed root. This fixture should contain the raw `.md` notes and resource files you want to test.

### Step 2: System Initialization
Run the equivalent of `wiki init` on the testbed directory. This creates the `.curator` infrastructure and sets up the search index.

### Step 3: Agent Rule Installation
Populate the `01_Workspaces` directory with the necessary rule files (`AGENTS.md`, `CLAUDE.md`, etc.). This ensures that agents interacting with the testbed follow the same protocol as the production environment.

---

## 6. Usage & Validation

Once created, interact with the testbed by prefixing commands with `WIKI_ROOT`:

```bash
# Verify the testbed is healthy
WIKI_ROOT=testbed wiki status

# Run the curation pipeline on the seeded notes
WIKI_ROOT=testbed wiki add "03_Notes/**/*.md"
WIKI_ROOT=testbed wiki curate

# Validate a specific claim
WIKI_ROOT=testbed wiki query "Ask a representative question for your fixture domain"
```
