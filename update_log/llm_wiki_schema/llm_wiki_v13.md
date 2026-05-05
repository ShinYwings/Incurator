SYMBIOTIC_OS_ARCHITECTURE - Agentic Zettelkasten Curator (v13.0)

> **v13.0 Changelog (from v12.0)**
> 1. **[RENAME] Pipeline Layer & Directory Names**: The 4-layer curation pipeline has been renamed to align with the Curator/Artist metaphor system. See Section 2 for full mapping.
>    - L1 Accessions (`01_Accessions/`, `ACC-`) → **L1 Contexts** (`01_Contexts/`, `CTX-`)
>    - L2 Fragments (`02_Fragments/`, `FRG-`) → **L2 Atoms** (`02_Atoms/`, `ATM-`)
>    - L3 Themes (`03_Themes/`, `THM-`) → **L3 Concepts** (`03_Concepts/`, `CON-`)
>    - L4 Curations (`04_Curations/`, `CUR-`) → **L4 Exhibitions** (`04_Exhibitions/`, `EXH-`)
> 2. **[NEW] Formalized Entity Metaphor System**: Human=Director, Curator=Compiler, Agent=Artist. Roles, permissions, and inter-entity interactions are now expressed through this metaphor in all documentation.
> 3. **[NEW] Two-Track Architecture**: Explicitly separated machine-readable backend (`.curator/`) from the human-friendly domain knowledge space (`02_Wiki/`) as a named architectural principle.
> 4. **[NEW] FinOps / Model Routing Principle**: Cost-efficiency through strict model-role separation is now a first-class design concern. Lightweight local SLM for Curator; high-reasoning LLM for Agent.
> 5. **[NEW] Infinite Knowledge Creation Loop**: The circular flow from `02_Wiki/` back into L1 ingestion is now explicitly named and documented as a core system property.

---

LLM-Wiki Curator is an autonomous, AI-maintained personal knowledge base designed for the SYMBIOTIC_OS_ARCHITECTURE v13.0. It functions as a Multi-Agent DAG (Directed Acyclic Graph) RAG system built to manage fragmented knowledge assets and execute complex projects safely without hallucinations.

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

Role: A background engine that independently executes the 4-layer pipeline (Context Summary → Atomization → Conceptual Structuring → Exhibition Layout) to maintain the massive knowledge graph (DAG). It does not create new knowledge on its own; it strictly focuses on compiling and assembling information to support the Director and Artist.

🤖 Entity Agent — "Artist"

Domain: 01_Workspaces/{Project_Name}/

Model Tier: High-reasoning LLM

Role: The active executor that performs project tasks (coding, planning, analysis) based on human commands and contexts provided by the Curator (qmd.yml). It operates exclusively on "Exhibitions" pre-staged by the Compiler, avoiding exhaustive raw searches. It promotes agreed-upon knowledge to 02_Wiki/.

1.2 Two-Track Architecture

The system maintains a strict "Two-Track" separation:

- **Machine-Readable Backend** (`.curator/`): The Compiler's hidden space. Not designed for human readability. Stores the full DAG, hash registry, event logs, and compiled knowledge packages (Exhibitions).
- **Human-Friendly Domain Space** (`02_Wiki/`): The official public Exhibition. Human-curated, promoted knowledge accessible to both humans and agents. The terminal output of the Infinite Knowledge Creation Loop.

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
│       ├── qmd.yml           # [Routing Loader] Context loader defining prior knowledge for the Agent
│       └── research_digest.md, todo_list.md, methodology.md
│
├── 02_Wiki/            # [SHARED_TRUTH] Official Exhibition — Two-Track Human-Friendly Space
├── 03_Notes/           # [HUMAN_TRUTH] 100% Human-verified source knowledge (Agent needs HITL to edit)
├── 04_Resources/       # [READ_ONLY] External reference PDFs, Docs (Immutable)
├── 05_Assets/          # [STATIC] System byproducts (Images, Zotero assets)
├── 06_Archives/        # [READ_ONLY] Terminated projects & legacy data
└── .curator/           # [CURATOR_RESIDENCE] Two-Track Machine-Readable Backend (Hidden Abstraction Space)
    ├── config.yml              # LLM backend, model, raw_dirs, collections_dir
    ├── state.sqlite            # Hash registry & ingest tracking DB (source-of-truth for dedup/provenance)
    ├── overview.md & index.md  # Primary routing tables for Agents (auto-rebuilt)
    ├── log.md & ledger.md      # Append-only event log and mandatory HITL correction record
    └── Collections/            # [DATA_PLANE] The L1~L4 DAG Knowledge Pipeline
        ├── 01_Contexts/    # L1: 1:1 Context Summaries of source documents
        ├── 02_Atoms/       # L2: Irreducible atomic knowledge units
        ├── 03_Concepts/    # L3: High-level conceptual clusters
        └── 04_Exhibitions/ # L4: Packaged Contexts for Agents & Humans
