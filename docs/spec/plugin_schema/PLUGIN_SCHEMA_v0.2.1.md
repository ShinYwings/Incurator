# Incurator Plugin Schema & API Contract (v0.2.1)

Audience: Obsidian plugin developers, frontend contributors, and coding agents.

This document is the plugin-side schema source of truth for the v0.2.1 line.
Backend contracts live in `docs/spec/curator_schema/SCHEMA_v0.2.1.md` and
`docs/spec/system_behavior/incurator_v0.2.1.md`. When there is a conflict,
the system behavior spec takes precedence. Implementation plans under
`docs/plans/update_plan/` are subordinate to this file.

v0.2.1 extends v0.2.0. Any v0.2.0 plugin field not contradicted here remains valid.

## 1. Plugin Authority Boundary

The Obsidian plugin owns:

- `PluginSettings` — persisted to `.obsidian/plugins/incurator/data.json`
- `SessionData` — stored separately in `sessions.json`; may be synced through
  Syncthing when session merge-on-save is enabled by the implementation
- Transient PDF.js extraction for open documents (never written to `.curator/`)
- Chat UI rendering and streaming
- Human approval prompts for import, reference registration, rebind, and promotion
- Rendering of progress/status/trace returned by backend MCP tools
- Best-effort Syncthing device registry refresh on startup, writing
  `.curator/devices.json` without requiring a manual backend command

The plugin must not:

- Write directly to `.curator/state.sqlite` or `.curator/Collections/`
- Call backend MCP tools that mutate durable state without explicit user action
- Maintain its own hard-coded cloud model list; use `get_available_models` from backend

The plugin may write `.curator/devices.json` as the single exception to the
`.curator/` write boundary. That file is sync metadata, not DAG state.

## 2. Persisted Settings Schema

### 2.1 `PluginSettings`

Stored in `data.json` (Obsidian plugin storage). All fields required unless marked optional.

```typescript
interface PluginSettings {
  // LLM provider selection
  provider: LLMProvider;           // "antigravity" | "claude" | "openai"
  model: string;                   // model ID, validated against backend catalogue
  chatMode: ChatMode;              // "chat" | "plan"
  codexReasoningEffort: CodexReasoningEffort;  // "low"|"medium"|"high"|"xhigh"
  claudeEffort: ClaudeEffort;      // "low"|"medium"|"high"|"xhigh"|"max"
  antigravityPrintTimeoutSec: number;

  // Usage tracking (device-local)
  providerUsage: Record<LLMProvider, ProviderUsage>;

  // UI preferences
  diffMode: "inline" | "side-by-side";
  streamingEnabled: boolean;
  maxContextLength: number;        // tokens

  // MCP configuration
  mcpServers: MCPServerConfig[];

  // PDF viewer settings
  pdfCaptureMode: "text" | "image" | "both";
  pdfWindowRadius: number;         // pages ± current page
  pdfOutlineEnabled: boolean;
  pdfRagEnabled: boolean;
  pdfRagTopK: number;
  pdfVisionFallback: boolean;
  pdfFullDocumentIndex: boolean;

  // Incurator integration
  incuratorEnabled: boolean;
  incuratorMcpCommand: string;          // per-device backend command, default "wiki"
  incuratorMcpArgs: string[];           // default ["mcp"]
  incuratorRepoPath: string;            // per-device absolute path to backend repo for 1-click updates
  incuratorDefaultDestination: string;   // vault-relative folder, e.g. "04_Resources"
  incuratorDefaultImportMode: "copy" | "reference";
  incuratorStatusPolling: boolean;

  // Zotero integration
  zoteroBasePath: string;          // default "~/Zotero"
  zoteroProfiles: ZoteroImportProfile[];

  // Scroll position persistence (optional)
  lastMarkdownScrollPosition?: LastMarkdownScrollPosition;
  fileScrollPositions?: Record<string, FileScrollPosition>;
}
```

Rules:

- `provider` and `model` must be consistent. If the backend catalogue changes a model ID,
  the plugin should fall back to the provider default rather than breaking settings.
- `providerUsage` is device-local and must not sync across Obsidian Sync.
- The chat sidebar footer may expose provider/model as one compact selector.
  Selecting a model from another provider must update both `provider` and `model`.
- `incuratorDefaultDestination` defaults to `"04_Resources"` for new installs.
- `incuratorDefaultImportMode` defaults to `"reference"` (no file copy).
- `incuratorMcpCommand`, `incuratorMcpArgs`, and `incuratorRepoPath` are per-device settings. They may
  point to `wiki mcp` when the backend is installed on PATH, or to a platform
  specific launcher such as `uv --directory /path/to/Incurator/backend run wiki mcp`.
- **1-Click Auto-Update:** The plugin calls `curator_get_version` via MCP. If the backend version
  does not match the plugin's `manifest.json` version, the plugin displays an update banner.
  If `incuratorRepoPath` is set, clicking the banner executes `cd <incuratorRepoPath> && git pull && ./setup.sh`.
