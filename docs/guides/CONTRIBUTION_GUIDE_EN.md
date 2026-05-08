# 🛠 incurator Contribution & Development Guide

This guide is for developers who want to contribute to the incurator project. It covers the current technical architecture, open challenges, and how to set up the development environment (Testbed) safely. For the system's design philosophy and differentiators, see [Project Philosophy (about.md)](../philosophy/about_EN.md).

---

## 1. Current Architecture: Knowledge Refinement Engine (Curator as Compiler)

incurator treats a personal knowledge base not as a "searchable pile of files" but as a verifiable knowledge DAG. From the start, this DAG was designed to be closer to a **machine-readable intermediate representation (IR)** that LLMs can reliably parse and reason over, rather than human-readable prose.

The Curator is a **compiler-inspired pipeline** that builds L1–L4 DAG nodes from source truth and agent interactions, then uses `wiki sync` to verify structural and logical consistency.

- **LLM-readable IR**: Context, Atom, Concept, and Exhibition are hierarchical IR layers. Each layer prioritizes stable frontmatter, relations, and provenance over human-readable prose.
- **Forward pass**: `wiki add` and `wiki curate` stack source/workspace inputs into a L1–L4 DAG.
- **Backward pass**: `wiki sync` walks the DAG in reverse to find structural, grounding, and logical gaps — and safely repairs what it can.
- **Feedback signal**: When a human edits a Context, Concept, or Exhibition, or when an agent surfaces new requirements, the diff becomes the signal that drives the next sync and re-generation cycle.

This architecture emerged from three constraints: LLM outputs can drift, knowledge nodes depend on each other, and human edits must propagate back through the entire DAG.

---

## 2. Roadmap & Current Challenges

The core challenge is evolving the Curator toward a true compiler — treating the LLM-generated knowledge DAG not as a static artifact but as a compiled output (IR) that supports inspection, optimization, incremental rebuild, and feedback incorporation.

### 🔑 Top Priority

- **`wiki add` performance**: Document registration and layer generation (L1–L3) is currently slow. Parallelizing this step or optimizing prompts is the most urgent improvement.
- **Source code ingestion**: Currently only document-based knowledge extraction is supported. Parsing source code (Python, TypeScript, C++, etc.) to extract logical structure, function dependencies, and algorithms as L2/L3 nodes would make incurator a strong tool for developer knowledge bases.

### 🧠 Intelligence & Pipeline Quality

- **Model benchmarking**: Curation must work well on small models. Measure the reasoning level required per layer and develop fallback strategies accordingly.
- **Generation vs. verification prompt separation**: Generation prompts should produce a wide set of good candidates; sync prompts should strictly verify logical equivalence, contradictions, merge candidates, and grounding.
- **Orchestration**: L1–L4 generation, sync backprop, workspace curation, and query sessions need a unified execution policy.

### 🏗 Architecture & State

- **Unified knowledge engine**: The `qmd` search index and Curator DB must agree on the same truth. Search results, DAG provenance, and sync reports should never diverge.
- **Sync-friendly state management**: SQLite (`state.sqlite`) is vulnerable to file-lock conflicts during multi-device sync. Long-term, a more sync-friendly state layer is needed.
- **Reproducible testbed validation**: `wiki add`, `wiki sync`, `wiki curate`, and MCP flows must be repeatedly verifiable against private fixtures.

### 🛠 User Experience & Tooling

- **Workspace setup automation**: Writing `curate.yml` and provisioning agent rules should be easier.
- **Visibility**: Users should be able to understand which layers are clean, fixed, or need review from `wiki status` and sync reports alone.
- **Testbed Validation Advancement**: A dedicated `wiki testbed run` command is needed to automatically execute scenarios defined in `dialogues/`, comparing expected results against actual DAG states to generate regression reports.
- **Learning curve**: Compiler-like concepts (forward/backward pass, layer status) need to be explained intuitively in the CLI and docs.

### 📂 Input Coverage

- **Parser expansion**: Images, PDFs, research materials, and specialist formats that aren't yet parsed need to be reliably lifted into L1 Contexts.

---

## 3. Development Environment: Testbed Pattern

