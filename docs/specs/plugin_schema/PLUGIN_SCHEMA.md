# Incurator Plugin Schema & API Contract (v0.9.0)

Audience: Obsidian plugin developers, frontend contributors, and coding agents.

> **v0.9.0 note (Plan C — Graph Quality):** the v0.9.0 release changes no plugin
> contract. The graph audit is a CLI surface (`wiki lint` Graph Quality section),
> and the plugin observes Plan C only through better backend evidence (canonical
> entities, active claim-grounded relations, and claim-grounded community reports
> on already-returned records). See SYSTEM_BEHAVIOR §27.6. The title version is
> bumped together with the other spec domains; the binding product version bump
> lands at the Plan C release step.
>
> **v0.8.0 note (Plan B — Evidence Compiler Integrity):** the v0.8.0 release
> changes no plugin contract. The compiler audit is a CLI surface
> (`wiki lint`), and the plugin observes Plan B only through better backend
> evidence (full-span hydration and claim support/formula labels on returned
> records). See SYSTEM_BEHAVIOR §26.5. The title version is bumped at the
> release step together with the other spec domains.

This document represents the most concrete layer (`spec`) of the documentation hierarchy (`philosophy` -> `guides` -> `spec`). It is the absolute schema source of truth for the plugin. Backend contracts live in `docs/specs/curator_schema/SCHEMA.md` and `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`. When there is a conflict, the system behavior spec takes precedence.

Implementation plans under `.agents/plans/` are transient and strictly subordinate to this spec.

Sections 1-11 below define the plugin contract, supporting DB-native search evidence, and dashboard click-to-use trace/insight commands. Historical plugin schema definitions are tracked via git history.

The current fields and command contracts below are the only supported plugin
contract.

## 1. Plugin Authority Boundary

The Obsidian plugin owns:

- `PluginSettings` — persisted to `.obsidian/plugins/incurator/data.json`
- `SessionData` — stored separately in `sessions.json`; may be synced through
  Syncthing when session merge-on-save is enabled by the implementation
- Transient PDF.js extraction for open documents (never written to `.curator/`)
- Chat UI rendering and streaming
- Human approval prompts for import, reference registration, rebind, and promotion
- Rendering of progress/status/trace returned by backend calls or backend-owned
  shared status snapshots
- Best-effort Syncthing device registry refresh on startup, writing
  `.cache/config/devices.json` without requiring a manual backend command

The plugin must not:

- Write directly to `.curator/state.sqlite` or `.curator/Collections/`
- Call backend MCP tools that mutate durable state without explicit user action
- Maintain its own hard-coded cloud model list; bundle the backend
  `backend/src/curator/data/models.json` catalogue at plugin build time

The plugin may write `.cache/config/devices.json` as the single exception to the
`.curator/` write boundary. That file is sync metadata, not DAG state. The
plugin may also read `.curator/runtime/*.json` dashboard snapshots, but backend
code is the only writer for those files. Dashboard backend health, source/job
counts, index readiness, and backend version display must come from those
snapshots or from explicit backend commands, not from Incurator MCP tool
polling.

Dashboard controls that change backend state must execute backend commands or
backend-owned APIs. The plugin must not implement those controls by directly
editing `.curator/config.yml`, `.curator/state.sqlite`, generated Collections,
or runtime snapshots.

Zotero plugin flows must use backend commands for Zotero database access. The
plugin must not route local Zotero search, metadata, annotation, or PDF path
resolution through Incurator MCP tools. The backend command layer owns Zotero
SQLite access, setup diagnostics, and filesystem resolution; the plugin receives
JSON results.
The command namespace for this local plugin API is hidden from the normal human
CLI surface:

```text
wiki plugin zotero search
wiki plugin zotero metadata
wiki plugin zotero annotations
wiki plugin zotero resolve-pdf
wiki plugin zotero status
wiki plugin zotero init
wiki plugin source status
wiki plugin source import
wiki plugin source register
wiki plugin source rebind
wiki plugin pdf context
wiki plugin pdf search
wiki plugin version
wiki plugin query
wiki plugin promote
wiki plugin db export
wiki plugin db import
```

PDF context requests should pass the richest available identity to backend:
local file path, source id, vault relpath, file hash, or Zotero attachment key.
The backend resolves Reference Mode stubs and Zotero attachments before reading
page text.
Source import requests may also pass a Zotero attachment key. In that case the
backend resolves the key to a local PDF path, imports/registers the source using
Reference Mode, and records a stable logical source id such as
`zotero:<attachmentKey>` instead of requiring the plugin to resolve the path
first.

### 1.1 PDF asset routing — `source register --asset-dir` (v0.5.6)

`wiki plugin source register` accepts an optional `--asset-dir <vault-relative
folder>`. Embedded PDF images extracted during instant L1 generation are written
under that folder instead of the default `05_Assets/<slug>/`. Contract:

- The value is a **vault-relative** folder (e.g. `05_Assets/Zotero Assets/kim2024`).
  The backend rejects unsafe values — absolute paths, `..` traversal, or paths
  that escape the vault root — by falling back to the default `05_Assets/<slug>/`
  location. Routing must never fail an ingest.
- The generated L1 page's `embedded_images` frontmatter and `![[...]]` figure
  embeds always reference the folder the images were **actually** written to,
  so embeds resolve in both the routed and the fallback case.
- Omitted or empty `--asset-dir` uses the default behavior:
  `05_Assets/<slug>/` where `<slug>` is derived from the source filename.
- The asset dir is **not persisted** in the backend DB. Each `register` call
  resolves its own routing; re-registering without `--asset-dir` writes to the
  default location. `source import` does not write images and takes no asset
  argument — image extraction happens only at instant-L1 time inside `register`.
- The plugin resolves the folder it passes: for Zotero-backed PDFs it reuses the
  matching Zotero import profile's asset spec (`resolveProfileAssetSpec` —
  asset folder + rendered per-item subfolder); for non-Zotero PDFs it appends a
  sanitized PDF filename stem to the `incuratorPdfAssetFolder` base folder when
  set, otherwise omits the flag. The per-source subfolder prevents generic
  extracted image filenames from colliding across differently named PDFs.

## 2. Persisted Settings Schema

### 2.1 `PluginSettings`

Stored in `data.json` (Obsidian plugin storage). All fields required unless marked optional.

