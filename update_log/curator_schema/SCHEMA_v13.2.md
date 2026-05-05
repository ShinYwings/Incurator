SCHEMA.md — Curator Schema & Operating Conventions (v13.2)

> **v13.2 Changelog (from v13.1)**
> 1. **[UPDATE] Unified Integrity Loop**: `wiki sync` is now the single user-facing structural/logical integrity command. It runs safe structural repair by default, then logical verification and limited backprop-style repair. `wiki lint`, `wiki sync --fix`, and `--deep` are removed from the public command surface; lint remains an internal structural engine.
> 2. **[NEW] Coverage-Preserving L3 Clustering**: L3 Concept generation now requires source coverage. Atom summaries are extracted from `## Definition / Claim`; if the clustering model omits related Atoms, the Curator creates fallback Concept plans for coherent unassigned source/topic groups instead of silently marking the source done.
> 3. **[UPDATE] Layer Status Semantics**: `state.sqlite` tracks per-source L1/L2/L3/L4 status. A source reaches `l3_status=done` only when at least one Atom from that source is actually referenced by a Concept `## Relations` section.
> 4. **[NEW] Sync Report State**: `.curator/sync-report.json` records the latest integrity health summary (`clean | fixed | review_needed | failed | stale`), fixed counts, structural/logical gaps, blocked checks, and review counts for `wiki status`.
> 5. **[NEW] Curate/Query Exhibition Policies**: `wiki curate` is a workspace-scoped persistent Exhibition flow keyed by `curate.yml`; `wiki query` is a session-oriented flow that may save a query Exhibition with `QRY-*` metadata when explicitly requested.
> 6. **[CLARIFY] Backprop Metaphor**: The Curator may repair generated DAG nodes when sync discovers loss from human/agent edits, but source truth directories remain immutable. Current automatic logical repair is conservative and centered on generated L3/L4 pages plus safe structural repairs.

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
This file defines the contract for building and maintaining the .curator/ DAG knowledge lake under the SYMBIOTIC_OS_ARCHITECTURE v13.2.
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
    ├── sync-report.json # [STATE] Latest sync health summary (auto-written)
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

3.3 L3: CONCEPT  [Updated in v13.2]

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

v13.2 coverage rule:
- Every L3 Concept MUST cite its constituent Atoms in `## Relations`.
- Source-level L3 completion is derived from actual Concept → Atom coverage, not merely from the existence of any Concept page.
- If clustering omits related Atoms, the Curator may create a fallback Concept for coherent unassigned source/topic groups. This is a coverage repair, not an automatic semantic merge.

3.4 L4: EXHIBITION  [Updated in v13.2]

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

Optional v13.2 frontmatter fields:

```yaml
# Present on persistent workspace Exhibitions created by `wiki curate`.
workspace: "Workspace Project Name"
workspace_path: "/absolute/path/to/01_Workspaces/Project"
curate_spec_hash: "12-char-hash"

# Present on query-session Exhibitions created by `wiki query --save-as`.
query_session: QRY-[UUID8]
ephemeral: false
question: "original user query"
```

Rules:
- `core_concepts` MUST be non-empty for saved L4 pages.
- `core_concepts` entries are plain strings like `03_Concepts/CON-UUID8`, not wikilink wrappers.
- Query save-back MUST resolve cited Atoms/Contexts to related Concepts before writing an Exhibition.

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

4. Pipeline Phases  [Updated in v13.2]

Phase 0 — SOURCE INGESTION + ATOMIZATION (wiki add)

Trigger: New or changed files detected in source dirs.
Action: For each new file:
  Register in state.sqlite with SHA-256 hash and status=pending.
  Generate 01_Contexts/CTX-UUID.md.
  Record context_id in DB & log.md.
  Extract L2 Atoms from each valid L1 Context.
  Cluster available Atoms into L3 Concepts.
  Repair clustering coverage by creating fallback Concepts for coherent unassigned Atoms.
  Run `wiki sync` by default unless explicitly skipped.

Phase 1 — EXHIBITION STAGING (wiki curate)

