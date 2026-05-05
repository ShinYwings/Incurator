SYMBIOTIC_OS_ARCHITECTURE - Agentic Zettelkasten Curator (v13.2)

> **v13.2 Changelog (from v13.1)**
> 1. **[UPDATE] `wiki sync` as the Integrity Loop**: `wiki sync` is now the single public consistency command. It performs safe structural repair by default, runs logical verification, attempts bounded generated-node repair, writes `sync-report.json`, and rebuilds routing tables. `wiki lint`, `wiki sync --fix`, and `--deep` are removed from the public interface.
> 2. **[NEW] Forward/Backward Curation Model**: `wiki add` and `wiki curate` act as forward compilation passes through the DAG. Human/agent edits create a loss signal. `wiki sync` acts as the backward verification/repair pass that traces generated knowledge back to evidence, repairs safe generated-node errors, and updates affected downstream pages when possible.
> 3. **[NEW] Coverage-Preserving L3 Clustering**: L3 Concept generation now extracts real Atom summaries from `## Definition / Claim`, detects unassigned Atoms, and creates fallback Concept plans for coherent unassigned source/topic groups. A source reaches `l3_status=done` only if its Atoms are actually covered by Concept `## Relations`.
> 4. **[UPDATE] Default Add/Curate Sync**: `wiki add` and `wiki curate` run sync after generation by default unless explicitly skipped.
> 5. **[NEW] Curate/Query Role Split**: `wiki curate` is the persistent workspace/agent Exhibition flow keyed by `curate.yml`. `wiki query` is a user-session flow; non-interactive queries leave no Exhibition unless `--save-as` is provided.
> 6. **[CLARIFY] Conservative Repair Boundary**: The backprop analogy is operational, not literal neural-network training. Current automatic logical repair is conservative and centered on generated L3/L4 pages plus safe structural repairs; immutable source truth is never rewritten.

> **v13.1 Changelog (from v13.0)**
> 1. **[NEW] `curate.yml` — Knowledge Requirement Specification**: Each workspace now holds a `curate.yml` file that declares the agent's knowledge scope, required domains, and topic priorities. The Curator uses this spec to select and stage Exhibitions targeted to that workspace's goals. This replaces the generic `qmd.yml` reference in the workspace topology.
> 2. **[UPDATE] Stage Labels — Action-Oriented**: Pipeline stage names now carry explicit action verbs aligned with the Compiler metaphor:
>    - L1 Contexts: **Collection & Summarization** (1:1 context preservation, knowledge candidate identification)
>    - L2 Atoms: **Selection & Atomization** (distillation of core candidates into irreducible units)
>    - L3 Concepts: **Structuring & Value Addition** (cross-atom conceptual network weaving)
>    - L4 Exhibitions: **Placement & Staging** (final compiled exhibit layout for Agent consumption)
> 3. **[NEW] Two Synthesis Paths — Formally Defined**: The mechanism by which curated knowledge enters `02_Wiki/` is now split into two explicit named paths:
>    - **Path A — Agent-Led Task Synthesis**: Agent executes projects in `01_Workspaces/` using Exhibitions as materials, promotes deliverables to `02_Wiki/` after HITL consensus.
>    - **Path B — Conversational Promotion**: Curator + Human dialog produces concepts; the Human decides to promote distilled insights to `02_Wiki/`.
> 4. **[UPDATE] 02_Wiki — Official Exhibition Hall**: `02_Wiki/` is now formally labeled as the "Official Exhibition Hall" — the terminal, human-readable output of the Infinite Knowledge Creation Loop, with Public Write Access for both Agents and Humans.
> 5. **[CLARIFY] `qmd.yml` vs `curate.yml`**: `qmd.yml` remains as the internal config file for the `qmd` search binary (managed by `wiki reindex`). `curate.yml` is a new per-workspace agent specification file. These are distinct files with distinct owners.

---

SYMBIOTIC_OS_ARCHITECTURE v13.2 — Full Specification