```typescript
interface PluginSettings {
  // LLM provider selection
  provider: LLMProvider;           // "antigravity" | "claude" | "openai" | "ollama" | "deepseek"
  model: string;                   // model ID, validated against backend catalogue
  chatMode: ChatMode;              // "chat" | "plan"
  codexReasoningEffort: CodexReasoningEffort;  // "low"|"medium"|"high"|"xhigh"
  claudeEffort: ClaudeEffort;      // "low"|"medium"|"high"|"xhigh"|"max"
  antigravityPrintTimeoutSec: number;
  deepseekApiKey: string;          // device-local optional key; empty = use DEEPSEEK_API_KEY

  // Usage tracking (device-local)
  providerUsage: Record<LLMProvider, ProviderUsage>;

  // UI preferences
  diffMode: "inline" | "side-by-side";
  streamingEnabled: boolean;
  quickQueryEnabled: boolean;      // drag-to-select In-line Copilot popover (default true)
  maxContextLength: number;        // tokens

  // MCP configuration for external/non-Incurator tool servers
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
  incuratorBackendCommand: string;          // per-device backend command, default "wiki"
  incuratorBackendArgs: string[];           // default []
  incuratorRepoPath: string;            // per-device absolute path to backend repo for 1-click updates
  incuratorDefaultDestination: string;   // vault-relative folder for reference stubs/copy imports
  incuratorDefaultImportMode: "copy" | "reference"; // reference creates a link stub
  incuratorPdfAssetFolder: string;       // vault-relative base folder for extracted PDF images of non-Zotero sources; each PDF gets a filename subfolder; "" = backend default 05_Assets/<slug>/
  incuratorStatusPolling: boolean;

  // Zotero integration
  zoteroBasePath: string;          // default "~/Zotero"
  zoteroProfiles: ZoteroImportProfile[];
  recentZoteroItems: string[];     // LRU item keys, newest first, max 50

  // Scroll position persistence (optional)
  lastMarkdownScrollPosition?: LastMarkdownScrollPosition;
  fileScrollPositions?: Record<string, FileScrollPosition>;
}
```

Rules:

- `provider` and `model` must be consistent. If the backend catalogue changes a model ID,
  the plugin should fall back to the provider default rather than breaking settings.
- `deepseekApiKey` is device-local secret material. It must not be written into
  shared vault config; backend config may instead reference `DEEPSEEK_API_KEY`
  through `llm.deepseek-api.api_key_env` or a local encrypted backend secret
  through `llm.deepseek-api.api_key_secret`.
- `providerUsage` is device-local and must not sync across Obsidian Sync.
- The chat sidebar footer may expose provider/model as one compact selector.
  Selecting a model from another provider must update both `provider` and `model`.
- AI Provider settings must show model context-window information on the
  **Model** row, not as a separate setting row.
- `incuratorDefaultDestination` defaults to `"04_Resources"` for new installs.
- `incuratorDefaultImportMode` defaults to `"reference"` (no file copy).
- `incuratorPdfAssetFolder` defaults to `""` (v0.5.6). When empty the plugin
  omits `--asset-dir` and the backend uses its default `05_Assets/<slug>/`.
  When set it is the base folder for non-Zotero add-source PDFs; the plugin
  appends a sanitized PDF filename stem. Zotero-backed PDFs derive their asset
  dir from the matching Zotero import profile (Section 1.1).
- Incurator backend enablement must render its configured/disabled state as a
  compact status row directly below the Enable setting, not squeezed into the
  Enable row.
- The Dashboard must not expose a standalone Devices tab. Syncthing device
  information belongs in Overview as a compact mapping from device name to the
  shared Vault and Zotero folders. The current device must be marked in that
  list, including local fallback entries that Syncthing does not list as remote
  devices. The Overview System table must not duplicate device identity.
- Purple context pins may be removed down to zero for the current turn. Automatic
  visible context may be re-created on the next turn. Pinned purple chips must
  expose eye/eye-off prompt inclusion controls and excluded refs must not be sent
  to the provider.
- Zotero data-directory configuration must have a single visible entry point:
  **Backend Zotero status > Open setup**. The setup dialog defaults to
  `~/Zotero`, displays home-directory paths with `~` instead of an absolute
  `/Users/...` prefix, and writes the backend-owned Zotero configuration.
- `incuratorBackendCommand`, `incuratorBackendArgs`, and `incuratorRepoPath` are
  per-device settings. They may point to `wiki` when the backend is installed on
  PATH, or to a platform specific launcher such as command `uv` with args
  `--directory /path/to/Incurator/backend run wiki`. When
  `.cache/config/devices.json` has a non-empty `backend.repo_path` for the local
  device, that value overrides any synced `incuratorRepoPath` from plugin
  `data.json` at runtime. Saving settings refreshes the local device entry so a
  path edit is recorded immediately.
- **Setup/build fingerprint check:** `./setup.sh` writes a shared backend/plugin
  build manifest. The plugin compares its bundled build fingerprint with
  `wiki plugin version`'s backend build fingerprint and displays a setup/rebuild
  banner only when those fingerprints are missing or mismatched. Semantic
  backend/plugin version labels alone are not enough to show an update banner
  when the fingerprints prove both sides came from the same local setup run. If
  `incuratorRepoPath` is set, clicking the banner executes
  `cd <incuratorRepoPath> && ./setup.sh`; it must not force `git pull`.
- `mcpServers` entries are for external/non-Incurator MCP servers. Incurator's
  own plugin integration must not require MCP tool discovery for static
  metadata such as model choices.
- On desktop startup and settings save, the plugin may read local Syncthing
  config files and refresh `.cache/config/devices.json` with the current device's
  launcher settings. This removes the need to run `wiki devices sync` for normal
  Obsidian use.
  The current device should be identified from Syncthing REST `myID` when
  available, then from per-device `incuratorRepoPath`/backend launcher metadata,
  before falling back to hostname matching.
  During refresh it preserves entries for devices still present in the active
  shared-folder snapshot and prunes stale device ids that no longer appear.
  Dashboard device lists must render every processed registry device, including
  Syncthing-only remote devices with no local backend launcher. Device names
  come from Syncthing/registry metadata. Platform text is shown only when a
  real `platform.system` or equivalent synced fact exists; otherwise the UI
  should label the platform as unknown.
- `recentZoteroItems` stores Zotero item keys only. The plugin updates it after
  successful Zotero imports and may use it to rank search suggestions, but it
  must not duplicate Zotero metadata in settings.
- Zotero-managed PDFs registered from the sidechat/purple-pin flow use
  Reference Mode. A failed backend import/register payload must surface as an
  error state and show a user-visible failure notice instead of silently
  returning to the previous chip state. Successful registration should return a
  queued or ready source state, and the generated `04_Resources` reference stub
  should identify the attachment with portable Zotero metadata rather than a
  device-local PDF path.
- Zotero path settings may contain a data directory or a direct
  `zotero.sqlite` file path. Backend PDF resolution must normalize direct
  sqlite paths to their parent data directory before checking Zotero `storage/`
  or linked-attachment roots.
