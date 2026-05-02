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

ROOT: /
├── 00_System/          # [STATIC] Scripts & Templates
├── 01_Workspaces/      # [AGENT_RESIDENCE] Knowledge synthesis & execution space
│   └── {Project_Name}/
│       ├── .agents/ & .antigravity/ # Agent skills, personas, and control limits
│       ├── Artifacts/        # Auto-generated code, intermediate outputs
│       ├── Concepts/         # Draft concepts pending human consensus
│       ├── Papers/           # Project-specific literature review sandbox
│       ├── Research Notes/   # Daily research tracking
│       ├── qmd.yml           # 🌟 Context loader defining prior knowledge for the agent
│       └── research_digest.md, todo_list.md, methodology.md
│
├── 02_Wiki/            # [SHARED_TRUTH] Official Exhibition managed by Agent & Curator
├── 03_Notes/           # [HUMAN_TRUTH] 100% Human-verified source knowledge (Agent needs HITL to edit)
├── 04_Resources/       # [READ_ONLY] External reference PDFs, Docs (Immutable)
├── 05_Assets/          # [STATIC] System byproducts (Images, Zotero assets)
├── 06_Archives/        # [READ_ONLY] Terminated projects & legacy data
└── .curator/           # [CURATOR_RESIDENCE] Hidden Abstraction Space
    ├── config.yml              # Project configuration
    ├── state.sqlite            # Hash registry & ingest tracking DB
    ├── overview.md & index.md  # Primary routing tables for Agents
    ├── log.md & ledger.md      # Hash tracking and mandatory HITL correction logs
    └── Collections/            # [DATA_PLANE] The L1~L4 DAG Knowledge Pipeline
        ├── 01_Accessions/  # L1: 1:1 Original Summaries
        ├── 02_Fragments/   # L2: Irreducible Knowledge Fragments
        ├── 03_Themes/      # L3: Thematic Clusters
        └── 04_Curations/   # L4: Packaged Contexts for Agents & Humans


2. Polymorphic Metadata Schema (L1-L4)

The Curator structures all knowledge within .curator/Collections/ into a 4-layer extraction and synthesis pipeline:

Layer 1: Accession (ACC-[UUID8])

A 1:1 hash-matched recap and initial registration of a single source document.

---
id: ACC-[UUID8]
type: accession
source_path: "[[relative/path/to/source.md]]"
source_hash: [SHA-256]
domain: "knowledge-domain-string"
last_updated: [YYYY-MM-DDThh:mm:ssZ]
---


Body sections: ## Summary, ## Key Claims, ## Fragmentation Candidates

Layer 2: Fragment (FRG-[UUID8])

Irreducible factual claims or logic blocks (atoms), distilled from one or more L1 Accessions.

---
id: FRG-[UUID8]
type: fragment
parent_source: "[[01_Accessions/ACC-UUID8]]"
claim_type: fact | equation | theoretical_constraint
contradicts: []
is_verified_by_human: false
is_flagged_for_agent: false
last_updated: [YYYY-MM-DDThh:mm:ssZ]
---


Body sections: ## Definition / Claim, ## Context, ## Constraints, ## Relations

Layer 3: Theme (THM-[UUID8])

Clusters of related L2 Fragments forming a coherent contextual or thematic unit.

---
id: THM-[UUID8]
type: theme
dependencies: ["[[02_Fragments/FRG-UUID8]]", "[[02_Fragments/FRG-UUID8]]"]
domain: "knowledge-domain-string"
last_updated: [YYYY-MM-DDThh:mm:ssZ]
---


Body sections: ## 1. Core Architecture, ## 2. Interaction of Fragments, ## 3. Open Questions

Layer 4: Curation (CUR-[UUID8])

Terminal knowledge outputs intricately packaged for Agent injection or conversational reference.

---
id: CUR-[UUID8]
type: curation
core_themes: ["[[03_Themes/THM-UUID8]]"]
confidence_score: 0.00 - 1.00
last_updated: [YYYY-MM-DDThh:mm:ssZ]
---


Body sections: ## 1. Executive Brief, ## 2. Theoretical Foundation, ## 3. Actionable Directives for Agent

3. Installation & Getting Started

To install the project locally with all prerequisites (Ollama, Node.js, and the qmd search engine) in one command, run:

chmod +x install.sh
./install.sh


3.1 Initialising a Vault

To scaffold a new wiki vault project with the full topological structure:

wiki init /path/to/your/vault


(Sets up the .obsidian/ marker, 00_System/ through 06_Archives/, and the .curator/ tracking database.)

4. Command-Line Interface (CLI)

The wiki CLI automates everything from file scanning to querying the DAG. (Revamped in v12.0)

4.1. Core Operations

wiki status: Inspect tracking database metrics, active LLM config, and collection counts.

wiki version: View the current installed version.

4.2. Source Ingestion & L1 Registration (wiki add)