```

2. Polymorphic Metadata Schema (L1-L4)

The Curator structures all knowledge within .curator/Collections/ into a 4-layer extraction and synthesis pipeline.

**v13.0 Layer → Directory → ID Prefix Mapping**

| Layer | Name         | Directory         | ID Prefix | Example          |
|-------|--------------|-------------------|-----------|------------------|
| L1    | Context      | 01_Contexts/      | CTX-      | CTX-a1b2c3d4     |
| L2    | Atom         | 02_Atoms/         | ATM-      | ATM-9f8e7d6c     |
| L3    | Concept      | 03_Concepts/      | CON-      | CON-12345678     |
| L4    | Exhibition   | 04_Exhibitions/   | EXH-      | EXH-abcdef01     |

Node IDs are prefixed UUIDs (CTX-/ATM-/CON-/EXH-) — never human slugs. Human-readable titles live in frontmatter only. IDs are generated once at page creation and never change. File names are {ID}.md.

Layer 1: Context (CTX-[UUID8])

A 1:1 hash-matched recap and initial registration of a single source document. Preserves the full original context of the source.

```yaml
id: CTX-[UUID8]
type: context
source_path: "[[relative/path/to/source.md]]"
source_hash: [SHA-256]
domain: "knowledge-domain-string"
last_updated: [YYYY-MM-DDThh:mm:ssZ]
tags: [tag1, tag2]
```

Body sections: ## Summary, ## Key Claims, ## Atomization Candidates, ## Source

Layer 2: Atom (ATM-[UUID8])

Irreducible factual claims or logic blocks, distilled from one or more L1 Contexts. Each Atom encodes a single, non-decomposable unit of knowledge.

```yaml
id: ATM-[UUID8]
type: atom
parent_source: "[[01_Contexts/CTX-UUID8]]"
claim_type: fact | equation | theoretical_constraint
contradicts: []
is_verified_by_human: false
is_flagged_for_agent: false
last_updated: [YYYY-MM-DDThh:mm:ssZ]
```

Body sections: ## Definition / Claim, ## Context, ## Constraints, ## Relations, ## Source

If an atom claim is later contradicted: set `contradicts: ["ATM-other"]` and `is_flagged_for_agent: true`. Do NOT silently overwrite — append an `## Updates [date]` section.

Layer 3: Concept (CON-[UUID8])

Clusters of related L2 Atoms forming a coherent high-level conceptual network. Minimum 2 atom dependencies required — singleton concepts (1 atom) are redundant.

```yaml
id: CON-[UUID8]
type: concept
dependencies: ["[[02_Atoms/ATM-UUID8]]", "[[02_Atoms/ATM-UUID8]]"]
domain: "knowledge-domain-string"
last_updated: [YYYY-MM-DDThh:mm:ssZ]
```

Body sections: ## 1. Core Architecture, ## 2. Interaction of Atoms, ## 3. Open Questions

Layer 4: Exhibition (EXH-[UUID8])

Terminal knowledge outputs intricately packaged for Agent injection or conversational reference. These are the "compiled exhibits" the Artist consumes.

```yaml
id: EXH-[UUID8]
type: exhibition
core_concepts: ["[[03_Concepts/CON-UUID8]]"]
confidence_score: 0.00 - 1.00
last_updated: [YYYY-MM-DDThh:mm:ssZ]
```

Body sections: ## 1. Executive Brief, ## 2. Theoretical Foundation, ## 3. Actionable Directives for Agent

3. Installation & Getting Started

To install the project locally with all prerequisites (Ollama, Node.js, and the qmd search engine) in one command, run:

```bash
chmod +x install.sh
./install.sh
```

3.1 Initialising a Vault

To scaffold a new wiki vault project with the full topological structure:

```bash
wiki init /path/to/your/vault
```

