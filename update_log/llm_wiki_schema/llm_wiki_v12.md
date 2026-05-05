SYMBIOTIC_OS_ARCHITECTURE - Agentic Zettelkasten Curator (v12.0)

LLM-Wiki Curator is an autonomous, AI-maintained personal knowledge base designed for the SYMBIOTIC_OS_ARCHITECTURE v12.0. It functions as a Multi-Agent DAG (Directed Acyclic Graph) RAG system built to manage fragmented knowledge assets and execute complex projects safely without hallucinations.

By restructuring the philosophy of the Zettelkasten into a Data Curation architecture, the Curator Engine ensures that all external information passes through a strict 4-layer refinement pipeline.

1. Entity Roles & Global Topology

The system operates through the organic interaction of three core entities: Human, Curator Engine, and Workspace Agent.

1.1 Entities & Permissions

👤 Entity Human

Domain: 03_Notes/

Role: The creator and owner of primary source knowledge. The Human is the ultimate decision-maker for knowledge synthesis, reviewing proposals from Agents/Curators and reaching consensus through Human-in-the-Loop (HITL) conversations.

⚙️ Entity Curator (Curator Engine)

Domain: .curator/ (Hidden space, exclusive read/write access)

Role: A background engine that independently executes the 4-layer pipeline (Accession $\rightarrow$ Fragmentation $\rightarrow$ Thematization $\rightarrow$ Context Packaging) to maintain the massive knowledge graph (DAG). It does not create new knowledge on its own; it strictly focuses on assembling information and supporting dialogue.

🤖 Entity Agent (Workspace Agent)

Domain: 01_Workspaces/{Project_Name}/

Role: The active executor that performs project tasks (coding, planning, analysis) based on human commands and contexts provided by the Curator (qmd.yml). It promotes agreed-upon knowledge to 02_Wiki (Exhibition).

1.2 Topology Map

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
│       ├── qmd.yml           # Context loader defining prior knowledge for the agent
│       └── research_digest.md, todo_list.md, methodology.md
│
├── 02_Wiki/            # [SHARED_TRUTH] Official Exhibition managed by Agent & Curator
├── 03_Notes/           # [HUMAN_TRUTH] 100% Human-verified source knowledge (Agent needs HITL to edit)
├── 04_Resources/       # [READ_ONLY] External reference PDFs, Docs (Immutable)
├── 05_Assets/          # [STATIC] System byproducts (Images, Zotero assets)
├── 06_Archives/        # [READ_ONLY] Terminated projects & legacy data
└── .curator/           # [CURATOR_RESIDENCE] Hidden Abstraction Space
    ├── config.yml              # LLM backend, model, raw_dirs, collections_dir
    ├── state.sqlite            # Hash registry & ingest tracking DB (source-of-truth for dedup/provenance)
    ├── overview.md & index.md  # Primary routing tables for Agents (auto-rebuilt)
    ├── log.md & ledger.md      # Append-only event log and mandatory HITL correction record
    └── Collections/            # [DATA_PLANE] The L1~L4 DAG Knowledge Pipeline
        ├── 01_Accessions/  # L1: 1:1 Original Summaries
        ├── 02_Fragments/   # L2: Irreducible Knowledge Fragments
        ├── 03_Themes/      # L3: Thematic Clusters
        └── 04_Curations/   # L4: Packaged Contexts for Agents & Humans
```

2. Polymorphic Metadata Schema (L1-L4)

The Curator structures all knowledge within .curator/Collections/ into a 4-layer extraction and synthesis pipeline. Node IDs are prefixed UUIDs (ACC-/FRG-/THM-/CUR-) — never human slugs. Human-readable titles live in frontmatter only.

Layer 1: Accession (ACC-[UUID8])

A 1:1 hash-matched recap and initial registration of a single source document.

```yaml
id: ACC-[UUID8]
type: accession
source_path: "[[relative/path/to/source.md]]"
source_hash: [SHA-256]
domain: "knowledge-domain-string"
last_updated: [YYYY-MM-DDThh:mm:ssZ]
tags: [tag1, tag2]
```

Body sections: Summary, Key Claims, Fragmentation Candidates, Source

Layer 2: Fragment (FRG-[UUID8])

Irreducible factual claims or logic blocks (atoms), distilled from one or more L1 Accessions.

```yaml
id: FRG-[UUID8]
type: fragment
parent_source: "[[01_Accessions/ACC-UUID8]]"
claim_type: fact | equation | theoretical_constraint
contradicts: []
is_verified_by_human: false
is_flagged_for_agent: false
last_updated: [YYYY-MM-DDThh:mm:ssZ]
```

Body sections: Definition / Claim, Context, Constraints, Relations, Source

If a fragment claim is later contradicted: set `contradicts: ["FRG-other"]` and `is_flagged_for_agent: true`. Do NOT silently overwrite — append an `## Updates [date]` section.