LLM-Wiki Curator is an autonomous, AI-maintained personal knowledge base designed for the SYMBIOTIC_OS_ARCHITECTURE v13.2. It functions as a Multi-Agent DAG (Directed Acyclic Graph) RAG system built to manage fragmented knowledge assets and execute complex projects safely without hallucinations.

By restructuring the philosophy of the Zettelkasten into a Data Curation architecture, the Curator Engine ensures that all external information passes through a strict 4-layer refinement pipeline.

To achieve both cost-efficiency (FinOps) and reasoning performance, this system enforces strict role separation and model routing: a lightweight local SLM drives the Curator's background compilation, while a high-reasoning LLM powers the Agent's execution. Only pre-compiled, verified knowledge packages are injected into the Agent, preventing token waste and hallucination.

1. Entity Roles & Global Topology

The system operates through the organic interaction of three core entities: Human (Director), Curator Engine (Compiler), and Workspace Agent (Artist).

1.1 Entities & Permissions

👤 Entity Human — "Director"

Domain: 03_Notes/

Role: The creator and owner of primary source knowledge. The Human is the ultimate decision-maker for knowledge synthesis, reviewing proposals from Agents/Curators and reaching consensus through Human-in-the-Loop (HITL) conversations.

⚙️ Entity Curator — "Compiler"

Domain: .curator/ (Hidden space, exclusive read/write access)

Model Tier: Lightweight local SLM (cost-optimized)

Role: A background engine that independently executes the 4-layer pipeline (Collection & Summarization → Selection & Atomization → Structuring & Value Addition → Placement & Staging) to maintain the massive knowledge graph (DAG). It does not create new source truth on its own; it compiles, assembles, verifies, and safely repairs generated DAG nodes to support the Director and Artist. When an Agent workspace provides a `curate.yml`, the Curator uses it to prioritize and scope which Exhibitions to stage.

🤖 Entity Agent — "Artist"

Domain: 01_Workspaces/{Project_Name}/

Model Tier: High-reasoning LLM

Role: The active executor that performs project tasks (coding, planning, analysis) based on human commands and pre-staged Exhibitions. The Agent declares its knowledge requirements via `curate.yml`; the Curator responds by surfacing targeted Exhibitions. It promotes agreed-upon knowledge to 02_Wiki/ via one of two Synthesis Paths.

1.2 Two-Track Architecture

The system maintains a strict "Two-Track" separation:

- **Machine-Readable Backend** (`.curator/`): The Compiler's hidden space. Not designed for human readability. Stores the full DAG, hash registry, event logs, and compiled knowledge packages (Exhibitions).
- **Human-Friendly Domain Space** (`02_Wiki/`): The Official Exhibition Hall. Human-curated, promoted knowledge accessible to both humans and agents. The terminal output of the Infinite Knowledge Creation Loop.

1.3 Topology Map

```text
ROOT: /
├── 00_System/          # [STATIC] Scripts & Templates
├── 01_Workspaces/      # [AGENT_RESIDENCE] Knowledge synthesis & execution space
│   └── {Project_Name}/
│       ├── .agents/ & .antigravity/ # Agent skills, personas, and control limits
│       ├── Artifacts/        # Auto-generated code, intermediate outputs
│       ├── Concepts/         # Draft concepts pending human consensus
│       ├── Papers/           # Project-specific literature review sandbox
│       ├── Research Notes/   # Daily research tracking
│       ├── curate.yml        # [KR_SPEC] Knowledge Requirement Specification — declares
│       │                     #   what the Agent needs the Curator to stage as Exhibitions
│       └── research_digest.md, todo_list.md, methodology.md
│
├── 02_Wiki/            # [OFFICIAL_EXHIBITION_HALL] Two-Track Human-Friendly Space
│                       #   — Public Write Access for Agent & Human (via HITL consensus)
├── 03_Notes/           # [HUMAN_TRUTH] 100% Human-verified source knowledge (Agent needs HITL to edit)
├── 04_Resources/       # [READ_ONLY] External reference PDFs, Docs (Immutable)
├── 05_Assets/          # [STATIC] System byproducts (Images, Zotero assets)
├── 06_Archives/        # [READ_ONLY] Terminated projects & legacy data
└── .curator/           # [CURATOR_RESIDENCE] Two-Track Machine-Readable Backend (Hidden Abstraction Space)
    ├── config.yml              # LLM backend, model, raw_dirs, collections_dir
    ├── state.sqlite            # Hash registry & ingest tracking DB (source-of-truth for dedup/provenance)
    ├── overview.md & index.md  # Primary routing tables for Agents (auto-rebuilt)
    ├── log.md & ledger.md      # Append-only event log and mandatory HITL correction record
    ├── sync-report.json        # Latest integrity health report surfaced by wiki status
    └── Collections/            # [DATA_PLANE] The L1~L4 DAG Knowledge Pipeline
        ├── 01_Contexts/    # [Stage 1: Collection & Summarization]
        │                   #   L1: Preserves the context of source data via 1:1 summarization
        │                   #   and identifies knowledge candidates
        ├── 02_Atoms/       # [Stage 2: Selection & Atomization]
        │                   #   L2: Selects core content and establishes irreducible minimum units
        ├── 03_Concepts/    # [Stage 3: Structuring & Value Addition]
        │                   #   L3: Weaves atoms into high-level concept networks
        └── 04_Exhibitions/ # [Stage 4: Placement & Staging]
                            #   L4: Finally staged and placed exhibits for Agent consumption
```

