SCHEMA.md — Curator Schema & Operating Conventions (v13.1)

> **v13.1 Changelog (from v13.0)**
> 1. **[NEW] `curate.yml` Schema**: Each workspace may carry a `curate.yml` Knowledge Requirement Specification file. Its schema is now formally defined (Section 3.5). The Curator reads this file to scope Exhibition staging and `search_curator` results for that workspace.
> 2. **[UPDATE] Stage Action Labels**: Each pipeline stage now carries an action-oriented label in directory comments and documentation:
>    - 01_Contexts/: **Collection & Summarization**
>    - 02_Atoms/: **Selection & Atomization**
>    - 03_Concepts/: **Structuring & Value Addition**
>    - 04_Exhibitions/: **Placement & Staging**
> 3. **[NEW] Two Synthesis Paths**: Section 6 (Control-Plane Files) is extended with a formal Two-Path Synthesis Protocol governing how knowledge reaches `02_Wiki/`.
> 4. **[UPDATE] 02_Wiki label**: Now formally "Official Exhibition Hall" with Public Write Access for both Agent and Human (via HITL consensus).
> 5. **[CLARIFY] `qmd.yml` vs `curate.yml`**: `qmd.yml` is the internal config for the `qmd` search binary and remains unchanged. `curate.yml` is a new per-workspace agent spec file. Different files, different owners, different lifecycles.

---

Audience: LLM Curator engine (Compiler) & Workspace Agents (Artists).
This file defines the contract for building and maintaining the .curator/ DAG knowledge lake under the SYMBIOTIC_OS_ARCHITECTURE v13.1.
The Curator reads source dirs (02_Wiki, 03_Notes, 04_Resources, 06_Archives) and writes
exclusively to .curator/. Human readability inside .curator/ is NOT a design goal.

1. Directory Layout

ROOT/
├── 00_System/          # [STATIC] Scripts & Templates
├── 01_Workspaces/      # [AGENT_RESIDENCE] Knowledge synthesis & execution space
│   └── {Project_Name}/
│       ├── curate.yml  # [KR_SPEC] Knowledge Requirement Specification (NEW in v13.1)
│       └── ...         # Artifacts, Concepts, Papers, research files
├── 02_Wiki/            # [OFFICIAL_EXHIBITION_HALL] Two-Track Human-Friendly Space (Public Write)
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
        ├── 01_Contexts/    # [Stage 1: Collection & Summarization]
        │                   #   L1: CTX-UUID.md — 1:1 hash-matched context summaries
        │                   #   Identifies knowledge candidates from source documents
        ├── 02_Atoms/       # [Stage 2: Selection & Atomization]
        │                   #   L2: ATM-UUID.md — Irreducible atomic knowledge units
        │                   #   Selected and distilled from identified candidates
        ├── 03_Concepts/    # [Stage 3: Structuring & Value Addition]
        │                   #   L3: CON-UUID.md — High-level conceptual clusters of atoms
        │                   #   Weaves atoms into structured concept networks
        └── 04_Exhibitions/ # [Stage 4: Placement & Staging]
                            #   L4: EXH-UUID.md — Terminal packaged contexts for Agents
                            #   Finally staged and placed exhibits for Agent consumption


Write boundary: The Curator MUST NOT modify any file outside .curator/ autonomously.

2. ID System

All pages use prefixed UUID4 IDs (8 hex chars): [Unchanged from v13.0]

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

3.1 L1: CONTEXT  [Unchanged from v13.0]

---
id: CTX-[UUID8]
type: context
source_path: "[[relative/path/to/source.md]]"
source_hash: [SHA-256]
domain: "knowledge-domain-string"
last_updated: YYYY-MM-DDThh:mm:ssZ
tags: [tag1, tag2]
---

Body sections: `## Summary` (required, fixed) followed by content-specific numbered sections (LLM-driven).

3.2 L2: ATOM  [Unchanged from v13.0]

---
id: ATM-[UUID8]
type: atom
parent_source: "01_Contexts/CTX-UUID8"
source_path: "[[relative/path/to/source]]"
claim_type: fact | equation | theoretical_constraint | entity | technique
confidence_score: 0.00
contradicts: []
is_verified_by_human: false
is_flagged_for_agent: false
last_updated: YYYY-MM-DDThh:mm:ssZ
---

Body sections: ## Definition / Claim, ## Context, ## Constraints, ## Relations

3.3 L3: CONCEPT  [Unchanged from v13.0]

