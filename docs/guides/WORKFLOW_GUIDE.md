# Incurator System Workflow

> This document explains how the three components of Incurator work together.

---

## 1. System Components

Incurator consists of three independent components.

```text
┌─────────────────────────────────────────────────────┐
│                   Obsidian Vault                    │
│                                                     │
│  ┌──────────────────────┐   ┌─────────────────────┐ │
│  │  Obsidian Plugin     │   │  .curator/ (backend) │ │
│  │  (incurator-agent)   │◄──►  Collections/       │ │
│  │  - Chat sidebar      │   │  L1 ~ L4 DAG        │ │
│  │  - Inline edit       │   │  state.sqlite       │ │
│  │  - PDF context       │   └──────────┬──────────┘ │
│  └──────────┬───────────┘              │            │
│             │ MCP                      │ wiki CLI   │
└─────────────┼──────────────────────────┼────────────┘
              │                          │
              ▼                          ▼
   ┌─────────────────────┐   ┌───────────────────────┐
   │  AI Agent (MCP)     │   │  wiki commands        │
   │  Claude Code        │   │  wiki add / query     │
   │  Antigravity        │   │  wiki sync / query    │
   │  Codex              │   │  wiki status / lint   │
   └─────────────────────┘   └───────────────────────┘
```

| Component | Role | Entry point |
|-----------|------|-------------|
| **Curator backend** | Source ingestion, 4-layer DAG, search | `wiki` CLI |
| **Obsidian plugin** | AI chat, inline edit, PDF handling inside Obsidian | Obsidian UI |
| **Agent MCP server** | Exposes Curator tools to AI agents (Claude Code, etc.) | `wiki mcp` |

---

## 2. Vault Location Structure

Understanding the **three distinct paths** in Incurator is essential.

| Path | Role | Example |
|------|------|---------|
| **Wiki system** | Where `wiki` CLI code lives | `/path/to/incurator/` |
| **Vault** (`VAULT_ROOT`) | Where raw files and `.curator/` reside | `/path/to/vault/` |
| **Workspace** | Where project-specific `curate.yml` lives | `<vault>/01_Workspaces/MyProject/` |

The `VAULT_ROOT` environment variable (or `env.VAULT_ROOT` in MCP config) must always point to the **Vault path**.

---

## 3. 4-Layer DAG Structure

Incurator processes source documents through four levels of abstraction.

```text
[Source file]  (03_Notes/, 04_Resources/, 02_Wiki/, etc.)
     │
     │  wiki add
     ▼
[L1: Contexts]  (DB Record: source_spans)
  - One context summary per source
  - Preserves original content, metadata, hash linkage
     │
     │  wiki build (L2 pass)
     ▼
[L2: Atoms]  (DB Record: knowledge_units)
  - Atomic knowledge units extracted from L1
  - One fact / claim / conclusion each
  - Includes verification evidence (citations)
     │
     │  wiki build (L3 pass)
     ▼
[L3: Concepts]  (DB Record: graph_entities/relations + community_reports)
  - Thematic clusters grouping Atoms from multiple sources
  - Cross-source comparison and synthesis
     │
     │  wiki build (L4 synthesis pass, automatic after L3)
     ▼
[L4: Synthesis]  (DB Record: synthesis_nodes) → .curator/Collections/04_Synthesis/SYN-UUID.md
  - SHARED, workspace-independent, corpus-wide cross-cutting insights
  - Distilled from all community reports (the "synthesis"/permanent-note tier)
  - Durable knowledge — NOT tailored to any one workspace
  - Regenerated wholesale; skipped when the report corpus is unchanged
     │
     │  query (dynamic Curation lens — never stored)
     ▼
[Curation]  per-workspace/query selection & recombination of L3/L4 nodes
  - Biased by the workspace curate.yml Knowledge Requirement Spec
  - Produced fresh on every query; not a frozen file
```

> **L4 Synthesis vs. Curation.** The synthesis layer is the durable shared top of
> the knowledge graph, just like the synthesis tier in other LLM wiki repos.
> **Curation** is the dynamic lens *above* it: it selects and recombines L3/L4
> nodes per workspace/query and is never persisted. v0.3.1 has no frozen
> per-workspace Exhibition file.

---

## 4. Core Workflows

### 4-1. Source Ingestion and DAG Construction

