# 🔌 MCP User Guide: Connect Your Agents


The **Incurator MCP Server** is the interface through which the Artist (human + agent) interacts with the Curator directly. Agents in workspaces — Claude Desktop, Claude Code, Antigravity — use this server to query the live DAG, inspect evidence, and push corrections or new insights back into the knowledge graph. This is how the Artist's feedback completes the loop: errors and discoveries during chat propagate to the underlying knowledge base, refining prior knowledge over time.

[한국어 가이드](MCP_USER_GUIDE_KR.md)

---

## 1. Prerequisites

Ensure you have the MCP dependencies installed:
```bash
uv pip install -e './backend[mcp]'
```

The current server targets the MCP Python SDK 1.x `mcp.server.fastmcp` contract;
the package metadata excludes MCP 2.x until that major API is migrated.

> [!NOTE]
> The server uses the `VAULT_ROOT` environment variable to locate your vault. Agent/plugin integrations should set it explicitly whenever possible. The v0.2.0 contract prefers explicit failure over silently falling back to the current working directory when a vault cannot be resolved.

---

## 2. Configuration

Run the following command to get a configuration snippet tailored for your client:
```bash
wiki mcp install
```
You can also specify a client: `wiki mcp install claude` or `wiki mcp install antigravity`.

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
- **Role**: Search the entire vault using DB-native hybrid search: FTS5 lexical
  retrieval, chunk-level vectors, typed query expansion, RRF, and configured
  reranking. Tier-2 LLM/HyDE expansion is recovery-only by default, engaging when
  raw lexical/vector confidence is low.
- **Indexing**: Searches authoritative DB search rows, not the derived markdown
  projection. Run `wiki add`/`wiki build` to bring pending sources into the graph
  before search.
- **Parameters**: `query`, `scope` (all/contexts/atoms/concepts/synthesis), `mode` (hybrid/lex/vec), `limit`.

#### `curator_layer_index`
- **Role**: Get a high-level overview of page counts and recent IDs for each layer.

#### `curator_status`
- **Role**: Check vault paths and search engine readiness.

### 3.2 DAG Traversal & Analysis

#### `curator_get_node`
- **Role**: Fetch the full markdown content of a node by ID (e.g., `SYN-abc12345`).

#### `curator_traverse_evidence`
- **Role**: Walk down a Synthesis node's evidence chain (SYN -> CON/REP -> ATM/source spans) to verify claims.

#### `curator_find_contradictions`
- **Role**: List Atoms flagged for human review or carrying contradictory claims.

#### `curator_dismiss_contradiction`
- **Role**: Dismiss a flagged contradiction if it is deemed invalid or unimportant by the human/agent.
- **Parameters**: `contradiction_id`, `reason`, `workspace_path` (optional).

#### `curator_resolve_contradiction`
- **Role**: Resolve a contradiction by providing a synthesized resolution or correction.
- **Parameters**: `contradiction_id`, `resolution_text`, `workspace_path` (optional).

#### `curator_get_provenance`
- **Role**: Retrieve the full provenance chain (origin source, atom, concept) for a given piece of generated knowledge.
- **Parameters**: `node_id`, `workspace_path` (optional).

### 3.3 Knowledge Maintenance

#### `curator_import_source`
- **Role**: Register an external file with the Incurator backend. Depending on policy, the backend may connect it without copying through Reference Mode, or safely copy it into a user-approved `04_Resources/` destination.
- **Parameters**: Depending on implementation stage, the input may be named `file_path` or `source_path`; both mean the absolute path to the external file. The policy must be explicit, such as `policy="reference"` or `destination_policy="mirror_03_to_04"`. Clients should call with `dry_run=true` first, show the proposal to the user, then call the mutating operation after approval.
- **Destination rule**: External PDFs default to Reference Mode. The backend creates a markdown reference stub under `04_Resources/` and leaves the PDF in its original location. Copy mode is explicit and still targets `04_Resources`, never `03_Notes`.
- **Portable identity**: Zotero imports persist only the effective attachment
  key (`zotero:<key>`); the backend resolves it through the current device's
  Zotero DB. Other external imports require a configured named root and persist
  `@<root_key>/<relative-path>`. Resolved absolute paths are never durable state.