Layer 3: Theme (THM-[UUID8])

Clusters of related L2 Fragments forming a coherent contextual or thematic unit. Minimum 2 fragment dependencies required — singleton themes (1 fragment) are redundant.

```yaml
id: THM-[UUID8]
type: theme
dependencies: ["[[02_Fragments/FRG-UUID8]]", "[[02_Fragments/FRG-UUID8]]"]
domain: "knowledge-domain-string"
last_updated: [YYYY-MM-DDThh:mm:ssZ]
```

Body sections: 1. Core Architecture, 2. Interaction of Fragments, 3. Open Questions

Layer 4: Curation (CUR-[UUID8])

Terminal knowledge outputs intricately packaged for Agent injection or conversational reference.

```yaml
id: CUR-[UUID8]
type: curation
core_themes: ["[[03_Themes/THM-UUID8]]"]
confidence_score: 0.00 - 1.00
last_updated: [YYYY-MM-DDThh:mm:ssZ]
```

Body sections: 1. Executive Brief, 2. Theoretical Foundation, 3. Actionable Directives for Agent

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

The wiki CLI automates everything from file scanning to querying the DAG. (Revamped in v12.0)

4.1. Core Operations

`wiki status`: Inspect tracking database metrics, active LLM config, and collection counts.

`wiki version`: View the current installed version.

4.2. Source Ingestion & L1 Registration (wiki add)

`wiki add PATH [-r]`: Discovers new or changed files in raw directories (02_Wiki, 03_Notes, 04_Resources) and generates L1 Accession summaries inside .curator/Collections/01_Accessions/. Updates the hash database (state.sqlite) and appends to the event log (log.md).

4.3. Source Management (wiki sources)

```text
wiki sources list          List all tracked source files.
wiki sources show ID       Show details for one source (with text preview).
wiki sources rm ID         Remove a source from tracking.
wiki sources retry ID      Retry a previously failed source.
```

4.4. Top-Down Extraction (wiki curate)

`wiki curate [SOURCE_ID]`: Runs the downstream extraction pipeline (L1 $\rightarrow$ L2 $\rightarrow$ L3 $\rightarrow$ L4) via three sequential LLM passes:

- **Pass 1** (thinking mode): Extract L2 Fragments from each L1 Accession. Checks for contradictions.
- **Pass 2**: Cluster Fragments into L3 Themes. This is a cross-source operation — it runs only after ALL Pass 1 outputs are complete. The pipeline is sequential, not parallel.
- **Pass 3**: Bundle L3 Themes into L4 Curations.

Then rebuilds index.md and appends to log.md.

```text
wiki curate [--force] [--batch] [--no-thinking] [--sync]
```

Optional: Append `--sync` to automatically execute global reverse verification (wiki sync) immediately after extraction.

4.5. Deductive Verification & Logic Alignment (wiki sync)

`wiki sync [NODE_ID]` (NEW in v12.0): The core Logic Alignment Engine. Runs structural verification (Mode A or B) followed by LLM logical deduction (Mode C always), then rebuilds all routing tables.

**Mode A — Global Structural Verification** (no NODE_ID):
Traces L4 $\rightarrow$ L1, verifying all wikilinks and dependencies are intact. Flags broken references and missing nodes. Triggered by standalone `wiki sync` or the `--sync` flag on `wiki curate`.

**Mode B — Targeted Bidirectional Propagation** (NODE_ID given):
Traces both upstream (to L1) and downstream (to L4) from the specified node to mend the affected conceptual branch. Automatically triggered when `curator_update_node` is called via MCP.

**Mode C — LLM Logical Deduction** (always runs after A or B):
LLM-based check that top-level conclusions are logically deducible from underlying raw facts. Automatically regenerates broken Theme or Curation pages unless `--no-fix` is passed.

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