```bash
# 1. Initialize Vault (once)
wiki init /path/to/vault

# 2. Add sources (wiki add) — register + instant L1 only (no LLM)
#    A specific file or entire directory
wiki add 03_Notes/paper.pdf
wiki add 04_Resources/

# Internally (Math-Aware v0.2.2):
#   - SHA-256 hash for deduplication
#   - Hybrid pipeline: defaults to pymupdf4llm (Markdown) parsing, integrates with VLM parsers when needed
#   - AST-based chunking: protects math formula blocks ($$...$$) during text splitting
#   - L1 Context file created immediately from structure → returns at once
#   - No LLM call; the source is searchable (BM25) as soon as L1 lands

# 3. Build L2/L3 (wiki build) — the deep, LLM-heavy pass
wiki build            # queue L2/L3 to the background worker (non-blocking)
wiki build --wait     # run L2 (Atoms) → L3 (Concepts) synchronously now
#   - Progress: .curator/dashboard.md updated in real-time (open in Obsidian to watch)

# Shortcut: do steps 2–4 (add → build → embed → sync) in one synchronous command
wiki update
```

> **Two-step ingest**: `wiki add` registers sources and generates instant L1
> (structural, no LLM) — fast and offline-capable. `wiki build` runs the deeper
> L2/L3 extraction; by default it queues to the MCP server's background
> IngestWorker, or use `--wait` to run now. L2 extraction sizes its section
> batches according to the active LLM client's prompt budget, so CLI-backed
> providers receive smaller prompts than local high-context models. Monitor via `wiki status` or
> `.curator/dashboard.md`. L4 Synthesis is produced by `wiki build`; workspace
> curation is a dynamic query lens rather than a separate staging pass.

### 4-2. Advanced Workspace Curation

```bash
# Create curate.yml in a Workspace folder (manually or via wiki workspace init)
# Key fields in curate.yml:
#   vault_root: /path/to/vault   ← Vault path
#   sources.include: ["03_Notes/**", "04_Resources/**"]
#   min_confidence: 0.70

# Generate a workspace-biased dynamic answer via query
wiki query "Your query here" --workspace 01_Workspaces/MyProject
```

### 4-3. Search and Query

```bash
# Natural language query (BM25 + vector + LLM rerank + Dynamic 2-Step RAG)
wiki query "How to estimate camera poses without COLMAP in Gaussian Splatting?"

# Query with an explicit workspace (curate.yml-biased dynamic curation)
wiki query --workspace 01_Workspaces/MyProject "Summarize our goals."

# Rebuild search index
wiki reindex

# Check overall status (includes background job progress)
wiki status

# DAG integrity check (v0.2.1 — incremental by default)
wiki sync              # default: revalidate only changed nodes (~1s when nothing changed)
wiki sync --full       # full revalidation (pre-v0.2.1 behaviour)
wiki sync --backward   # manual backprop trigger for a specific node
wiki lint

# When the MCP server is not running or you want foreground processing
wiki jobs list
wiki jobs run          # process queued L2/L3 background jobs now
wiki jobs cancel <id>  # cancel a queued job before a worker claims it
wiki jobs rerun <id>   # requeue a completed, failed, or cancelled job
```

The default `wiki --help` surface is intentionally limited to daily user
workflows. Integration and development commands remain callable but are hidden
from the normal help listing: `wiki plugin ...` for Obsidian plugin JSON calls,
`wiki mcp ...` for external agents, `wiki testbed ...` for development
fixtures, and `wiki devices ...` for launcher diagnostics.

> **wiki sync default changed (v0.2.1)**: On an unchanged DAG, `wiki sync` only runs a
> content_hash scan (~0.6 seconds). Only changed nodes and their downstream are LLM-revalidated.
> Use `--full` for a complete revalidation.

> **Curation-native Queries**:
> - **Workspace Agent**: When a workspace is specified, queries use the persona
>   and Knowledge Requirement Spec in `curate.yml`.
> - **Vault Agent**: General vault queries use the global fallback persona.
> - **L3/L4 Evidence**: Queries select from L3 Concepts, L4 Synthesis nodes,
>   memory paths, source sections, and insight candidates as needed.
> - **No Frozen Query Artifacts**: Query answers are sessionless and traced with
>   `QTR-` records; explicit promotion writes reviewed results to `02_Wiki/`.

> **Background worker fallback**: When the MCP server is running, IngestWorker processes
> queued jobs automatically. During tests or offline CLI use, `wiki jobs run` drains the
> same queue in the foreground. Use `wiki jobs cancel <id>` for a queued job that
> should not run, and `wiki jobs rerun <id>` to retry a completed, failed, or
> cancelled job.