2. Polymorphic Metadata Schema (L1-L4)

[Unchanged from v13.0 except v13.2 additions — see SCHEMA_v13.2.md for full details]

**v13.2 Layer → Directory → ID Prefix Mapping (unchanged)**

| Layer | Name         | Directory         | ID Prefix | Example          |
|-------|--------------|-------------------|-----------|------------------|
| L1    | Context      | 01_Contexts/      | CTX-      | CTX-a1b2c3d4     |
| L2    | Atom         | 02_Atoms/         | ATM-      | ATM-9f8e7d6c     |
| L3    | Concept      | 03_Concepts/      | CON-      | CON-12345678     |
| L4    | Exhibition   | 04_Exhibitions/   | EXH-      | EXH-abcdef01     |

3. curate.yml — Knowledge Requirement Specification

Each workspace that wants targeted Exhibition staging must provide a `curate.yml` at its root. This file is read by the Curator when `search_curator` is called via MCP and when `wiki curate --workspace` is invoked.

```yaml
# curate.yml — Knowledge Requirement Specification
# Place at: 01_Workspaces/{Project_Name}/curate.yml

project: "project-name"
description: "Brief description of this workspace's goal and context"

# Knowledge domains this workspace operates in
domains:
  - "machine-learning"
  - "knowledge-management"

# Specific topics the curator should prioritize for Exhibition staging
topics:
  - "transformer architecture"
  - "attention mechanism"
  - "zettelkasten workflow"

# Minimum confidence threshold — Exhibitions below this score are not surfaced
min_confidence: 0.70

# Optional: restrict search scope to specific DAG layers
# Values: all | contexts | atoms | concepts | exhibitions
scope: "all"
```

If `curate.yml` is absent, the Curator falls back to unscoped global search (equivalent to v13.0 behavior).

3.1 Curate/Query Exhibition Metadata (v13.2)

Workspace Exhibitions created by `wiki curate` may include:

```yaml
workspace: "Workspace Project Name"
workspace_path: "/absolute/path/to/workspace"
curate_spec_hash: "12-char-hash"
```

Query save-back Exhibitions created by `wiki query --save-as` include:

```yaml
query_session: QRY-[UUID8]
ephemeral: false
question: "original query"
```

Saved L4 pages must always have non-empty `core_concepts`. Query save-back resolves cited Atoms/Contexts to related Concepts before writing an Exhibition.

4. Installation & Getting Started

[Unchanged from v13.0]

```bash
chmod +x install.sh
./install.sh
```

Initialising a Vault:

```bash
wiki init /path/to/your/vault
```

Scaffolding a new Workspace with curate.yml:

```bash
wiki workspace init /path/to/vault/01_Workspaces/MyProject
```