wiki add (Legacy: wiki sync): Discovers new or changed files in raw directories (02_Wiki, 03_Notes, 04_Resources) and generates L1 Accession summaries inside .curator/Collections/01_Accessions/. Updates the hash database (state.sqlite) and appends to the event log (log.md).

4.3. Top-Down Extraction (wiki curate)

wiki curate (Legacy: wiki ingest): Runs the downstream extraction pipeline (L1 $\rightarrow$ L2 $\rightarrow$ L3 $\rightarrow$ L4). It extracts L2 Fragments, builds L3 Themes, and bundles L4 Curations context.

Optional Reverse Verification: You can optionally append the --sync flag to automatically execute the global reverse verification (L4 $\rightarrow$ L1 logic alignment) immediately after the downward extraction is complete.

wiki curate [--batch] [--no-thinking] [--sync]


4.4. Deductive Verification & Logic Alignment (wiki sync)

wiki sync (NEW in v12.0): Acts as the core Logic Alignment Engine that dynamically switches between two operational modes based on the tracking database (DB) state. Crucially, upon completion of either mode, wiki sync automatically regenerates all routing tables and tracking logs (index.md, ledger.md, log.md, and overview.md) to reflect the newly synchronized DAG state.

Global Reverse Verification (No DB Modifications Detected): This is executed either explicitly via the standalone wiki sync command or dynamically if the --sync flag is passed during wiki curate. If the DB indicates no targeted file modifications have occurred, the engine defaults to a top-down logical validation. It starts at Layer 4 (Curations) and traces claims backwards all the way down to Layer 1 (Accessions) to verify if top-level conclusions are logically deducible from the underlying raw facts. If a logical gap is found, it prompts the user (HITL) and propagates corrections.

Targeted Bidirectional Propagation (DB Modifications Detected): When an Agent modifies a specific node (e.g., L2 or L3) via the MCP server, the DB logs this modification. Upon invocation, wiki sync reads the DB, identifies the explicitly modified file, and automatically triggers bidirectional matching. It traces both upstream (to L1) and downstream (to L4) strictly from that modified file to dynamically mend and re-align the affected conceptual branch.

4.5. Semantic Search & Querying

wiki query "<your question>": Search and curate a referenced answer using the qmd indexing engine.

4.6. Agent Services & MCP Tools

The system exposes an MCP stdio server to integrate directly with LLM workspaces and agents. Agents can manage the DAG via the following exposed tools:

search_curator: Pulls background context from the local .curator/ Collections and raw files.

curator_update_node(node_id, new_content): Overwrites or updates a specific DAG node's content. The DB tracks this modification, which subsequently forces wiki sync into its bidirectional propagation mode.

curator_reindex(): Force-rebuilds the qmd semantic & lexical search index after modifications.

curator_curate_accession(): Triggers a re-run of the pipeline for specific Layer 1 Accessions to correct cascading errors down to Layers 2-4.

5. Pipeline Rules & Agent Workflow (⚠️ Critical)

To prevent hallucinations and maintain absolute data integrity, all entities and AI Agents must adhere to the 3-Phase Agent-Curator Workflow:

Phase 1: Pre-requisite Discovery (The Curator's Bridge)

Before answering queries or executing tasks, Agents do not blindly perform exhaustive searches across raw directories.

Rule: The Agent must first query search_curator to traverse the .curator/ directory and pull verified prior knowledge via the qmd search index.

Phase 2: Validation & Strong Negotiation (HITL)

Agents must cross-reference the retrieved .curator/ knowledge with the original source files (e.g., 03_Notes).

Rule: If the system detects logical contradictions or misconceptions, it cannot arbitrarily modify the source. The Agent must immediately halt, flag the error to the Human, and initiate a debate (e.g., "⚠️ I detected a misconception in 02_Fragments/FRG-abc.md. Do you want me to update it?").

Phase 3: Automatic Re-curation & Propagation (The Infinite Loop)

Upon human approval, the Agent implements the fix using the MCP tools. When any file in the .curator/ abstraction space is modified, the DB flags the system that the conceptual branch is out of sync.

Rule (Bidirectional Tracking via DB): The Agent calls curator_update_node, updating the file on disk. The state.sqlite DB logs this modification. The Curator then automatically invokes wiki sync. Recognizing the state.sqlite modification, wiki sync enters Targeted Bidirectional Mode centering on the altered file:

Upstream Alignment: Verifies if the underlying L1 Accession still logically aligns.

Downstream Cascade: Automatically invalidates and updates any connected L3 Themes and L4 Curations.

Finalization: Upon successful logic alignment, wiki sync forces an immediate update of all core routing indexes and tracking files (index.md, ledger.md, log.md, overview.md). Finally, the Agent calls curator_reindex to rebuild the qmd search index cleanly.

$\rightarrow$ Exhibition: Fully vetted and synchronized contexts are then exhibited back into 02_Wiki, endlessly expanding the knowledge ecosystem loop.