- Zotero PDF resolution failures must be structured. `wiki plugin zotero
  resolve-pdf` returns `state=db_missing` when no readable Zotero database is
  found, `state=attachment_key_missing` when the DB has no requested attachment
  key, and `state=attachment_file_missing` when the DB has an attachment path
  but no readable PDF exists in any configured data or linked-attachment root.
  The response should include checked roots/paths where available so the plugin
  can show repair-oriented UI without guessing filesystem locations itself.
- Plugin Zotero repair UI should be centralized. Settings, Dashboard, Zotero
  link failures, and sidechat Add-to-Incurator failures should open the same
  Zotero setup/repair dialog instead of each inventing separate status,
  save-root, or repair handling.
- When backend Zotero responses include checked roots or checked attachment
  paths, the shared repair dialog should present them as candidate roots that
  can populate the data-directory or linked-attachment-root field. The plugin
  should not require the user to manually copy long filesystem paths from an
  error message.
- Chat system prompts must instruct the model to use English as the internal
  working language for every question: translate the latest user request to
  English for reasoning, search terms, MCP/tool arguments, and synthesis, then
  postprocess the final answer back into the original input language unless the
  user explicitly requests another output language.
- When MCP tool output for `curator_query` is rendered into the chat transcript,
  the plugin may compact the visible tool-result block, but it must preserve
  parseable `fallback`, `error`, and `trace` fields so the Sources & Trace panel
  can link the answer to its source evidence and query trace.

### 2.1.1 Zotero Import Profiles

Saved Zotero import profiles define the note template, output folder,
subfolder, filename, asset folder, and bibliography style used by the import
wizard. When one or more profiles exist, the wizard opens with the first saved
profile loaded so edits made in settings are reflected without manually
re-selecting the profile.

The Zotero item search modal must request empty-query suggestions when it opens.
Empty-query suggestions come from the backend's recent Zotero results; returned
results may then be re-ranked by `recentZoteroItems` so recently imported items
float to the top.

Output subfolders, filenames, and asset subfolders are rendered through the
plugin's Nunjucks `TemplateRenderer`. The renderer supports the same base item
metadata used by note templates plus path-oriented filters such as `pathSafe`,
`firstAuthorLast`, `authorLast`, and `joinTags`. Rendered path segments must be
sanitized before writing files into the vault.

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
  diffAutoOpened?: boolean;  // true once this message's edit diff was auto-opened
}
```

Rules:

- `chatSessions` is local plugin history. It is not sent to the backend.
- `diffAutoOpened` is set once, when a completed assistant answer that proposes
  `ai-agent-edit` blocks has its diff auto-opened. It makes the immediate diff
  open at-most-once per message and prevents re-opening on history re-render.
- When synchronized, separate sessions from different devices must be preserved.
  Concurrent edits to the same session are last-writer-wins by `updatedAt`.
- `activeChatSessionId` is the session currently visible in the sidebar.
- Sidebar chat titles are display summaries derived from the first assistant
  answer after the first user question. Until that answer exists, the first user
  question is the temporary title. Session rows display relative last activity
  from `updatedAt`.
- Sessions containing pinned `ContextRef` items with `backendStatus` must not
  assume that status is still current on next load; re-poll via
  `wiki plugin source status`.

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
The canonical catalogue is `backend/src/curator/data/models.json`.

The plugin must not ship a parallel handwritten cloud model list. At build time,
it imports and bundles the backend `models.json` file directly. At runtime,
settings, chat sidebar controls, and the Incurator Dashboard LLM Provider card
read the bundled catalogue synchronously; they must not wait for MCP startup or
tool discovery to populate model names.

The backend may still expose `get_available_models` for external MCP agents, but
the Obsidian plugin's model dropdown must not depend on that MCP tool.

### 3.2 `ModelOption` (Plugin Representation)

```typescript
interface ModelOption {
  id: string;
  label: string;
  supportsVision: boolean;
  supportsThinking: boolean;
  defaultEffort: string;
}
```

The plugin UI must use `supportsThinking` and the backend's `efforts` array to render appropriate configuration controls (e.g., hiding reasoning sliders for standard models). There are no fictional "tiers" transmitted from the backend.

DeepSeek appears in the catalogue under plugin provider key `deepseek` and maps
to backend key `deepseek-api`. The plugin must call the API directly with a
Bearer key from `deepseekApiKey` or `DEEPSEEK_API_KEY`; it must not attempt a
CLI/OAuth login flow for DeepSeek.

## 4. Source Status Schema

### 4.1 `IncuratorSourceState`

```typescript
type IncuratorSourceState =
  | "unknown"           // status not yet fetched
  | "untracked"         // not registered in backend
  | "l1_ready"          // registered and L1 is usable, but L2/L3 are not ready
  | "l2_ready"          // L2 Atoms exist, but L3 Concepts are not ready
  | "queued"            // registered, L2/L3 job pending
  | "running"           // L2/L3 job in progress
  | "l3_ready"          // L3 complete (concept-grounded answers available)
  | "l4_ready"          // L4 Synthesis complete
  | "stale"             // content hash changed since registration
  | "missing"           // registered but file not found at stored path
  | "moved"             // file path changed, hash matches a known source
  | "hash_drift"        // path unchanged but content hash changed
  | "moved_and_hash_drift"  // both path and hash changed
  | "error";            // last ingest attempt failed
```

Rules:

- `"l1_ready"` corresponds to `l1_status='done'` while L2/L3 are incomplete.
- `"l2_ready"` corresponds to `l2_status='done'` while L3 is incomplete.
- `"l3_ready"` corresponds to `l3_status='done'` while L4 is incomplete.
- `"l4_ready"` corresponds to `l4_status='done'`.
- `"error"` wins over all ready states when any active layer reports `error`.
- `"running"` must expose `runningLayer` ("l1"|"l2"|"l3"|"l4") to show progress.
- `"untracked"` must trigger the "Add to Incurator" action prompt, not silent import.

### 4.1.1 "Added" badge for built sources (v0.5.6)

- The four ready states — `l1_ready`, `l2_ready`, `l3_ready`, `l4_ready` —
  render as a single non-clickable **"Added"** badge in the chat context chip.
  Clicking it is a no-op (it must NOT fall through to the re-ingest modal or
  Zotero auto-register). The badge tooltip still exposes the underlying layer
  state (e.g. `Incurator: l2_ready`).
- This is a label + click-guard only. There is no `added` backend state and no
  new DB status; the status poll keeps returning the layer states above.
- A subsequent refresh that re-derives `stale`, `missing`, `moved`,
  `hash_drift`, `moved_and_hash_drift`, or `error` makes the badge actionable
  (clickable) again with its existing label and behavior.
- `queued` and `running` keep their existing labels and informational click
  behavior (job notice), unchanged.

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
  l1Complete?: boolean;
  l2Complete?: boolean;
  l3Complete?: boolean;
  l4Complete?: boolean;
}
```

