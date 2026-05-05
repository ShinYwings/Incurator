SCHEMA.md — Curator Schema & Operating Conventions (v13.0)

> **v13.0 Changelog (from v12.0)**
> 1. **[RENAME] Layer Names & Directory Paths**: All four collection directories and their node ID prefixes have been renamed to match the Compiler/Artist metaphor system.
>    - L1 Accession (`01_Accessions/`, `ACC-`) → **L1 Context** (`01_Contexts/`, `CTX-`)
>    - L2 Fragment (`02_Fragments/`, `FRG-`) → **L2 Atom** (`02_Atoms/`, `ATM-`)
>    - L3 Theme (`03_Themes/`, `THM-`) → **L3 Concept** (`03_Concepts/`, `CON-`)
>    - L4 Curation (`04_Curations/`, `CUR-`) → **L4 Exhibition** (`04_Exhibitions/`, `EXH-`)
> 2. **[NEW] Two-Track Architecture** label applied to the `.curator/` vs `02_Wiki/` split.
> 3. **[NEW] Entity Metaphor System**: Human=Director, Curator=Compiler, Agent=Artist — reflected in section headers and HITL protocol descriptions.
> 4. **[UPDATE] Schema fields**: `parent_source` now references `01_Contexts/CTX-*`; `core_themes` field on L4 renamed to `core_concepts` referencing `03_Concepts/CON-*`; `contradicts` on L2 now references `ATM-` IDs.
> 5. **[UPDATE] MCP tool signatures**: `curator_traverse_evidence` now walks `EXH → CON → ATM`; `curator_curate_accession` parameter renamed to `context_id`; `scope` values on `search_curator` updated to new layer names.
> 6. **[FACTCHECK] Frontmatter corrections** (aligned with actual generated files):
>    - L2 `parent_source`: plain string path (no wikilink brackets), e.g. `"01_Contexts/CTX-UUID8"`
>    - L2: added `source_path` and `confidence_score` fields (present in generated output)
>    - L3 `dependencies`: YAML bare-list format `[[[...]], [[...]]]`, not quoted-string array
>    - L3: added `confidence_score` field
>    - L4 `core_concepts`: same YAML bare-list format `[[[...]], [[...]]]`
> 7. **[FACTCHECK] Body section corrections** (aligned with actual generated files):
>    - L1: only `## Summary` is a fixed required header; subsequent sections are content-specific numbered sections (LLM-driven, not prescribed)
>    - L2: `## Source` does not exist; `## Relations` is the terminal section (contains wikilinks back to parent)
>    - L3: added `## 3. Mathematical Framework` section (between Interaction and Open Questions) and `## Relations` terminal section
>    - L4: body uses `- **1. Executive Brief**:` bold-bullet format, NOT `##` section headers

---

Audience: LLM Curator engine (Compiler) & Workspace Agents (Artists).
This file defines the contract for building and maintaining the .curator/ DAG knowledge lake under the SYMBIOTIC_OS_ARCHITECTURE v13.0.
The Curator reads source dirs (02_Wiki, 03_Notes, 04_Resources, 06_Archives) and writes
exclusively to .curator/. Human readability inside .curator/ is NOT a design goal.

1. Directory Layout

