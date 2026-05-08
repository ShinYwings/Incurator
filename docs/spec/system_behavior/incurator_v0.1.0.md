# InCurator - Agentic Zettelkasten Curator (v0.1.0)

InCurator is an autonomous, AI-maintained personal knowledge base designed for the InCurator v0.1.0 architecture. It functions as a Multi-Agent DAG (Directed Acyclic Graph) RAG system built to manage fragmented knowledge assets and execute complex projects safely without hallucinations.

By restructuring the philosophy of the Zettelkasten into a Data Curation architecture, the InCurator Engine ensures that all external information passes through a strict 4-layer refinement pipeline.

To achieve both cost-efficiency (FinOps) and reasoning performance, this system enforces strict role separation and model routing: a lightweight local SLM drives the Curator's background compilation, while a high-reasoning LLM powers the Agent's execution. Only pre-compiled, verified knowledge packages are injected into the Agent, preventing token waste and hallucination.

## 1. Entity Roles & Global Topology

The system operates through the organic interaction of three core entities: Human (Director), InCurator Engine (Compiler), and Workspace Agent (Artist).

### 1.1 Entities & Permissions

👤 **Entity Human — "Director"**

**Domain**: 03_Notes/

**Role**: The creator and owner of primary source knowledge. The Human is the ultimate decision-maker for knowledge synthesis, reviewing proposals from Agents/Curators and reaching consensus through Human-in-the-Loop (HITL) conversations.

⚙️ **Entity InCurator — "Compiler"**

**Domain**: .curator/ (Hidden space, exclusive read/write access)

**Model Tier**: Lightweight local SLM (cost-optimized)

**Role**: A background engine that independently executes the 4-layer pipeline (Collection & Summarization → Selection & Atomization → Structuring & Value Addition → Placement & Staging) to maintain the massive knowledge graph (DAG). It does not create new source truth on its own; it compiles, assembles, verifies, and safely repairs generated DAG nodes to support the Director and Artist. When an Agent workspace provides a `curate.yml`, the Curator uses it to prioritize and scope which Exhibitions to stage.

🤖 **Entity Agent — "Artist"**

**Domain**: 01_Workspaces/{Project_Name}/

**Model Tier**: High-reasoning LLM

**Role**: The active executor that performs project tasks (coding, planning, analysis) based on human commands and pre-staged Exhibitions. The Agent declares its knowledge requirements via `curate.yml`; the Curator responds by surfacing targeted Exhibitions. It promotes agreed-upon knowledge to 02_Wiki/ via one of two Synthesis Paths.

### 1.2 Two-Track Architecture

The system maintains a strict "Two-Track" separation:

- **Machine-Readable Backend** (`.curator/`): The Compiler's hidden space. Not designed for human readability. Stores the full DAG, hash registry, event logs, and compiled knowledge packages (Exhibitions).
- **Human-Friendly Domain Space** (`02_Wiki/`): The Official Exhibition Hall. Human-curated, promoted knowledge accessible to both humans and agents. The terminal output of the Infinite Knowledge Creation Loop.

### 1.3 Topology Map

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
    ├── config.yml              # Project configuration (LLM backend, model, raw_dirs, collections_dir)
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

## 2. Polymorphic Metadata Schema (L1-L4)

[See SCHEMA_v0.1.0.md for full details]

**Layer → Directory → ID Prefix Mapping**

| Layer | Name         | Directory         | ID Prefix | Example          |
|-------|--------------|-------------------|-----------|------------------|
| L1    | Context      | 01_Contexts/      | CTX-      | CTX-a1b2c3d4     |
| L2    | Atom         | 02_Atoms/         | ATM-      | ATM-9f8e7d6c     |
| L3    | Concept      | 03_Concepts/      | CON-      | CON-12345678     |
| L4    | Exhibition   | 04_Exhibitions/   | EXH-      | EXH-abcdef01     |

## 3. curate.yml — Knowledge Requirement Specification

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