---
id: CON-[UUID8]
type: concept
domain: "knowledge-domain-string"
confidence_score: 0.00
last_updated: YYYY-MM-DDThh:mm:ssZ
---

Body sections: ## 1. Core Architecture, ## 2. Interaction of Atoms, ## 3. Mathematical Framework, ## 4. Open Questions, ## Relations

Note: Concept → Atom edges live only in the terminal `## Relations` section as
`[[02_Atoms/ATM-UUID8]]` wikilinks. Do not duplicate them in frontmatter.

3.4 L4: EXHIBITION  [Unchanged from v13.0]

---
id: EXH-[UUID8]
type: exhibition
core_concepts: ["03_Concepts/CON-UUID8", "03_Concepts/CON-UUID8"]
confidence_score: 0.00 - 1.00
last_updated: YYYY-MM-DDThh:mm:ssZ
---

Body format: bold-bullet list (NOT `##` section headers):

- **1. Executive Brief**: [one-paragraph synthesis]
- **2. Theoretical Foundation**: [cross-concept logical chain with wikilinks]
- **3. Actionable Directives for Agent**: [concrete tasks with fragment references]

3.5 curate.yml — Knowledge Requirement Specification  [NEW in v13.1]

Location: 01_Workspaces/{Project_Name}/curate.yml
Owner: Agent (Artist) / Human (Director)
Read by: Curator (Compiler) via MCP tool calls and `wiki curate --workspace`

```yaml
# curate.yml — Knowledge Requirement Specification
# Declares what this workspace needs the Curator to stage as Exhibitions.
# Absence of this file → unscoped global search (v13.0 behavior).

project: "project-name"               # Workspace identifier (string, no spaces)
description: "..."                     # What this workspace is for

# Knowledge domains this workspace operates in.
# Used to filter Exhibitions surfaced by search_curator.
domains:
  - "machine-learning"
  - "knowledge-management"

# Specific topic strings the Curator should prioritize.
# Used to boost relevance scoring during Exhibition staging.
topics:
  - "transformer architecture"
  - "attention mechanism"

# Minimum confidence_score for surfaced Exhibitions.
# Exhibitions below this threshold are suppressed from search_curator results.
# Default: 0.60 (system minimum). Must be in [0.0, 1.0].
min_confidence: 0.70

# DAG layer scope restriction for search_curator.
# Values: all | contexts | atoms | concepts | exhibitions
# Default: "all"
scope: "all"
```

Validation rules:
- `project`: required, non-empty string
- `domains`: optional list of strings; empty list = no domain filter
- `topics`: optional list of strings; used for relevance boost, not hard filter
- `min_confidence`: optional float in [0.0, 1.0]; default 0.60
- `scope`: optional enum; default "all"

4. Pipeline Phases  [Unchanged from v13.0]

Phase 0 — SOURCE INGESTION + ATOMIZATION (wiki add)

Trigger: New or changed files detected in source dirs.
Action: For each new file:
  Register in state.sqlite with SHA-256 hash and status=pending.
  Generate 01_Contexts/CTX-UUID.md.
  Record context_id in DB & log.md.
  Extract L2 Atoms from each valid L1 Context.
  Cluster available Atoms into L3 Concepts.

Phase 1 — EXHIBITION STAGING (wiki curate)

Trigger: L3 Concepts exist and, optionally, a workspace curate.yml scopes the task.
Action:
  Pass 3 (Exhibitions): Bundle L3 Concepts into L4 Exhibitions for Agent consumption.

v13.1 addition: If `--workspace PATH` is given, curate.yml is read to boost relevance
scoring for declared `domains` and `topics` during Pass 3.

Phase 2 — DEDUCTIVE VERIFICATION & LOGIC ALIGNMENT (wiki sync)  [Unchanged from v13.0]

5. Control-Plane Files

5.1 .curator/index.md  [Unchanged from v13.0]

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

5.2 .curator/log.md  [Unchanged from v13.0]

```markdown
---
title: Curator Log
type: log
---

## [YYYY-MM-DD] curate | global pipeline
- created: [[03_Concepts/CON-12345678]]
- created: [[04_Exhibitions/EXH-abcdef01]]

## [YYYY-MM-DD] sync | Deductive verification pass
- Routing tables rebuilt by wiki sync
```

5.3 Two-Path Synthesis Protocol  [NEW in v13.1]