## 5. Curator Query Schema

### 5.1 `wiki plugin query` Contract

The plugin calls `wiki plugin query` for sidebar-style concept-grounded answers.
The backend may expose the same behavior through MCP for external agents, but
the local Obsidian plugin path must not require Incurator MCP startup.

Command input:
```json
{
  "question": "What are the main contributions of this paper?",
  "input_language": "English",
  "english_query": "What are the main contributions of this paper?",
  "final_output_language": "English",
  "workspace_path": "/absolute/path/to/workspace",
  "force_new": false
}
```

JSON output:
```typescript
interface CuratorQueryResult {
  ok: boolean;
  answer?: string;
  question: string;
  input_language?: string;       // detected original language, e.g. English/Korean
  english_query?: string;        // query actually used for internal search/reasoning
  final_output_language?: string;// language required for final user-facing answer
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

- For ordinary workspace/domain questions without a primary selected context on
  the latest user turn, the Obsidian sidechat must call `wiki plugin query`
  directly and inject the formatted answer/trace into provider context.
- The Obsidian sidechat must send structured language metadata with plugin
  queries: `input_language`, `english_query` when already known, and
  `final_output_language`. For non-English input, the backend may compute
  `english_query`, but the JSON response must expose the resolved
  `english_query` so the English internal query is auditable.
- The plugin detects `input_language` with a deterministic Unicode-script
  classifier (Hangul → Korean; Han without Kana → Chinese; Hiragana/Katakana →
  Japanese; Cyrillic → Russian; Arabic/Devanagari/Thai/Greek/Hebrew/…; default
  Latin → English), run fresh per request. A single canonical detector is shared
  by the curator-query path and the plain-chat path. `final_output_language`
  always equals the freshly detected `input_language` unless the latest request
  explicitly asks for another output language.
- The three language fields are response/trace-only. They appear in this JSON but
  are never written into generated node frontmatter.
- Backend query search, intent classification, and synthesis context must use
  `english_query` as the internal working query. The final answer must target
  `final_output_language`, not a language inferred from earlier chat turns.
- The plugin must skip `wiki plugin query` when the latest turn is focused on
  user-selected text, an editable line range, a PDF page reference, or a
  selected crop/image. Those turns are answered from the selected context rather
  than from a workspace-wide dynamic curation query.
- PDF-focused turns use adaptive routing. Visible local PDF.js context is always
  preferred and does not require source registration. When local context is
  unavailable, the plugin may request read-only backend PDF context: unregistered
  PDFs receive an ephemeral parse, registered L1-complete PDFs receive durable CTX
  sections, and `curator_query` is allowed only after L3 completes. Passive chat
  must never import or register a PDF.
- The backend does not save query answers as generated Exhibitions. Each query is
  a sessionless curation answer with a `QTR-` trace over selected DB-native search
  and graph evidence.
- When the latest chat turn is not inside a workspace folder, the plugin sends an
  empty `workspace_path` so the backend resolves `workspace_id=default`. The
  plugin must not bind an arbitrary workspace (e.g. the first `curate.yml` in the
  vault) to a conversational chat.
- If `fallback="l3_incomplete"` and `trace.l3_complete=false`, do not present
  the response as concept-grounded. Show that the document is still being
  processed and fall back to `fetch_document_section` or local PDF context.
- The returned answer text may be used to call `wiki plugin promote` after user
  approval.
- The plugin must display `trace` in a "Sources & Trace" panel when available.

### 5.2 `wiki plugin promote` Contract

Command input:
```json
{
  "question": "What should we preserve from this answer?",
  "answer": "The reviewed answer text to promote.",
  "workspace_path": ""
}
```

JSON output:
```typescript
interface PromoteAnswerResult {
  ok: boolean;
  promoted_to?: string;      // vault-relative path in 02_Wiki/
  error?: string;
}
```

Rules:

- The plugin must request explicit user confirmation before calling
  `promote_answer`.
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
  pageLabels?: string[];       // PDF PageLabels, 0-based physical page -> printed label
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
  Text-mode capture must not set `isScannedLike=true` when the viewer exposes
  substantial selectable DOM text; usable PDF.js/DOM text remains the fast path
  and must not be replaced by image fallback.
- PDF context must never be written to `.curator/` without explicit user approval.
- PDF viewer chat and durable PDF knowledge refinement are separate workflows.
  Normal chat over an open PDF must use viewer-local page/selection/crop context
  first and must not require source registration. Purple context chips and
  `Add to Incurator` are the durable refinement controls: they register the
  source, create instant L1, and queue L2/L3 build jobs.
- Provider-context assembly must never import/register an untracked PDF as a
  side effect. Passive viewing and read-only backend fallback leave source rows,
  reference stubs, CTX pages, assets, and ingest jobs unchanged.
- Backend PDF context responses expose
  `context_source="durable_l1_projection"|"ephemeral_parse"` and may expose a
  `degraded_reason`. Durable L1 projection serving requires a registered source,
  `l1_complete=true`, and a readable CTX projection. The CTX projection is
  derived/disposable; SQLite remains authoritative for source/L1 status and
  source-span locators.
- Queued L2/L3 jobs are executed only by an explicit worker path such as
  Dashboard Jobs `Run queued`, `wiki jobs run`, or an active backend worker. The
  Add-source chip must not wait for L2/L3 completion.
- In sidechat prompts, user-added context references such as line references,
  selected text, explicit text snippets, and PDF snips are the primary focus for
  the current turn, including when those explicit snippets are pinned. Pinned
  whole files/pages and automatically visible context are background grounding.
  Context chips may be toggled invisible/excluded; excluded chips remain visible
  in the UI but must not be included in model prompts, continuity summaries, or
  primary-context detection.
- Selected-context sidechat turns should include current page/document structure
  as supplementary grounding when available: Markdown headings as a compact
  outline and PDF outline/window context for PDF tabs. These outline/page blocks
  must not replace the selected text, line range, or crop as the primary answer
  target.
- If a selected PDF text/crop is itself a cross-reference pointer (for example
  `Section A4.2`, `p580`, `Figure 19.1`, or `Eq. (19.6)`), the plugin may add a
  `<resolved_cross_references>` block ahead of generic page background. Each
  reference entry should identify the label, resolved target page when known,
  section title when known, confidence, and the fetched target text/snippet.
  Pointer resolution failures must not silently turn the current page into the
  answer target; the prompt must tell the provider when the referenced target
  could not be located.
- Attached PDF/image snips must be sent to vision-capable models as image parts.
  For non-vision models, the prompt must explicitly state that image details are
  unavailable instead of silently dropping the crop.
- When the active PDF viewer already provides local page text, nearby window
  text, or image/crop context, provider context assembly must skip backend
  whole-PDF context and PDF RAG calls for that turn. Local PDF.js text/image
  context is the fast path; backend PDF window/outline and RAG are fallback
  paths when local viewer context is unavailable.
- For a PDF-focused turn, the plugin must not run `curator_query` as though the
  relevant PDF were concept-grounded unless that source is L3-complete. L1
  section serving and L3 workspace querying are separate capabilities.
- If the latest user message includes an editable Markdown line-range and asks
  to fix, rewrite, polish, translate, or otherwise modify the selected text, the
  assistant must propose an `ai-agent-edit` SEARCH/REPLACE block. Ordinary
  questions about selected text must answer normally without proposing edits.
- If the latest request uses selected PDF/text context as an example for a
  Markdown-file edit, the selected region is a pattern clue, not the sole edit
  target. Provider context must include the full content of open Markdown edit
  targets so the assistant can search the whole file for similar occurrences,
  preserve HTML as HTML and Markdown as Markdown, and return SEARCH/REPLACE
  hunks that are reviewed in the Markdown editor before mutation.
- SEARCH location must be resilient and ambiguity-safe. A single shared matcher
  (`utils/editMatch.findSearchBlock`) is used by every apply and preview path. It
  tries `exact` → `line-trim` (same line count, per-line trimmed equality, for
  indentation/whitespace drift) → `anchored` (≥3-line blocks, first/last non-blank
  trimmed lines as anchors). It returns the REAL file span (callers splice the
  file's own text). When two or more spans are plausible, or an anchored span
  balloons past 3× the search size, it returns `null` and the UI reports "could
  not find" — it never applies a guessed/ambiguous edit. The preview diff is built
  with the same matcher, so the shown diff equals what apply writes.
- Proposed edits must never flood the chat transcript with raw SEARCH/REPLACE
  code. While streaming, all `ai-agent-edit` content (from the first edit marker)
  is collapsed behind a single placeholder; once finalized, each proposal renders
  as a compact diff-review pill. Orphan markers (`<<<<`/`====`/`>>>>`) left by a
  malformed/partial block are stripped from the RENDERED message only (fence-aware,
  evidence-gated); stored `ChatMessage.content` is never mutated, so copy stays
  faithful.
- Immediate diff (safe-gated): on answer completion, if the proposals target a
  single existing file AND that file is the active `MarkdownView` (or no Markdown
  note is focused), the plugin opens the in-editor `DiffViewer` automatically,
  once per message (`diffAutoOpened`); it never force-opens a background tab or
  steals a different focused note — those keep the clickable Review-Diff pill.
  This runs only from the generation-complete path, never on history re-render.
- A non-blocking notice warns when a single replacement rewrites a very large
  region (model-independent guard against whole-answer-as-one-REPLACE scope drift).
- There is NO on-disk diff artifact. The previous `00_System/Agent Diffs/` note
  feature and its `editArtifactEnabled` setting were removed in v0.5.0; the
  in-editor `DiffViewer` is the single source of truth. (Pre-existing artifact
  files in users' vaults are left untouched.)

## 7. Backend Access Contract

Static metadata such as the model catalogue must not go through MCP; it is
bundled from backend `models.json` at plugin build time. Plugin-local backend
operations should use shared runtime snapshots for read-only status and
`wiki plugin ...` JSON commands for plugin-specific backend logic.

Current local dynamic methods for v0.2.2:

| Method | Backend command |
|---|---|
| `getSourceStatus(path/hash)` | `wiki plugin source status` |
| `ingestPdf(request)` | `wiki plugin source import` → `wiki plugin source register`; accepts file path or Zotero attachment key; passes `--asset-dir` to `register` when the plugin resolves a PDF asset folder (Section 1.1) |
| `rebindSource(args)` | `wiki plugin source rebind` |
| `getPdfContext(args)` | `wiki plugin pdf context` |
| `getPdfRagHits(args)` | `wiki plugin pdf search` |
| `checkBackendVersion()` | `wiki plugin version` |
| `curatorQuery(question, opts)` | `wiki plugin query` |
| `promoteAnswer(args)` | `wiki plugin promote` |

Rules:

- All methods must return `null`/empty gracefully when `incuratorEnabled=false`
  or when the backend command cannot return JSON.
- Plugin-local Incurator calls must use backend JSON commands only. They must
  not discover or call Incurator MCP tools as a fallback.

## 8. Current Rules

- v0.2.2 plugin source-status normalization must treat missing
  `l2_complete`/`l3_complete` fields as `false`.
- The plugin must not maintain `MODEL_OPTIONS` as a cloud-model fallback. Use
  the bundled backend `models.json` catalogue for model controls. MCP
  `get_available_models` is for external agents, not plugin dropdown hydration.
- Plugin settings written in v0.2.0 format (missing `incuratorStatusPolling` etc.) must
  be migrated on load by applying `DEFAULT_SETTINGS` as defaults.
- `SessionData` separated from `PluginSettings` is a v0.2.1 change. Old `data.json`
  files with embedded `chatSessions` must be migrated to `sessions.json` on first load.
The sidechat final answer is generated by the plugin-selected provider/model.
Incurator backend calls provide retrieved context, source status, PDF windows,
or backend synthesis blocks only when the plugin explicitly calls those backend
commands. Provider context must not carry a stale `final_output_language` from a
previous backend query; the latest user message language controls the final
answer language.

PDF crop images are temporary chat context. They may be sent as image parts to
vision-capable models or represented as text fallback for non-vision models, but
chat crop context must not leave durable images under `05_Assets`.

The Zotero linked attachment root is only the base path for Zotero
`attachments:` linked-attachment records. Normal Zotero storage attachments use
the data directory `storage/<KEY>/...` path and do not require this root.

---

# v0.3.2 Curation-Native Plugin Contract

The sections above (1–8) define the inherited v0.2.2 plugin contract. The
sections below define the plugin payloads and panels for the v0.3.1
curation-native rebuild and the v0.3.2 search/trace dashboard additions. Backend contracts live in
`docs/specs/system_behavior/SYSTEM_BEHAVIOR.md` §15–§20 and
`docs/specs/curator_schema/SCHEMA.md` §11.

## 9. v0.3.2 Local Plugin Commands

The hidden `wiki plugin …` namespace (§1) gains these commands. They return JSON,
call shared backend services, and never go through MCP for same-device flows:

```text
wiki plugin curate plan --workspace-path PATH --json
wiki plugin prompt trace --trace-id ID --json
wiki plugin insight list --workspace-path PATH --json
wiki plugin insight show --insight-id ID --workspace-path PATH --json
wiki plugin insight promote --insight-id ID --workspace-path PATH --json
wiki plugin insight reject --insight-id ID --workspace-path PATH --reason TEXT --json
wiki plugin trace list --workspace-path PATH --limit N --json
wiki plugin trace show --trace-id QTR-... --workspace-path PATH --json
wiki plugin synthesis list --workspace-path PATH --limit N --json
wiki plugin synthesis show --synthesis-id SYN-... --workspace-path PATH --json
wiki plugin models ollama --workspace-path PATH --json
wiki plugin models pull --model ID --json
wiki plugin correction propose --node-id ID --correction TEXT --previous TEXT --workspace-path PATH --json
wiki plugin git status --json
wiki plugin git log --limit N --json
wiki plugin git diff --stat --json
wiki plugin git history --file-path PATH --query TEXT --limit N --json
wiki plugin git push --json
wiki plugin git commit --message TEXT --json
```

`wiki plugin models ollama` returns
`{ ok, host, ram_gb, models: [{ id, label, vram_gb, supports_vision, installed,
fits_ram }] }` — the `data/models.json` Ollama catalogue merged with live
`ollama list` (`installed`) and a `vram_gb <= detected RAM` (`fits_ram`) flag.
`wiki plugin models pull --model ID` runs `ollama pull ID` and returns
`{ ok, model, error? }`. The dashboard LLM Provider card uses these to recommend
models, badge install/RAM status, and offer a one-click **Pull**.

Client method mapping (`plugin/src/agent/incuratorClient.ts`):

| Method | Backend command |
|---|---|
| `getCuratePlan(workspacePath)` | `wiki plugin curate plan` |
| `getPromptTrace(traceId)` | `wiki plugin prompt trace` |
| `listInsightCandidates(workspacePath)` | `wiki plugin insight list` |
| `getInsightCandidate(insightId, workspacePath)` | `wiki plugin insight show` |
| `promoteInsight(insightId, workspacePath)` | `wiki plugin insight promote` |
| `rejectInsight(insightId, workspacePath, reason)` | `wiki plugin insight reject` |
| `listQueryTraces(workspacePath, limit)` | `wiki plugin trace list` |
| `getQueryTrace(traceId, workspacePath)` | `wiki plugin trace show` |
| `listSynthesisNodes(workspacePath, limit)` | `wiki plugin synthesis list` |
| `getSynthesisAudit(synthesisId, workspacePath)` | `wiki plugin synthesis show` |
| `proposeCorrection(nodeId, correction, previous, workspacePath)` | `wiki plugin correction propose` |
| `getGitStatus()` | `wiki plugin git status` |
| `getGitLog(limit)` | `wiki plugin git log` |
| `getGitDiffStat()` | `wiki plugin git diff --stat` |
| `getGitHistory(filePath, queryText, limit)` | `wiki plugin git history` |
| `pushGitChanges()` | `wiki plugin git push` |
| `commitGitChanges(message)` | `wiki plugin git commit` |

Rules:

- These methods return `null`/empty gracefully when `incuratorEnabled=false` or
  when the backend cannot return JSON, like all other plugin-local methods (§7).
- `promoteInsight` requires explicit user confirmation before it is called, the
  same rule as `promoteAnswer` (§5.2). It writes only to `02_Wiki/` backend-side.
- Plugin-local Incurator calls must use backend JSON commands only; they must not
  discover or call Incurator MCP tools as a fallback.

### 9.1 Git Plugin Commands

Git operations use the local `git` binary via backend JSON commands. There is
**no** GitHub CLI (`gh`) dependency and the plugin stores no GitHub tokens;
HTTPS-push authentication, if used, is handled by the user's git credential
helper outside the plugin.

`wiki plugin git status --json` returns a structured repository state:

```typescript
interface GitStatusResult {
  ok: boolean;
  repo: {
    is_repo: boolean;
    root: string;
    branch?: string;
    upstream?: string;
    ahead?: number;
    behind?: number;
    remote_url?: string;
  };
  working_tree?: {
    clean: boolean;
    staged: number;
    unstaged: number;
    untracked: number;
    conflicted: number;
  };
  warnings?: string[];
  error?: string;
  message?: string;
}
```

`wiki plugin git history` accepts an active Markdown file path and optional
selected text. It must reject paths outside the vault root. With selected text it
uses a short normalized excerpt for exact pickaxe-style lookup first; if no exact
match exists it falls back to recent file history and marks the result as
`exact_match: false`. Returned patches/snippets are capped.

`wiki plugin git push` must refuse unsafe pushes: not a git repository, missing
upstream/remote, conflicted working tree, branch behind or diverged from
upstream, or missing `git`. It must not merge, rebase, or create commits
implicitly. This supports vaults that already create commits through scheduled
jobs. `wiki plugin git commit` is a guarded explicit fallback only; if used, it
stages files according to `.gitignore` and must not add ignored files.

Sidechat must call these backend commands through `IncuratorClient` for explicit
status, push, and selected-text/file-history requests. It must not depend on
provider-native shell/tool behavior to guess Git commands.

## 10. v0.3.2 Query Result And Trace Payloads

`wiki plugin query` (§5.1) returns the curation-native fields additively. `CuratorQueryResult`
gains:

```typescript
interface CuratorQueryResult {
  // ... fields from §5.1: ok, answer, question, input_language, english_query,
  // final_output_language, trace, error ...
  route?: "auto" | "local" | "global" | "explore" | "source-section";
  trace_id?: string;              // QTR-<UUID8>
  prompt_trace_ids?: string[];    // PTR-<UUID8>
  source_span_ids?: string[];     // SPAN-<UUID8>
  community_report_ids?: string[];// REP-<UUID8>
  memory_path_ids?: string[];     // MPATH-<UUID8>
  insight_candidate_ids?: string[];// INS-<UUID8>
  warnings?: string[];
}
```

New trace and evidence interfaces (`plugin/src/types.ts`):

```typescript
interface IncuratorPromptTrace {
  traceId: string;        // PTR-<UUID8>
  promptId: string;
  promptVersion: string;
  family: string;
  validatorStatus: "ok" | "repaired" | "failed" | "pending";
  validatorErrors: string[];
  modelProvider?: string;
  modelName?: string;
}