If `curate.yml` is absent, the Curator falls back to unscoped global search.

### 3.1 Curate/Query Exhibition Metadata

Workspace Exhibitions created by `wiki curate` include:

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

## 4. Persona System

The persona system bridges the general-purpose curation engine with domain-specific knowledge work. It has two tiers that compose at runtime.

### 4.1 Two-Tier Architecture

**Curator Persona** — stored in `.curator/config.yml` under the `persona:` key. Set during `wiki init` via a multi-turn LLM interview. Applies vault-wide.

Fields:

- `area`: broad knowledge area (e.g., STEM, Humanities, Law, Medicine)
- `text`: free-text description of the user's knowledge focus and goals
- `knowledge_artifacts`: list of primary artifact types produced (papers, code, reports, etc.)
- `verification_philosophy`: how strictly claims should be verified
- `exhibition_intent`: always `"knowledge-worker"` at Curator level
- `confidence`: sub-object with `high_threshold` (float) and `low_threshold` (float)
- `disambiguation_keywords`: list of domain-specific terms to disambiguate concepts
- `updated_at`: ISO 8601 timestamp of last update

**Artist Persona** — stored in `curate.yml` under the `persona:` key. Created during the first `wiki curate --workspace <name>` run or via `wiki persona update --workspace <name>`. Overrides Curator persona fields for that workspace.

Fields:

- `domain`: primary domain string (e.g., "computer-vision")
- `subdomain`: more specific focus area (e.g., "neural-radiance-fields")
- `text`: free-text description of the workspace's knowledge goal
- `exhibition_intent`: `"researcher"` | `"engineer"` | `"learner"`
- `disambiguation_keywords`: workspace-specific disambiguation terms
- `confidence`: sub-object with `high_threshold` and `low_threshold` (overrides Curator)
- `updated_at`: ISO 8601 timestamp of last update

### 4.2 Injection Points

| Pipeline Stage | Persona Used | How Applied |
| --- | --- | --- |
| `wiki sync` verification | Curator `text` | Prepended as domain context to verification prompts |
| `wiki query` synthesis | Curator `text` | Prepended as agent context to synthesis prompt |
| L3 Concept generation | Artist `text` + `domain` | Guides concept clustering and naming |
| L4 Exhibition generation | Artist `exhibition_intent` + `text` | Shapes exhibit format and detail level |
| Exhibition confidence pre-filter | Artist `confidence` thresholds | Overrides Curator thresholds for `min_confidence` |
| Concept disambiguation | Artist `disambiguation_keywords` | Applied during L3 clustering to avoid false merges |

When no `curate.yml` is present (e.g., `wiki query` without a workspace), the Curator persona is the sole context.

### 4.3 Evolution Mechanism

- `wiki add` accumulates source domains to signal vault knowledge drift.
- `wiki persona update` refines the Curator persona using accumulated knowledge as context.
- `wiki persona update --workspace <name>` refines the Artist persona for that workspace.
- Default behavior when no persona is configured: STEM defaults (`confidence.high_threshold = 0.85`, `confidence.low_threshold = 0.55`).

### 4.4 CLI Commands

```text
wiki persona                          Show the current Curator persona.
wiki persona update                   Re-run the Curator persona interview.
wiki persona update --workspace NAME  Update the Artist persona for NAME.
```

## 5. Installation & Getting Started

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

## 5. Command-Line Interface (CLI)

### 5.1 Workspace Initialization (wiki workspace)

```text
wiki workspace init PATH    Scaffold a workspace directory with curate.yml template.
wiki workspace list         List workspaces with curate.yml under 01_Workspaces/.
```

### 5.2 wiki curate — Workspace-Scoped Curation

```text
wiki curate --workspace PATH   Read curate.yml from PATH and prioritize curation
                                for declared domains and topics.
```

By default, `wiki curate` runs `wiki sync` after generation to ensure DAG integrity.

### 5.3 wiki sync — Unified Integrity Command