The Testbed is an independent, reproducible environment for verifying incurator's behavior without affecting the actual vault.

Testbed sources may include personal notes, workspace directives, research files, and unpublished agent conversations. Do not include such material in public commits.

For a detailed guide on building and automating testbed environments, see [DEV_SCRIPTS_SPEC.md](DEV_SCRIPTS_SPEC.md).

**Testbed commands:**

```bash
# List available scenarios
wiki testbed list

# Initialize a specific scenario (default: testbed_template)
# Optional: --llm <provider> --model <model_name>
wiki testbed init <scenario_name> --force
```

### Core Philosophy: Private Stage Fixture

A testbed should start from a **private stage fixture** — a curated set of source files (L0) representing a specific domain or problem set — rather than an empty folder. The fixture itself is excluded from Git; only the abstracted testbed patterns and reusable helper code are made public.

**Success criteria:**

- **Reproducible**: Running the generation script produces exactly the same vault state every time.
- **Isolated**: `WIKI_ROOT` env var prevents any interference with the main vault.
- **Verifiable**: Contains enough complexity to test L1→L3 transitions and cross-source concept merging.
>
> [!TIP]
> **Practical Validation Cases & Workflows**
> During development, you can use the following private validation cases to verify system utility. To build these validation cases yourself, follow the **scenario creation guide in [DEV_SCRIPTS_SPEC.md](file:///home/shin/Workspace/incurator/docs/guides/DEV_SCRIPTS_SPEC.md)**.
> - **Domain Isolation & Merge Testing**: Input a pair of related concepts (e.g., a PDF paper + an analysis note of that paper) along with one piece of knowledge from a completely different domain. Verify that the system naturally groups related knowledge into a **Concept (L3)** while clearly isolating unrelated knowledge.
> - **Workspace-Based Real-World Verification**: Add an active project workspace to the Testbed to simulate a real-world environment. For example, intentionally omit a key insight from the raw data and then ask about it via the MCP server. Verify the pipeline's completeness by ensuring the system recognizes the missing information and prompts a Curator update to supplement or correct the knowledge base.
>
> [!IMPORTANT]
> **Early Development Environment & Logic Warning**
> incurator is in its early stages, and all experiments and validations were conducted by the developer using the **antigravity** agent environment. As a result, some internal logic may be unintentionally tailored to that specific environment. **If you encounter issues in other agents or IDEs, we highly encourage contributions that generalize these environment-specific logic parts.**

---

## 4. Testbed Directory Structure

```text
testbed/
├── 01_Workspaces/       # Agent rules and workspace context
│   └── <Workspace_Name>/
│       ├── .agents/      # Rules for general coding agents
│       └── .antigravity/ # Rules for Antigravity/Gemini agents
├── 02_Wiki/             # (Optional) Human-approved prior knowledge
├── 03_Notes/            # Human-authored source truth (primary input)
│   ├── Papers/
│   └── <Topic>/
├── 04_Resources/        # External reference metadata
├── 05_Assets/           # Images, PDFs, binary data
└── .curator/            # System internals (initialized via CLI)
    ├── Collections/     # Generated DAG (L1–L4)
    ├── config.yml       # Testbed-specific LLM and path config
    └── state.sqlite     # Provenance and hash tracking
```

---

## 5. Scenario Implementation & Validation Workflow

When creating and executing a new validation scenario, follow these standard 4 steps. For detailed instructions, see the [Scenario Creation Guide](file:///home/shin/Workspace/incurator/docs/guides/DEV_SCRIPTS_SPEC.md).

1. **Scenario Scaffolding**: Create a new scenario folder under `scripts/dev/` and write a `MASTER_PLAN.md`.
2. **Data Seeding**: Place anonymized source files into the `stage/` directory.
3. **System Initialization**: Build the test-only vault using `wiki testbed init <name> --force`.
4. **Automation Dialogue Creation**: Write and execute scripts in `dialogues/` to automate the verification logic.

---

## 6. Submission Checklist

- [ ] Run `ruff check src/` and `mypy src/`.
- [ ] Run `pytest`.
- [ ] Verify changes in the `testbed/` vault using `wiki testbed init <scenario> --force`.
- [ ] Ensure `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` are synchronized.
