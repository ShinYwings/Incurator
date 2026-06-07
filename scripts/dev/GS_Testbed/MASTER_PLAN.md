# GS_Testbed Master Plan

Domain: **Gaussian Splatting Geometry Lab**
Source corpus: 2DGS + EWA Splatting paper notes, corresponding PDFs, and a
deliberately separate LLM/RAG wiki article to test domain boundary handling.

---

## Directory Layout

```text
scripts/dev/GS_Testbed/
├── create_testbed.py          # initializes testbed/ from stage/
├── MASTER_PLAN.md             # this file
├── stage/                     # immutable source corpus (checked in)
│   ├── 01_Workspaces/Gaussian Splatting Geometry Lab/
│   │   ├── curate.yml         # workspace specification
│   │   └── ...                # research notes, methodology docs
│   ├── 02_Wiki/LLM/           # separate domain (intentional)
│   ├── 03_Notes/Papers/       # human paper review notes (immutable)
│   ├── 04_Resources/Zotero/   # source PDFs (immutable)
│   └── 05_Assets/             # figures and supplementary material
├── fixture_workspace_rules/   # dev-only agent rule templates
│   ├── managed/               # agent-managed rule files
│   └── owned/                 # human-owned rule files
└── dialogues/                 # automated validation scripts
    ├── dialogue_1_workspace_mcp.py
    ├── dialogue_2_agent_exhibition_update.py
    └── dialogue_3_query_session.py
```

---

## Setup

```bash
# 1. Initialize (resets testbed/ to a clean state every time)
wiki testbed init GS_Testbed --force

# 2. Populate (requires LLM backend — Gemini CLI by default)
WIKI_ROOT=testbed wiki add
WIKI_ROOT=testbed wiki curate --workspace "testbed/01_Workspaces/Gaussian Splatting Geometry Lab"
# IMPORTANT: wiki reindex must run AFTER curate for BM25 to return hits in dialogues.
# wiki add/curate do incremental index updates; only wiki reindex fully rebuilds BM25.
WIKI_ROOT=testbed wiki reindex

# 3. Verify
WIKI_ROOT=testbed wiki status
WIKI_ROOT=testbed wiki sync
```

---

## Dialogues

Each dialogue is a standalone Python script. Exit codes:

- `0` = passed
- `1` = assertion failure
- `2` = skipped (prerequisites not met)

### dialogue_1_workspace_mcp.py

**Always runnable** (no data required).

- `curator_status` — vault resolves, qmd info present
- `curator_layer_index` — all four layers returned
- `search_curator` with `WORKSPACE_PATH` — `curate_spec_applied` matches project name; no crash on empty collections
- `curator_curate_workspace` — new tool: accepts either `ok=True` + exhibition name (data present) or graceful error/None (no L3 data)

```bash
python scripts/dev/GS_Testbed/dialogues/dialogue_1_workspace_mcp.py
```

### dialogue_2_agent_exhibition_update.py

**Requires data** (skips with exit 2 if collections empty).

- If no Exhibition exists: calls `curator_curate_workspace` to create one, then re-validates count
- `curator_get_node` on a real EXH — body and frontmatter present
- `curator_update_node` — `updated=True`, `routing_tables_rebuilt=True`, gaps list present

```bash
python scripts/dev/GS_Testbed/dialogues/dialogue_2_agent_exhibition_update.py
```

### dialogue_3_query_session.py

**Requires data** (skips with exit 2 if collections empty).

**Part A — `--save-as`** (explicit, non-ephemeral Exhibition):

- Creates Exhibition via `wiki query --save-as "title"`
- Validates `query_session` starts with `QRY-`, `workspace` matches, `ephemeral=False`

**Part B — `--curate`** (session-scoped, ephemeral Exhibition):

- Skips if no L3 Concepts (first sub-prerequisite)
- Runs `wiki query --curate` with an initial question; expects one new EXH with `ephemeral=True`
- Runs a second session with a follow-up turn; verifies `## Follow-up:` section in body and no duplicate EXH files

**LLM dependency**: Part B requires an active Gemini CLI session to generate the initial answer.
Without it, `_save_curation_page` finds no L3 hits and the Exhibition is never created — Part B
exits with a clear message. Run Part A (`--save-as`) for basic path coverage without LLM.

```bash
python scripts/dev/GS_Testbed/dialogues/dialogue_3_query_session.py
```

---

## Immutable Source Corpus

Do **not** edit files under `stage/03_Notes/` or `stage/04_Resources/` — they are the immutable scenario inputs. Update them only when explicitly changing the test scenario.

- `03_Notes/Papers/2D Gaussian Splatting for Geometrically Accurate Radiance Fields.md`
- `03_Notes/Papers/EWA splatting.md`
- `04_Resources/Zotero/Huang et al. - 2024 - 2D Gaussian Splatting for Geometrically Accurate Radiance Fields.pdf`
- `04_Resources/Zotero/Zwicker et al. - 2002 - EWA splatting.pdf`
- `02_Wiki/LLM/rag-overview.md` (separate domain — must remain isolated)

---

## Expected Curator Behavior

- L1 Contexts preserve source provenance separately for each note and reference.
- L2–L4 should merge 2DGS/EWA note–reference material into shared "splatting geometry" concepts.
- LLM/RAG wiki article must stay in a separate concept cluster (domain isolation test).
- `wiki query --curate` accumulates a running session Exhibition; each follow-up appends a `## Follow-up:` section without creating a new EXH file.
- `curator_curate_workspace` via MCP creates or refreshes the workspace Exhibition from current L3 Concepts.
