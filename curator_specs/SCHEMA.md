# SCHEMA.md — Curator Schema & Operating Conventions

> **Audience**: LLM Curator engine only.
> This file defines the contract for building and maintaining the `.curator/` DAG knowledge lake.
> The Curator reads source dirs (02_Wiki, 03_Notes, 04_Resources, 06_Archives) and writes
> **exclusively** to `.curator/`. Human readability is NOT a design goal.

---

## 1. Directory Layout

```
ROOT/
├── 02_Wiki/            # [READ] Agent-managed knowledge base (promoted Concepts)
├── 03_Notes/           # [READ] Human-verified atomic knowledge — highest epistemic authority
├── 04_Resources/       # [READ] External PDFs, docs — IMMUTABLE
├── 06_Archives/        # [READ] Terminated projects — IMMUTABLE
└── .curator/           # [WRITE ONLY] Curator residence
    ├── config.yml      # Project configuration
    ├── state.sqlite    # Hash registry & ingest tracking DB
    ├── overview.md     # [ROUTING] Domain manifest
    ├── index.md        # [ROUTING] Layer → ID pointer table (auto-rebuilt)
    ├── log.md          # [STATE] Ingest event log (auto-appended)
    ├── ledger.md       # [OVERRIDE] Human corrections → silently override L1-L4
    └── Collections/
        ├── 01_Summaries/   # L1: SUM-UUID.md — 1:1 hash-matched source summaries
        ├── 02_Atoms/       # L2: ATM-UUID.md — irreducible facts / equations
        ├── 03_Concepts/    # L3: CON-UUID.md — clustered atom groups
        └── 04_Synthesis/   # L4: SYN-UUID.md — terminal cross-domain outputs
```

**Write boundary**: The Curator MUST NOT modify any file outside `.curator/`.

---

## 2. ID System

All pages use prefixed UUID4 IDs (8 hex chars):

| Layer | Prefix | Example |
|---|---|---|
| L1 Summary | `SUM-` | `SUM-a1b2c3d4` |
| L2 Atom | `ATM-` | `ATM-9f8e7d6c` |
| L3 Concept | `CON-` | `CON-12345678` |
| L4 Synthesis | `SYN-` | `SYN-abcdef01` |

IDs are generated once at page creation and never change. File names are `{ID}.md`.

---

## 3. Metadata Schemas

All timestamps: ISO 8601 (`YYYY-MM-DDThh:mm:ssZ`). Stored ONLY in `.curator/Collections/`.

### 3.1 L1: ACCESSION

```yaml
---
id: SUM-[UUID8]
type: summary
source_path: "[[relative/path/to/source.md]]"
source_hash: [SHA-256]
domain: "knowledge-domain-string"
last_updated: YYYY-MM-DDThh:mm:ssZ
tags: [tag1, tag2]
---
```

**Body sections**: `## Summary`, `## Key Claims`, `## Atom Candidates`, `## Source`

### 3.2 L2: FRAGMENT

```yaml
---
id: ATM-[UUID8]
type: atom
parent_source: "[[01_Summaries/SUM-UUID8]]"
source_path: "[[relative/path/to/source.md]]"
claim_type: fact | equation | theoretical_constraint
contradicts: []       # List of ATM-UUIDs with conflicting claims
is_verified_by_human: false
is_flagged_for_agent: false
last_updated: YYYY-MM-DDThh:mm:ssZ
---
```

**Body sections**: `## Definition / Claim`, `## Context`, `## Constraints`, `## Relations`, `## Source`

- Use LaTeX for equations: `$E = mc^2$`, `$$\nabla \cdot E = \rho/\varepsilon_0$$`
- Cross-reference via `[[02_Atoms/ATM-UUID8]]`
- If a new source contradicts existing atom: set `contradicts: ["ATM-other"]` and `is_flagged_for_agent: true`

### 3.3 L3: CONCEPT

```yaml
---
id: CON-[UUID8]
type: concept
dependencies: ["[[02_Atoms/ATM-UUID8]]", "[[02_Atoms/ATM-UUID8]]"]
domain: "knowledge-domain-string"
last_updated: YYYY-MM-DDThh:mm:ssZ
---
```

**Body sections**: `## 1. Core Architecture`, `## 2. Interaction of Atoms`, `## 3. Mathematical Framework`, `## 4. Open Questions`

- Minimum 2 atom dependencies per concept
- Do NOT create singleton concepts (1 atom = 1 concept is redundant)

### 3.4 L4: SYNTHESIS