interface IncuratorEvidenceTrace {
  route: string;
  traceId: string;             // QTR-<UUID8>
  promptTraceIds: string[];
  sourceSpanIds: string[];
  communityReportIds: string[];
  memoryPathIds: string[];
  insightCandidateIds: string[];
}

interface IncuratorCuratePlan {
  planId: string;              // PLAN-<UUID8>
  workspaceId: string;
  curateSpecHash: string;
  route: string;
  promptProfile: string;
  selectedSources: string[];
  excludedSources: { path: string; reason: string }[];
  allowedModes: string[];
  knownGaps: string[];
  validationErrors: string[];
}

interface IncuratorInsightCandidate {
  id: string;                  // INS-<UUID8>
  classification: "correction" | "contradiction" | "derived_insight"
    | "style_only" | "promotion_request" | "ambiguous";
  statement: string;
  status: "pending" | "accepted" | "rejected" | "promoted" | "needs_review";
  affectedNodeIds: string[];
  confidence: number;
}
```

## 11. v0.3.1 Trace Panel Rendering

The chat "Sources & Trace" panel (`plugin/src/ui/incuratorQueryTrace.ts`) renders,
when the fields are present:

- a **route badge** (`auto`/`local`/`global`/`explore`/`source-section`);
- the active workspace and `curate.yml` spec hash;
- **source spans** cited by the answer (id + preview, grouped by source);
- **community reports** used (id + title);
- **prompt trace links** (prompt id/version + validator status), each opening the
  full `IncuratorPromptTrace` via `getPromptTrace`;
- a **memory-path summary** for explore answers (the hop chain);
- **insight candidates** with their classification and a promote action that calls
  `promoteInsight` after explicit user confirmation.

Rules:

- The panel must degrade gracefully: missing curation-native fields render nothing rather
  than erroring, so an older/partial backend response still shows the v0.2.2 trace.
- Insight-candidate promotion and any backprop action are explicit user actions;
  the panel must not auto-promote or auto-patch.
- The curation panel surfaces `IncuratorCuratePlan.validationErrors` and
  `excludedSources` so the user sees why sources were dropped, rather than the
  plugin silently inventing workspace scope (the §5.1 no-arbitrary-workspace rule
  is retained).

## 12. v0.3.2 Dashboard Trace And Insight Click-To-Use

The Dashboard gains first-class Trace and Insights surfaces. These surfaces are
read-only by default and mutate durable backend state only through explicit hidden
backend commands.

### 12.1 Query Trace Commands

```ts
type QueryTraceSummary = {
  traceId: string;          // QTR-<UUID8>
  workspaceId: string;
  route: "local" | "global" | "explore" | "source-section";
  warnings: string[];
  createdAt: string;
  latencyMs?: number;
};