```text
wiki sync                    Run safe structural repair, logical verification,
                             bounded generated-node repair, report update,
                             and routing-table rebuild.
wiki sync --no-fix           Report-only mode; do not repair files or DB.
wiki sync --dry-run          Preview mode; do not repair or rebuild routing.
wiki sync NODE_ID            Targeted verification around one DAG node.
```

The `wiki sync` command is the single public command for maintaining consistency. It performs safe structural repair by default, runs logical verification, attempts bounded generated-node repair, writes `sync-report.json`, and rebuilds routing tables. Internal structural verification (formerly `wiki lint`) is now performed as part of this unified flow.

### 5.4 wiki query — Session Flow

`wiki query` is for user-session Q&A without a workspace agent.

```text
--save-as "title"   Save the answer as a persistent L4 Exhibition (ephemeral: false).
                    Frontmatter includes query_session (QRY-UUID8), workspace (if set),
                    and question. Requires at least one reachable L3 Concept.

--curate            Create and accumulate a session-scoped Exhibition (ephemeral: true).
                    First answer creates the Exhibition; each follow-up appends a
                    ## Follow-up: <question> section and merges core_concepts.
                    At session end the user is prompted to keep (sets ephemeral: false)
                    or discard (deletes file, rebuilds index). Silently skipped if no
                    L3 Concepts are reachable from the query hits.
```

By default (no flag), non-interactive query runs do not leave an Exhibition.

## 6. Workflow Rules

### 6.1 The Curator's Bridge (Scoped Exhibition Staging)

Before answering queries or executing tasks, Artists (Agents) do not blindly search raw directories.

Rule: The Agent calls `curator_layer_index()` first, then `search_curator()`. If the calling workspace has a `curate.yml`, the MCP server applies its `domains`, `topics`, and `min_confidence` filters automatically to surface targeted Exhibitions.

### 6.2 Strong Human-AI Negotiation (HITL)

If the system detects logical contradictions in source knowledge (`03_Notes`), it MUST halt, flag the error to the Human (Director), and initiate a debate before any modification.

Principle of Immutability: Even with human approval, original notes (`03_Notes`) are never overwritten. Only the DAG nodes (Atoms/Concepts) within `.curator/` are updated.

### 6.3 Synthesis — Two Paths to the Official Exhibition Hall

Exhibits at the L4 (Exhibitions) stage flow into `02_Wiki/` via exactly two paths:

**🔄 Path A — Agent-Led Task Synthesis**

- Entity: 🤖 Artist (Agent) + 👤 Director (Human)
- Process: Inside `01_Workspaces/`, the Agent performs project tasks using staged Exhibitions as primary materials (not raw notes). Deliverables and insights produced through HITL negotiation are written by the Agent to `02_Wiki/`.
- Trigger: Agent completes a task milestone and the Human approves the result.

**💬 Path B — Conversational Promotion**

- Entity: ⚙️ Compiler (InCurator Engine) + 👤 Director (Human)
- Process: The Human asks a question; the Curator answers within its Concept network (L3). An extended dialogue develops. If the Human judges that a derived insight is notable, they explicitly promote it to `02_Wiki/`.
- Trigger: Human issues a promotion command after a productive Q&A session.

### 6.4 The Infinite Knowledge Creation Loop

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

### 6.5 Forward/Backward Integrity Loop

The InCurator Engine follows an operational loop similar to forward and backward passes in deep learning:

- **Forward pass**: `wiki add` compiles source truth upward into L1 Contexts, L2 Atoms, and L3 Concepts. `wiki curate` compiles selected Concepts into L4 Exhibitions. By default, these commands run a `wiki sync` pass after generation.
- **Loss signal**: Human/agent edits to generated DAG nodes, missing links, uncovered Atoms, structural gaps, or logical verification failures reveal where the compiled graph no longer matches its evidence.
- **Backward pass**: `wiki sync` traces Exhibitions and Concepts back toward their evidence, repairs safe structural errors, verifies L3/L4 logic, and rewrites generated L3/L4 nodes when the gap is recoverable.
- **Forward rebuild**: After a generated node is repaired, downstream dependent pages are rebuilt only when such downstream endpoints exist.