ROOT/
├── 00_System/          # [STATIC] Scripts & Templates
├── 01_Workspaces/      # [AGENT_RESIDENCE] Knowledge synthesis & execution space (contains qmd.yml)
├── 02_Wiki/            # [SHARED_TRUTH] Two-Track Human-Friendly Space — Official Exhibition
├── 03_Notes/           # [HUMAN_TRUTH] 100% Human-verified source knowledge (Agent needs HITL to edit)
├── 04_Resources/       # [READ_ONLY] External reference PDFs, Docs (Immutable)
├── 05_Assets/          # [STATIC] System byproducts (Images, Zotero assets)
├── 06_Archives/        # [READ_ONLY] Terminated projects & legacy data
└── .curator/           # [CURATOR_RESIDENCE] Two-Track Machine-Readable Backend (WRITE ONLY for Curator)
    ├── config.yml      # Project configuration (LLM backend, model, raw_dirs, collections_dir)
    ├── state.sqlite    # Hash registry & ingest tracking DB (source-of-truth for dedup/provenance)
    ├── overview.md     # [ROUTING] Domain manifest
    ├── index.md        # [ROUTING] Layer → ID pointer table (auto-rebuilt)
    ├── log.md          # [STATE] Ingest event log & hash tracking (auto-appended)
    ├── ledger.md       # [STATE] Hash tracking & mandatory HITL correction logs
    └── Collections/
        ├── 01_Contexts/    # L1: CTX-UUID.md — 1:1 hash-matched context summaries
        ├── 02_Atoms/       # L2: ATM-UUID.md — Irreducible atomic knowledge units
        ├── 03_Concepts/    # L3: CON-UUID.md — High-level conceptual clusters of atoms
        └── 04_Exhibitions/ # L4: EXH-UUID.md — Terminal packaged contexts for Agents


Write boundary: The Curator MUST NOT modify any file outside .curator/ autonomously.

2. ID System

All pages use prefixed UUID4 IDs (8 hex chars):

Layer        | Prefix | Example
-------------|--------|----------------
L1 Context   | CTX-   | CTX-a1b2c3d4
L2 Atom      | ATM-   | ATM-9f8e7d6c
L3 Concept   | CON-   | CON-12345678
L4 Exhibition| EXH-   | EXH-abcdef01

IDs are generated once at page creation and never change. File names are {ID}.md.
Human-readable titles live in frontmatter only — never embedded in the ID.

3. Metadata Schemas

All timestamps: ISO 8601 (YYYY-MM-DDThh:mm:ssZ). Stored ONLY in .curator/Collections/.

3.1 L1: CONTEXT

---
id: CTX-[UUID8]
type: context
source_path: "[[relative/path/to/source.md]]"
source_hash: [SHA-256]
domain: "knowledge-domain-string"
last_updated: YYYY-MM-DDThh:mm:ssZ
tags: [tag1, tag2]
---


Body sections: `## Summary` (required, fixed) followed by content-specific numbered sections (LLM-driven, e.g. `## 1. Overview and Prerequisites`, `## 2. ...`). The `## Summary` header is the only prescribed fixed anchor; subsequent structure reflects the source document's natural organization.

3.2 L2: ATOM

---
id: ATM-[UUID8]
type: atom
parent_source: "01_Contexts/CTX-UUID8"
source_path: ""
claim_type: fact | equation | theoretical_constraint
confidence_score: 0.00
contradicts: []       # List of ATM-UUIDs with conflicting claims
is_verified_by_human: false
is_flagged_for_agent: false
last_updated: YYYY-MM-DDThh:mm:ssZ
---


Body sections: ## Definition / Claim, ## Context, ## Constraints, ## Relations

Note: `parent_source` is a plain path string (no wikilink brackets). `source_path` is populated when the atom is derived directly from a file path. `## Relations` is the terminal section and contains wikilinks back to the parent context (no separate `## Source` section).

Use LaTeX for equations: $E = mc^2$, $$\nabla \cdot E = \rho/\varepsilon_0$$

Cross-reference via [[02_Atoms/ATM-UUID8]]

If a new source contradicts existing atom: set contradicts: ["ATM-other"] and is_flagged_for_agent: true

3.3 L3: CONCEPT

---
id: CON-[UUID8]
type: concept
dependencies: [[[02_Atoms/ATM-UUID8]], [[02_Atoms/ATM-UUID8]]]
domain: "knowledge-domain-string"
confidence_score: 0.00
last_updated: YYYY-MM-DDThh:mm:ssZ
---


Body sections: ## 1. Core Architecture, ## 2. Interaction of Atoms, ## 3. Mathematical Framework, ## 4. Open Questions, ## Relations