This creates the workspace directory structure and generates a `curate.yml` template.

5. Command-Line Interface (CLI)

[Unchanged from v13.0 except additions below]

5.1 Workspace Initialization (wiki workspace)

```text
wiki workspace init PATH    Scaffold a workspace directory with curate.yml template.
wiki workspace list         List workspaces with curate.yml under 01_Workspaces/.
```

5.2 wiki curate — Workspace-Scoped Curation (addition)

```text
wiki curate --workspace PATH   Read curate.yml from PATH and prioritize curation
                               for declared domains and topics.
```

5.3 wiki sync — Unified Integrity Command (v13.2)

```text
wiki sync                    Run safe structural repair, logical verification,
                             bounded generated-node repair, report update,
                             and routing-table rebuild.
wiki sync --no-fix           Report-only mode; do not repair files or DB.
wiki sync --dry-run          Preview mode; do not repair or rebuild routing.
wiki sync NODE_ID            Targeted verification around one DAG node.
```

Removed public commands/options:

```text
wiki lint
wiki sync --fix
wiki sync --deep
```

The old lint functionality remains as an internal structural verification engine used by `wiki sync` and `wiki status`.

5.4 wiki query — Session Flow (v13.2)

`wiki query` is for user-session Q&A without a workspace agent. By default, non-interactive query runs do not leave an Exhibition. If `--save-as` is provided, the answer is saved as an L4 query Exhibition with `QRY-*` session metadata and validated Concept links.

5.5 All Other Commands

[Unchanged from v13.0 — see llm_wiki_v13.0.md Section 4]

6. Workflow Rules

6.1 The Curator's Bridge (Scoped Exhibition Staging)

Before answering queries or executing tasks, Artists (Agents) do not blindly search raw directories.

Rule: The Agent calls `curator_layer_index()` first, then `search_curator()`. If the calling workspace has a `curate.yml`, the MCP server applies its `domains`, `topics`, and `min_confidence` filters automatically to surface targeted Exhibitions.

6.2 Strong Human-AI Negotiation (HITL)

If the system detects logical contradictions in source knowledge (`03_Notes`), it MUST halt, flag the error to the Human (Director), and initiate a debate before any modification.

Principle of Immutability: Even with human approval, original notes (`03_Notes`) are never overwritten. Only the DAG nodes (Atoms/Concepts) within `.curator/` are updated.

6.3 Synthesis — Two Paths to the Official Exhibition Hall

Exhibits at the L4 (Exhibitions) stage flow into `02_Wiki/` via exactly two paths:

**🔄 Path A — Agent-Led Task Synthesis**

- Entity: 🤖 Artist (Agent) + 👤 Director (Human)
- Process: Inside `01_Workspaces/`, the Agent performs project tasks using staged Exhibitions as primary materials (not raw notes). Deliverables and insights produced through HITL negotiation are written by the Agent to `02_Wiki/`.
- Trigger: Agent completes a task milestone and the Human approves the result.

**💬 Path B — Conversational Promotion**

- Entity: ⚙️ Compiler (Curator) + 👤 Director (Human)
- Process: The Human asks a question; the Curator answers within its Concept network (L3). An extended dialogue develops. If the Human judges that a derived insight is notable, they explicitly promote it to `02_Wiki/`.
- Trigger: Human issues a promotion command after a productive Q&A session.

6.4 The Infinite Knowledge Creation Loop

Regardless of the path, newly promoted knowledge in `02_Wiki/` is automatically re-ingested into the Curator's L1 (Contexts) pipeline on the next `wiki add` run, endlessly expanding the knowledge ecosystem. DAG integrity is maintained throughout via `state.sqlite`.

```text
Source (03_Notes / 04_Resources / 02_Wiki)
   │  wiki add
   ▼
01_Contexts  →  02_Atoms  →  03_Concepts  →  04_Exhibitions
                                                    │
                         ┌──────────────────────────┤
                         │ Path A: Agent task work  │ Path B: Curator-Human dialog
                         ▼                          ▼
                       02_Wiki/ (Official Exhibition Hall)
                         │
                         └── wiki add → back into L1 pipeline (Loop)
```