> **Instant L1 / L2·L3 Separation**: `wiki add` always creates the CTX, ToC,
> section markers, and coarse Atom Candidates instantly from parser structure
> without an LLM call (structural L1). Starting in v0.2.2, this step uses
> **AST-based chunking** to preserve math formula blocks such as `$$...$$`
> during text splitting. Deep L2/L3 extraction is separated from `wiki add`
> and performed by the distinct `wiki build` command. By default this queues
> background work; `--wait` requests synchronous execution. In MCP flows,
> `curator_register_source` maps to L1 registration and `curator_build_source`
> maps to L2/L3 building.

> **v0.2.1 performance path**: L2 runs multiple section-aware batches in parallel
> when the LLM client can be safely cloned. L3 tries embedding-based clustering
> first and falls back to the legacy LLM clustering plan only when embeddings are
> unavailable.

---

## 5. Obsidian Plugin Workflow

The plugin acts as an AI assistant inside Obsidian, optionally integrating with the Curator backend.

```text
Plugin standalone:
  User chat → Direct LLM call (Antigravity/Claude/OpenAI/DeepSeek/Ollama)

With Curator backend:
  User chat → Plugin calls backend tools → Curator searches the derived corpus
            → LLM generates an answer grounded in traceable evidence
```

### PDF Processing Flow (v0.2.1 — Adaptive Routing)

```text
Open PDF in Obsidian
     │
     │ check_source_status(file_hash) auto-call
     ▼
┌─── Unregistered ──────────────────────────────────────────────┐
│ ephemeral L1 mode: PDF.js in-memory parsing                   │
│ plugin UI: "+ Add to Incurator" button                        │
│ agent: read sections with fetch_document_section(source_key)   │
└───────────────────────────────────────────────────────────────┘
     │
     │ user clicks "+ Add" or calls import_source
     ▼
┌─── Processing ────────────────────────────────────────────────┐
│ external PDFs: create 04_Resources markdown reference stub     │
│ backend writes instant structural L1 CTX without an LLM call   │
│ L2/L3 extraction runs in the background                        │
│ fetch_document_section can read CTX sections after L1 complete │
└───────────────────────────────────────────────────────────────┘
     │
     │ L3 complete
     ▼
┌─── Indexed ──────────────────────────────────────────────────┐
│ plugin UI: "Indexed" status                                  │
│ agent: curator_query(question, workspace_id="...") available  │
└───────────────────────────────────────────────────────────────┘
     │
     │ dynamic curation query
     ▼
Answer with Sources & Trace
```

---

## 6. Agent Workflows

There are two agent access paths:

- **Obsidian plugin agent on the same device** uses shared runtime snapshots and
  hidden `wiki plugin ...` JSON commands. It does not start `wiki mcp` for
  local backend access.
- **External workspace agents** such as Claude Code, Claude Desktop,
  Antigravity, or other MCP clients use `wiki mcp`.

Keep these paths separate. Add same-device Obsidian plugin features under
`wiki plugin ...`; add external-agent features to the MCP server.

### External Agent (MCP) Workflow

AI agents like Claude Code and Antigravity access Curator through the MCP server.

#### Starting the MCP Server

```bash
# Run the MCP server with an explicit Vault path
VAULT_ROOT=/path/to/vault wiki mcp

# Or set it in your MCP client configuration:
# {
#   "mcpServers": {
#     "incurator": {
#       "command": "wiki",
#       "args": ["mcp"],
#       "env": { "VAULT_ROOT": "/path/to/vault" }
#     }
#   }
# }
```

### Agent Session Flow

```text
Agent session starts
     │
     │ 1. curator_check_workspace(workspace_path)
     │    → Validate curate.yml and install agent rules
     ▼
Domain query occurs
     │
     │ 2. curator_query(query, workspace_path)
     │    → Route through local/global/explore/source-section evidence
     │    → Return answer plus Sources & Trace
     ▼
Answer generated (with citations from search results)
     │
     │ (Optional) New source discovered
     │ 3. curator_add_knowledge(content, source_type)
     │    → Create Atom → auto-update index
     ▼
Session ends
```

### Key MCP Tools

| Tool | Purpose |
|------|---------|
| `curator_check_workspace` | Verify Workspace state and install rules at session start |
| `curator_query` | Natural language answer with Sources & Trace |
| `curator_workspace_init` | Create a new Workspace (interview-style wizard) |
| `curator_add_knowledge` | Add a new knowledge unit (Atom) directly |
| `curator_propose_correction` | Propose a reviewed correction over generated nodes |
| `curator_get_node` | Retrieve content of a specific node (CTX/ATM/CON/SYN) |