Trigger: L3 Concepts exist and, optionally, a workspace curate.yml scopes the task.
Action:
  Pass 3 (Exhibitions): Bundle L3 Concepts into L4 Exhibitions for Agent consumption.
  Run `wiki sync` by default unless explicitly skipped.

v13.1 addition: If `--workspace PATH` is given, curate.yml is read to boost relevance
scoring for declared `domains` and `topics` during Pass 3.

v13.2 addition: `wiki curate` is workspace-scoped. With the same workspace and same
`curate.yml` hash, it updates the existing workspace Exhibition instead of treating
each run as unrelated. If the spec changes, a new revision may be staged while older
Exhibitions remain preserved unless explicitly deleted.

Phase 2 — DEDUCTIVE VERIFICATION & LOGIC ALIGNMENT (wiki sync)  [Updated in v13.2]

`wiki sync` is the single public integrity command. It performs:

1. structural check
2. safe structural repair unless `--no-fix` or `--dry-run`
3. L4→L3 logical verification when L4 exists
4. L3→L2 logical verification
5. contradiction/equivalence scan through the internal lint engine
6. conservative logical repair and re-verification, bounded to two iterations
7. routing table rebuild and sync report update

Safe structural repairs include:
- remove empty layer wikilinks such as `[[01_Contexts/]]`
- normalize obvious wikilinks
- repair certain `source_path`, `parent_source`, `core_concepts`, and `## Relations` fields when DB/body evidence makes the target unambiguous
- remove nested/duplicated frontmatter emitted by an LLM inside generated page bodies

Forbidden automatic repairs:
- deleting knowledge nodes as a fallback
- silently removing unresolved broken links
- modifying `03_Notes/`, `04_Resources/`, or `06_Archives/`
- inventing L4 Exhibitions when none exist

Backprop-style repair metaphor:
- `wiki add` and `wiki curate` are forward passes that compile source knowledge upward through L1→L4.
- Human/agent edits to generated DAG nodes create a form of loss signal.
- `wiki sync` is the backward verification pass: it traces generated knowledge back toward evidence, repairs safe generated-node errors, then rebuilds only affected downstream pages when possible.
- This is an operational analogy, not full neural-network training. The Curator does not rewrite immutable source truth and does not automatically merge/delete ambiguous knowledge.

Phase 3 — QUERY SESSION SAVE-BACK (wiki query)  [NEW in v13.2]

`wiki query` is a user-session-oriented path. Non-interactive queries do not leave
an Exhibition unless `--save-as` is provided. Saved query Exhibitions receive
`query_session: QRY-UUID8`, `ephemeral: false`, and validated non-empty
`core_concepts`.

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

5.3 .curator/sync-report.json  [NEW in v13.2]

The latest sync report is an auto-written machine-readable summary consumed by
`wiki status`.

```json
{
  "generated_at": "YYYY-MM-DDThh:mm:ssZ",
  "reason": "sync | add | curate | query | ...",
  "health": "clean | fixed | review_needed | failed | stale",
  "safe_fixed": 0,
  "rebuilt_downstream": 0,
  "needs_review": 0,
  "blocked_logical_checks": 0,
  "equivalence_candidates": [],
  "structural_gaps": [],
  "logical_gaps": [],
  "structural_issues": []
}
```

5.4 Two-Path Synthesis Protocol  [NEW in v13.1]

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

10. CLI Commands  [v13.2 additions and simplifications]

```text
wiki workspace init PATH    Scaffold workspace dir + curate.yml template.
wiki workspace list         List workspaces with curate.yml under 01_Workspaces/.

wiki curate --workspace PATH   Read curate.yml from PATH; boost curation priority
                               for declared domains/topics during Pass 3.

wiki sync                    Run default safe repair + logical verification.
wiki sync --no-fix           Report-only; do not repair files/DB.
wiki sync --dry-run          Preview; do not repair or rebuild routing tables.
wiki sync NODE_ID            Targeted verification around one DAG node.
```

Removed from the public v13.2 command surface:
- `wiki lint`
- `wiki sync --fix`
- `wiki sync --deep`

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