6.5 Forward/Backward Integrity Loop (v13.2)

The Curator now follows an operational loop similar to forward and backward passes in deep learning:

- **Forward pass**: `wiki add` compiles source truth upward into L1 Contexts, L2 Atoms, and L3 Concepts. `wiki curate` compiles selected Concepts into L4 Exhibitions.
- **Loss signal**: Human/agent edits to generated DAG nodes, missing links, uncovered Atoms, structural gaps, or logical verification failures reveal where the compiled graph no longer matches its evidence.
- **Backward pass**: `wiki sync` traces Exhibitions and Concepts back toward their evidence, repairs safe structural errors, verifies L3/L4 logic, and rewrites generated L3/L4 nodes when the gap is recoverable.
- **Forward rebuild**: After a generated node is repaired, downstream dependent pages are rebuilt only when such downstream endpoints exist.

This analogy is intentionally bounded. The Curator does not modify immutable source truth (`03_Notes`, `04_Resources`, `06_Archives`), does not invent missing L4 Exhibitions, and does not automatically merge/delete ambiguous knowledge. Ambiguous cases remain `needs_review`.

6.6 Coverage-Preserving Concept Generation (v13.2)

L3 generation must not silently strand a source's Atoms. The Curator now:

- extracts real Atom summaries from `## Definition / Claim`
- asks the model to cluster Atoms into Concepts
- splits known hard topic-boundary false merges
- detects unassigned Atoms after clustering
- creates fallback Concept plans for coherent unassigned source/topic groups with at least two Atoms
- marks a source `l3_status=done` only when at least one Atom from that source appears in a Concept `## Relations` section

This is why a RAG source with Retriever, Generator, BM25, Parametric Memory, and RAG Framework Atoms must produce a RAG Concept even if the clustering model initially omits it.

7. Confidence Decision Tree

```text
EXH confidence_score:
>= 0.90  DIRECT_RETRIEVAL   — Agent can cite directly.
0.60–0.90 PARTIAL_BACKTRACK — Run curator_traverse_evidence (CON → ATM) before citing.
< 0.60   FULL_VERIFICATION  — Halt. Trigger STRONG_NEGOTIATION with Human (Director).
                              Set is_flagged_for_agent: true on relevant ATMs.
```

Additionally, `curate.yml`'s `min_confidence` provides a workspace-level pre-filter: Exhibitions below that threshold are suppressed from `search_curator` results for that workspace.

7.1 Latest Sync Health (v13.2)

`wiki status` surfaces `.curator/sync-report.json` after Config, Sources, Collections, and Pipeline Layer Status. The report includes:

- `health`: `clean | fixed | review_needed | failed | stale`
- last sync time and trigger
- fixed structural/logical counts
- remaining structural gaps
- remaining logical gaps
- equivalence candidates
- needs-review count
- blocked logical checks

8. Immutability Rules

[Unchanged from v13.0]

- Never modify 04_Resources/ or 06_Archives/.
- Never modify 03_Notes/ autonomously — requires HITL.
- Never delete a .curator/Collections/ page without explicit user confirmation.
- Never overwrite existing atom claims silently — use ## Updates [date] sections.
- Never invent citations — if no traceable ATM-UUID, mark confidence_score < 0.60.
- Never bypass state.sqlite.
- Never access .curator/ files directly — use MCP tools.
- Never treat `wiki sync` as permission to alter source truth. It repairs generated DAG state only.

9. MCP Tools Reference

[Additions and changes from v13.0]

search_curator(query, scope, mode, limit, min_score)
  v13.1: Now auto-detects workspace curate.yml via WORKSPACE_PATH env var.
  Applies domain/topic/min_confidence filters from curate.yml when present.
  scope: 'all' | 'contexts' | 'atoms' | 'concepts' | 'exhibitions'

curator_curate_context(context_id)  [v13.2 naming]
  Re-run the L2→L4 extraction pipeline for a single L1 Context.

[All other tools unchanged from v13.0 — see Section 12 of llm_wiki_v13.0.md]