- `mcpServers` entries are stored but managed via the backend MCP server registration
  flow; the plugin must not hard-code Incurator server config.
- On desktop startup, the plugin may read local Syncthing config files and
  refresh `.curator/devices.json` with the current device's launcher settings.
  This removes the need to run `wiki devices sync` for normal Obsidian use.

### 2.2 `SessionData`

Stored in a separate `sessions.json` file. It must never be merged into
`data.json`.

The implementation must tolerate `sessions.json` being synchronized between
devices. Before writing, it should read the current on-disk file and merge
sessions by `ChatSession.id`, keeping the session copy with the newest
`updatedAt` timestamp. This prevents a Linux save from deleting a distinct macOS
session, or vice versa, after Syncthing has delivered remote changes.

```typescript
interface SessionData {
  chatSessions: ChatSession[];
  activeChatSessionId?: string;
  deletedSessionIds?: string[];  // tombstones so synced deletes do not reappear
}

interface ChatSession {
  id: string;           // UUID
  title: string;
  createdAt: number;    // unix ms
  updatedAt: number;    // unix ms
  messages: ChatMessage[];
}

interface ChatMessage {
  id: string;           // UUID
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;    // unix ms
  contextRefs?: ContextRef[];
  isStreaming?: boolean;
}
```

Rules:

- `chatSessions` is local plugin history. It is not sent to the backend.
- When synchronized, separate sessions from different devices must be preserved.
  Concurrent edits to the same session are last-writer-wins by `updatedAt`.
- `activeChatSessionId` is the session currently visible in the sidebar.
- Sessions containing pinned `ContextRef` items with `backendStatus` must not
  assume that status is still current on next load; re-poll via `check_source_status`.

### 2.3 `MCPServerConfig`

```typescript
interface MCPServerConfig {
  name: string;
  command: string;
  args: string[];
  env?: Record<string, string>;
  enabled: boolean;
}
```

## 3. Model Catalogue

### 3.1 Source of Truth

The plugin must not maintain a divergent hard-coded cloud model list.
The canonical catalogue is `backend/src/curator/data/models.json`, served via
the `get_available_models` MCP tool at runtime.

The plugin must not ship a parallel static cloud model list. Before the backend
responds, the model control may show only the persisted current/custom model.
Once `get_available_models` returns, the live backend catalogue becomes the UI
source of truth.

### 3.2 `ModelOption` (Plugin Representation)

```typescript
interface ModelOption {
  id: string;
  label: string;
  tier: "stable" | "preview" | "legacy";  // plugin display tiers
  supportsVision: boolean;
}
```

Backend catalogue tiers (`"flash"`, `"think"`) map to plugin tiers as follows:

| Backend tier | Plugin tier |
|---|---|
| `flash` | `stable` |
| `think` | `stable` |
| `preview` | `preview` |
| `legacy` | `legacy` |

## 4. Source Status Schema

### 4.1 `IncuratorSourceState`

```typescript
type IncuratorSourceState =
  | "unknown"           // status not yet fetched
  | "untracked"         // not registered in backend
  | "l1_ready"          // registered and L1 is usable, but L2/L3 are not ready
  | "queued"            // registered, L2/L3 job pending
  | "running"           // L2/L3 job in progress
  | "indexed"           // L1 complete (instant RAG available)
  | "curated"           // L3 complete (concept-grounded answers available)
  | "stale"             // content hash changed since registration
  | "missing"           // registered but file not found at stored path
  | "moved"             // file path changed, hash matches a known source
  | "hash_drift"        // path unchanged but content hash changed
  | "moved_and_hash_drift"  // both path and hash changed
  | "error";            // last ingest attempt failed
```

Rules:

- `"indexed"` corresponds to `l1_status='done'` in backend `sources` table.
- `"curated"` corresponds to `l3_status='done'`.
- `"running"` must expose `runningLayer` ("l1"|"l2"|"l3"|"l4") to show progress.
- `"untracked"` must trigger the "Add to Incurator" action prompt, not silent import.

### 4.2 `IncuratorSourceStatus`

```typescript
interface IncuratorSourceStatus {
  state: IncuratorSourceState;
  sourceId?: number;
  sourcePath?: string;
  destinationRelpath?: string;
  contextId?: string;       // CTX-<UUID8> when L1 complete
  pageCount?: number;
  currentPath?: string;     // for "moved" state
  candidatePath?: string;   // for "moved" state
  requiresRebind?: boolean;
  message?: string;
  updatedAt?: number;       // unix ms of last status poll
  runningLayer?: string;    // "l1"|"l2"|"l3"|"l4" when running
}
```

## 5. Curator Query Schema

### 5.1 `curator_query` MCP Tool Contract

The plugin calls `curator_query` via MCP for sidebar-style concept-grounded answers.

MCP tool input:
```json
{
  "question": "What are the main contributions of this paper?",
  "workspace_path": "/absolute/path/to/workspace",
  "force_new": false
}
```

