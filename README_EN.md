created: 2026-04-27T20:11
updated: 2026-05-06T00:00

# 🧠 Agentic Zettelkasten: Auto-Curating Workspace

This is a cost-effective Multi-Agent DAG (Directed Acyclic Graph) system built to safely execute complex projects without massive token waste and hallucinations amidst a flood of fragmented knowledge assets.

This system has reconstructed the Zettelkasten philosophy of connecting knowledge into a professional curation architecture. Collected external information is handled by the 'Curator Engine' and goes through a machine-friendly **4-stage professional curation pipeline (Stage 1: Context Summarization ➡️ Stage 2: Atomization ➡️ Stage 3: Concept Structuring ➡️ Stage 4: Exhibition Staging)**.

Only precisely 'compiled' knowledge packages through this process are injected into the 'Execution Agent (Artist)', which possesses powerful reasoning capabilities. Ultimately, through collaboration between humans and agents, a true **Synthesis** is achieved, forming an infinite knowledge creation loop that circulates this into the system's official knowledge (Wiki).

The curation loop works a little like training: `wiki add` and `wiki curate` are forward passes that compile source knowledge upward through the DAG, while `wiki sync` is the backward verification pass. Human and agent edits act as a loss signal: when generated nodes drift from their evidence, the Curator traces the graph back, safely repairs generated structure, and rewrites recoverable L3/L4 nodes. This is an operational analogy, not literal neural-network training: the system never rewrites immutable source truth and leaves ambiguous repairs for human review.

## What Makes This System Different

### DAG-Based Knowledge Compiler

The Curator does not store loose notes as flat search results. It compiles source material into a layered evidence graph:

```text
Source → L1 Context → L2 Atom → L3 Concept → L4 Exhibition
```

Each layer has a different job: preserve source context, extract irreducible claims, weave related claims into concepts, and stage task-ready knowledge packages for agents.

### Integrity-Aware Curation

The Curator is not a one-shot generator. It continuously checks whether generated knowledge still traces back to its evidence.

- `wiki add` and `wiki curate` compile knowledge forward through the DAG.
- `wiki sync` traces the compiled graph backward toward source evidence.
- Safe structural issues are repaired automatically.
- Recoverable generated-node gaps can update L3/L4 pages.
- Ambiguous cases stay visible as review items instead of being silently deleted.

### Workspace-Scoped Knowledge Staging

Each agent workspace can declare what it needs in `curate.yml`. The Curator uses that specification to surface and stage Exhibitions for the workspace's actual task, rather than forcing every agent to search the full vault equally.

### Coverage-Preserving Concept Generation

The Curator checks whether source Atoms are represented in L3 Concepts. If a clustering model omits coherent related Atoms, the Curator creates a fallback Concept for that source/topic group. Small but important topics, such as a RAG cluster containing Retriever, Generator, BM25, Parametric Memory, and Retrieval-Augmented Generation Atoms, should still become Concepts.

## 👥 3 Core Entities (The Entities: Curator & Artist Metaphor)

Our system organically interacts by strictly separating roles and usage models (Model Routing) for each entity to capture both **Cost Efficiency (FinOps)** and reasoning performance simultaneously.

| Entity | Metaphor (Role) | Architecture & Key Activities |
| :--- | :--- | :--- |
| **👤 Human** | Director | • Creator and owner of the source knowledge in `03_Notes`<br>• Reviews agent/curator proposed knowledge and makes final decisions (HITL)<br>• Reaches consensus through dialogue and approves the final Wiki |
| **⚙️ Curator** | Compiler | • [Based on Local SLM] Background engine residing in the `.curator/` hidden space<br>• Exclusively handles knowledge graph (DAG) maintenance and data preprocessing (Optimizes token consumption)<br>• Executes L1 ➡️ L4 refinement pipeline (Prohibited from creating new knowledge on its own) |
| **🤖 Execution Agent (Agent)** | Artist | • [Based on High-Reasoning LLM] Task executor residing in `01_Workspaces/`<br>• Acts based on the 'exhibits' staged by the curator without heavy original text searches<br>• Performs coding, planning, analysis, etc., and promotes agreed knowledge to `02_Wiki` |

## 📂 Core Directory Structure & Data Permissions (Two-Track Architecture)

The system features a two-track directory structure that separates a machine-readable backend exhibition preparation space (`.curator`) and a human-readable domain knowledge space (`02_Wiki`).

