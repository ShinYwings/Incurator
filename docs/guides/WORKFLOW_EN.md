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
   │  Claude Code        │   │  wiki add / curate    │
   │  Gemini CLI         │   │  wiki sync / query    │
   │  Antigravity        │   │  wiki status / lint   │
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
[L1: Contexts]  .curator/Collections/01_Contexts/CTX-UUID.md
  - One context summary per source
  - Preserves original content, metadata, hash linkage
     │
     │  wiki add (Phase A)
     ▼
[L2: Atoms]  .curator/Collections/02_Atoms/ATM-UUID.md
  - Atomic knowledge units extracted from L1
  - One fact / claim / conclusion each
  - Includes verification evidence (citations)
     │
     │  wiki add (Phase B)
     ▼
[L3: Concepts]  .curator/Collections/03_Concepts/CON-UUID.md
  - Thematic clusters grouping Atoms from multiple sources
  - Cross-source comparison and synthesis
     │
     │  wiki curate --workspace <path>
     ▼
[L4: Exhibitions]  .curator/Collections/04_Exhibitions/EXH-UUID.md
  - Final context packages scoped to a specific Workspace's curate.yml
  - Terminal unit consumed by agents
  - Primary source for agent searches
```

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

# Internally:
#   - SHA-256 hash for deduplication
#   - PyMuPDF (PDF) / regex (MD) / BeautifulSoup (HTML) parsing + image extraction
#   - L1 Context file created immediately from structure → returns at once
#   - No LLM call; the source is searchable (BM25) as soon as L1 lands

# 3. Build L2/L3 (wiki build) — the deep, LLM-heavy pass
wiki build            # queue L2/L3 to the background worker (non-blocking)
wiki build --wait     # run L2 (Atoms) → L3 (Concepts) synchronously now
#   - Progress: .curator/dashboard.md updated in real-time (open in Obsidian to watch)
```

> **Two-step ingest**: `wiki add` registers sources and generates instant L1
> (structural, no LLM) — fast and offline-capable. `wiki build` runs the deeper
> L2/L3 extraction; by default it queues to the MCP server's background
> IngestWorker, or use `--wait` to run now. Monitor via `wiki status` or
> `.curator/dashboard.md`. L4 Exhibitions require a separate `wiki curate` command.

### 4-2. Workspace Curation

```bash
# Create curate.yml in a Workspace folder (manually or via wiki workspace init)
# Key fields in curate.yml:
#   vault_root: /path/to/vault   ← Vault path
#   sources.include: ["03_Notes/**", "04_Resources/**"]
#   min_confidence: 0.70

# Generate L4 Exhibition
wiki curate --workspace 01_Workspaces/MyProject
```

### 4-3. Search and Query

```bash
# Natural language query (BM25 + vector + LLM rerank)
wiki query "How to estimate camera poses without COLMAP in Gaussian Splatting?"

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
```

> **wiki sync default changed (v0.2.1)**: On an unchanged DAG, `wiki sync` only runs a
> content_hash scan (~0.6 seconds). Only changed nodes and their downstream are LLM-revalidated.
> Use `--full` for a complete revalidation.

> **Background worker fallback**: When the MCP server is running, IngestWorker processes
> queued jobs automatically. During tests or offline CLI use, `wiki jobs run` drains the
> same queue in the foreground.

> **Instant L1 / L2·L3 Separation**: `wiki add` always creates the CTX, ToC,
> section markers, and coarse Atom Candidates instantly from parser structure
> without an LLM call (structural L1). The deep L2/L3 extraction is separated
> from `wiki add` and performed by a distinct `wiki build` command.

> **v0.2.1 performance path**: L2 runs multiple section-aware batches in parallel
> when the LLM client can be safely cloned. L3 tries embedding-based clustering
> first and falls back to the legacy LLM clustering plan only when embeddings are
> unavailable.

---

## 5. Obsidian Plugin Workflow

The plugin acts as an AI assistant inside Obsidian, optionally integrating with the Curator backend.

```text
Plugin standalone:
  User chat → Direct LLM call (Antigravity/Claude/OpenAI)

With Curator backend:
  User chat → Plugin calls MCP tools → Curator searches Exhibitions
            → LLM generates answer grounded in Exhibition content
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
     │ wiki curate if needed
     ▼
L4 Exhibition created → searchable via search_curator
```

---

## 6. AI Agent (MCP) Workflow

AI agents like Claude Code, Gemini CLI, and Antigravity access Curator through the MCP server.

### Starting the MCP Server

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
     │    → Validate curate.yml, install agent rules, confirm Exhibition exists
     ▼
Domain query occurs
     │
     │ 2. search_curator(query, workspace_path)
     │    → BM25 + vector search over Exhibitions
     │    → Automatically runs wiki curate if no results found
     ▼
Answer generated (with citations from search results)
     │
     │ (Optional) New source discovered
     │ 3. curator_add_knowledge(content, source_type)
     │    → Create Atom → auto-update index
     ▼
Session ends
     │
     │ 4. (Optional) curator_curate_workspace
     │    → Refresh Exhibition
```

### Key MCP Tools

| Tool | Purpose |
|------|---------|
| `curator_check_workspace` | Verify Workspace state and install rules at session start |
| `search_curator` | Natural language search (Exhibition-based) |
| `curator_workspace_init` | Create a new Workspace (interview-style wizard) |
| `curator_curate_workspace` | Regenerate L4 Exhibition for the current Workspace |
| `curator_add_knowledge` | Add a new knowledge unit (Atom) directly |
| `curator_update_node` | Edit an existing DAG node and propagate changes |
| `curator_get_node` | Retrieve content of a specific node (CTX/ATM/CON/EXH) |

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
#    - ~/.gemini/settings.json
#    - ~/.gemini/antigravity/mcp_config.json
#    - <vault>/.claude/settings.json

# 5. Add sources and curate
wiki add 03_Notes/
wiki curate --workspace 01_Workspaces/MyProject

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
                                                             │ wiki curate
[Machine Layer]                                              ▼
  .curator/Collections/04_Exhibitions/ ◄─────── L4 EXH (workspace-scoped)
                    │
         ┌──────────┼──────────┐
         ▼          ▼          ▼
    wiki query  MCP Agent  Obsidian Plugin
   (CLI search) (AI agent)  (chat sidebar)
```

---

## Related Docs

- [Plugin Guide](PLUGIN_GUIDE_EN.md) — Obsidian plugin features in detail
- [MCP User Guide](MCP_USER_GUIDE_EN.md) — AI agent MCP connection setup
- [User Guide](USER_GUIDE_EN.md) — CLI command reference
- [System Philosophy](../philosophy/about.md) — Curator/Artist metaphor background
