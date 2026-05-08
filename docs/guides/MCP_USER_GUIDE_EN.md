# 🔌 MCP User Guide: Connect Your Agents


The **InCurator MCP Server** is the interface through which the Artist (human + agent) interacts with the Curator directly. Agents in workspaces — Claude Desktop, Claude Code, Gemini CLI — use this server to browse the Curator's staged Exhibitions, and to push corrections or new insights back into the knowledge graph. This is how the Artist's feedback completes the loop: errors and discoveries during chat propagate to the underlying knowledge base, refining prior knowledge over time.

[한국어 가이드](MCP_USER_GUIDE.md)

---

## 1. Prerequisites

Ensure you have the MCP dependencies installed:
```bash
uv pip install -e '.[mcp]'
```

> [!NOTE]
> The server uses the `WIKI_ROOT` environment variable to locate your vault. If not set, it will auto-discover the vault by walking up from the current directory.

---

## 2. Configuration

Run the following command to get a configuration snippet tailored for your client:
```bash
wiki mcp install
```
You can also specify a client: `wiki mcp install claude` or `wiki mcp install gemini`.

### Example Configuration (`mcp_config.json` or `settings.json`)
```json
{
  "mcpServers": {
    "incurator": {
      "command": "wiki",
      "args": ["mcp"],
      "env": {
        "WIKI_ROOT": "/absolute/path/to/your/vault"
      }
    }
  }
}
```

---

## 3. Available Tools

### 3.1 Search & Discovery

#### `search_curator`
- **Role**: Search the entire vault using the QMD engine (BM25 + Vector + Rerank).
- **Auto-Sync**: If new sources are pending, it automatically runs `wiki curate` before searching.
- **Parameters**: `query`, `scope` (all/contexts/atoms/concepts/exhibitions), `mode` (hybrid/lex/vec), `limit`.

#### `curator_layer_index`
- **Role**: Get a high-level overview of page counts and recent IDs for each layer.

#### `curator_status`
- **Role**: Check vault paths and search engine readiness.

### 3.2 DAG Traversal & Analysis

#### `curator_get_node`
- **Role**: Fetch the full markdown content of a node by ID (e.g., `EXH-abc12345`).

#### `curator_traverse_evidence`
- **Role**: Walk down an Exhibition's evidence chain (EXH ➡️ CON ➡️ ATM) to verify claims.

#### `curator_find_contradictions`
- **Role**: List Atoms flagged for human review or carrying contradictory claims.

### 3.3 Knowledge Maintenance

#### `curator_add_knowledge`
- **Role**: Save a conversational insight as a new **L2 Atom**. This knowledge will be synthesized into the DAG in the next curation cycle.

#### `curator_update_node`
- **Role**: Overwrite a node's content.
- **Automatic Repair (Backprop)**: If updating an **Exhibition (EXH)**, `wiki sync` is triggered internally to propagate changes upstream to Concepts and Atoms, rewriting them to maintain consistency. This allows for immediate correction of prior knowledge discovered during chat.

#### `curator_reindex`
- **Role**: Manually rebuild the QMD search index.

### 3.4 Persona Management

#### `curator_update_artist_persona`

- **Role**: Updates the Artist `persona:` block in a workspace's `curate.yml` using a natural-language request.
- **Parameters**: `workspace_path` (absolute path to the workspace), `request` (natural-language instruction string).
- **Example**: `"This workspace is for a computer vision researcher. Set the confidence threshold to 0.85 and exhibition_intent to researcher."`

#### `curator_update_curator_persona`

- **Role**: Updates the Curator `persona:` block in `.curator/config.yml` using a natural-language request.
- **Parameters**: `request` (natural-language instruction string).
- **Example**: `"I am a STEM researcher focused on machine learning and systems design. I prioritize rigor and only work with high-confidence (0.85+) knowledge."`
