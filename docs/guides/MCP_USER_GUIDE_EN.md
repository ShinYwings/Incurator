# 🔌 MCP User Guide: Connect Your Agents


The **Incurator MCP Server** is the interface through which the Artist (human + agent) interacts with the Curator directly. Agents in workspaces — Claude Desktop, Claude Code, Gemini CLI — use this server to browse the Curator's staged Exhibitions, and to push corrections or new insights back into the knowledge graph. This is how the Artist's feedback completes the loop: errors and discoveries during chat propagate to the underlying knowledge base, refining prior knowledge over time.

[한국어 가이드](MCP_USER_GUIDE.md)

---

## 1. Prerequisites

Ensure you have the MCP dependencies installed:
```bash
cd backend
uv pip install -e '.[mcp]'
```

> [!NOTE]
> The server uses the `VAULT_ROOT` environment variable to locate your vault. Agent/plugin integrations should set it explicitly whenever possible. The v0.2.0 contract prefers explicit failure over silently falling back to the current working directory when a vault cannot be resolved.

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
    "Incurator": {
      "command": "/absolute/path/to/wiki",
      "args": ["mcp"],
      "env": {
        "VAULT_ROOT": "/absolute/path/to/your/vault"
      }
    }
  }
}
```

> [!TIP]
> If you sync your configuration across multiple devices, the `command` absolute path might differ between Linux and macOS. Ensure you use the correct absolute path for the executable on each specific machine.

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

#### `curator_import_source`
- **Role**: Register an external file with the Incurator backend. Depending on policy, the backend may connect it without copying through Reference Mode, or safely copy it into a user-approved `04_Resources/` destination.
- **Parameters**: Depending on implementation stage, the input may be named `file_path` or `source_path`; both mean the absolute path to the external file. The policy must be explicit, such as `policy="reference"` or `destination_policy="mirror_03_to_04"`. Clients should call with `dry_run=true` first, show the proposal to the user, then call the mutating operation after approval.
- **Destination rule**: External PDFs default to `04_Resources`, never `03_Notes`. If the active note is `03_Notes/Vision/Foo.md`, the default proposal is `04_Resources/Vision/Foo/<pdf-file>.pdf`. Without a linked note, the fallback proposal is `04_Resources/Inbox/<pdf-file>.pdf`.
- **No overwrite**: Same-hash files reuse the existing source record. Same-name but different-hash collisions require a suffix or a human-selected destination.

#### `curator_list_external_resources`
- **Role**: Return the list of external libraries (e.g., Zotero) configured in the platform-aware global settings (`~/.config/curator/config.yml`) along with their active absolute paths.

#### `curator_source_status`
- **Role**: Check the processing status of a file and the status of the `external_path` fallback logic. Can be used to identify files that have been `MOVED`.
- **Parameters**: Use whichever identifier the implementation supports: `source_id`, `logical_source_id`, `source_path`, or `file_path`.
- **Obsidian plugin display**: The plugin can render this result as a PDF chip status badge, such as `untracked`, `queued`, `running L1`, `running L2`, `running L3`, `running L4`, `indexed`, `stale`, `moved`, or `error`.

#### `curator_rebind_source`
- **Role**: Heal broken links caused by Hash Drift (e.g., Apple Pencil annotations) or moved files. Re-establishes the connection for a `logical_source_id` with a new path and hash after human confirmation.
- **Parameters**: `logical_source_id` (unique identifier), `new_path` (new absolute path).
- **Important**: This tool must be called only after Human-in-the-Loop approval. The backend must separate proposal from mutation, and the client must show which file will be rebound to which logical source.

#### `curator_search_source`
- **Role**: Search within a specific source or PDF page range. The Obsidian plugin uses this to combine immediate viewer context with backend RAG results for the currently open PDF.
- **Parameters**: `query`, `source_id` or `source_path`, optionally `page_start`, `page_end`, `limit`, and `mode`.
- **Returns**: page number, score, snippet, and source provenance.

#### `curator_get_pdf_page`
- **Role**: Return backend-stored text/provenance for a specific PDF page.
- **Parameters**: `source_id` or `source_path`, `page`.
- **Use case**: Provides stable text context when the plugin viewer context is incomplete or when a provider strips image attachments.

#### `curator_add_knowledge`
- **Role**: Save a conversational insight as a new **L2 Atom**. This knowledge will be synthesized into the DAG in the next curation cycle.

#### `curator_update_node`
- **Role**: Overwrite a node's content.
- **Automatic Repair (Backprop)**: If updating an **Exhibition (EXH)**, `wiki sync` is triggered internally to propagate changes upstream to Concepts and Atoms, rewriting them to maintain consistency. This allows for immediate correction of prior knowledge discovered during chat.

#### `curator_reindex`
- **Role**: Manually rebuild the QMD search index.

### 3.4 Document Status & On-demand Queries (v0.2.1)

#### `check_source_status`

- **Role**: Look up a file's registration state by its SHA-256 hash. Called automatically by the plugin when a PDF is opened to determine whether the agent should use ephemeral mode or `curator_query`.
- **Parameters**: `file_hash` (SHA-256 hash string of the file).
- **Returns**: `registered`, `source_id`, `l1_complete`, `l2_complete`, `l3_complete`, `jobs_pending`.
- **Implementation status**: The backend looks up `sources.content_hash` and returns queued/running `ingest_jobs` with the source status.
- **Note**: Works regardless of path differences (terminal absolute path vs. plugin relative path) — same hash means the same result. CLI and plugin ingestion paths are transparent to each other.

#### `fetch_document_section`

- **Role**: Return the text of a specific document section. If the document is unregistered, the plugin serves it from in-memory (PDF.js). After `wiki add`/`import_source` reaches `l1_complete=True`, the backend serves the CTX `Source Sections` immediately. `curator_query` remains available after L3 completes.
- **Parameters**: `source_key` (logical_source_id or file_hash), `toc_id` (section id from the CTX frontmatter `toc` array), `page_start`/`page_end` (page-range fallback for PDFs without a ToC).
- **Implementation status**: When `source_key` resolves to a tracked source or file path, the backend returns text by CTX section marker, source heading, or PDF page. With the v0.2.1 default (`llm.instant_l1: true`), the L1 CTX is generated without an LLM call, so section reads become available quickly.
- **Agent usage**: The agent reads the ToC minimap in its system prompt, then calls this tool with the relevant `toc_id`.

#### `curator_query`

- **Role**: Search for relevant L3 Concepts by natural-language question and synthesize an LLM answer on demand. If an Exhibition for the same question was previously generated, returns it from cache without calling an LLM again.
- **Parameters**: `question` (natural-language query string), `workspace_path` (absolute path to the workspace directory, defaults to `""`), `force_new` (bypass cache and regenerate, default `false`).
- **Returns**: `ok`, `answer` (synthesized answer text), `exhibition_id` (EXH node ID of the generated or cached Exhibition), `cache_hit` (boolean), `question` (echoed back), `trace` object containing: `matched_concepts` (list of CON IDs), `source_ids`, `source_paths`, `latency_ms`, `l3_complete` (whether L3 DAG is fully built for related sources).
- **Cache key**: `sha256(workspace_id + ":" + normalized_question)[:16]` stored as `cache_key` in the EXH frontmatter.
- **Cache invalidation**: Backprop changes to a referenced CON automatically invalidate the EXH cache. EXHs with `is_verified_by_human=true` are protected from invalidation.
- **Implementation status**: Implemented in v0.2.1. Requires `l3_complete=true` for full concept-graph answers. If L3 is incomplete, the tool returns `ok=true`, `fallback="l3_incomplete"`, `answer=""`, and `trace.l3_complete=false`; clients should fall back to source sections or local PDF context.

#### `promote_exhibition`

- **Role**: Promote an agent-generated query Exhibition to `02_Wiki/` after human review. The promoted EXH receives `is_verified_by_human=true` and `exhibition_origin="promoted"`, and is excluded from future backprop rebuilds.
- **Parameters**: `exh_id` (EXH node ID to promote), `workspace_path` (absolute path to the workspace directory, optional).
- **Returns**: `ok`, `exhibition_id` (the EXH that was promoted), `promoted_to` (absolute path of the new page inside `02_Wiki/`).
- **Implementation status**: Implemented in v0.2.1. Calls `classify_wiki_topic` + `save_wiki_page` internally; updates the original EXH frontmatter with `promoted_to` so the link is bidirectional.

#### `check_ingest_status`

- **Role**: Return the current background ingest job queue status. The plugin polls this every 5 seconds after `wiki add` or `import_source` to detect when L2/L3 processing completes. Stop polling when `idle: true` and refresh the UI.
- **Parameters**: `workspace_path` (absolute path, optional).
- **Returns**:
  - `ok` (always true)
  - `running` — list of currently running jobs (each includes `source_name`, `phase`, `progress`, `progress_current`, `progress_total`)
  - `queued` — list of queued jobs
  - `done_today` — number of jobs completed today
  - `idle` — `true` when both `running` and `queued` are empty
- **Implementation status**: Implemented in v0.2.1. `.curator/dashboard.md` is also auto-updated by `IngestWorker` on every job state change (Obsidian live preview re-renders automatically on file change).

#### `get_available_models`

- **Role**: Return the list of models per provider from the `models.json` file bundled with the backend package. Used by the plugin UI to dynamically populate the model selection dropdown.
- **Parameters**: none.
- **Returns**: `{ "antigravity": [...], "claude": [...] }` — per-provider model list.

### 3.5 Workspace Management

#### `curator_workspace_init`

- **Role**: Initialize a new workspace with `curate.yml`, agent rules, and an auto-generated Artist persona. Use this when `curator_check_workspace` reports a missing `curate.yml`, or when the user asks to connect a workspace to their Curator.
- **Parameters**: `workspace_path` (absolute path), `project` (slug), `description`, `domains` (list), `topics` (list), `min_confidence`.
- **Agent detection**: The connecting client runtime (Claude, Gemini, Codex, etc.) is auto-detected and the matching rule file is installed.
- **Scenario handling**:
  - *Empty directory* — everything is created from scratch.
  - *Agent-only* — existing rule file is modified by LLM to integrate Curator hooks; returns `integration_prompt` if LLM is unavailable.
  - *Full/restore* — owned files are refreshed to latest templates; managed block is replaced in-place.
- **Returns**: `ok`, `workspace`, `agent`, `scenario`, `created`, `updated`, `persona`, `rule_integration` (if LLM auto-modified), `integration_prompt` (if LLM unavailable), `recommended_next_steps`.

#### `curator_check_workspace`

- **Role**: Verify that a workspace is healthy and load the active Exhibition as primary context. **Call this at every session start before responding to any domain query.**
- **Parameters**: `workspace_path` (absolute path to the workspace directory).
- **Returns**: `ok`, `workspace`, `project`, `scenario`, `exhibition`, `exhibition_exists`, `issues`.
  - `scenario` will be `"agent-only"` if Curator rules are not yet installed — call `curator_workspace_init` to fix.

### 3.5 Persona Management

#### `curator_update_artist_persona`

- **Role**: Updates the Artist `persona:` block in a workspace's `curate.yml` using a natural-language request.
- **Parameters**: `workspace_path` (absolute path to the workspace), `request` (natural-language instruction string).
- **Example**: `"This workspace is for a computer vision researcher. Set the confidence threshold to 0.85 and exhibition_intent to researcher."`

#### `curator_update_curator_persona`

- **Role**: Updates the Curator `persona:` block in `.curator/config.yml` using a natural-language request.
- **Parameters**: `request` (natural-language instruction string).
- **Example**: `"I am a STEM researcher focused on machine learning and systems design. I prioritize rigor and only work with high-confidence (0.85+) knowledge."`