- **No overwrite**: Same-hash files reuse the existing source record. Same-name but different-hash collisions require a suffix or a human-selected destination.

#### `curator_register_source`
- **Role**: Fast structural registration of a source (L1 generation) without deep LLM processing.
- **Parameters**: `file_path` or `source_path`.
- **Return**: On success, includes `warnings`. If the best-effort search index
  refresh is skipped because the index/database is temporarily unavailable,
  registration still succeeds and the skipped refresh is reported there.
- **Note**: Replaces the synchronous part of the deprecated `curator_ingest_source`.

#### `curator_build_source`
- **Role**: Trigger the deep L2 (Atoms) and L3 (Concepts) knowledge extraction for a registered source.
- **Parameters**: `file_path` or `source_id`.
- **Return**: A synchronous (`wait=true`) build returns `ok=false` if the ingest
  pipeline produces no result for the requested source. If extraction succeeds
  but the best-effort search refresh fails, `ok` remains true and `warnings`
  describes the skipped refresh.

#### `curator_add_all`
- **Role**: Run `wiki add` across the workspace source directories, discovering new or changed raw files and ensuring structural registration (L1) is up to date.
- **Result**: Returns `discovered`, `removed`, and `summarized` counts.

#### `curator_build_all`
- **Role**: Trigger deep L2 and L3 knowledge extraction for all sources in the workspace that have pending jobs.

#### `curator_sync`
- **Role**: Synchronize the knowledge graph DAG. Identifies changed nodes and invalidates affected downstream caches/jobs incrementally.

#### `curator_lint`
- **Role**: Perform validation and health checks on the workspace DAG to ensure schema and link integrity.
- **v0.8.0**: the report additionally includes the Compiler Integrity audit —
  unsupported/failed/stale claim counts, evidence-hash mismatches,
  broad-fallback findings, and formula-status inconsistencies. The tool's
  input schema is unchanged; only the report content is richer. Agents should
  treat release-blocking structural audit findings the same way as broken links:
  fix or escalate, never ignore. Failed/stale/unchecked claims are excluded from
  serving and are telemetry, not sync review blockers. Evidence returned by
  query/search tools now hydrates full span text (hash-verified against the source) instead of a
  200-character preview, and claims carry `support_status`/`formula_status`
  labels — `unchecked`, `failed`, `stale`, or retired claims must not be
  presented as verified knowledge.

#### `curator_ingest_source` (Deprecated)
- **Role**: Legacy combined ingestion. Use `curator_register_source` followed by `curator_build_source` instead.

#### `curator_list_external_resources`
- **Role**: Return the list of external libraries (e.g., Zotero) configured in the machine-local settings (`.cache/config/config.yml` at the repository root) along with their active absolute paths.


#### `curator_rebind_source`
- **Role**: Heal broken links caused by Hash Drift (e.g., Apple Pencil annotations) or moved files. Re-establishes the connection for a `logical_source_id` with a new path and hash after human confirmation.
- **Parameters**: `logical_source_id` (unique identifier), `new_path` (new absolute path).
- **Important**: This tool must be called only after Human-in-the-Loop approval. The backend must separate proposal from mutation, and the client must show which file will be rebound to which logical source.

#### `curator_search_sources`
- **Role**: Search within a specific source or PDF page range. The Obsidian plugin uses this to combine immediate viewer context with backend RAG results for the currently open PDF.
- **Parameters**: `query`, `source_id` or `source_path`, optionally `page_start`, `page_end`, `limit`, and `mode`.
- **Returns**: page number, score, snippet, and source provenance.
- **Note**: The singular alias `curator_search_source` was removed in v0.2.1.


#### `curator_get_pdf_context`
- **Role**: Adaptive PDF chat context. For registered, L1-complete sources it
  serves the durable CTX projection without reparsing the PDF. Otherwise it
  performs read-only on-demand extraction and never registers the source. This
  is the primary tool used to assemble `<pdf_window>` and `<document_outline>`
  context blocks. **Agentic usage**: Agents should proactively call this tool
  with `radius=0` and a specific `page_num` when asked to read a specific
  chapter or page.