`curator_get_node(node_id)`: Fetch a single DAG node (ACC-/FRG-/THM-/CUR-) by ID. Returns frontmatter + body.

`curator_traverse_evidence(cur_id)`: Walk a Curation's full evidence chain (CUR $\rightarrow$ THM $\rightarrow$ FRG). Required before citing any Curation with confidence_score < 0.90.

`curator_find_contradictions(node_id=None)`: List Fragments flagged for review or carrying contradicts entries. Scoped to a subgraph if node_id given.

`curator_layer_index()`: Return per-layer page counts and recent IDs. Use as the first call when entering a fresh vault.

`curator_status()`: Return vault root, qmd readiness, and total page counts.

`curator_update_node(node_id, new_content)`: Overwrites a DAG node's markdown file. Automatically triggers wiki sync Mode B (targeted bidirectional propagation) + Mode C (LLM logical deduction), then rebuilds all routing tables. Requires HITL approval before calling.

`curator_reindex()`: Force-rebuild the qmd semantic & lexical search index after modifications.

`curator_curate_accession(accession_id)`: Triggers a re-run of the pipeline for a specific Layer 1 Accession to correct cascading errors down to Layers 2-4.

5. Pipeline Rules & Agent Workflow (Critical)

To prevent hallucinations and maintain absolute data integrity, all entities and AI Agents must adhere to the 3-Phase Agent-Curator Workflow:

Phase 1: Pre-requisite Discovery (The Curator's Bridge)

Before answering queries or executing tasks, Agents do not blindly perform exhaustive searches across raw directories.

Rule: The Agent must first call `curator_layer_index()` to understand vault scope, then `search_curator()` to traverse the .curator/ directory and pull verified prior knowledge via the qmd search index.

Phase 2: Validation & Strong Negotiation (HITL)

Agents must cross-reference the retrieved .curator/ knowledge with the original source files (e.g., 03_Notes/).

Rule: If the system detects logical contradictions or misconceptions, it cannot arbitrarily modify the source. The Agent must immediately halt, flag the error to the Human, and initiate a debate (e.g., "⚠️ I detected a misconception in 02_Fragments/FRG-abc.md. Do you want me to update it?").

If a Curation has confidence_score < 0.60: call `curator_traverse_evidence()` and `curator_find_contradictions()` before proceeding, and halt for human review.

Phase 3: Automatic Re-curation & Propagation (The Infinite Loop)

Upon human approval, the Agent implements the fix using the MCP tools.

Rule (Bidirectional Tracking): The Agent calls `curator_update_node(node_id, new_content)`. This writes the file, then automatically invokes wiki sync in Targeted Bidirectional Mode (Mode B + Mode C) centering on the altered file:

- **Upstream Alignment**: Verifies if the underlying L1 Accession still logically aligns.
- **Downstream Cascade**: Automatically invalidates and updates any connected L3 Themes and L4 Curations.
- **Finalization**: Forces an immediate update of all core routing indexes and tracking files (index.md, ledger.md, log.md, overview.md).

Finally, the Agent calls `curator_reindex()` to rebuild the qmd search index cleanly.

$\rightarrow$ Exhibition: Fully vetted and synchronized contexts are then exhibited back into 02_Wiki, endlessly expanding the knowledge ecosystem loop.

Section 6. Confidence Decision Tree

```text
CUR confidence_score:
>= 0.90  DIRECT_RETRIEVAL  — Agent can cite directly without backtracking.
0.60-0.90 PARTIAL_BACKTRACK — Run curator_traverse_evidence (THM -> FRG) before citing.
< 0.60   FULL_VERIFICATION  — Halt. Trigger STRONG_NEGOTIATION with human.
                              Set is_flagged_for_agent: true on relevant FRGs.
```

Section 7. Immutability Rules

- Never modify 04_Resources/ or 06_Archives/ — treat as read-only constants.
- Never modify 03_Notes/ autonomously — human-verified truth, requires HITL.
- Never delete a .curator/Collections/ page without explicit user confirmation.
- Never overwrite existing fragment claims silently — append an `## Updates [date]` section instead.
- Never invent citations — if a claim has no traceable FRG-UUID, mark confidence_score < 0.60.
- Never bypass state.sqlite — it is the source of truth for deduplication and provenance.
- Never access .curator/ files directly — use MCP tools exclusively.