---

## 7. Installation Flow

```bash
# 1. Clone the repository
git clone https://github.com/your/incurator.git
cd Incurator

# 2. Full install (backend + plugin)
./setup.sh

# 3. Initialize Vault
wiki init /path/to/your/vault

# 4. MCP config auto-update (handled by setup.sh or wiki init):
#    wiki init updates these files automatically:
#    - ~/.antigravity/settings.json
#    - ~/.antigravity/mcp_config.json
#    - <vault>/.claude/settings.json

# 5. Add sources
wiki add 03_Notes/

# 6. Verify search
wiki query "First question"
```

---

## 8. Data Flow Summary

```text
[Human Layer]
  03_Notes/ ──┐
  04_Resources/ ──┤── wiki add ──► L1 CTX ──► L2 ATM ──► L3 CON
  02_Wiki/ ───┘                                              │
                                                             │ wiki query
[Machine Layer (state.sqlite DB)]                            ▼
  .curator/Collections/04_Synthesis/ ◄─────── L4 SYN (shared)
                    │
         ┌──────────┼──────────┐
         ▼          ▼          ▼
    wiki query  MCP Agent  Obsidian Plugin
   (CLI search) (AI agent)  (chat sidebar)
```

---

## 9. v0.3.2 Curation-Native Compile Model

v0.3.2 makes the Curator a **compiler** whose intermediate representation and
search index both live in the DB. The markdown collection is a derived,
disposable Obsidian projection, not the search corpus.

- **`state.sqlite` is the single source of truth** for curation knowledge:
  `source_spans`, `knowledge_units`, `graph_entities`/`graph_relations`,
  `community_reports`, `memory_paths`, dependencies, prompt runs, insight
  candidates.
- **`.curator/Collections/` L1–L4 markdown (CTX/ATM/CON/SYN) is emitted FROM the
  DB** for Obsidian inspection. It is not authoritative and can be re-emitted at
  any time — no DB↔file drift.
- **Search is DB-native**: FTS5 over authoritative records, chunk-level vectors,
  typed query expansion, RRF, and configured reranking.
- **L4 Synthesis is a generated search projection**, not an editable human
  artifact. Durable human-reviewed results are written only by explicit
  promotion to `02_Wiki/`.

Forward compile flow:

```text
wiki add   → parse (no LLM) → DB source_spans            → emit CTX projection
wiki build → LLM            → DB knowledge_units          → emit ATM projection
           → LLM+embeddings → DB entities/relations/reports→ emit CON projection
           → DB-native search rows/chunks/embeddings
wiki query → route → typed expansion + FTS5/vector/RRF/rerank + DB graph traversal → answer + QTR
```

### 9.1 Query Routes

`wiki query "..." --route <route>` answers through the v0.3.1 `QueryOrchestrator`:
`local` (entity/fact), `global` (community reports), `explore` (memory paths +
insight candidates), `source-section` (one source), or `auto` (orchestrator
selection). Without `--route`, `auto` runs. The same routing is available to
agents via MCP `curator_query` / `curator_explore`.

### 9.2 Backprop & Insight Lifecycle (Backward Pass)

Human/agent feedback is a **loss signal**. The backward pass classifies a change
before any patch and protects source truth:

- Agents classify feedback with MCP `curator_propose_correction`: correction /
  contradiction / derived_insight / style_only / promotion_request / ambiguous.
  Derived insights become provisional **insight candidates**; corrections yield
  an explicit patch plan over GENERATED nodes only. `03_Notes/`/`04_Resources/`
  are never edited.
- `wiki insight list|show|promote` (or MCP `curator_list_insight_candidates` /
  `curator_promote_insight`) review candidates; promotion writes only `02_Wiki/`.

### 9.3 Prompt Traceability

Every LLM call is a registered, versioned prompt contract that records a
`prompt_runs` (`PTR-`) trace (model, validator status, input/output hashes).
Inspect with `wiki prompt list|show|trace|eval` or MCP `curator_get_prompt_trace`.
Every query records a `QTR-` trace linking its route, evidence, and prompt runs.

---

## Related Docs

- [Plugin Guide](PLUGIN_GUIDE.md) — Obsidian plugin features in detail
- [MCP User Guide](MCP_USER_GUIDE.md) — AI agent MCP connection setup
- [User Guide](USER_GUIDE.md) — CLI command reference
- [System Philosophy](../philosophy/ABOUT_KR.md) — Curator/Artist metaphor background