(Sets up the full directory topology, .obsidian/ marker, 00_System/ through 06_Archives/, and the .curator/ tracking database.)

4. Command-Line Interface (CLI)

The wiki CLI automates everything from file scanning to querying the DAG. (Revamped in v12.0, layer naming updated in v13.0)

4.1. Core Operations

`wiki status`: Inspect tracking database metrics, active LLM config, and collection counts.

`wiki version`: View the current installed version.

4.2. Source Ingestion & L1 Registration (wiki add)

`wiki add PATH [-r]`: Discovers new or changed files in raw directories (02_Wiki, 03_Notes, 04_Resources) and generates L1 Context summaries inside .curator/Collections/01_Contexts/. Updates the hash database (state.sqlite) and appends to the event log (log.md).

4.3. Source Management (wiki sources)

```text
wiki sources list          List all tracked source files.
wiki sources show ID       Show details for one source (with text preview).
wiki sources rm ID         Remove a source from tracking.
wiki sources retry ID      Retry a previously failed source.
```

4.4. Top-Down Extraction (wiki curate)

`wiki curate [SOURCE_ID]`: Runs the downstream extraction pipeline (L1 → L2 → L3 → L4) via three sequential LLM passes:

- **Pass 1** (thinking mode): Extract L2 Atoms from each L1 Context. Checks for contradictions.
- **Pass 2**: Cluster Atoms into L3 Concepts. This is a cross-source operation — it runs only after ALL Pass 1 outputs are complete. The pipeline is sequential, not parallel.
- **Pass 3**: Bundle L3 Concepts into L4 Exhibitions.

Then rebuilds index.md and appends to log.md.

```text
wiki curate [--force] [--batch] [--no-thinking] [--sync]
```

Optional: Append `--sync` to automatically execute global reverse verification (wiki sync) immediately after extraction.

4.5. Deductive Verification & Logic Alignment (wiki sync)

`wiki sync [NODE_ID]` (introduced in v12.0): The core Logic Alignment Engine. Runs structural verification (Mode A or B) followed by LLM logical deduction (Mode C always), then rebuilds all routing tables.

**Mode A — Global Structural Verification** (no NODE_ID):
Traces L4 → L1, verifying all wikilinks and dependencies are intact. Flags broken references and missing nodes. Triggered by standalone `wiki sync` or the `--sync` flag on `wiki curate`.

**Mode B — Targeted Bidirectional Propagation** (NODE_ID given):
Traces both upstream (to L1) and downstream (to L4) from the specified node to mend the affected conceptual branch. Automatically triggered when `curator_update_node` is called via MCP.

**Mode C — LLM Logical Deduction** (always runs after A or B):
LLM-based check that top-level conclusions are logically deducible from underlying raw facts. Automatically regenerates broken Concept or Exhibition pages unless `--no-fix` is passed.

Finalization: Upon completion, wiki sync automatically rebuilds all routing tables and tracking logs (index.md, ledger.md, log.md, and overview.md).

```text
wiki sync [NODE_ID] [--dry-run] [--no-fix]
```

4.6. Semantic Search & Querying

`wiki query "QUESTION"`: Search and synthesize a referenced answer using the qmd indexing engine (BM25 + vector + LLM rerank). Entering interactive chat mode when called without an argument.

```text
wiki query "QUESTION" [--mode hybrid|lex|vec] [--scope all|...] [--save-as TITLE]
```

4.7. Index & Health

```text
wiki reindex              Force-rebuild the qmd semantic & lexical search index.
wiki lint [--deep] [--fix] Health checks: orphan nodes, broken wikilinks, contradictions.
```

4.8. LLM Configuration

```text
wiki config provider        Switch and configure LLM backend interactively.
wiki config models list     List available Ollama models.
wiki config models use      Select an Ollama model interactively.
```

4.9. Agent Services & MCP Server

```text
wiki mcp              Start the MCP stdio server for workspace agent integration.
wiki mcp install      Print a config snippet for Claude / Gemini IDE integration.
```

The system exposes an MCP stdio server to integrate directly with LLM workspaces and agents. Agents manage the DAG via the following exposed tools:

`search_curator(query, scope, mode, limit, min_score)`: Semantic and lexical search across the Curator DAG via qmd (BM25 + vector + LLM rerank). USE THIS before any raw directory search.

`curator_get_node(node_id)`: Fetch a single DAG node (CTX-/ATM-/CON-/EXH-) by ID. Returns frontmatter + body.