Note: `dependencies` uses YAML bare-list format with wikilinks directly (not a quoted-string array). `confidence_score` is set by the LLM during generation. `## 3. Mathematical Framework` contains formal equations and definitions where applicable. `## Relations` is a terminal section listing all dependency wikilinks.

Minimum 2 atom dependencies per concept

Do NOT create singleton concepts (1 atom = 1 concept is redundant)

3.4 L4: EXHIBITION

---
id: EXH-[UUID8]
type: exhibition
core_concepts: [[[03_Concepts/CON-UUID8]], [[03_Concepts/CON-UUID8]]]
confidence_score: 0.00 - 1.00
last_updated: YYYY-MM-DDThh:mm:ssZ
---


Body format: bold-bullet list (NOT `##` section headers):

- **1. Executive Brief**: [one-paragraph synthesis of the exhibition topic]
- **2. Theoretical Foundation**: [cross-concept logical chain with inline wikilinks to Concepts and Atoms]
- **3. Actionable Directives for Agent**: [concrete tasks with fragment references and confidence/flagged-atom summary]

Note: `core_concepts` uses YAML bare-list format. The body uses `- **N. Title**:` inline format, not `##` heading sections.

4. Pipeline Phases

Phase 0 — SOURCE INGESTION (wiki add)

Trigger: New or changed files detected in source dirs.
Action: For each new file:

Register in state.sqlite with SHA-256 hash and status=pending.

Generate 01_Contexts/CTX-UUID.md.

Record context_id in DB & log.md.

Phase 1 — TOP-DOWN EXTRACTION (wiki curate)

Trigger: Sources with status=pending in DB.
Action: Runs the downward extraction pipeline via three LLM passes:

Pass 1 (Atoms, thinking mode): Extract L2 Atoms from L1 Context. Check contradictions.

Pass 2 (Concepts): Cluster related L2 Atoms into L3 Concepts.

Pass 3 (Exhibitions): Bundle L3 Concepts into L4 Exhibitions for Agent consumption.

Note: Pass 2 (clustering) must complete after ALL Pass 1 outputs are done — Concepts are
cross-source constructs. The pipeline is sequential, not parallel.

Optional: Use wiki curate --sync to automatically run deductive verification immediately after extraction.

Phase 2 — DEDUCTIVE VERIFICATION & LOGIC ALIGNMENT (wiki sync)

Trigger: Executed manually, via --sync flag, or triggered by curator_update_node via MCP.
Action: Runs three independent modes. Modes A and B handle structural integrity; Mode C
handles logical coherence via LLM.

Mode A — Global Structural Verification (No node_id given):
Traces L4 → L1 to verify all wikilinks and dependencies are intact.
Flags broken references and missing nodes.

Mode B — Targeted Bidirectional Propagation (node_id given):
Centers on the specified node. Traces both upstream (to L1) and downstream (to L4)
to mend and re-align the affected conceptual branch.

Mode C — LLM Logical Deduction (always runs after A or B):
LLM-based check that top-level conclusions are logically deducible from underlying facts.
Flags logical gaps. Automatically regenerates broken Concept/Exhibition pages unless --no-fix.

Finalization: Auto-rebuilds routing tables (index.md, ledger.md, log.md, overview.md).

5. Control-Plane Files

.curator/index.md

Auto-rebuilt after every wiki sync / wiki curate. Uses frontmatter + layer-grouped bullet lists (NOT a table). Format:

```markdown
---
title: "Curator Index"
type: index
updated: YYYY-MM-DDThh:mm:ssZ
---

## L1 — Contexts

- [[01_Contexts/CTX-a1b2c3d4|CTX-a1b2c3d4]]

## L2 — Atoms

- [[02_Atoms/ATM-9f8e7d6c|ATM-9f8e7d6c]]

## L3 — Concepts

- [[03_Concepts/CON-12345678|CON-12345678]]

## L4 — Exhibitions

- [[04_Exhibitions/EXH-abcdef01|EXH-abcdef01]]

---

**Stats:** N contexts · N atoms · N concepts · N exhibitions
```