MCP tool output:
```typescript
interface CuratorQueryResult {
  ok: boolean;
  answer?: string;
  exhibition_id?: string;        // EXH-<UUID8> of the generated/reused Exhibition
  cache_hit?: boolean;           // true if a cached Exhibition was returned
  question: string;
  trace?: CuratorQueryTrace;
  error?: string;
}

interface CuratorQueryTrace {
  matched_concepts: string[];    // CON-<UUID8> IDs
  source_ids: number[];
  source_paths: string[];
  section_ids?: string[];        // toc sN IDs when section provenance exists
  latency_ms: number;
  l3_complete: boolean;          // whether full concept graph was available
}
```

Rules:

- The plugin must not call `curator_query` for unregistered sources. Use
  plugin-served ephemeral sections via `fetch_document_section` for unregistered PDFs.
- If `fallback="l3_incomplete"` and `trace.l3_complete=false`, do not present
  the response as concept-grounded. Show that the document is still being
  processed and fall back to `fetch_document_section` or local PDF context.
- `exhibition_id` may be used to call `promote_exhibition` after user approval.
- The plugin must display `trace` in a "Sources & Trace" panel when available.

### 5.2 `promote_exhibition` MCP Tool Contract

MCP tool input:
```json
{
  "exh_id": "EXH-12345678",
  "workspace_path": ""
}
```

MCP tool output:
```typescript
interface PromoteExhibitionResult {
  ok: boolean;
  exhibition_id?: string;
  promoted_to?: string;      // vault-relative path in 02_Wiki/
  error?: string;
}
```

Rules:

- The plugin must request explicit user confirmation before calling `promote_exhibition`.
- After promotion, the plugin should refresh the status of any pinned context
  referencing the source.
- Promotion must not be called automatically; it always requires a human action.

## 6. PDF Context Schema

### 6.1 `ContextRef` (Chat Context Attachment)

```typescript
interface ContextRef {
  type: "file" | "selection" | "line-range" | "pdf-page" | "text" | "image";
  label: string;
  content: string;
  isPinned?: boolean;
  sourceViewType?: string;
  imageBase64?: string;
  backendStatus?: IncuratorSourceStatus;
  windowPages?: PdfWindowPage[];
  outline?: PdfOutlineItem[];
  ragHits?: PdfRagHit[];
  textQuality?: PdfTextQuality;
  isScannedLike?: boolean;
  filePath?: string;
  lineStart?: number;
  lineEnd?: number;
  pageNum?: number;
}
```

### 6.2 PDF Quality Fields

```typescript
interface PdfTextQuality {
  score: number;            // 0.0–1.0
  charCount: number;
  wordCount: number;
  lineCount: number;
  brokenCharRatio: number;
  whitespaceRatio: number;
  isScannedLike: boolean;   // true if OCR or low text density
  source: PdfTextSource;    // "pdfjs" | "obsidian-text-layer" | "dom" | "none"
  reason?: string;
}
```

Rules:

- `isScannedLike=true` must trigger vision fallback if `pdfVisionFallback=true`.
- PDF context must never be written to `.curator/` without explicit user approval.

## 7. IncuratorClient API Contract

`IncuratorClient` wraps MCP tool calls through `MCPManager`. It must implement
these methods for v0.2.1:

| Method | MCP tools tried (priority order) |
|---|---|
| `getSourceStatus(path)` | `curator_source_status` |
| `checkSourceStatus(hash)` | `check_source_status` |
| `ingestPdf(request)` | `curator_import_source` → `curator_ingest_source` |
| `rebindSource(args)` | `curator_rebind_source` |
| `search(query)` | `search_curator` |
| `getPdfWindow(args)` | `curator_get_source_page`, `curator_get_pdf_page` |
| `getDocumentOutline(args)` | (derived from `check_source_status` CTX) |
| `getPdfRagHits(args)` | `curator_search_source`, `curator_search_sources` |
| `curatorQuery(question, opts)` | `curator_query` |
| `promoteExhibition(exhId)` | `promote_exhibition` |

Rules:

- All methods must return `null`/empty gracefully when `incuratorEnabled=false`
  or when the Incurator MCP server is not connected.
- `tryTool` must try names in priority order and skip tools that return `isError=true`.
- Backend MCP tool names take precedence; legacy fallback names are listed for
  backwards compatibility with older backend versions.

## 8. Compatibility Rules

- v0.2.1 plugin must accept `check_source_status` responses that lack `l2_complete`/`l3_complete`
  (older backend). Treat missing fields as `false`.
- The plugin must not maintain `MODEL_OPTIONS` as a cloud-model fallback. Use
  `get_available_models`; show current/custom model only while unavailable.
- Plugin settings written in v0.2.0 format (missing `incuratorStatusPolling` etc.) must
  be migrated on load by applying `DEFAULT_SETTINGS` as defaults.
- `SessionData` separated from `PluginSettings` is a v0.2.1 change. Old `data.json`
  files with embedded `chatSessions` must be migrated to `sessions.json` on first load.