```yaml
---
id: SYN-[UUID8]
type: synthesis
core_concepts: ["[[03_Concepts/CON-UUID8]]"]
confidence_score: 0.00 - 1.00
requires_math_rigor: true | false
last_updated: YYYY-MM-DDThh:mm:ssZ
---
```

**Body sections**: `## 1. Executive Research Brief`, `## 2. Theoretical Foundation`, `## 3. State of the Art & Limitations`, `## 4. Actionable Directives for Agent`

---

## 4. Pipeline Phases

### Phase 0 — SYNC (`wiki sync`)

**Trigger**: New or changed files detected in source dirs.
**Action**: For each new file:
1. Register in `state.sqlite` with SHA-256 hash and `status=pending`.
2. Run Pass 0 LLM call → generate `01_Summaries/SUM-UUID.md`.
3. Record `summary_id` in DB.

**Cost**: 1 LLM call per new source file.

### Phase 1 — ATOMS (`wiki ingest`, Pass 1)

**Trigger**: Sources with `status=pending` in DB.
**Input**: L1 Summary `atom_candidates` list.
**Action**: For each candidate:
- If atom for this concept already exists → merge via `## Updates [date]` section.
- If new → create `02_Atoms/ATM-UUID.md`.
- Check for contradictions → set `contradicts` and `is_flagged_for_agent: true` if found.

### Phase 2 — CONCEPTS (`wiki ingest`, Pass 2)

**Trigger**: After Pass 1 completes for a source.
**Input**: New ATM-UUIDs created in Pass 1.
**Action**:
1. Cluster atoms with shared logical theme (min 2 per cluster).
2. Create `03_Concepts/CON-UUID.md` for each cluster.

### Phase 3 — SYNTHESIS (`wiki ingest`, Pass 3)

**Trigger**: After Pass 2 completes.
**Input**: New CON-UUIDs from Pass 2.
**Action**:
1. Identify concept pairs/groups with cross-domain connections.
2. Create `04_Synthesis/SYN-UUID.md` for each valid synthesis.

---

## 5. Control-Plane Files

### `.curator/index.md`

Auto-rebuilt after every `wiki ingest`. Format:

```markdown
| SYN_ID | TARGET_TOPIC | CONFIDENCE | EVIDENCE_CHAIN |
|---|---|---|---|
| SYN-042 | Topic name | 0.95 | [[CON-012]], [[ATM-088]] |
```

### `.curator/log.md`

Append-only. Format:

```markdown
## [YYYY-MM-DDThh:mm:ssZ] ingest | Source Title
- created: [[02_Atoms/ATM-uuid]]
- updated: [[02_Atoms/ATM-other]]
- created: [[03_Concepts/CON-uuid]]
```

### `.curator/ledger.md`

Human-authored overrides. These silently override any conflicting claim in L1-L4
without requiring user re-confirmation. The Curator checks ledger FIRST before
writing any atom that matches a ledger entry topic.

---

## 6. Wikilink Convention

- Internal cross-references: `[[LAYER/ID]]` — e.g., `[[02_Atoms/ATM-abc12345]]`
- Never use plain markdown links for cross-references inside `.curator/`
- Ledger overrides: `[[.curator/ledger]]`

---

## 7. Confidence Decision Tree

```
SYN confidence_score:

>= 0.90 → DIRECT_RETRIEVAL: Agent can cite directly without backtracking
0.60–0.90 → PARTIAL_BACKTRACK: Traverse EVIDENCE_CHAIN (CON → ATM nodes) before citing
< 0.60  → FULL_VERIFICATION: Halt. Trigger STRONG_NEGOTIATION with human.
           Set is_flagged_for_agent: true on relevant ATMs.
```

---

## 8. Immutability Rules

- ❌ **Never modify** `04_Resources/` or `06_Archives/` — treat as read-only constants.
- ❌ **Never modify** `03_Notes/` — human-verified truth. Read only.
  If `03_Notes` contradicts an ATM: flag the ATM (`is_flagged_for_agent: true`),
  do NOT silently overwrite `03_Notes`.
- ❌ **Never delete** a `.curator/Collections/` page without explicit user confirmation.
- ❌ **Never overwrite** existing atom claims silently — use `## Updates [date]` sections.
- ❌ **Never invent** citations — if a claim has no traceable ATM-UUID, mark `confidence_score < 0.60`.

---

## 9. Ledger Override Protocol

If `.curator/ledger.md` contains a correction relevant to an atom or synthesis:
1. Apply the correction without asking for user confirmation.
2. Annotate the affected page: `*[Override from ledger: date]*`
3. Log the override in `.curator/log.md` with tag `[LEDGER_OVERRIDE]`.

---

*This file evolves with the pipeline. Update when conventions change and commit.*