`curator_traverse_evidence(exh_id)`: Walk an Exhibition's full evidence chain (EXH → CON → ATM). Required before citing any Exhibition with confidence_score < 0.90.

`curator_find_contradictions(node_id=None)`: List Atoms flagged for review or carrying contradicts entries. Scoped to a subgraph if node_id given.

`curator_layer_index()`: Return per-layer page counts and recent IDs. Use as the first call when entering a fresh vault.

`curator_status()`: Return vault root, qmd readiness, and total page counts.

`curator_update_node(node_id, new_content)`: Overwrites a DAG node's markdown file. Automatically triggers wiki sync Mode B (targeted bidirectional propagation) + Mode C (LLM logical deduction), then rebuilds all routing tables. Requires HITL approval before calling.

`curator_reindex()`: Force-rebuild the qmd semantic & lexical search index after modifications.

`curator_curate_accession(context_id)`: Triggers a re-run of the pipeline for a specific Layer 1 Context to correct cascading errors down to Layers 2-4.

5. Pipeline Rules & Agent Workflow (Critical)

To prevent hallucinations and maintain absolute data integrity, all entities and AI Agents must adhere to the 3-Phase Agent-Curator Workflow:

Phase 1: Pre-requisite Discovery (The Compiler's Bridge)

Before answering queries or executing tasks, Artists (Agents) do not blindly perform exhaustive searches across raw directories.

Rule: The Agent must first call `curator_layer_index()` to understand vault scope, then `search_curator()` to traverse the .curator/ directory and pull verified prior knowledge (Exhibitions) via the qmd search index.

Phase 2: Validation & Strong Negotiation (HITL)

Agents must cross-reference the retrieved .curator/ knowledge with the original source files (e.g., 03_Notes/).

Rule: If the system detects logical contradictions or misconceptions, it cannot arbitrarily modify the source. The Agent must immediately halt, flag the error to the Human (Director), and initiate a debate (e.g., "⚠️ I detected a misconception in 02_Atoms/ATM-abc.md. Do you want me to update it?").

If an Exhibition has confidence_score < 0.60: call `curator_traverse_evidence()` and `curator_find_contradictions()` before proceeding, and halt for human review.

Phase 3: Automatic Re-curation & Propagation (The Infinite Knowledge Creation Loop)

Upon human approval, the Agent implements the fix using the MCP tools.

Rule (Bidirectional Tracking): The Agent calls `curator_update_node(node_id, new_content)`. This writes the file, then automatically invokes wiki sync in Targeted Bidirectional Mode (Mode B + Mode C) centering on the altered file:

- **Upstream Alignment**: Verifies if the underlying L1 Context still logically aligns.
- **Downstream Cascade**: Automatically invalidates and updates any connected L3 Concepts and L4 Exhibitions.
- **Finalization**: Forces an immediate update of all core routing indexes and tracking files (index.md, ledger.md, log.md, overview.md).

Finally, the Agent calls `curator_reindex()` to rebuild the qmd search index cleanly.

→ Exhibition: Fully vetted and synchronized contexts are then exhibited back into 02_Wiki/, endlessly expanding the Infinite Knowledge Creation Loop back into L1 ingestion, with DAG integrity maintained via state.sqlite.

Section 6. Confidence Decision Tree

```text
EXH confidence_score:
>= 0.90  DIRECT_RETRIEVAL  — Agent can cite directly without backtracking.
0.60-0.90 PARTIAL_BACKTRACK — Run curator_traverse_evidence (CON -> ATM) before citing.
< 0.60   FULL_VERIFICATION  — Halt. Trigger STRONG_NEGOTIATION with human (Director).
                              Set is_flagged_for_agent: true on relevant ATMs.
```

Section 7. Immutability Rules

- Never modify 04_Resources/ or 06_Archives/ — treat as read-only constants.
- Never modify 03_Notes/ autonomously — human-verified truth (Director's domain), requires HITL.
- Never delete a .curator/Collections/ page without explicit user confirmation.
- Never overwrite existing atom claims silently — append an `## Updates [date]` section instead.
- Never invent citations — if a claim has no traceable ATM-UUID, mark confidence_score < 0.60.
- Never bypass state.sqlite — it is the source of truth for deduplication and provenance.
- Never access .curator/ files directly — use MCP tools exclusively.