Knowledge enters `02_Wiki/` (Official Exhibition Hall) via exactly two paths. Curators
and Agents MUST respect these paths — direct writes to 02_Wiki/ outside these paths
are prohibited without explicit Director authorization.

**Path A — Agent-Led Task Synthesis**
Trigger: Agent completes a task milestone and receives Director (Human) HITL approval.
Process:
  1. Agent uses staged Exhibitions (L4) as primary source materials.
  2. Agent executes task within 01_Workspaces/ (code, analysis, planning).
  3. Agent proposes deliverable to Director via conversation.
  4. Director approves → Agent writes result to 02_Wiki/.
Constraint: Agent MUST NOT write to 02_Wiki/ without explicit Director approval.

**Path B — Conversational Promotion**
Trigger: Human explicitly decides a conversation-derived insight deserves promotion.
Process:
  1. Human asks a question; Curator answers from Concept network (L3).
  2. Extended Curator-Human dialog develops the idea further.
  3. Human issues promotion command (e.g., "promote this to wiki").
  4. Human or Curator writes the distilled insight to 02_Wiki/.
Constraint: Curator MUST NOT auto-promote without explicit Human instruction.

**Infinite Knowledge Creation Loop**
After either path:
  02_Wiki/ content is re-ingested on the next `wiki add` run → enters L1 (Contexts)
  pipeline → flows through L2 → L3 → L4 → back to 02_Wiki/ → loop continues.
  DAG integrity is maintained throughout via state.sqlite.

6. Wikilink Convention  [Unchanged from v13.0]

Internal cross-references: [[LAYER/ID]] — e.g., [[02_Atoms/ATM-9f8e7d6c]]
Never use plain markdown links for cross-references inside .curator/
Ledger overrides: [[.curator/ledger]]

7. Confidence Decision Tree  [Unchanged from v13.0]

EXH confidence_score:
>= 0.90  → DIRECT_RETRIEVAL: Agent can cite directly.
0.60–0.90 → PARTIAL_BACKTRACK: Traverse CON → ATM before citing.
< 0.60   → FULL_VERIFICATION: Halt. STRONG_NEGOTIATION with Director.
            Set is_flagged_for_agent: true on relevant ATMs.

v13.1 addition: curate.yml `min_confidence` acts as a workspace-level pre-filter.
Exhibitions below that threshold are excluded from search_curator results for the workspace
before the above decision tree is consulted.

8. Immutability Rules  [Unchanged from v13.0]

❌ Never modify 04_Resources/ or 06_Archives/.
❌ Never modify 03_Notes/ autonomously — human-verified truth (Director's domain).
❌ Never delete a .curator/Collections/ page without explicit user confirmation.
❌ Never overwrite existing atom claims silently — use ## Updates [date] sections.
❌ Never invent citations — if no traceable ATM-UUID, mark confidence_score < 0.60.
❌ Never bypass state.sqlite.
❌ Never write to 02_Wiki/ outside of the Two-Path Synthesis Protocol.

9. Mandatory HITL & Correction Protocol  [Unchanged from v13.0]

HALT → FLAG → APPLY (via curator_update_node MCP) → LOG (to ledger.md).

10. CLI Commands  [v13.1 additions only]

```text
# All v13.0 commands unchanged. New in v13.1:

wiki workspace init PATH    Scaffold workspace dir + curate.yml template.
wiki workspace list         List workspaces with curate.yml under 01_Workspaces/.

wiki curate --workspace PATH   Read curate.yml from PATH; boost curation priority
                               for declared domains/topics during Pass 3.
```

11. Agent Workflow  [Unchanged from v13.0 except curate.yml note]

Phase 1: Pre-requisite Discovery
  Call curator_layer_index(), then search_curator().
  v13.1: If WORKSPACE_PATH env var is set, MCP auto-applies curate.yml filters.

Phase 2: Validation & Strong Negotiation (HITL)  [Unchanged]

Phase 3: Re-curation & Propagation
  Upon Director approval, call curator_update_node(node_id, new_content).
  Then call curator_reindex().
  Finally, promote via Path A or Path B to 02_Wiki/.

12. MCP Tools Reference  [v13.1 changes only]

search_curator(query, scope, mode, limit, min_score)
  v13.1: Reads WORKSPACE_PATH env var. If set, loads curate.yml from that path.
  Applies domain/topic boost and min_confidence filter from curate.yml automatically.
  All other parameters and behavior unchanged from v13.0.

[All other tools unchanged from v13.0]

This file evolves with the pipeline. Update when conventions change and commit.
