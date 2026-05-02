# SYMBIOTIC_OS_ARCHITECTURE - LLM-Wiki Curator (v11.0)

**LLM-Wiki Curator** is an autonomous, AI-maintained personal knowledge base designed for the **SYMBIOTIC_OS_ARCHITECTURE v11.0**. It establishes a 4-layer directed acyclic graph (DAG) knowledge pipeline to summarize, parse, cluster, and synthesize atomic facts and high-level concepts from raw user notes and reference materials.

---

## 1. Entity Roles & Global Topology

### 1.1 Entities & Permissions
- **Entity Curator**: Residence: `.curator/`. Read access to raw spaces, write access *strictly* to `.curator/`. Performs hash monitoring, DAG construction, and semantic indexing.
- **Entity Agent**: Residence: `01_Workspaces/{Project_Name}/`. Context loader via `qmd.yml`. Reads and writes within active workspace; shallow write with HITL in `03_Notes`. Promotes concepts to `02_Wiki`.

### 1.2 Topology Map
```
ROOT: /
├── 00_System/          # [STATIC] Scripts & Templates
├── 01_Workspaces/      # [AGENT_RESIDENCE] Active projects 
│   └── {Project_Name}/
│       ├── .agents/          # Agent skills & workflow rules
│       ├── .antigravity/     # Agent control limits
│       ├── Artifacts/        # Auto-generated code, images, temp outputs
│       ├── Concepts/         # Draft concepts. Promoted to 02_Wiki upon maturity.
│       ├── Papers/           # Project-specific sandbox
│       ├── qmd.yml           # Defines which `.curator/Collections` to load
│       ├── methodology.md    # [GROUND_TRUTH] Geometric/math pipelines
│       └── todo_list.md      # Milestones & task tracking
├── 02_Wiki/            # [SHARED_TRUTH] Agent Managed Knowledge Base
├── 03_Notes/           # [HUMAN_TRUTH] 100% Human verified atomic knowledge
├── 04_Resources/       # [READ_ONLY] External reference PDFs, Docs
├── 05_Assets/          # [STATIC] System byproducts
├── 06_Archives/        # [READ_ONLY] Terminated projects & legacy data
└── .curator/           # [CURATOR_RESIDENCE] Hidden Abstraction Space
    ├── overview.md     # [ROUTING] Domain manifest
    ├── index.md        # [ROUTING] Synthesis ID -> Pointer mapping
    ├── log.md          # [STATE] Hash registry for Foundation Sources
    ├── ledger.md       # [OVERRIDE] High-priority user corrections
    └── Collections/    # [DATA_PLANE] DAG Knowledge Lake
        ├── 01_Summaries/   # L1: 1:1 Hash-matched summaries
        ├── 02_Atoms/       # L2: Irreducible facts/equations
        ├── 03_Concepts/    # L3: Clustered logic
        └── 04_Synthesis/   # L4: Terminal knowledge outputs
```

---

## 2. Polymorphic Metadata Schema

The Curator structures all knowledge within `.curator/Collections/` into 4 layers:

### Layer 1: Summary (`SUM-[UUID8]`)

A 1:1 hash-matched recap of a single source document.

```yaml
---
id: SUM-[UUID8]
type: summary
source_path: "[[relative/path/to/source.md]]"
source_hash: [SHA-256]
domain: "knowledge-domain-string"
last_updated: [YYYY-MM-DDThh:mm:ssZ]
tags: [tag1, tag2]
---
```

**Body sections**: `## Summary`, `## Key Claims`, `## Atom Candidates`, `## Source`

### Layer 2: Atom (`ATM-[UUID8]`)

Irreducible factual claims, distilled from one or more L1 summaries.

```yaml
---
id: ATM-[UUID8]
type: atom
parent_source: "[[01_Summaries/SUM-UUID8]]"
source_path: "[[relative/path/to/source.md]]"
claim_type: fact | equation | theoretical_constraint
contradicts: []
is_verified_by_human: false
is_flagged_for_agent: false
last_updated: [YYYY-MM-DDThh:mm:ssZ]
---
```

**Body sections**: `## Definition / Claim`, `## Context`, `## Constraints`, `## Relations`, `## Source`