.curator/log.md

Append-only. Uses frontmatter. Event types: `add` (source ingestion), `curate` (pipeline run), `sync` (verification), `lint` (health check). Format:

```markdown
---
title: Curator Log
type: log
---

## [YYYY-MM-DDThh:mm:ssZ] curate | global pipeline
- created: [[03_Concepts/CON-12345678]]
- created: [[04_Exhibitions/EXH-abcdef01]]

## [YYYY-MM-DD] lint | system
- Ran wiki lint and updated all manifests

## [YYYY-MM-DD] sync | Deductive verification pass
- Routing tables rebuilt by wiki sync
```


.curator/ledger.md

Mandatory HITL Log. This file stores human-verified interventions. Whenever an Agent (Artist) halts to flag a logical contradiction and receives Director (Human) authorization to fix it, the executed resolution is appended here for auditability.

6. Wikilink Convention

Internal cross-references: [[LAYER/ID]] — e.g., [[02_Atoms/ATM-9f8e7d6c]]

Never use plain markdown links for cross-references inside .curator/

Ledger overrides: [[.curator/ledger]]

7. Confidence Decision Tree

EXH confidence_score:

>= 0.90 → DIRECT_RETRIEVAL: Agent can cite directly without backtracking
0.60–0.90 → PARTIAL_BACKTRACK: Traverse EVIDENCE_CHAIN (CON → ATM nodes) before citing
< 0.60  → FULL_VERIFICATION: Halt. Trigger STRONG_NEGOTIATION with human (Director).
           Set is_flagged_for_agent: true on relevant ATMs.


8. Immutability Rules

❌ Never modify 04_Resources/ or 06_Archives/ — treat as read-only constants.