```
/
├── 00_System/               # System and template management (scripts, prompt templates, etc.)
│
├── 01_Workspaces/           # 🎨 🤖 Artist (Agent) Residence / Knowledge fusion and project execution space
│   └── {Project Name}/ 
│       ├── .agents/         # Agent control rules and persona settings
│       ├── Artifacts/       # Experimental code, deliverables, etc. (Drafts and sketches)
│       ├── Concepts/        # 💡 Concepts derived from discussions with humans (Incorporated into 02_Wiki after consensus)
│       ├── Papers/          # 📚 Paper review sandbox that reinterprets global knowledge into the project context
│       ├── curate.yml          # 🌟 [Knowledge Requirement Specification] Determines the scope of the 'Exhibition'
│       └── research_digest.md, todo_list.md, etc.  # Project status and task tracking documents
│
├── 02_Wiki/                 # 🏛️ 🤖 Agent & ⚙️ Curator-led official exhibition hall [PERM: Public Write Access]
│   └── (Domain-based directory convenient for human reference. Exhibits final Synthesis results)
│
├── 03_Notes/                # 👤 Human-centric source knowledge [PERM: Strict Read-Only]
│   └── (Human's primary knowledge. No AI can directly modify this original source - Principle of Immutability)
│
├── 04_Resources/            # 📚 Immutable external knowledge [PERM: Strict Read-Only]
│
├── 06_Archives/             # 📦 Legacy knowledge [PERM: Read-Only]
│
└── .curator/                # ⚙️ Hidden space exclusive to Curator (Local SLM) [PERM: Curator/Agent MCP Tool]
    ├── config.yml           # Project environment settings
    ├── state.sqlite         # Core DB for hash registry and state tracking
    ├── overview.md & index.md # Routing tables referenced first by the agent
    ├── sync-report.json     # Latest integrity report displayed by wiki status
    └── Collections/         # 🧠 Curation 4-stage pipeline (L1~L4)
        ├── 01_Contexts/     # [Stage 1: Collection & Summarization] L1: Preserves context via 1:1 summarization
        ├── 02_Atoms/        # [Stage 2: Selection & Atomization] L2: Selects core content into independent Atoms
        ├── 03_Concepts/     # [Stage 3: Structuring & Value Addition] L3: Weaves atoms to form and structure high-level Concepts
        └── 04_Exhibitions/  # [Stage 4: Placement & Staging] L4: Finally staged and placed exhibits for the agent
```

## ⚠️ Workflow and Operational Rules (Pipeline Rules)

### 1. The Curator's Bridge for Knowledge Exploration

- **Purpose:** To prevent token waste and cost generation caused by meaningless original text searches by large models (Agents).
- **Operation:** When starting a new query, agents and humans do not search directly through original notes (`03_Notes`). Instead, they first explore the **Exhibitions** pre-placed by the curator in `.curator/` to secure verified prior knowledge before beginning full-scale creation (reasoning).
- **Detailed Mechanism:** The execution agent of each workspace holds a **Knowledge Requirement Specification (curate.yml)** specifying its goals and requirements. Based on this, when the agent requests data from the curator via the MCP server, the curator selects knowledge optimized for that specification and provides it in the form of an 'Exhibition'.

### 1.1 Integrity-Aware Curation

- **Forward pass:** `wiki add` creates L1 Contexts, L2 Atoms, and L3 Concepts from source truth. `wiki curate` stages L4 Exhibitions for a workspace.
- **Loss signal:** Human or agent edits, missing links, uncovered Atoms, or logical gaps reveal where the compiled DAG no longer matches its evidence.
- **Backward pass:** `wiki sync` runs safe structural repair, logical verification, and bounded generated-node repair. It can update recoverable L3/L4 nodes and rebuild affected downstream pages.
- **Boundary:** `wiki sync` does not rewrite `03_Notes`, `04_Resources`, or `06_Archives`, does not invent missing Exhibitions, and does not delete ambiguous knowledge as a fallback.

### 2. Strong Human-AI Negotiation (HITL: Strong Negotiation)

- If the system discovers logical contradictions or errors within the knowledge (originals such as `03_Notes`), it absolutely does not arbitrarily modify the original. It immediately stops the work and raises an objection to the Director (Human) to initiate a discussion.
- **Principle of Immutability:** Even if human approval is granted, the original note (`03_Notes`) itself is not overwritten. Instead, the agent updates the knowledge nodes (Atoms/Concepts) within `.curator/` to safely correct the logical structure of the overall system.

### 2.1 Sync Command

```bash
wiki sync          # default: safe repair + logical verification
wiki sync --no-fix # report-only
wiki sync --dry-run
```

`wiki status` shows the latest sync health after the Config, Sources, Collections, and Pipeline Layer Status sections.

### 2.2 Coverage-Preserving Concept Generation

Concept generation checks whether source Atoms are actually represented in L3. If the clustering model omits coherent related Atoms, the Curator creates a fallback Concept for that source/topic group instead of silently marking the source complete. For example, RAG Atoms such as Retriever, Generator, BM25, Parametric Memory, and Retrieval-Augmented Generation should be promoted into a RAG Concept even if the clustering model initially misses them.

### 3. Fusion of Knowledge and Ecosystem Circulation (Synthesis)

Exhibits at the L4 (Exhibitions) stage can be newly staged in real-time according to queries. The refined knowledge is incorporated (**Synthesis**) into the final official knowledge (`02_Wiki`) through two paths.

#### 🔄 Path A: Agent-Led Task Synthesis

- **Entity:** 🤖 Execution Agent (Artist) + 👤 Human (Director)
- **Process:** Within `01_Workspaces`, the agent performs project tasks using the Exhibitions prepared by the curator as materials.
- **Result:** Insights and deliverables completed through negotiation with the human are recorded by the agent in `02_Wiki`.

#### 💬 Path B: Conversational Promotion

- **Entity:** ⚙️ Curator + 👤 Human (Director)
- **Process:** When the human asks a question, the curator answers within the concept network (L3) it has built. Afterwards, it develops ideas by engaging in ample conversation with the human.
- **Result:** If the content derived during the conversation is deemed a great concept, that content is officially promoted to `02_Wiki`.

#### 🔁 The Infinite Loop

Regardless of the path, the newly staged official knowledge in `02_Wiki` flows back into the background curator's L1 (Contexts) pipeline, endlessly expanding the entire knowledge ecosystem. All these changes are logged in `state.sqlite` to robustly maintain the DAG integrity of the entire system.