type TraceListResult = {
  ok: boolean;
  traces: QueryTraceSummary[];
  error?: string;
};

type QueryTraceDetail = {
  ok: boolean;
  traceId: string;
  workspaceId: string;
  route: "local" | "global" | "explore" | "source-section";
  routeReason: string;
  sourceSpanIds: string[];
  communityReportIds: string[];
  synthesisNodeIds: string[];
  memoryPathIds: string[];
  promptTraceIds: string[];
  insightCandidateIds: string[];
  retrievalTrace?: {
    expansions?: unknown[];
    ftsCandidates?: unknown[];
    vectorCandidates?: unknown[];
    rrf?: unknown[];
    rerank?: unknown[];
    degraded?: string[];
  };
  warnings: string[];
  latencyMs?: number;
  createdAt: string;
  error?: string;
};
```

`wiki plugin trace list` returns `TraceListResult` for the currently open
Obsidian vault because the plugin backend runner executes with the vault root as
its working directory. `wiki plugin trace show` returns `QueryTraceDetail`.
Dashboard Trace UI is vault-local, not tied to `01_Workspaces/` directories;
external workspace folders are backend/domain concepts and must not be inferred
by the plugin dashboard. Trace rows may be partial when only prompt-run joins
exist, but the plugin must render partial rows rather than failing.

### 12.2 Synthesis Audit Commands

```ts
type SynthesisSummary = {
  id: string;                 // SYN-<UUID8>
  title: string;
  confidence: number;
  sourceSpanIds: string[];
  communityReportIds: string[];
  promptRunId?: string;
  updatedAt: string;
};