- **Parameters**:
  - `file_path` (required): Absolute filesystem path to the PDF.
  - `query` (optional): Query string to score pages by relevance. When provided, the most relevant pages are returned rather than a fixed window.
  - `page_num` (optional, default 0): Current 1-based page number. 0 = no current page (returns query-scored or first N pages).
  - `radius` (optional, default 2): Pages around `page_num` to include in the window.
  - `max_pages` (optional, default 8): Maximum pages to return.
- **Returns**:
  - `ok`: `true` on success, `false` on error.
  - `source_tracked`: Whether the PDF is registered in the Incurator knowledge graph.
  - `total_pages`: Total page count.
  - `pages`: `[{page_num, text, score}]` — up to `max_pages` most relevant pages.
  - `outline`: `[{title, page_num, level}]` — document table of contents.
  - `is_empty_pdf`: `true` if the PDF contains no extractable text (scanned/image-only).
  - `context_source`: `durable_l1_projection` or `ephemeral_parse`.
  - `degraded_reason`: Optional reason that durable context could not provide
    exact text.
- **Why it replaces multiple calls**: Previously the plugin made three separate MCP calls (`pdf_window`, `document_outline`, `pdf_rag_hits`) that did not exist in the backend and silently returned empty results. This tool unifies them in a single call that actually works.
- **Performance**: Registered L1 sources read the CTX projection first.
  Ephemeral/degraded fallback uses `parse_page_window()` to read only requested
  pages, making it safe for 600-page documents without loading the full file.

#### `curator_get_pdf_toc`
- **Role**: Extract a raw Table of Contents directly from a PDF. Prefer
  `curator_get_pdf_context` for registered L1 sources because it can return the
  durable CTX ToC without reparsing the original PDF.
- **Parameters**: `file_path` (Absolute filesystem path to the PDF).
- **Returns**: `[{title, page, level}]`

#### `curator_add_knowledge`
- **Role**: Promote a conversational insight or discussion to the human-verified Wiki space (`02_Wiki/`). This permanently captures valuable information from the chat into the project's durable Wiki.
- **Return**: Successful promotion returns the `wiki_path` and `warnings`. A
  search refresh failure is reported in `warnings` without discarding the
  already-written Wiki page.

#### `curator_update_node`
- **Role**: Disabled non-mutating endpoint. Direct generated-node overwrites are not supported.
- **Use instead**: `curator_propose_correction` for reviewed corrections, or `promote_answer` / `curator_promote_insight` for durable human-approved knowledge.

#### `curator_propose_correction`
- **Role**: Propose a correction targeting an authoritative generated record.
  The backend classifies the proposal and returns a recommended action; it does
  not overwrite the target automatically. Markdown pages under
  `.curator/Collections/` are derived inspection projections, so editing them is
  not a correction mechanism.
- **Parameters**: `node_id`, `correction`, `workspace_path` (optional),
  `previous` (optional prior artifact text).
- **Backend handling**: Returns classification, recommended action, affected node
  ids, review requirement, trace id, and any provisional insight candidate.

#### `curator_reindex`
- **Role**: Manually rebuild DB-native search state (`search_documents`,
  `search_chunks`, FTS5 rows, and missing/stale chunk embeddings).
- **Degraded result**: Returns `ok=true` with `degraded=true` when lexical FTS5 is
  current but embeddings, query expansion, or reranking are unavailable. Query
  traces record `vector_unavailable`, runtime `vector_failed`,
  `query_expander_unavailable`, or `reranker_failed` as appropriate. Provider
  embedding/reranker output must have exact request cardinality and finite
  numeric values, and ready embeddings for one provider/model must share one
  dimension; an invalid embedding batch is not partially persisted.

### 3.4 Document Status & On-demand Queries (v0.2.1)

#### `check_source_status`

- **Role**: Look up a file's registration state by its SHA-256 hash. The plugin
  calls it when backend PDF context or an explicit Add/status action needs to
  distinguish ephemeral mode, durable L1 section serving, and L3-complete
  `curator_query`; local viewer context does not wait for this call.
- **Parameters**: `file_hash` (SHA-256 hash string of the file).
- **Returns**: `registered`, `source_id`, `l1_complete`, `l2_complete`, `l3_complete`, `jobs_pending`.
- **Implementation status**: The backend looks up `sources.content_hash` and returns queued/running `ingest_jobs` with the source status.
- **Note**: Works regardless of path differences (terminal absolute path vs. plugin relative path) — same hash means the same result. CLI and plugin ingestion paths are transparent to each other.

