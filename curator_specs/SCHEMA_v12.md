SCHEMA.md — Curator Schema & Operating Conventions (v12.0)

Audience: LLM Curator engine & Workspace Agents.
This file defines the contract for building and maintaining the .curator/ DAG knowledge lake under the SYMBIOTIC_OS_ARCHITECTURE v12.0.
The Curator reads source dirs (02_Wiki, 03_Notes, 04_Resources, 06_Archives) and writes
exclusively to .curator/. Human readability inside .curator/ is NOT a design goal.

1. Directory Layout

ROOT/
├── 00_System/          # [STATIC] Scripts & Templates
├── 01_Workspaces/      # [AGENT_RESIDENCE] Knowledge synthesis & execution space (contains qmd.yml)
├── 02_Wiki/            # [SHARED_TRUTH] Official Exhibition managed by Agent & Curator
├── 03_Notes/           # [HUMAN_TRUTH] 100% Human-verified source knowledge (Agent needs HITL to edit)
├── 04_Resources/       # [READ_ONLY] External reference PDFs, Docs (Immutable)
├── 05_Assets/          # [STATIC] System byproducts (Images, Zotero assets)
├── 06_Archives/        # [READ_ONLY] Terminated projects & legacy data
└── .curator/           # [CURATOR_RESIDENCE] Hidden Abstraction Space (WRITE ONLY for Curator)
    ├── config.yml      # Project configuration
    ├── state.sqlite    # Hash registry & ingest tracking DB
    ├── overview.md     # [ROUTING] Domain manifest
    ├── index.md        # [ROUTING] Layer → ID pointer table (auto-rebuilt)
    ├── log.md          # [STATE] Ingest event log & hash tracking (auto-appended)
    ├── ledger.md       # [STATE] Hash tracking & mandatory HITL correction logs
    └── Collections/
        ├── 01_Accessions/  # L1: ACC-UUID.md — 1:1 hash-matched original summaries
        ├── 02_Fragments/   # L2: FRG-UUID.md — Irreducible knowledge fragments/atoms
        ├── 03_Themes/      # L3: THM-UUID.md — Thematic clusters of fragments
        └── 04_Curations/   # L4: CUR-UUID.md — Terminal packaged contexts for Agents


Write boundary: The Curator MUST NOT modify any file outside .curator/ autonomously.

2. ID System

All pages use prefixed UUID4 IDs (8 hex chars):

Layer

Prefix

Example

L1 Accession

ACC-

ACC-a1b2c3d4

L2 Fragment

FRG-

FRG-9f8e7d6c

L3 Theme

THM-

THM-12345678

L4 Curation

CUR-

CUR-abcdef01

IDs are generated once at page creation and never change. File names are {ID}.md.

3. Metadata Schemas

All timestamps: ISO 8601 (YYYY-MM-DDThh:mm:ssZ). Stored ONLY in .curator/Collections/.

3.1 L1: ACCESSION

---
id: ACC-[UUID8]
type: accession
source_path: "[[relative/path/to/source.md]]"
source_hash: [SHA-256]
domain: "knowledge-domain-string"
last_updated: YYYY-MM-DDThh:mm:ssZ
tags: [tag1, tag2]
---


Body sections: ## Summary, ## Key Claims, ## Fragmentation Candidates, ## Source

3.2 L2: FRAGMENT

---
id: FRG-[UUID8]
type: fragment
parent_source: "[[01_Accessions/ACC-UUID8]]"
claim_type: fact | equation | theoretical_constraint
contradicts: []       # List of FRG-UUIDs with conflicting claims
is_verified_by_human: false
is_flagged_for_agent: false
last_updated: YYYY-MM-DDThh:mm:ssZ
---


Body sections: ## Definition / Claim, ## Context, ## Constraints, ## Relations, ## Source

Use LaTeX for equations: $E = mc^2$, $$\nabla \cdot E = \rho/\varepsilon_0$$

Cross-reference via [[02_Fragments/FRG-UUID8]]

If a new source contradicts existing fragment: set contradicts: ["FRG-other"] and is_flagged_for_agent: true

3.3 L3: THEME

---
id: THM-[UUID8]
type: theme
dependencies: ["[[02_Fragments/FRG-UUID8]]", "[[02_Fragments/FRG-UUID8]]"]
domain: "knowledge-domain-string"
last_updated: YYYY-MM-DDThh:mm:ssZ
---


Body sections: ## 1. Core Architecture, ## 2. Interaction of Fragments, ## 3. Open Questions

Minimum 2 fragment dependencies per theme

Do NOT create singleton themes (1 fragment = 1 theme is redundant)

3.4 L4: CURATION

---
id: CUR-[UUID8]
type: curation
core_themes: ["[[03_Themes/THM-UUID8]]"]
confidence_score: 0.00 - 1.00
last_updated: YYYY-MM-DDThh:mm:ssZ
---


Body sections: ## 1. Executive Brief, ## 2. Theoretical Foundation, ## 3. Actionable Directives for Agent

4. Pipeline Phases

Phase 0 — SOURCE INGESTION (wiki add)

(Legacy: wiki sync)

Trigger: New or changed files detected in source dirs.
Action: For each new file:

Register in state.sqlite with SHA-256 hash and status=pending.

Generate 01_Accessions/ACC-UUID.md.

Record accession_id in DB & log.md.

Phase 1 — TOP-DOWN EXTRACTION (wiki curate)

(Legacy: wiki ingest)

Trigger: Sources with status=pending in DB.
Action: Runs the downward extraction pipeline.

Pass 1 (Fragments): Extract L2 Fragments from L1 Accession. Check contradictions.

Pass 2 (Themes): Cluster related L2 Fragments into L3 Themes.

Pass 3 (Curations): Bundle L3 Themes into L4 Curations context for Agents.

Optional: Use wiki curate --sync to automatically run deductive verification immediately after extraction.

Phase 2 — DEDUCTIVE VERIFICATION & LOGIC ALIGNMENT (wiki sync)

(NEW in v12.0)

Trigger: Executed manually, via --sync flag, or automatically triggered by DB modifications via MCP.
Action: Dynamically switches between two modes:

Global Reverse Verification (No DB mods): Traces L4 $\rightarrow$ L1 to ensure top-level conclusions are deducible from raw facts. Flags logical gaps.

Targeted Bidirectional Propagation (DB mods detected): Traces upstream (to L1) and downstream (to L4) centering strictly on the modified node to mend and re-align the conceptual branch.
Finalization: Auto-rebuilds routing tables (index.md, ledger.md, log.md, overview.md).

5. Control-Plane Files

.curator/index.md

Auto-rebuilt after every wiki sync / wiki curate. Format:

| CUR_ID | TARGET_TOPIC | CONFIDENCE | EVIDENCE_CHAIN |
|---|---|---|---|
| CUR-abcdef01 | Topic name | 0.95 | [[THM-12345678]], [[FRG-9f8e7d6c]] |


.curator/log.md

Append-only. Format:

## [YYYY-MM-DDThh:mm:ssZ] add | Source Title
- created: [[02_Fragments/FRG-9f8e7d6c]]
- updated: [[02_Fragments/FRG-a1b2c3d4]]
- created: [[03_Themes/THM-12345678]]


.curator/ledger.md

Mandatory HITL Log. This file stores human-verified interventions. Whenever an Agent halts to flag a logical contradiction and receives user authorization to fix it, the executed resolution is appended here for auditability.

6. Wikilink Convention

Internal cross-references: [[LAYER/ID]] — e.g., [[02_Fragments/FRG-9f8e7d6c]]

Never use plain markdown links for cross-references inside .curator/

Ledger overrides: [[.curator/ledger]]

7. Confidence Decision Tree

CUR confidence_score:

>= 0.90 → DIRECT_RETRIEVAL: Agent can cite directly without backtracking
0.60–0.90 → PARTIAL_BACKTRACK: Traverse EVIDENCE_CHAIN (THM → FRG nodes) before citing
< 0.60  → FULL_VERIFICATION: Halt. Trigger STRONG_NEGOTIATION with human.
           Set is_flagged_for_agent: true on relevant FRGs.


8. Immutability Rules

❌ Never modify 04_Resources/ or 06_Archives/ — treat as read-only constants.

❌ Never modify 03_Notes/ autonomously — human-verified truth. Read only.
If 03_Notes contradicts a FRG: flag the FRG (is_flagged_for_agent: true), initiate Human-In-The-Loop (HITL), do NOT silently overwrite.

❌ Never delete a .curator/Collections/ page without explicit user confirmation.

❌ Never overwrite existing fragment claims silently — use ## Updates [date] sections.

❌ Never invent citations — if a claim has no traceable FRG-UUID, mark confidence_score < 0.60.

9. Mandatory HITL & Correction Protocol (Ledger)

In v12.0, the Curator and Agents CANNOT silently override conflicting claims. If a misconception or logical contradiction is found:

HALT: Stop execution. Do not arbitrarily modify the source or DAG node.

FLAG: Trigger a debate with the Human (e.g., "⚠️ I detected a misconception in FRG-9f8e7d6c. Do you want me to update it?").

APPLY: Upon explicit human approval, the Agent updates the node using the curator_update_node MCP tool.

LOG: The resolution is automatically appended to .curator/ledger.md as an immutable audit trail.

10. Agent Workflow & MCP Tooling

All AI Workspace Agents MUST adhere to the following 3-Phase Workflow to interact with the DAG:

Phase 1: Pre-requisite Discovery

Agents MUST use search_curator MCP tool to pull prior knowledge via the qmd search index from .curator/.

Phase 2: Validation & Strong Negotiation (HITL)

Cross-reference retrieved data with raw sources. If contradictions exist, follow the Mandatory HITL Protocol (Section 9).

Phase 3: Automatic Re-curation & Propagation

Upon human approval, Agent applies fixes using curator_update_node(node_id, new_content).

For cascading L1 extraction errors, Agent can use curator_curate_accession() to force a top-down re-run.

Modifying a node logs the change in state.sqlite, triggering wiki sync (Targeted Bidirectional Mode) to align the DAG.

Agent finally calls curator_reindex() to cleanly update semantic/lexical search bases.

This file evolves with the pipeline. Update when conventions change and commit.