This analogy is intentionally bounded. The Curator does not modify immutable source truth (`03_Notes`, `04_Resources`, `06_Archives`), does not invent missing L4 Exhibitions, and does not automatically merge/delete ambiguous knowledge. Ambiguous cases remain `needs_review`.

### 6.6 Coverage-Preserving Concept Generation

L3 generation must not silently strand a source's Atoms. The InCurator Engine:

- extracts real Atom summaries from `## Definition / Claim`
- asks the model to cluster Atoms into Concepts
- splits known hard topic-boundary false merges
- detects unassigned Atoms after clustering
- creates fallback Concept plans for coherent unassigned source/topic groups with at least two Atoms
- marks a source `l3_status=done` in `state.sqlite` only when at least one Atom from that source appears in a Concept `## Relations` section

This ensures that all constituent facts are accounted for in the higher-level conceptual synthesis.

## 7. Confidence Decision Tree

```text
EXH confidence_score:
>= 0.90  DIRECT_RETRIEVAL   — Agent can cite directly.
0.60–0.90 PARTIAL_BACKTRACK — Run curator_traverse_evidence (CON → ATM) before citing.
< 0.60   FULL_VERIFICATION  — Halt. Trigger STRONG_NEGOTIATION with Human (Director).
                              Set is_flagged_for_agent: true on relevant ATMs.
```

Additionally, `curate.yml`'s `min_confidence` provides a workspace-level pre-filter: Exhibitions below that threshold are suppressed from `search_curator` results for that workspace.

### 7.1 Latest Sync Health

`wiki status` surfaces `.curator/sync-report.json` after Config, Sources, Collections, and Pipeline Layer Status. The report includes:

- `health`: `clean | fixed | review_needed | failed | stale`
- last sync time and trigger
- fixed structural/logical counts
- remaining structural gaps
- remaining logical gaps
- equivalence candidates
- needs-review count
- blocked logical checks

## 8. Immutability Rules

- Never modify 04_Resources/ or 06_Archives/.
- Never modify 03_Notes/ autonomously — requires HITL.
- Never delete a .curator/Collections/ page without explicit user confirmation.
- Never overwrite existing atom claims silently — use ## Updates [date] sections.
- Never invent citations — if no traceable ATM-UUID, mark confidence_score < 0.60.
- Never bypass state.sqlite.
- Never access .curator/ files directly — use MCP tools.
- Never treat `wiki sync` as permission to alter source truth. It repairs generated DAG state only.

## 9. MCP Tools Reference

```text
search_curator(query, scope, mode, limit, min_score)
  Auto-detects workspace curate.yml via WORKSPACE_PATH env var.
  Applies domain/topic/min_confidence filters from curate.yml when present.
  scope: 'all' | 'contexts' | 'atoms' | 'concepts' | 'exhibitions'
  On first call for a workspace with no Exhibition, auto-triggers wiki curate --workspace.

curator_status()
  Returns vault_root, qmd_ready, total_pages.

curator_layer_index()
  Returns count and sample IDs for each layer (context, atom, concept, exhibition).

curator_get_node(node_id)
  Returns body and frontmatter for any CTX/ATM/CON/EXH node.

curator_update_node(node_id, new_content)
  Writes new_content to the node file, rebuilds routing tables, returns gaps list.

curator_curate_workspace(workspace_path?)
  Create or refresh the L4 Exhibition for a workspace by running wiki curate --workspace.
  workspace_path defaults to the WORKSPACE_PATH env var.
  Returns {ok: true, exhibition: "EXH-xxxx.md"} or {error: "..."}.
  Call this after curator_update_node or when search_curator finds no Exhibition.

curator_curate_context(context_id)
  Re-run the L1→L3 compilation pipeline for a single source.
```

---
This specification defines the operational contract for InCurator v0.1.0.