### Layer 3: Concept (`CON-[UUID8]`)

Clusters of related L2 atoms forming a coherent conceptual unit.

```yaml
---
id: CON-[UUID8]
type: concept
dependencies: ["[[02_Atoms/ATM-UUID8]]", "[[02_Atoms/ATM-UUID8]]"]
domain: "knowledge-domain-string"
last_updated: [YYYY-MM-DDThh:mm:ssZ]
---
```

**Body sections**: `## 1. Core Architecture`, `## 2. Interaction of Atoms`, `## 3. Mathematical Framework`, `## 4. Open Questions`

### Layer 4: Synthesis (`SYN-[UUID8]`)

Terminal cross-domain knowledge outputs combining multiple L3 concepts.

```yaml
---
id: SYN-[UUID8]
type: synthesis
core_concepts: ["[[03_Concepts/CON-UUID8]]"]
confidence_score: 0.00 - 1.00
requires_math_rigor: true | false
last_updated: [YYYY-MM-DDThh:mm:ssZ]
---
```

**Body sections**: `## 1. Executive Research Brief`, `## 2. Theoretical Foundation`, `## 3. State of the Art & Limitations`, `## 4. Actionable Directives for Agent`

---

## 3. Installation & Getting Started

To install the project locally with all prerequisites (Ollama, Node.js, and the `qmd` search engine) in one command, run:

```bash
chmod +x install.sh
./install.sh
```

> [!NOTE]
> Installing Ollama on Linux requires sudo privileges when prompted by the script. Alternatively, you can install Ollama manually from [Ollama.com](https://ollama.com/download) first.

### 3.1 Initialising a Vault

To scaffold a new wiki vault project with the full topological structure:

```bash
wiki init /path/to/your/vault
```

This sets up:
* `.obsidian/` vault marker
* Full folder topologies (`00_System/` ... `06_Archives/`)
* `.curator/` configuration files, tracking database, and collections

---

## 4. Command-Line Interface (CLI)

The `wiki` CLI automates everything from file scanning to querying the DAG.

### 4.1. Core Operations
* **`wiki status`**: Inspect tracking database metrics, active LLM config, and collection counts.
* **`wiki version`**: View the current installed version.

### 4.2. File Synchronization & Summaries
* **`wiki sync`**: Discovers new or changed files in raw directories and generates L1 summaries in `.curator/Collections/01_Summaries/`.
* **`wiki sources list`**: View all tracked raw sources.
* **`wiki sources show <id>`**: Inspect file metadata and content preview.
* **`wiki sources rm <id>`**: Remove a file from tracking and delete it optionally.

### 4.3. Pipeline Ingestion
* **`wiki ingest`**: Runs the 3-pass LLM pipeline to promote L1 summaries into L2 Atoms, L3 Concepts, and L4 Synthesis.
  ```bash
  wiki ingest [--batch] [--no-thinking]
  ```

### 4.4. Semantic Search & Querying
* **`wiki query "<your question>"`**: Search and synthesize a referenced answer using the qmd indexing engine (hybrid, lex, or vec).
  ```bash
  wiki query "What is Unbalanced Schrödinger Bridge Initialization?" --mode hybrid --save-as SYN-usb-init
  ```

### 4.5. Search Index & Maintenance
* **`wiki reindex`**: Rebuilds the qmd semantic/lexical search index manually.
* **`wiki lint`**: Lints the wiki for broken links, missing parents, orphans, or contradictions.
  ```bash
  wiki lint [--deep] [--fix] [--save]
  ```

### 4.6. Agent Services
* **`wiki mcp`**: Spawns an MCP stdio server to integrate directly with LLM workspaces and agents.
* **`wiki mcp install`**: Outputs installation JSON snippets for your local IDE/Client.

---

## 5. Control Rules & Human-in-the-Loop (HITL)

1. **Rule of Immutability**: All files in `04_Resources` and `06_Archives` are immutable constants.
2. **Rule of Strong Negotiation**: If the Curator identifies math errors or contradictions within `03_Notes`, the Agent initiates strong negotiation via HITL.
3. **Ledger Priority**: Rules/corrections in `.curator/ledger.md` silently override any underlying DAG context.