#### `fetch_document_section`

- **Role**: Return backend text for a registered document section by CTX section
  id, source heading, or PDF page range. Unregistered viewer turns do not call
  this tool; the plugin uses local in-memory PDF.js context or its read-only
  backend PDF-context fallback instead. For large documents whose L1 uses
  `source_text_policy: on_demand`, the backend reads the original source instead
  of relying on inline CTX text. `curator_query` becomes available after L3
  completes.
- **Parameters**: `source_key` (logical_source_id or file path), `content_hash` (SHA-256 hex of the source file — alternative lookup key when the vault path is unknown, e.g. from the plugin's `fileHash` field), `toc_id` (section id from the CTX frontmatter `toc` array), `page_start`/`page_end` (page-range fallback for PDFs without a ToC).
- **Page cache (v0.26.0)**: For PDF page-range requests (`page` / `page_start` / `page_end`) combined with a `content_hash`, the backend uses a persistent per-page cache at `.cache/pdf_pages/<hash>/<pagenum>.txt`.  Cache hits are served without re-parsing the PDF; misses trigger a bounded parse of only the requested pages (not the entire document) and the result is written to cache for future sessions.  The response includes `context_source` (`pdf_page_cache` / `pdf_page_cache_partial`), `cache_hits`, and `cache_misses` fields.
- **Implementation status**: When `source_key` or `content_hash` resolves to a tracked source or file path, the backend returns text by CTX section marker, source heading, or PDF page. With the v0.2.1 default (`llm.instant_l1: true`), the L1 CTX is generated without an LLM call, so section reads become available quickly.
- **Agent usage**: The agent reads the ToC minimap in its system prompt, then calls this tool with the relevant `toc_id`.  For cross-page equation lookups from the popover, the plugin calls this tool with `content_hash` + `page` when the PDF is not open in the viewer.

#### `curator_query`

- **Role**: Answer a natural-language question through the dynamic Curation lens
  (DB graph + DB-native hybrid search over source spans, atoms, reports, and the
  shared L4 Synthesis layer) and synthesize an LLM answer. **Sessionless**:
  returns an answer + trace and writes no vault file.
- **Parameters**: `question` (natural-language query string), `workspace_path` (absolute path to the workspace directory, defaults to `""`).
- **Returns**: `ok`, `answer` (synthesized answer text), `question` (echoed back), `trace` object containing: `matched_concepts` (list of CON IDs), `source_paths`, `synthesis_node_ids`, `community_report_ids`, `source_span_ids`, `prompt_trace_ids`, `trace_id` (`QTR-`), `route`, `pack_id`, `snapshot`, `budget`, `latency_ms`, `l3_complete` (whether L3 DAG is fully built for related sources). For synthesized answers, `source_span_ids` are the spans cited by the validated answer output, not the full retrieved pack. `pack_id`, `snapshot`, and `budget` are populated only for ContextService-backed routes; routes that have not been migrated to ContextService return `null` for those fields.
- **Context bounds**: ContextService applies the context budget before synthesis, and the synthesizer receives the full already-budgeted pack. Large L1 source recaps and raw PDF text should be fetched explicitly with source/PDF tools instead of being pushed wholesale through `curator_query`.
- **Implementation status**: v0.3.2. Requires `l3_complete=true` for full
  concept-graph answers. If L3 is incomplete, the tool returns a degraded trace
  and uses DB-native lexical/vector retrieval where possible; clients can still
  fall back to source sections or local PDF context. For an evidence pack without
  synthesis, use `curator_fetch_context`.
- **Workspace policy failures**: An empty path or a directory without
  `curate.yml` uses the `default` policy. If the file exists but is unreadable,
  malformed, has an invalid root/source-scope shape, or is semantically invalid,
  the query fails before retrieval instead of silently widening to the
  unrestricted default policy.
- **Provider failures**: If answer synthesis fails after retrieval, the tool
  returns `ok=false` with the existing `error`, QTR/PTR ids, warnings,
  ContextService metadata, and selected provenance that were already recorded.
  Configured fallback is attempted first. The tool does not return an empty
  success or discard the trace, and unexpected runtime/storage defects are not
  relabelled as provider failures.

#### `promote_answer`

- **Role**: Promote a sessionless Q&A answer into `02_Wiki/` after human review. Writes only `02_Wiki/`; source truth is never touched.
- **Parameters**: `question`, `answer` (the text to promote), `workspace_path` (optional), `source_span_ids` (optional — the answer's `source_span_ids` from its query trace).
- **Returns**: `ok`, `promoted_to` (vault-relative path of the new page inside `02_Wiki/`).
- **Source documents**: when `source_span_ids` is supplied, the promoted page gets a deterministic `## Sources` section of `[[04_Resources/…]]` links to the original source documents (every distinct source backing the answer, including multi-source syntheses). Because the `02_Wiki/` note is a visible vault file, those sources then appear in Obsidian's Graph view and Backlinks pane — the hidden DAG can't. Pass the trace's `source_span_ids` to enable this.
- **Implementation status**: v0.3.1. Calls `classify_wiki_topic` + `save_wiki_page` internally. (To promote a reviewed insight candidate instead, use `curator_promote_insight`.)

#### `check_ingest_status`

- **Role**: Return the current background ingest job queue status. The plugin
  polls this after explicit Add Source registration queues L2/L3 work. Stop
  polling when `idle: true` and refresh the UI.
- **Parameters**: `workspace_path` (absolute path, optional).
- **Returns**:
  - `ok` (always true)
  - `running` — list of currently running jobs (each includes `source_name`, `phase`, `progress`, `progress_current`, `progress_total`)
  - `queued` — list of queued jobs
  - `done_today` — number of jobs completed today
  - `idle` — `true` when both `running` and `queued` are empty
- **Implementation status**: Implemented in v0.2.1. The backend-local dashboard cache is updated by `IngestWorker` on every job state change.

#### `get_available_models`

- **Role**: Return the list of models per provider from the `models.json` file bundled with the backend package. This is for external MCP clients. The Obsidian plugin bundles the same backend `models.json` at build time and does not require this MCP tool for its model dropdown.
- **Parameters**: none.
- **Returns**: `{ "antigravity": [...], "claude": [...] }` — per-provider model list.

> Note: Obsidian plugin local Zotero and dashboard flows do not require MCP.
> They use backend-owned shared runtime snapshots and backend JSON commands.

#### `curator_get_version`

- **Role**: Return the installed version of the Incurator backend as a string (e.g., `"0.2.2"`). Used by external clients to detect backend capability.
- **Parameters**: none.
- **Returns**: Backend version string.

### 3.5 Workspace Management

#### `curator_workspace_init`

- **Role**: Initialize a new workspace with `curate.yml`, agent rules, and an auto-generated Artist persona. Use this when `curator_check_workspace` reports a missing `curate.yml`, or when the user asks to connect a workspace to their Curator.
- **Parameters**: `workspace_path` (absolute path), `project` (slug), `description`, `domains` (list), `topics` (list), `min_confidence`.
- **Agent detection**: The connecting client runtime (Claude, Antigravity, Codex, etc.) is auto-detected and only the matching rule file is installed. Codex and Antigravity share `AGENTS.md`; the managed Curator block in that file is rendered for the detected runtime. The vault root comes from the `VAULT_ROOT` env var the server is started with (authoritative); `curate.yml.vault_root` — written relative to the workspace dir so it stays portable across synced devices — is only the fallback for standalone tool calls.
- **Scenario handling**:
  - *Empty directory* — everything is created from scratch.
  - *Agent-only* — existing rule file is modified by LLM to integrate Curator hooks; returns `integration_prompt` if LLM is unavailable.
  - *Full/restore* — owned files are refreshed to latest templates; managed block is replaced in-place.
- **Returns**: `ok`, `workspace`, `agent`, `scenario`, `created`, `updated`, `persona`, `rule_integration` (if LLM auto-modified), `integration_prompt` (if LLM unavailable), `recommended_next_steps`.

#### `curator_check_workspace`

- **Role**: Verify that a workspace is healthy and load its `curate.yml` rules. **Call this at every session start before responding to any domain query.**
- **Parameters**: `workspace_path` (absolute path to the workspace directory).
- **Returns**: `ok`, `workspace`, `project`, `scenario`, `issues`.
  - `scenario` will be `"agent-only"` if Curator rules are not yet installed — call `curator_workspace_init` to fix.

### 3.5 Persona Management

#### `curator_update_artist_persona`

- **Role**: Updates the Artist `persona:` block in a workspace's `curate.yml` using a natural-language request.
- **Parameters**: `workspace_path` (absolute path to the workspace), `request` (natural-language instruction string).
- **Example**: `"This workspace is for a computer vision researcher. Set the confidence threshold to 0.85 and focus the output style on research hypotheses."`

#### `curator_update_curator_persona`

- **Role**: Updates the Curator `persona:` block in `.curator/settings.yml` using a natural-language request.
- **Parameters**: `request` (natural-language instruction string).
- **Example**: `"I am a STEM researcher focused on machine learning and systems design. I prioritize rigor and only work with high-confidence (0.85+) knowledge."`

### 3.6 Curation-Native Tools (v0.3.1)

These tools expose the v0.3.1 curation-native compiler: `curate.yml` policy
compilation, the query orchestrator's explore route, prompt-run traces, and the
derived-insight lifecycle. They are backed by the same shared services as the CLI
and plugin, and they never edit read-only source truth (`03_Notes/`,
`04_Resources/`, `06_Archives/`).

#### `curator_validate_curate_spec`

- **Role**: Validate a workspace `curate.yml` (the Knowledge Requirement
  Specification) and return its compiled runtime policy summary.
- **Parameters**: `workspace_path`.
- **Returns**: `ok`, `errors`, `spec_hash`, and a `policy` object
  (`default_route`, `allowed_routes`, `prompt_profile`, `require_source_spans`,
  `backprop_enabled`).

#### `curator_plan_workspace`

- **Role**: Compile `curate.yml` into a recorded `curation_plans` row (the
  inspectable bridge between the spec and a curation run).
- **Parameters**: `workspace_path`.
- **Returns**: `plan_id` (`PLAN-…`), `workspace_id`, `route`.
- **Failure semantics**: Missing or invalid `curate.yml` returns `ok=false` and
  records no `curation_plans` row. Validation always precedes persistence.

#### `curator_fetch_context`

- **Role**: Return the **curated evidence pack** — the workspace-KRS-biased
  selection of evidence the agent's own reasoning LLM should ground on — **without
  a synthesized answer**. This is curation as a *dynamic lens over the live DAG*,
  not a frozen file; it is the primary surface for reasoning agents (e.g. the
  Obsidian agent) that do their own synthesis. For broad questions the pack leads
  with the shared **L4 Synthesis** nodes.
- **Workspace policy failures**: An empty path or a directory without
  `curate.yml` uses the `default` policy. If the file exists but is unreadable,
  malformed, has an invalid root/source-scope shape, or is semantically invalid,
  the request fails before evidence retrieval instead of silently widening to
  the unrestricted default.
- **Parameters**: `query`, `workspace_path` (optional).
- **Returns**: `route`, `trace_id` (`QTR-…`), `retrieval_execution_id` (`RTR-…`),
  `workspace_id`, `evidence` (each item has `kind` — `synthesis` |
  `community_report` | `entity` | `source_span` | `memory_path` | `search_hit`
  — plus `id`/`title`/`text`/`score`, provenance ids, and a `locator` dict with
  `source_kind`/`relpath`/`heading`/`locator_status` for span-backed items),
  `source_span_ids`, `community_report_ids`, `synthesis_node_ids`,
  `memory_path_ids`, `warnings`. Search-hit evidence preserves hydrated
  `source_span_ids`. `trace_id` identifies the single authoritative orchestrated
  query trace; `retrieval_execution_id` is the child RTR-* consumed by Plan F.
  There is intentionally **no** `answer` field.

Plan F upgrades this surface to the unified ContextService `context_fetch`
contract. The returned pack is versioned, budget bounded, snapshot-stamped, and
explicit about omissions. Expansions and exact verification use stable handles
from the pack; if the snapshot changes, the backend returns a typed conflict
instead of mixing old and new evidence. Expanded handles are consumed once per
pack snapshot. If the requested budget cannot fit a handle, the backend reports
that handle in `expansion_refused` instead of requeueing it in `next`, so agents
do not loop on the same impossible expansion.

#### `curator_explore`

- **Role**: Run the **explore** route of the query orchestrator: discover
  non-obvious connections, record HippoRAG-style memory paths, and create
  provisional insight candidates. Builds a primer from the shared L4 synthesis
  nodes + community reports, and combines the DB graph with DB-native hybrid
  search over authoritative records.
- **Unified pack path (v0.20.0)**: explore now grounds on the same
  `ContextService` pack as the other routes — it produces a `PACK-*`/`SNAP-*`
  snapshot and obeys the shared token budget, with the follow-up/insight
  generation running as a synthesis step over that normalized pack rather than a
  separate retrieval pipeline (SYSTEM_BEHAVIOR §31.8). `curator_fetch_context`
  now also returns explore-route grounding for discovery-signal questions instead
  of degrading them to `local`.
- **Parameters**: `query`, `workspace_path` (optional).
- **Returns**: `answer`, `route`, `trace_id` (`QTR-…`), `synthesis_node_ids`,
  `memory_path_ids`, `insight_candidate_ids`, `prompt_trace_ids`, `warnings`.

#### `curator_get_prompt_trace`

- **Role**: Return one recorded prompt run (`PTR-…`) for debugging prompt
  behavior — prompt id/version, model, validator status/errors, input/output
  hashes.
- **Parameters**: `trace_id`, `workspace_path` (optional).

#### `curator_list_insight_candidates`

- **Role**: List provisional insight candidates (derived insights, corrections,
  contradictions awaiting human review). Candidates are **not** human truth.
- **Parameters**: `workspace_path` (optional), `status` (default `pending`).

#### `curator_promote_insight`

- **Role**: Promote an insight candidate to a durable note under `02_Wiki/` after
  explicit approval. Writes only to `02_Wiki/`; sets the candidate to `promoted`.
- **Parameters**: `insight_id`, `workspace_path` (optional).

#### `curator_propose_correction`

- **Role**: Propose a correction to a generated node. The change is **classified
  before any patch** (correction / contradiction / derived_insight / style_only /
  promotion_request / ambiguous). Source truth is never rewritten; derived
  insights become provisional candidates and corrections target generated nodes
  only.
- **Parameters**: `node_id`, `correction`, `workspace_path` (optional),
  `previous` (optional prior artifact text).
- **Returns**: `classification`, `recommended_action`, `patch_node_ids`,
  `requires_human_review`, `insight_candidate_id`, `trace_id`, `reason`.

### 3.7 Zotero Integration

#### `curator_search_zotero_items`
- **Role**: Search Zotero items by title or author.
- **Parameters**: `query`, `workspace_path` (optional), `custom_paths` (optional), `limit`.

#### `curator_get_zotero_item_metadata`
- **Role**: Retrieve detailed metadata for a specific Zotero item.
- **Parameters**: `item_key`, `workspace_path` (optional), `custom_paths` (optional).

#### `curator_get_zotero_annotations`
- **Role**: Extract annotations and highlights from a Zotero PDF attachment.
- **Parameters**: `item_key`, `workspace_path` (optional), `custom_paths` (optional).

#### `curator_resolve_zotero_pdf`
- **Role**: Locate the physical PDF file path for a Zotero item.
- **Parameters**: `item_key`, `workspace_path` (optional), `custom_paths` (optional).

### 3.8 Configuration Management

#### `curator_get_provider_config`
- **Role**: Retrieve the current LLM provider configuration and the packaged
  model catalogue used by provider/model selectors.
- **Parameters**: `workspace_path` (optional).
- **Return**: `llm`, `models_json`, and `warnings`. `models_json` is loaded from
  the installed `curator.data` package, so it remains available after source
  modules are reorganized.

#### `curator_set_provider_config`
- **Role**: Update the LLM provider configuration dynamically.
- **Parameters**: `primary` (backend key such as `claude-code`, `codex-cli`,
  `antigravity-cli`, `deepseek-api`, or `ollama`), `model`, `host`,
  `api_key_env`, `api_key`, `base_url`, and `workspace_path` (all except
  `primary` optional).