❌ Never modify 03_Notes/ autonomously — human-verified truth (Director's domain). Read only.
If 03_Notes contradicts an ATM: flag the ATM (is_flagged_for_agent: true), initiate Human-In-The-Loop (HITL), do NOT silently overwrite.

❌ Never delete a .curator/Collections/ page without explicit user confirmation.

❌ Never overwrite existing atom claims silently — use ## Updates [date] sections.

❌ Never invent citations — if a claim has no traceable ATM-UUID, mark confidence_score < 0.60.

❌ Never bypass state.sqlite — it is the source of truth for deduplication and provenance.

9. Mandatory HITL & Correction Protocol (Ledger)

The Curator (Compiler) and Agents (Artists) CANNOT silently override conflicting claims. If a misconception or logical contradiction is found:

HALT: Stop execution. Do not arbitrarily modify the source or DAG node.

FLAG: Trigger a debate with the Human (Director) (e.g., "⚠️ I detected a misconception in ATM-9f8e7d6c. Do you want me to update it?").

APPLY: Upon explicit human approval, the Agent updates the node using the curator_update_node MCP tool.

LOG: The resolution is automatically appended to .curator/ledger.md as an immutable audit trail.

10. CLI Commands

```text
wiki init PATH                     Scaffold a new Curator vault with full directory topology.
wiki status                        Inspect tracking DB metrics, active LLM config, and collection counts.
wiki version                       View current installed version.

wiki add PATH [-r]                 Discover new/changed source files. Generates L1 Context
                                   summaries, registers hashes in state.sqlite, appends to log.md.

wiki sources list                  List all tracked source files.
wiki sources show ID               Show details for one source (with text preview).
wiki sources rm ID                 Remove a source from tracking.
wiki sources retry ID              Retry a previously failed source.

wiki curate [SOURCE_ID]            Run downstream extraction pipeline (L1 → L2 → L3 → L4).
  --force                          Re-curate already-curated sources.
  --batch                          Skip interactive confirmation.
  --no-thinking                    Disable thinking mode in Pass 1 (faster).
  --sync                           Auto-run wiki sync after curating.

wiki sync [NODE_ID]                Core Logic Alignment Engine.
  --dry-run                        Report gaps without fixing or rebuilding routing tables.
  --no-fix                         Detect gaps but skip LLM-based auto-repair.
  Mode A (no NODE_ID): Global structural verification (L4 → L1).
  Mode B (NODE_ID given): Targeted bidirectional propagation from specified node.
  Mode C (always): LLM logical deduction verification.

wiki query "QUESTION"              Semantic search via qmd + LLM synthesis with citations.
  --mode hybrid|lex|vec            Search mode (default: hybrid = BM25 + vector + LLM rerank).
  --scope all|contexts|atoms|...   Restrict search to a specific DAG layer.
  --save-as TITLE                  Save answer as a new L4 Exhibition page.

wiki reindex                       Force full rebuild of the QMD search index.
wiki lint [--deep] [--fix]         Health checks (orphans, broken links, contradictions).
wiki config provider               Switch and configure LLM backend interactively.
wiki config models list            List available Ollama models.
wiki config models use             Select an Ollama model interactively.
wiki mcp                           Start the MCP stdio server for workspace agent integration.
wiki mcp install                   Print config snippet for Claude / Gemini IDE integration.
```

Section 11. Agent Workflow & MCP Tooling

All AI Workspace Agents (Artists) MUST adhere to the following 3-Phase Workflow to interact with the DAG:

Phase 1: Pre-requisite Discovery (The Compiler's Bridge)

Agents MUST use search_curator MCP tool to pull prior knowledge (Exhibitions) via the qmd search index from .curator/.
Use curator_layer_index() first to understand what is available in the vault.

Phase 2: Validation & Strong Negotiation (HITL)

Cross-reference retrieved data with raw sources. If contradictions exist, follow the Mandatory HITL Protocol (Section 9).

Phase 3: Automatic Re-curation & Propagation (The Infinite Knowledge Creation Loop)

Upon Director (Human) approval, Agent applies fixes using curator_update_node(node_id, new_content).

curator_update_node writes the file and automatically runs wiki sync (Mode B + Mode C)
to propagate upstream and downstream changes, then rebuilds all routing tables.

Agent finally calls curator_reindex() to cleanly update semantic/lexical search bases.

12. MCP Tools Reference

search_curator(query, scope, mode, limit, min_score)
  Semantic and lexical search across the Curator DAG via qmd (BM25 + vector + LLM rerank).
  scope: 'all' | 'contexts' | 'atoms' | 'concepts' | 'exhibitions'
  mode: 'hybrid' | 'lex' | 'vec'

curator_get_node(node_id)
  Fetch a single DAG node (CTX-/ATM-/CON-/EXH-) by ID. Returns frontmatter + body.

curator_traverse_evidence(exh_id)
  Walk an Exhibition's full evidence chain: EXH → CON → ATM.
  Returns confidence score, all concept pages, all atom pages, and flagged atom count.
  Use before citing any EXH with confidence_score < 0.90.

curator_find_contradictions(node_id=None)
  List Atoms carrying contradicts entries or is_flagged_for_agent: true.
  If node_id given, scopes to the subgraph reachable from that node.

curator_layer_index()
  Return per-layer page counts and recent IDs for all four layers.
  Use as the agent's first call to get a vault overview.

curator_status()
  Return vault root, qmd binary readiness, and total page counts.

curator_update_node(node_id, new_content)
  Overwrite a DAG node's markdown file. Runs wiki sync (Mode B + C) automatically.
  Returns: {updated, gaps, routing_tables_rebuilt}

curator_reindex()
  Rebuild the qmd search index over all Collections pages.
  Call after any bulk edits or curator_update_node calls.

curator_curate_accession(context_id)
  Re-run the L2→L4 extraction pipeline for a single L1 Context (launches wiki curate --batch).

This file evolves with the pipeline. Update when conventions change and commit.