type SynthesisListResult = {
  ok: boolean;
  synthesis: SynthesisSummary[];
  error?: string;
};

type SynthesisAuditReport = {
  ok: boolean;
  kind: "synthesis" | "report" | "answer";
  id: string;
  synthesis?: {
    id: string;
    title: string;
    statement: string;
    confidence: number;
    sourceSpanIds: string[];
    communityReportIds: string[];
    promptRunId?: string;
  };
  communityReports: unknown[];
  entities: unknown[];
  relations: unknown[];
  knowledgeUnits: unknown[];
  sourceSpans: unknown[];
  promptRuns: IncuratorPromptTrace[];
  queryTrace?: QueryTraceDetail;
  dependencyWarnings: string[];
  warnings: string[];
  error?: string;
};
```

`wiki plugin synthesis list` returns recent L4 synthesis nodes for the currently
open vault. `wiki plugin synthesis show` returns the read-only L4→L1 audit chain
for one `SYN-` id. The plugin must not attempt to compute this chain itself from
SQLite; it must render the backend JSON and degrade gracefully if only partial
evidence is available.

### 12.3 Insight Detail And Review Commands

`wiki plugin insight list` returns candidates for the currently open Obsidian
vault. `wiki plugin insight show` returns the current insight-candidate fields
plus:

- `evidence`
- `sourceEventId`
- `promptRunId`
- `createdAt`
- `updatedAt`

`wiki plugin insight reject` marks a candidate rejected with a reason. `wiki
plugin insight promote` remains the only promotion path and writes only to
`02_Wiki/` after explicit user confirmation.

### 12.3 Correction Proposal Command

`wiki plugin correction propose` accepts `node_id`, correction text, optional
previous text, and workspace path. It calls the backend correction classifier and
returns the classification, recommended action, any created insight candidate id,
and whether human review is required. The plugin must never overwrite generated
nodes directly.

### 12.4 Safety And Boundary Rules

- Dashboard Trace and Insights tabs call hidden local `wiki plugin ... --json`
  commands via the plugin's vault-local backend command runner, not MCP tools and
  not `01_Workspaces/` paths.
- Dashboard Trace and Insights tabs must use a list/detail flow: list commands
  render summaries, and selecting a row loads the backend detail payload before
  exposing follow-up actions such as promote/reject.
- Runtime snapshots remain backend-owned local read models. The plugin reads
  them but never writes them, and it must let the local backend refresh them
  before treating dashboard status or source rows as current.
- Runtime snapshots can contain machine-local absolute paths. The plugin must
  not assume a synced `.curator/runtime/*.json` file belongs to the current
  device.
- Dashboard must not edit `.curator/state.sqlite`, `.curator/Collections/`,
  `03_Notes/`, `04_Resources/`, or `06_Archives` directly.
- Prompt trace UI does not expose raw prompt input/output bodies by default in
  v0.3.2; ids, hashes, model, route, validator status, evidence ids, and warnings
  are sufficient.

## 13. In-line Copilot Quick Query (v0.4.0)

The plugin provides a drag-to-select quick query surface ("In-line Copilot") for
one-off questions about a selected passage. It is gated by
`PluginSettings.quickQueryEnabled` (default `true`).

### 13.1 Trigger And Surface

- On a non-empty text selection anywhere in the workspace (Markdown editor,
  reading view, or PDF), the plugin shows exactly one floating trigger button next
  to the selection. No toolbar or multi-button cluster is rendered.
- Activating the button — or invoking the `quick-query-selection` command
  (default hotkey `Cmd+Shift+K`) while text is selected — opens a single popover
  containing only a free-text query input and a submit control. No preset/quick-
  action buttons are present.
- Selections made inside the plugin's own button/popover must not re-trigger the
  surface.

### 13.2 Context And Follow-ups

- The selected passage is always supplied as the current turn's
  `<primary_focus_selection>`.
- The plugin should refresh active Obsidian context before each quick-query
  request and may include the active Markdown/PDF page, nearby PDF window pages,
  and available Markdown/PDF outline as background context. Background context
  must be marked as supplementary and must not override the selected passage.
- Follow-up questions asked in the same popover may include a short in-memory
  trace of prior quick-query turns from that popover only. These turns are
  ephemeral and are not the chat-sidebar session history.
- Quick query must not run workspace-wide `wiki plugin query` merely because
  background context is present; it answers from the selected passage plus
  current page/outline background.

### 13.3 Answer Rendering

- On submit, the input row is hidden while the model answer streams; the chat
  bubble layout is not used. After the answer completes, a compact follow-up
  input may return in the same popover.
- The answer streams as plain text while generating and is rendered as Markdown
  (math/LaTeX included) once the stream completes. Provider thinking/status
  scaffolding (`<thinking>`, `<think>`, `<thought>` blocks) is stripped from the
  displayed answer.
- CLI providers may emit progress on stderr. Antigravity `agy` stderr lines that
  are recognizable as progress/status must stay in the thinking/status block. If
  `agy` exits successfully with empty stdout and stderr contains non-status
  answer text, that text is recovered as the assistant answer rather than
  leaving the UI on `Thinking...` or producing an empty message.
- The answer container keeps text selectable/copyable and is size-capped
  (`max-height`/`max-width`) with internal scrolling for long answers.
- Rendered assistant links that parse as page/section targets (`#page=N`,
  `p.N`, `#section=A4.2`, `Section A4.2`, or `§A4.2`) should navigate the open
  Incurator PDF viewer to the resolved page. Section targets resolve through the
  active PDF outline. Printed page targets (`p.N` / `page N`) resolve through
  the PDF's native PageLabels array when available; explicit `#page=N` targets
  remain physical page numbers. Links that do not parse as page/section targets
  retain normal Obsidian/Markdown behavior.

### 13.4 Ephemerality And Boundaries

- The popover is a temporary surface. Closing it (close button, `Escape`, or an
  outside click once the answer is complete) discards the exchange. It must never
  be written into `SessionData` or the chat sidebar history.
- The query is issued through the standard `LLMClient` using the active
  provider/model. No prior chat-sidebar turns are appended.
- An in-flight quick query is aborted when its popover is dismissed.

---

## 14. LaTeX-preserving copy (chat sidebar + note Reading View) (v0.5.4)

Selecting part of a rendered assistant reply (chat sidebar) or a note (Reading
View) and copying it (`Cmd/Ctrl+C`, or `Cmd/Ctrl+X`) places the formulas' LaTeX
**source** (`$...$` / `$$...$$`) on the clipboard instead of the empty MathJax SVG.

### 14.1 Renderer constraint (why this needs render-time stamping)

- Obsidian renders math (chat sidebar and reading view alike) as MathJax **CHTML**
  and keeps **no** LaTeX source in the rendered DOM: there is no
  `annotation[encoding="application/x-tex"]`, no `mjx-assistive-mml`, and no source
  attribute on the `mjx-container` or its `.math` wrapper (verified against a live
  vault). A selection that spans a formula therefore carries no recoverable source.
- Consequence: any rendered surface must **re-attach** the source at render time
  (stamping) for a selection-based copy to recover it. The selection visually
  *skipping* a non-selectable formula does **not** prevent capture — the math node
  is still present in the selection range's `cloneContents()`, so the stamped source
  is read regardless of the visual highlight.
- Live Preview / Source mode are unaffected — CodeMirror copies the markdown source
  natively — so the plugin augments only the **chat sidebar** and the note
  **Reading View**, not the Live Preview editor.

### 14.2 Behavior contract

- The chat sidebar renders each assistant reply from a source string the plugin
  holds. Immediately after each `MarkdownRenderer.render(...)` resolves, the plugin
  stamps every rendered `.math` element with its source as `data-tex` and its kind
  as `data-tex-display` = `"inline" | "block"`, in document order.
- **Correctness guard:** the source is parsed for `$...$` / `$$...$$` (code-span,
  fenced-code, and escaped-`\$` aware) and the stamp is applied **only when the
  parsed formula count exactly equals the rendered `.math` count**. On any mismatch
  the block is left unstamped (no wrong source is ever attached; the formula simply
  falls back to non-recoverable, as before).
- The existing element-scoped `copy` handler on the chat message container then
  serializes a math-containing selection to `text/plain` with LaTeX preserved,
  reading each formula's source from its `data-tex` stamp (`getLatexFromMathEl`
  checks `data-tex` first, then the legacy annotation/script lookups). A selection
  with no rendered math is a no-op (native copy is byte-identical).
- A formula partially overlapped by the selection is captured **whole**; the plugin
  does not emit a truncated half-formula.

### 14.3 Note Reading-View contract

- The plugin registers a Markdown post-processor. For each rendered section that
  contains `.math`, it reconstructs the section's source from `getSectionInfo`
  (`text` sliced by `lineStart..lineEnd`) and calls the same `data-tex` stamping as
  the chat path, under the same exact-count correctness guard.
- A document-level `copy` and `cut` interceptor is registered on the main document
  and every pop-out window, in the **capture** phase (so it runs before any
  view-level handler). It acts **only** when the selection is anchored inside a
  `.markdown-reading-view` **and** its cloned fragment contains rendered math; on
  either guard failing it returns before `preventDefault`, leaving the native
  clipboard untouched (non-math copies and Live Preview / source mode are never
  intercepted).
- When it acts, the selection is serialized to Markdown with LaTeX preserved
  (`selectionToMarkdownWithLatex` via Obsidian's `htmlToMarkdown`) and written to
  `text/plain`. Reading View is read-only, so `cut` writes the clipboard but deletes
  nothing; Live Preview's native cut already removes the source.
