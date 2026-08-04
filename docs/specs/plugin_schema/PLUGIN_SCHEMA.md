# Incurator Plugin Schema & API Contract (v0.42.0)

Audience: Obsidian plugin developers, frontend contributors, and coding agents.

> **v0.40.0 note (Commit-Boundary Persistence):** existing synced session and
> Zotero-profile files are parsed and merged inside Obsidian's atomic
> `DataAdapter.process()` callback. This API requires Obsidian 1.1.0+, so the
> plugin manifest raises `minAppVersion` to `1.1.0`; `versions.json` keeps
> v0.39.2 as the compatible fallback for Obsidian 1.0.x. Persisted JSON shapes
> are unchanged.

> **v0.39.0 note (Authored-Note Topology):** no plugin settings or wire shape
> change. Existing graph/explore surfaces consume only backend-authoritative
> `active` relations. Human-authored links may shape topology but never appear as
> fabricated factual support or citations; diagnostic rows retain their explicit
> lifecycle/edge-class labels. See SYSTEM_BEHAVIOR §27.3.1.
>
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
- `ZoteroProfilesFile` — Zotero import profiles + recent-item LRU, stored in
  `.curator/zotero_profiles.json` (v0.30.0; vault-resident so Syncthing carries
  it across devices, like `sessions.json`)
- Transient PDF.js extraction for open documents (never written to `.curator/`)
- Chat UI rendering and streaming
- Human approval prompts for import, reference registration, rebind, and promotion
- Rendering of progress/status/trace returned by backend calls or backend-owned
  shared status snapshots
- Best-effort Syncthing device registry refresh on startup, writing
  `.cache/config/devices.json` without requiring a manual backend command

The plugin must not:

- Write directly to repo-cache `state.sqlite` or `.curator/Collections/`
- Call backend MCP tools that mutate durable state without explicit user action
- Maintain its own hard-coded cloud model list; bundle the backend
  `backend/src/curator/data/models.json` catalogue at plugin build time

The plugin may write `.cache/config/devices.json` as the single exception to the
`.curator/` write boundary. That file is sync metadata, not DAG state. The
plugin may also read repo-cache `runtime/*.json` dashboard snapshots, but backend
code is the only writer for those files. Dashboard backend health, source/job
counts, index readiness, and backend version display must come from those
snapshots or from explicit backend commands, not from Incurator MCP tool
polling.

Dashboard controls that change backend state must execute backend commands or
backend-owned APIs. The plugin must not implement those controls by directly
editing `.curator/settings.yml`, repo-cache `state.sqlite`, generated Collections,
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
wiki plugin context fetch
wiki plugin context expand
wiki plugin context verify
wiki plugin context feedback
wiki plugin version
wiki plugin query
wiki plugin promote
wiki plugin db export
wiki plugin db import
```

The backend implementation of this namespace is the backend-local
`curator.plugin_api` function API. That module may be implemented as a package
internally, but its import path, exported function names used by CLI/MCP
wrappers, and JSON envelopes are part of the plugin contract. The plugin does
not call these functions in-process; it observes them through hidden backend
commands such as `wiki plugin source status`, `wiki plugin pdf context`, and
`wiki plugin query`.

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
- `source register` returns `warnings: string[]` on success. Non-fatal
  maintenance failures, such as a skipped DB-native search-index refresh after
  L1 generation, must be surfaced there instead of being silently swallowed.
  Unexpected programming errors must still propagate to the CLI wrapper, which
  returns the normal `{ok:false,error}` envelope.

### 1.2 AssetSource model & status key (Plan G target, vNEXT)

The plugin currently resolves a source asset's path/identity ad hoc across many
call sites (`getPdfRefSourcePath`, `resolvePdfRefSourcePath`,
`resolveExternalPdfPath`, `resolveZoteroAttachmentPath`, `toAbsolutePath`,
`buildSyncedExternalPdfState`) and keys backend source-status inconsistently
(sometimes by `sourcePath`, sometimes by `zotero:<key>`). `AssetSource` (not
`PdfSource`) is the generic model — it covers PDFs, markdown notes, and external
image attachments (the asset-routing scope folded into Plan G). Plan G introduces
ONE model and ONE resolver.

```typescript
interface AssetSource {
  absPath?: string;      // resolved real file on disk
  relpath?: string;      // in-vault path/stub (Reference Mode)
  zoteroKey?: string;
  fileHash?: string;
  displayName: string;
  resolutionStatus: "resolved" | "path_unresolved" | "untracked";
}

// Single resolver. Prefers backend resolution (IncuratorClient) when available;
// keeps a thin local Zotero fallback ONLY when the backend command is offline.
function resolveAssetSource(input, deps): Promise<AssetSource>;

// Single canonical cache key for the backend source-status map. Used by BOTH
// the writer (post-ingest) and the badge reader, eliminating the
// path-vs-zotero:key mismatch (audit item 3).
function assetStatusKey(s: AssetSource): string;
```

Contract:
- `assetStatusKey` is derived deterministically from a `AssetSource` and is the only
  key used to read and write `incuratorStatusByPath`; the writer and reader MUST
  use the same key for the same logical source so the "Added"/"Queued" badge
  never desyncs (item 3).
- Zotero detection MUST NOT rely on `leaf.view.getState()` `as any` casts
  (item 4); the `AssetSource.zoteroKey` field is the discriminator.
- Registered source badge states: `isAddedState` recognizes `queued`, `running`,
  and `l1_ready..l4_ready` as already registered. `l1_ready..l4_ready` collapse
  to the **Added** label; `queued`/`running` keep their own labels
  (`Queued`/`Building...`) while remaining inert so they cannot re-trigger Add
  Source before the background build completes.
- `absPath` is runtime-only and authoritative only for the current open/read
  operation. It is never persisted. Zotero views persist
  `zoteroAttachmentKey`; generic external views persist `externalRef`.
- **Zotero runtime cache invalidation (required).** Backend-resolved
  `attachment_key → absPath` values may be cached only in memory to avoid
  repeated lookup on the hot path. That cache MUST be invalidated
  whenever the resolution inputs can change, so it never serves a stale/broken
  absolute path:
  - it is keyed by, and tied to, the workspace **configuration epoch** (the
    Zotero data-directory / linked-attachment-root settings + active workspace);
    a change to any of those clears the cache;
  - it is fully cleared on plugin reload / `onunload`→`onload` (the cache is
    in-memory only, never persisted to `data.json`);
  - a cached `absPath` whose file no longer exists at resolve time is treated as
    a miss and re-resolved (never returned as-is);
  - **device-portable**: absolute paths differ per machine/OS. The cache is
    memory-only and per-process. Persisted `externalPdfDocs`, Obsidian view
    state, plugin `data.json`, and `.curator/sessions.json` contain no absolute
    locator. Zotero restores by attachment key through the backend; generic
    external sources restore by `externalRef`. Persisted session context
    refs MUST NOT rely on `ContextRef.filePath` or
    `backendStatus.sourcePath/currentPath/candidatePath` as durable identity when
    those fields are absolute paths from another device; keep portable identity
    (`zoteroAttachmentKey`, `fileHash`, vault-relative relpath, page number) and
    re-resolve the physical path locally.

Backend responses may carry an absolute path for an immediate open operation.
The plugin keeps it outside persistable DTOs.

The plugin must not direct users to a backend path-migration command. Backend
source identity is assumed to use the current Zotero-key or named-root contract;
unsupported legacy device-local DB recovery is outside the plugin UI.

### 1.3 Internal module ownership and stable facades (v0.36.0)

The plugin may decompose large implementation files behind stable TypeScript
facades. The following import paths and their current public exports remain
compatible for the entrypoint, plugin consumers, and tests:

- `src/agent/llmClient.ts` — facade for `src/agent/llm/`
- `src/ui/chatSidebar.ts` — facade for `src/ui/chat/`
- `src/ui/externalPdfView.ts` — facade for `src/ui/pdf/`

Implementation behavior belongs in the owner directories. A facade may declare
stable constants/types or re-export owned symbols, but must not retain duplicate
or inert implementation text merely to satisfy a source-string test. Tests for
sandboxing, provider commands, PDF state, rendering, and chat orchestration must
inspect or import the module that actually owns that behavior. `plugin/main.ts`
remains the Obsidian lifecycle entrypoint and may consume either the stable
facades or explicit owner modules without changing command IDs, view types,
settings fields, persisted DTOs, or backend command envelopes.

### 1.4 Asynchronous lifecycle safety (v0.36.0, strengthened in v0.40.1)

- Every public provider request owns a locally captured `AbortController` for
  its complete lifetime. `streamChat` and `complete` accept an optional caller
  `AbortSignal`; surfaces that can overlap (including independent Quick Query
  popovers) must create and abort their own signal. Closing one surface must not
  abort another surface's request. A request with an explicit caller signal must
  not replace the legacy foreground pointer used by sidebar controls.
- `LLMClient.abort()` remains the foreground-control API for existing sidebar
  stop/dismiss actions. The foreground pointer selects an active request but is
  never the source of truth for another request's lifetime. When a newer request
  finishes, an older still-active request becomes foreground again.
- A provider request whose local signal is already aborted, including one
  cancelled during asynchronous context preparation, must settle before any
  HTTP or CLI transport launches. Provider-specific error classification must
  rethrow `AbortError` unchanged.
- Streaming and non-streaming CLI subprocesses bind to the request-local signal.
  Non-streaming CLI construction must use the per-call model override and the
  same GUI-safe augmented environment (`PATH` plus device-local CLI temp paths)
  as streaming CLI construction.
- Closing an External PDF view invalidates its render token before timer,
  observer, cache, and index cleanup. Any in-flight PDF render must discard its
  result instead of touching the closed view DOM.
- Optional child-process streams must be checked before writes. A missing MCP
  `args` array is normalized to an empty array during command preparation.

#### 1.4.1 Leaf narrowing must not trust the view-type string (v0.41.1)

Obsidian 1.7.2+ restores workspace tabs as **deferred** views. A deferred
`leaf.view` answers `getViewType()` with the real registered type while being a
placeholder that carries none of the concrete view class's methods. A matching
view-type string is therefore **not** proof of class identity, and neither is it
proof after an in-place plugin update, which can leave a live leaf holding an
instance built from the previous bundle.

- Narrowing a leaf to `ExternalPdfView` MUST go through a capability-checked
  guard that verifies the methods the caller will actually invoke. A bare cast
  guarded only by the view-type string is a defect.
- A leaf that fails the guard degrades to the leaf's persisted state. It MUST
  NOT throw, and it MUST NOT be force-loaded as a side effect of assembling
  context — building context is a read-only observation of the workspace.
- This is a shared-path invariant, not a per-surface one: the leaf resolver
  feeds both active-context capture and the open-tab inventory, so one
  unguarded cast takes down the context pins, sidechat Send, and the Quick
  Query popover together.

#### 1.4.3 Long provider waits must show progress (v0.42.0)

A CLI-backed provider round-trip is dominated by the provider service
handshake, not by inference: measured on a development machine, `agy --print`
takes 8.2–12.2 s for a one-word answer regardless of model or effort, while the
CLI binary itself starts in 0.29 s and an Incurator backend round-trip is
0.20 s. `--print` also cannot stream — nothing arrives until the whole answer
is ready.

- Any surface that awaits a provider turn MUST show a progressing indicator
  (elapsed seconds), not a static label. A frozen "Thinking…" is
  indistinguishable from a hang for the entire wait, and that ambiguity has
  already caused a real crash to be misread as slowness.
- A streaming callback MUST NOT overwrite the progressing indicator with static
  text while it has no content to show.
- The indicator MUST stop on success, on error, and on surface teardown, and
  MUST stop ticking once its surface is gone.

#### 1.4.2 Page canvases are exclusive to one render task (v0.41.1)

External PDF page canvases are reused across zoom, scroll, and document swaps.
PDF.js rejects a second `render()` on a canvas whose previous task is still
in flight ("Cannot use the same canvas during multiple render() operations").

- Each page's in-flight render task MUST be retained and cancelled, and its
  promise awaited, before a new render claims that page's canvas.
- Document swap, reload-from-disk, and view close MUST cancel every in-flight
  page render. The render token alone is insufficient: it prevents work
  scheduled after the bump but cannot release a canvas already owned by PDF.js.
- A cancelled task rejects with PDF.js's cancellation exception. That rejection
  is the expected outcome and MUST NOT be surfaced as a render failure.

## 2. Persisted Settings Schema

> **Logging is not a setting.** Plugin logs go through a namespaced logger
> (`src/utils/logger.ts`): `warn`/`error` always emit (prefixed `[Incurator]`),
> while verbose `debug`/`info` are gated by the per-device dev flag
> `localStorage["incurator-debug"]` (read once at load). There is **no**
> `PluginSettings` field for logging and it is never synced.

### 2.1 `PluginSettings`

Stored in `data.json` (Obsidian plugin storage). All fields required unless marked optional.

```typescript
interface PluginSettings {
  // LLM provider selection
  provider: LLMProvider;           // "antigravity" | "claude" | "openai" | "ollama" | "deepseek"
  model: string;                   // model ID, validated against backend catalogue
                                   // (v0.23.0) NO `latexModel` plugin setting: the
                                   // region-extraction model is sourced from the
                                   // backend `llm.latex_extract_model`/`vision_model`
                                   // via the Dashboard runtime snapshot — see §2.6.
  chatMode: ChatMode;              // "chat" | "plan"
  codexReasoningEffort: CodexReasoningEffort;  // ""|"low"|"medium"|"high"|"xhigh"|"max"|"ultra"
  claudeEffort: ClaudeEffort;      // ""|"low"|"medium"|"high"|"xhigh"|"max"
  agentEffort: string;             // Ollama/Antigravity reasoning-effort slot; empty = provider default
  antigravityPrintTimeoutSec: number;
  deepseekApiKey: string;          // device-local optional key; empty = use DEEPSEEK_API_KEY
  ollamaHost: string;              // default "http://localhost:11434"

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
  incuratorBackendCommand: "wiki";          // sentinel; runtime resolves <repo>/.venv/bin/wiki
  incuratorBackendArgs: string[];           // default []
  incuratorRepoPath: "";                // no persisted device path; runtime discovery only
  incuratorDefaultDestination: string;   // vault-relative folder for reference stubs/copy imports
  incuratorDefaultImportMode: "copy" | "reference"; // reference creates a link stub
  incuratorPdfAssetFolder: string;       // vault-relative base folder for extracted PDF images of non-Zotero sources; each PDF gets a filename subfolder; "" = backend default 05_Assets/<slug>/
  incuratorStatusPolling: boolean;

  // Cross-device knowledge auto-sync over Syncthing (optional; undefined = enabled for older data.json)
  autoSyncEnabled?: boolean;       // master switch for all auto-sync behavior
  autoSyncOnLoad?: boolean;        // run autosync once when Obsidian opens
  autoSyncWatch?: boolean;         // watch peer snapshots; filter the known self snapshot (desktop only)
  autoSyncNotify?: boolean;        // toast only when peers actually delivered changes

  // Zotero integration
  zoteroBasePath: "";              // deprecated persisted field; backend cache owns roots
  // v0.30.0: zoteroProfiles/recentZoteroItems live in-memory on settings for
  // call-site compatibility but are ALWAYS persisted as [] in data.json; the
  // durable store is .curator/zotero_profiles.json (ZoteroProfilesFile below).
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
- `codexReasoningEffort`, `claudeEffort`, and `agentEffort` are persisted
  provider-specific effort slots. Empty `agentEffort` means the active
  Ollama/Antigravity backend should use its provider default.
- `ollamaHost` is the plugin-side Ollama base URL. Empty or missing values fall
  back to `http://localhost:11434`.
- **Region extraction (v0.22.0, supersedes the v0.21.0 `latexModel` plugin setting)**:
  the dedicated vision models (`llm.vision_model` / `llm.latex_extract_model`) are
  configured in the Dashboard (§2.1.2) and are honored at the **backend `add source`
  ingest layer** and the plugin's interactive PDF extraction surfaces
  (SYSTEM_BEHAVIOR §26.2a). The plugin no longer persists a `latexModel` setting.
  The interactive PDF right-click **Convert to LaTeX** action calls
  `wiki plugin pdf transcribe`, which resolves
  `latex_extract_model → vision_model → (main chat model if vision-capable)` in the
  backend; its returned text MUST be normalized (one
  `<transcription>...</transcription>` block; explanatory prose, labels, and fences
  stripped) before the plugin copies or injects it. An Antigravity-backed
  extraction passes the complete transcription request as the `agy --print`
  prompt and the resolved model through `--model`. An explicit
  `latex_extract_model` or `vision_model` used by this action receives `low`
  effort when that model declares `low`; fixed/no-effort models omit
  `--effort`. If both explicit slots are empty, the final main-model fallback
  retains its user-selected effort. Stdin-only prompt transport or scratch-agent
  progress narration is not a successful transcription.
  **Cmd+Shift+X "Snip PDF Region to Chat" (v0.28.0)** routes by the *main chat
  model's* vision capability instead (SYSTEM_BEHAVIOR §26.2a): a vision-capable
  main model receives the crop image DIRECTLY via the interactive chat image
  channel (§2.1.3) with NO `wiki plugin pdf transcribe` round-trip; a non-vision
  main model falls back to `wiki plugin pdf transcribe` (text injected, image
  dropped). The pymupdf `regionText` is retained as a caption in both cases.
- `deepseekApiKey` is device-local secret material. It must not be written into
  shared vault config; backend config may instead reference `DEEPSEEK_API_KEY`
  through `llm.deepseek-api.api_key_env` or a local encrypted backend secret
  through `llm.deepseek-api.api_key_secret`.
- `providerUsage` is device-local and must not sync across Obsidian Sync.
- All plugin `data.json` writes MUST flow through one serialized settings
  writer (`persistSettings`). Direct call sites must not each invoke
  `saveData(_persistableSettings())`; scroll-position debounces, usage
  accounting, migrations, `saveSettings`, `updateSettings`, and unload all share
  the same writer so concurrent saves cannot clobber each other with stale whole
  settings snapshots.
- `autoSyncEnabled`, `autoSyncOnLoad`, `autoSyncWatch`, and `autoSyncNotify` are
  optional for older `data.json` files. Runtime reads use the `!== false`
  convention, so absent values are treated as enabled and only explicit `false`
  disables that auto-sync behavior. The desktop incoming-data watcher MUST
  register an error listener: directory deletion, rename, and permission errors
  are logged instead of surfacing as unhandled Electron exceptions, while the
  60-second safety poll remains available.
- The chat sidebar footer may expose provider/model as one compact selector.
  Selecting a model from another provider must update both `provider` and `model`.
- AI Provider settings must show model context-window information on the
  **Model** row, not as a separate setting row. Catalogue context windows are
  provider/CLI token capacities. The current per-document context clipping
  helper is a conservative character guard, not an exact tokenizer or a claim
  that the full model window is available to one attached document.
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
  visible context may be re-created on the next turn. The plugin MUST enumerate
  every eligible open Markdown/PDF leaf and record whether that leaf is currently
  visible in its split. Every unique `(view type, portable source/file identity,
  page when present)` context key renders a chip. Visible leaves default to
  eye-on; hidden tab-group leaves default to eye-off. Only eye-on or explicitly
  pinned/materialized refs may contribute to provider tab lists, bodies, outlines,
  continuity summaries, primary-context detection, or edit targets. Hidden
  identity-only PDF chips MUST NOT be sent with placeholder content; inclusion
  must first materialize the page or surface an actionable capture failure.
  Pinned purple chips must expose eye/eye-off prompt inclusion controls and
  excluded refs must not be sent to the provider. Tab open/close/layout changes
  must refresh this inventory in addition to active-leaf changes.
- Zotero data-directory configuration must have a single visible entry point:
  **Backend Zotero status > Open setup**. The setup dialog defaults to
  `~/Zotero`, displays home-directory paths with `~` instead of an absolute
  `/Users/...` prefix, and writes the backend-owned Zotero configuration.
- `incuratorBackendCommand`, `incuratorBackendArgs`, and `incuratorRepoPath` are
  per-device settings. The default command `wiki` is a sentinel for
  `<repo>/.venv/bin/wiki`; the plugin must not resolve a bare PATH `wiki`.
  When `incuratorRepoPath` is blank, the desktop plugin may use a memory-only
  local sibling repo hint such as `<workspace>/Incurator` when it contains both
  `setup.sh` and `.venv/bin/wiki`. That hint must not be persisted to plugin
  `data.json`. When `.cache/config/devices.json` has a non-empty
  `backend.repo_path` for the local device, that value overrides any synced
  `incuratorRepoPath` from plugin `data.json` at runtime. Saving settings
  refreshes the local device entry so a path edit is recorded immediately.
- **Setup/build fingerprint check:** `./setup.sh` writes a shared backend/plugin
  build manifest. The plugin compares its bundled build fingerprint with
  `wiki plugin version`'s backend build fingerprint and displays a setup/rebuild
  banner only when those fingerprints are missing or mismatched. Semantic
  backend/plugin version labels alone are not enough to show an update banner
  when the fingerprints prove both sides came from the same local setup run. If
  the backend package has no generated build manifest, `wiki plugin version`
  still returns `build.backend_version`, `build.plugin_version`,
  `build.git_commit`, and `build.schema` fallback fields so the update check has
  a stable JSON shape. If `incuratorRepoPath` is set, clicking the banner executes
  `cd <incuratorRepoPath> && ./setup.sh`; it must not force `git pull`.
  The runtime MUST also compare its own bundled build identity with the plugin
  bundle installed in the active vault. A disk/runtime mismatch means a newer or
  different bundle has been copied but not loaded; sidechat provider launch MUST
  stop before credential/provider startup and expose a reload action. The update
  action may offer renderer reload only after every required plugin artifact has
  copied successfully; a partial copy must remain an error and must not reload.
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
- **Zotero profile storage (v0.30.0).** The durable store for import profiles
  and the recent-item LRU is `.curator/zotero_profiles.json`:

  ```typescript
  interface ZoteroProfilesFile {
    profiles: ZoteroImportProfile[];
    recentItems: string[];        // LRU item keys, newest first, max 50
  }
  ```

  Contract:
  - On plugin load (after settings and session load), the plugin reads the
    file and mirrors it into `settings.zoteroProfiles` /
    `settings.recentZoteroItems` so existing call sites are unchanged.
  - **Read and parse are distinct failure modes.** Only a missing file triggers
    legacy migration. An unreadable file, a file that contains invalid JSON
    (corruption, truncation) **or a structurally unrecognizable payload** (not
    an object carrying both `profiles` and `recentItems` arrays — the exact
    shape the plugin writes) MUST NOT — post-migration the legacy fields are
    blank, so that fallback would load an empty list and the next save would
    silently overwrite the recoverable file. In both cases the plugin keeps
    profiles read-only for the session (the load guard stays unset so no write
    can occur), logs the error, and surfaces a Notice telling the user to
    repair or delete the file. Entry-level damage inside the arrays still
    normalizes and counts as loaded.
  - A profile entry is valid only if its `name` is a string; `{}` or name-less
    junk entries are dropped during normalization. An empty-string name remains
    valid (the settings UI allows blanking a name and renders a `Profile N`
    fallback), so real profiles are never destroyed by normalization. The
    remaining required string fields (`templatePath`, `outputFolder`,
    `outputSubfolder`, `outputFilename`, `assetFolder`, `assetSubfolder`,
    `bibliographyStyle`) are coerced to `""` when missing or non-string —
    field-level damage must not delete the profile — and unknown/deprecated
    keys (e.g. `imageFolder`) are preserved for the asset-folder migration.
    `lastUsedAt` is kept only when numeric.
  - If the file is missing and legacy profiles exist in `data.json`, the plugin
    migrates them non-destructively: write the new file first, then persist
    settings (which blanks the legacy fields). The migration is best-effort —
    an I/O failure is logged and retried on the next load; it never aborts
    plugin onload.
  - `data.json` persists `zoteroProfiles: []` and `recentZoteroItems: []` —
    the vault file is the single durable store — but **only after the store
    has loaded/migrated** (the load guard is set). Before that point the
    legacy values pass through persistence unchanged: `loadSettings()` may
    persist its own migrations before `loadZoteroProfiles()` runs, and
    blanking then would destroy the only copy of the legacy profiles if the
    subsequent store write failed.
  - Writes go through `saveZoteroProfiles()` (invoked from `saveSettings()`),
    guarded so a write can never happen before the initial load (which would
    wipe the synced file with empty in-memory state).
  - For an existing canonical file, a serialized write parses, validates,
    merges, and serializes the exact current text supplied to the synchronous
    `DataAdapter.process()` callback. Local same-name profiles win while
    peer-only profiles, recent keys, and timestamped deletion tombstones
    survive. The merge boundary normalizes both operands, so a partially
    damaged runtime payload with missing `profiles` or `recentItems` treats
    that property as an empty array instead of throwing. The plugin installs
    in-memory state only from the committed string returned by `process()`.
    Typed structural corruption blocks writes without changing canonical
    bytes; a generic process failure rejects that save but does not permanently
    misclassify otherwise valid data as corrupt.
  - Initial creation when the canonical file is genuinely missing may use a
    sibling temporary file and rename, with cleanup after partial temp-write or
    rename failure. The portable adapter exposes no create-if-absent/CAS
    contract, so simultaneous first creation is not claimed as conflict-free.
    `ZoteroImportProfile` contains only vault-relative paths, so the file is
    portable across Linux/macOS.
- Zotero-managed PDFs registered from the sidechat/purple-pin flow use
  Reference Mode. A failed backend import/register payload must surface as an
  error state and show a user-visible failure notice instead of silently
  returning to the previous chip state. Successful registration should return a
  queued or ready source state, and the generated `04_Resources` reference stub
  should identify the attachment with portable Zotero metadata rather than a
  device-local PDF path. When the plugin supplies both its resolved local path
  and `zoteroAttachmentKey`, the backend must retain the key as the portable
  source identity and must not require the path in generic
  `external.path_roots`.
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
- Curator DAG pages live under the hidden `.curator/Collections/` folder, which
  Obsidian's `metadataCache` never indexes, so curator-layer wikilinks
  (`[[<layer>/<ID>]]` for `01_Contexts/CTX-`, `02_Atoms/ATM-`, `03_Concepts/CON-`,
  `04_Synthesis/SYN-`) are not natively resolvable. The plugin MUST register a
  single markdown post-processor that rewrites these rendered links — accepting an
  optional `.curator/Collections/` prefix and an optional `.md` suffix, and
  preserving any `#` subpath — into clickable links that call
  `workspace.openLinkText(".curator/Collections/<layer>/<ID>.md", "", false)`. The
  rewrite MUST apply on every surface that renders curator markdown (chat sidebar
  answer, quick-query popover answer, and the reading view of an opened DAG page),
  MUST mark a link whose target file does not exist with an `is-missing` class
  instead of opening a nonexistent page, and MUST NOT alter non-curator internal
  links, external links, real-vault embeds, or `[[PHASE:…]]` edit-loop markers.
  The rewrite is navigation-only: it does not register these hidden nodes in the
  native Graph view or Backlinks pane.
- Chat-sidebar assistant answer links that encode an explicit vault block target
  (`<note>#^<block_id>`) or render as a source locator label
  (`<note> > ^<block_id>`) MUST open through
  `workspace.openLinkText("<note>#^<block_id>", "", false)`. The parser MUST be
  conservative: ordinary local links without a block anchor and external URLs
  keep their normal behavior.
- All sidechat providers MUST receive the same grounded vault-link instruction
  from the shared base system prompt. The provider should emit
  `[[vault/relative/path|label]]` only when an exact existing target path is
  present in included open/pinned context, a usable ContextService locator, or a
  provider tool result. Markdown targets omit `.md`; non-Markdown suffixes are
  preserved; known `#heading` and `#^block_id` subpaths are retained, with an
  explicit block id taking precedence over a heading. The prompt MUST prohibit
  invented paths and use plain text when the target is uncertain.
- Prompt-included `ContextRef` values MUST retain their `filePath` identity when
  present. A safe vault-relative Markdown/PDF ref exposes that identity as one
  completed `vault_link_target` literal (including a known PDF page), without a
  competing raw `.md` path, so weaker providers copy rather than reconstruct
  it; absolute, external, or unsupported file paths retain a plain file-path
  label only. ContextService
  provider formatting MUST expose a `vault_link_target` only for vault-backed
  locators with a non-empty relative path and a usable `exact` or
  `fallback_file` status. The declared source kind and file suffix MUST agree
  (`vault_pdf` with `.pdf`; Markdown kinds with `.md`). External, stale,
  unavailable, duplicate-anchor, source-fallback, mismatched, or otherwise
  ambiguous locators MUST NOT become vault-link targets.
- Ordinary visible-vault wikilinks in assistant Markdown remain owned by
  Obsidian's native renderer and navigation. The plugin MUST NOT scan the full
  vault for prompt candidates or regex-rewrite arbitrary answer prose after
  generation. Hidden Curator links, PDF page/section links, and explicit block
  locators retain their existing scoped handlers.

### 2.1.1 Zotero Import Profiles

Saved Zotero import profiles define the note template, output folder,
subfolder, filename, asset folder, and bibliography style used by the import
wizard. Each profile carries an optional `lastUsedAt` epoch-ms timestamp
(v0.23.0), stamped when the profile is used for an import or when a new profile is
created. The wizard presents profiles **most-recently-used first**: the Import
Profile dropdown is ordered by `lastUsedAt` descending (profiles never used sort
last, preserving their insertion order; ties stable), and the wizard opens with
the most-recently-used profile loaded so the user's current working profile is at
the top without manual re-selection. Sorting operates on a copy
(`sortProfilesByRecency`); the persisted `zoteroProfiles` insertion order is not
mutated by rendering.

**Profile editing must write through to the live stored profile (v0.42.1).**
Persisting profiles replaces `settings.zoteroProfiles` with objects re-read from
the merged on-disk store, so any object reference captured when the editor was
rendered is detached as soon as the first edit saves. A settings editor
therefore MUST resolve the profile it mutates at write time (by index into the
current `settings.zoteroProfiles`) rather than holding a captured reference;
writing to a stale reference silently discards every edit after the first while
still showing the typed value in the field. The profile editor exposes no Save
button, so each field MUST also commit on blur — `onChange` alone leaves the
final keystroke's write racing the store swap.

Successful Zotero note imports MUST stamp the originating profile name into note
frontmatter as `zotero_profile`. The reload command MUST prefer the matching
profile by that stamp for template rendering and annotation asset localization,
falling back to `zoteroProfiles[0]` only for older notes without a valid stamp.

The reload command MUST resolve the Zotero **item key** before re-rendering. A
`citekey` is not a Zotero item key (`get_zotero_item_metadata` queries
`items.key`), so when no item key can be parsed from `zotero_app_url` the reload
MUST NOT rewrite the note from a citekey-derived empty-metadata result: if the
backend returns empty metadata, reload MUST abort with a clear error and leave
the note unchanged.

The deprecated `imageFolder` profile field is retired from stored profiles by a
one-time load-time migration: on load, any profile still carrying `imageFolder`
is normalized to `assetFolder`/`assetSubfolder` (same mapping as
`resolveProfileAssetSpec`) and `imageFolder` is deleted, then settings are
persisted. New code MUST read `assetFolder`/`assetSubfolder`.

The Zotero item search modal must request empty-query suggestions when it opens.
Empty-query suggestions come from the backend's recent Zotero results; returned
results may then be re-ranked by `recentZoteroItems` so recently imported items
float to the top.

Output subfolders, filenames, and asset subfolders are rendered through the
plugin's Nunjucks `TemplateRenderer`. The renderer supports the same base item
metadata used by note templates plus path-oriented filters such as `pathSafe`,
`firstAuthorLast`, `authorLast`, and `joinTags`. Rendered path segments must be
sanitized before writing files into the vault.

The import writer MUST preserve exact-path update behavior. If creation fails
because a case-insensitive filesystem already contains the same vault path with
different letter case, it MUST resolve exactly one case-insensitive existing
file, read that file as the template's existing content, re-render, and modify
the existing file. This user-triggered import refreshes the selected item's
current Zotero links/keys while preserving persisted template regions. It MUST
NOT swallow non-collision creation failures or guess a match beyond the output
path.

### 2.1.2 Vision/PDF Extraction Model Rows (Dashboard, v0.22.0)

The Dashboard **LLM Provider** card exposes TWO rows for the backend vision
extraction models (SCHEMA §2.5; SYSTEM_BEHAVIOR §26.2a), mirroring the
Primary/Fallback rows and persisting through `wiki config set llm.<key>`:

- **PDF ingest model (full-page)** → `llm.vision_model`. A dropdown of
  **vision-capable** catalogue models (`supportsVision === true`) plus
  "— (disabled, use pymupdf4llm)". Status shows the model + health (installed/
  exceeds-RAM for Ollama; reachable for cloud).
- **LaTeX/region extract model (light)** → `llm.latex_extract_model`. The same
  vision-only dropdown plus "— (use PDF ingest model)". When empty, the row's
  status MUST show the EFFECTIVE resolved model (e.g. "↳ using <vision_model>") so
  the fallback is visible, never implicit.

These are backend config values, set in the Dashboard and consumed by the backend
`add source` ingest path. Both rows filter to vision-capable models so a text-only
model cannot be selected via the UI; the backend additionally validates vision at
use and raises on a configured-but-non-vision model. (The plugin's interactive
region surfaces consuming these values is a planned follow-up — see the §2.1
region-extraction rule.)

### 2.1.3 Interactive chat image channel (v0.28.0)

When a chat turn carries an image (Cmd+Shift+X crop, pasted image, or PDF-page
capture) and the active provider runs via CLI (`shouldUseCli` → antigravity,
claude, codex; Ollama/DeepSeek use the HTTP image-block path), `LLMClient` MUST:

- **Write** each image content part to `<repo>/.cache/cli/chat_images/<run-id>/`.
  If the repository path cannot be resolved, fail visibly; there is no vault
  fallback. This is the only allowed temp/cache root for plugin-created chat
  images. Reference the image in
  the CLI prompt by absolute path (e.g. "Read the image file at <path> …"),
  mirroring the backend `vision.describe_image_via_cli` pattern. The OS sandbox
  (§ v0.23.0) still wraps every invocation.
- **Enable scoped `Read` for image-bearing turns ONLY**: drop `Read` from the
  claude `--disallowedTools` denylist and add `--add-dir <chat_images dir>`;
  antigravity reads natively under `--add-dir`; codex reads under
  `--sandbox workspace-write` + `--add-dir`. DB-scoped MCP curator tools stay
  available (denylist mode — NOT `--allowedTools`, which would drop MCP). The gate
  is "any message in the assembled `LLMMessage[]` payload carries an image part": a
  **text-only turn MUST keep the hardened denylist that lists `Read`** and MUST NOT
  add the image dir.
- **Confined claude Read scope.** claude is the only provider whose `Read` is
  denied by default, so it is the only one re-enabling `Read` on an image turn.
  For that turn the claude `--add-dir` MUST be confined to JUST the `<chat_images
  dir>` — NOT the broad allowed roots (vault + Zotero) — so the re-enabled `Read`
  cannot reach arbitrary vault/Zotero files (claude has no blanket permission
  bypass, so an out-of-add-dir `Read` would prompt/deny). This preserves the
  v0.23.0 no-vault-read hardening for image turns. antigravity/codex keep their
  existing broad add-dir set (they always have native file reads; OS-sandboxed).
- **Cleanup robustness.** Cleanup (below) MUST also run if pre-spawn setup
  (`getCliCwd`/`buildCliCommand`) throws synchronously before any child spawns, since
  no `close`/`error` event fires in that case.
- **Cleanup.** Temp PNGs are removed in the outermost `finally` of the CLI/stream
  call (success, error, AND abort); the per-run subdir is removed; stale
  `chat_images/*` dirs are swept on plugin load. No temp image survives a completed
  send.

`ContextRef.pendingCropBase64` (a crop awaiting deferred handling) is resolved at
send-time by `materializeContextRefs`: a **vision-capable** main model KEEPS
`imageBase64` (so it flows through this channel) and retains `content`/`regionText`
as a caption; a **non-vision** main model calls `transcribePdfCrop` and replaces
`content` with the LaTeX (dropping `imageBase64`). The flag is cleared either way.
The materialize step runs AFTER the assistant "Thinking…" message is rendered, so
Send is never blocked by transcription/image work.

### 2.2 `SessionData`

Stored in a separate `sessions.json` file. It must never be merged into
`data.json`.

The implementation must tolerate `sessions.json` being synchronized between
devices. For an existing file, it parses and merges the exact current text
supplied inside Obsidian's atomic `DataAdapter.process()` callback. Sessions are
merged by `ChatSession.id`, keeping the copy with the newest `updatedAt`
timestamp. This prevents a Linux save from deleting a distinct macOS session,
or vice versa, when a sync peer updates the canonical file near the commit.
All read/merge/write operations are serialized in one process so overlapping
save requests cannot commit from the same stale disk snapshot. Backend
`wiki reset` must not delete this shared durable file.

Canonical session reads MUST distinguish `missing`, `valid`, `corrupt`, and
`unreadable`. Only `missing` may enter legacy/default migration. `corrupt` or
`unreadable` state MUST preserve the existing file, surface a recovery notice,
and block ordinary writes for that plugin run; the same fail-closed rule applies
if invalid state appears between load and save. Existing valid writes MUST use
the synchronous atomic process callback for strict parse, merge, sanitization,
and serialization, then install only the returned committed text. A generic
process failure rejects the current save without reclassifying valid bytes as
corrupt. Initial creation may use a sibling temporary file plus rename; a failed
temp write or rename MUST leave any previous target intact and remove the
temporary file. The adapter has no portable simultaneous create-if-absent/CAS
guarantee, so that first-create limitation is explicit.

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
- Every `sessions.json` write, including first-write and legacy-migration
  paths where no previous file can be merged, must pass through the sync
  sanitizer. Device absolute paths in `ContextRef.filePath` and runtime-local
  `backendStatus` fields must not be persisted as durable session identity.

Zotero profile storage follows the same typed-read, fail-closed, serialized,
commit-time atomic process rule for an existing file. Profile deletion records
a timestamped tombstone keyed by profile name; a peer-only stale profile cannot
be unioned back after deletion.

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

The persisted current-schema field remains required. Runtime command
preparation nevertheless normalizes malformed or legacy missing/null `args` to
`[]` so a damaged setting cannot crash plugin startup before validation or UI
repair.

For HTTP-provider tool injection, model-facing MCP function identifiers are a
sanitized transport detail. Each exposure pass must build an explicit,
collision-free map from the exposed identifier to the original `(serverName,
toolName)` pair; dispatch must never reconstruct original names by splitting or
unsanitizing model text. If two original pairs sanitize to the same identifier,
both remain callable under deterministic unique exposed names.

MCP process shutdown rejects and removes every pending JSON-RPC request before
clearing runtime state. It then waits for graceful exit, sends `SIGTERM` after a
bounded grace period, escalates to `SIGKILL` if necessary, and waits for a final
bounded completion. Late exit events from an old process generation must not
clear a restarted server's process or ready state. Request timeout handles are
cleared on response, exit, and shutdown so each Promise settles exactly once.
Each generation starts with an empty newline-delimited JSON buffer, and stdout
from a child that is no longer current must be ignored.

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
  contextWindow?: number;
  efforts?: string[];
  defaultEffort?: string;
}
```

The plugin UI uses `efforts` as the sole reasoning-control authority. An absent
or empty array hides the effort control and causes command construction to omit
the provider effort argument. On an explicit model change the effort resets to
`defaultEffort` (or the first declared effort); load-time migration preserves a
still-valid stored effort and otherwise normalizes it. There is no parallel
`supportsThinking` flag or fictional "tier" transmitted from the backend.

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
- `"l2_ready"` corresponds to `l2_status='done'` with at least one authoritative
  verified serving unit while L3 is incomplete.
- `"l3_ready"` corresponds to `l3_status='done'` while L4 is incomplete or
  `l4_status='skipped'` because no eligible shared synthesis exists.
- `"l4_ready"` corresponds to `l4_status='done'`.
- `"error"` wins over all ready states when any active layer reports `error`.
- `"running"` must expose `runningLayer` ("l1"|"l2"|"l3"|"l4") to show progress.
- `"untracked"` must trigger the "Add to Incurator" action prompt, not silent import.
- Dashboard layer badges must render `l4_status='skipped'` explicitly as
  `Skipped`, not as an empty/unknown status.
- Dashboard Knowledge Graph counts are DB-serving counts: L1 done sources,
  serving L2 units, live L3 community reports, and current L4 synthesis nodes.
  The plugin must not count disposable Collection Markdown files.
- `l3_ready` requires a live report grounded in that source. An exception-free
  global pass with no eligible report is `skipped`, not `l3_ready`.

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
  synthesis_node_ids?: string[];
  community_report_ids?: string[];
  memory_path_ids?: string[];
  insight_candidate_ids?: string[];
  prompt_trace_ids?: string[];
  source_span_ids?: string[];
  trace_id?: string;             // QTR-<UUID8>
  route?: "local" | "global" | "explore" | "source-section";
  pack_id?: string | null;       // PACK-<UUID8> for ContextService-backed routes
  snapshot?: Record<string, unknown> | null;
  budget?: Record<string, unknown> | null;
  latency_ms: number;
  l3_complete: boolean;          // whether full concept graph was available
}
```

Rules:

- For ordinary workspace/domain questions without a primary selected context on
  the latest user turn, the Obsidian sidechat must call
  `wiki plugin context fetch` by default and inject the formatted evidence pack
  into provider context. It must not inject the backend synthesized answer by
  default.
- For L3-complete ContextService-backed answers, `wiki plugin query` MUST return
  the same `pack_id`, `snapshot`, `budget`, prompt trace ids, and provenance
  arrays at the additive result level and inside `trace`. L3-incomplete degraded
  fallback may omit these fields until it is migrated to ContextService.
- Expected provider failures return `ok=false` and the existing `error` field
  while preserving the available QTR/PTR ids, warnings, ContextService metadata,
  and retrieval provenance at the additive result level and inside `trace`.
  The hidden command must print this one parseable JSON object and exit 1; it
  must not emit a traceback or report exit 0. Unexpected runtime/storage defects
  remain exceptions rather than being relabelled as provider failures.
- `wiki plugin query` remains the explicit backend-synthesis JSON surface. It is
  not the default sidechat grounding path once `wiki plugin context fetch` is
  available.
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
- The Incurator PDF viewer must keep scroll work lightweight: lazy page rendering
  and current-page detection are coalesced through `requestAnimationFrame` so a
  burst of raw scroll events schedules at most one page calculation/render trigger
  per frame. Pending scroll frames are cancelled when the view closes.
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
- A PDF snip (`Cmd+Shift+X`) must capture the text **scoped to the cropped
  rectangle** — the text-layer lines whose boxes fall inside the snip — and use
  that region text as the crop's primary-focus content. It must not inject the
  whole page text (or its RAG hits) into the primary focus, and it must not
  discard the region text entirely. The crop image is first transcribed through
  the backend-resolved PDF extraction model; when that succeeds, the transcription
  replaces the text-layer region text and the crop image is not forwarded to the
  main chat model. When extraction fails and the cropped region has no selectable
  text (e.g. a scanned page), the crop falls back to an image-only reference that
  is still marked as primary focus.
- Selected-context sidechat turns should include current page/document structure
  as supplementary grounding when available: Markdown headings as a compact
  outline and PDF outline/window context for PDF tabs. These outline/page blocks
  must not replace the selected text, line range, or crop as the primary answer
  target.
- If selected PDF text/crop or the latest PDF-focused user request is itself a
  cross-reference pointer (for example `Section A4.2`, `p580`, `Figure 19.1`,
  `Eq. (19.6)`, `수식 (10)`, or a bare dotted equation label such as `(19.11)`),
  the plugin may add a `<resolved_cross_references>` block ahead of generic page
  background. Each reference entry should identify the label, resolved target
  page when known, section title when known, confidence, and the fetched target
  text/snippet. Pointer resolution first uses local PDF outline/window/index/search
  evidence. For an exact equation label in the latest request that is missing
  from the loaded window, the plugin may fetch a small ordered adjacent-page set
  through read-only backend PDF context (`page_num=<candidate>`, `radius=0`), next
  page first, and must stop at the first exact label match. If that bounded scan
  exhausts without an exact label, any loose same-number search hit must remain
  unresolved and must not be serialized into `<resolved_cross_references>`.
  Latest-request resolution runs only for the active PDF or an explicit primary
  PDF context ref with the same canonical document identity; visible,
  pinned-background, and merely prompt-included PDF tabs do not qualify. This
  fetch requires a resolvable current-device source identity, never registers
  the PDF, and never broadens a provider's native filesystem roots or tool
  permissions. Pointer resolution failures must not silently turn the current
  page into the answer target; the prompt must tell the provider when the
  referenced target could not be located.
- Theorem-family pointers (`Theorem`, `Lemma`, `Corollary`, `Proposition`,
  `Definition`, `Result`, `Claim`, `Conjecture`) accept letter-prefixed
  appendix numbering (e.g. `Result A4.1`), and their line-anchored definition
  sites (a line beginning `Result A4.1. …`) participate in the caption/
  definition index exactly like figure and equation captions. Outline titles
  of the form `Appendix 4 …` additionally answer to the aliased number `A4`
  so appendix-numbered anchors can locate their owning outline range; the
  alias is additive and never shadows the plain chapter entry in document
  order.
- Explicit printed-page locators (`p581`, `p. 581`, `page 581`) resolve to a
  physical PDF page through an ordered evidence chain: (1) PDF `pageLabels`
  when present; (2) a front-matter offset inferred from printed header/footer
  numbers visible in already-known page texts — the modal `physical − printed`
  delta is accepted only with at least two supporting pages and a strict
  majority of candidate-bearing pages, ties failing closed; (3) a direct scan
  of known page texts for a page whose extracted printed header equals the
  requested number; (4) an identity guess (physical = printed) that is kept
  only while unverified — the moment the identity page's own extracted header
  names a different printed number, the locator flips to unresolved instead.
  A contradicted identity page must never be serialized into
  `<resolved_cross_references>` (fail closed: no context is always preferred
  to wrong-page context). During async resolution the plugin may run a small
  bounded number of fetch rounds (≤3): a contradicted identity page yields a
  header-derived repair candidate (`printed + observed delta`) that the next
  round fetches and accepts only through the printed-header scan, and headers
  on fetched pages feed back into offset inference so resolution converges.
- Attached PDF/image snips must be sent to vision-capable models as image parts.
  For non-vision models, the prompt must explicitly state that image details are
  unavailable instead of silently dropping the crop. A primary-focus reference
  that carries an image but no text (an image-only crop or dragged image) must
  still emit a `<primary_focus_selection>` anchor naming the attached image as
  the core subject, so the image is never buried under background page context.
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
- **Localized-question edit-affordance suppression (v0.23.0).** A `Cmd+Shift+L`
  line-range (and any other primary-focus selection) is BOTH a primary-context
  ref and an editable ref, which previously injected the `<editable_selection>`
  affordance and the `<edit_review_loop>` contract into the very same payload that
  the recency anchor told to "answer only, do not modify the document" — a direct
  contradiction that let long, edit-heavy sessions drift back to whole-file edits.
  The contract is now: when the latest turn carries a primary-focus selection AND
  is NOT itself a Markdown edit request (`shouldSuppressEditAffordances`), the
  plugin MUST omit both the `<editable_selection>` block and the
  `<edit_review_loop>` contract so the recency anchor is unopposed. The suppression
  is UNCONDITIONAL with respect to prior turns — it does not consult
  `priorAnswerOpenedEditLoop`, because the reported failure case is exactly a fresh
  localized question following an earlier whole-document edit. Genuine edit turns
  are unaffected: any edit-phrased request flips the latest turn back to an edit
  request and restores both affordances.
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
- **Accept-All cursor (v0.14.1)**: after `Accept All`, the cursor is restored to
  the FIRST changed hunk's line (cached when the diff opened), not the end of the
  rewritten region. A whole-file review must not teleport the caret to the bottom
  of the document.
- **Toolbar anchoring (v0.14.1)**: before computing the floating toolbar
  position, the DiffViewer scrolls the first hunk into view and recomputes
  `coordsAtPos` on the next frame, so the Accept/Reject bar anchors near the hunk
  even when it opened off-screen. The screen-top fallback is only used when
  coordinates remain unavailable after the scroll.
- **Review serialization (v0.14.1)**: opening a diff for an edit proposal is
  serialized behind a single in-flight guard. Because the `DiffViewer` is a
  singleton, a second review click cannot re-point it mid-open; concurrent
  review requests are ignored until the current open settles.
- **Derived proposal status (v0.14.1)**: each edit-proposal pill shows a status
  derived at render time from the LIVE file content via the shared
  `findSearchBlock` matcher — never from persisted state:
  - `reviewable` — the SEARCH block still matches the file (or it is a new-file
    proposal); the pill opens the Diff Viewer.
  - `applied` — the SEARCH no longer matches and either the REPLACE block has one
    unambiguous match in the file, or the proposal is a deletion with an empty /
    whitespace-only REPLACE block; the pill is shown as already applied (clicking
    will not re-run a doomed match).
  - `not_found` — neither matches; the pill reports it honestly instead of
    surfacing a confusing "could not find" only after a click.
  This is self-healing across re-render, session reload, and the
  propose→accept→next-turn cycle (no `ChatMessage` schema field is added).
- **Path resolution fallback (v0.14.1)**: `resolveVaultFile` adds a final
  case-insensitive, whitespace-trimmed full-path scan over the vault's Markdown
  files before reporting a file as not found. It does not fall back to basename
  matching, because a same-named note in another folder is a different target.

### 6.1 Edit-Loop State Machine Contract (v0.14.0, demoted to a hint in v0.24.0)

The four-phase loop is an **observable quality hint, not a hard gate** (v0.27.0).
A valid, matchable `ai-agent-edit` proposal is ALWAYS reviewable regardless of
whether the model emitted the `[[PHASE:…]]` markers. The earlier hard gate
suppressed the diff entirely when the markers were missing or mis-ordered, which
made the feature unusable on token-limited and low-instruction-following models
(they would describe an edit, emit a valid SEARCH/REPLACE block, but get no
diff). The contract below still shapes a *conforming* answer's presentation; a
non-conforming answer now renders the diff pills plus a soft, non-blocking hint.

- **Canonical phase markers.** When the agent proposes any `ai-agent-edit`
  block, the response MUST contain the four phases, in order, each introduced by
  a stable sentinel token on its own line:
  - `[[PHASE:ANALYSED]]` — what the agent understood and the concrete gap to close.
  - `[[PHASE:REVIEWED]]` — critique of its own plan *before* editing.
  - `[[PHASE:UPDATED]]` — the `ai-agent-edit` SEARCH/REPLACE block(s).
  - `[[PHASE:REVIEWED]]` — self-check that the edit closes the gap, and a clear
    statement that the edits are **proposed and pending the user's review/Accept
    in the Diff Viewer** (v0.14.1). The agent MUST NOT claim the edits are already
    applied or saved — nothing is written to disk until the user accepts.
  Markers are English and machine-parseable; phase *body* text follows the user's
  language. The sentinel form (`[[PHASE:LABEL]]`) is chosen so it cannot collide
  with note content or model headings and survives the existing thought-block and
  `ai-agent-edit` stripping passes. The first `REVIEWED` precedes `UPDATED`; the
  second follows it.
- **Prompt contract (`getEditLoopContract()`).** A single composable system-prompt
  block instructs the agent to emit the markers. It is anchored as the LAST system
  block (strongest attention) and is appended whenever a turn is likely to produce
  a mutation: the latest message is a Markdown edit request, OR an editable
  line-range selection exists, OR an open Markdown edit target exists, OR the
  prior assistant turn already opened an edit loop (multi-turn edit continuation).
  **Override (v0.23.0):** none of these conditions apply when the latest turn is a
  localized question (a primary-focus selection present and the turn is not a
  Markdown edit request). In that case `shouldSuppressEditAffordances` is true and
  the contract block is NOT appended, regardless of `priorAnswerOpenedEditLoop`.
- **Runtime validator (`context/editLoopContract.ts`).** `validateEditLoop(content)`
  returns `{ ok, missing, hasEdits }`. The contract is required ONLY when
  `hasEdits` is true (the content contains at least one `ai-agent-edit` block). A
  response containing edit blocks but missing or mis-ordering the four phases is
  `ok: false`. A pure Q&A response with no edit blocks is never gated.
- **Soft hint (v0.24.0, replaces the old hard gate).** When `validateEditLoop`
  returns `ok: false` for an edit-bearing response, the diff is STILL reviewable:
  `maybeAutoOpenDiff` proceeds under its normal safe-focus gate, and the render
  path shows the edit pills plus a non-blocking note
  (`.ai-agent-edit-loop-hint`) with an optional **Re-run with review** button.
  There is no longer a blocked banner, no "Override & review anyway" escape
  hatch, and no `editLoopBlocked`/`editLoopOverridden` message state — a valid
  edit is never a dead end on any model.
- **Observable UI.** A conforming response (markers present AND valid) renders each
  phase as a distinct, labeled, collapsible section
  (`.ai-agent-edit-phase[data-phase]`), reusing the thought-block styling
  vocabulary; the inline diff/review pill is anchored inside the `UPDATED`
  section. The contract does not expose private chain-of-thought — the phases are
  deliberate, user-facing work products.

### 6.2 Output-Token Truncation Recovery (v0.27.0)

Token-limited providers (Gemini's `MAX_TOKENS`, OpenAI/Ollama `length`, Claude
`max_tokens`) frequently cut an answer off mid-stream — often inside an
`ai-agent-edit` block, leaving a broken proposal and no diff.

- **Normalized signal.** `StreamChunk` carries `finishReason`
  (`stop | length | tool_calls | content_filter | error`) and a derived
  `truncated` boolean. Each provider adapter's `extractDelta` maps its native
  field: Antigravity `finishReason==="MAX_TOKENS"`, OpenAI/DeepSeek/Ollama
  `finish_reason==="length"`, Claude `message_delta.stop_reason==="max_tokens"`.
  `SAFETY`/`RECITATION`/`content_filter` terminate the stream but are NOT
  treated as truncation (continuing cannot help).
- **Auto-continue.** On a truncated finish the chat layer issues up to **3**
  continuation requests (`buildContinuationPrompt`), each appending the partial
  as an assistant turn + a "resume exactly where you stopped" user turn. When the
  cut happened inside an edit block, the prompt tells the model to finish the
  SEARCH/REPLACE body and close the fence rather than re-open a new block. The
  loop stops on a clean finish, the cap, or a zero-delta round (stuck model).
- **Fence-safe stitch.** Continuations are spliced with longest-overlap
  suffix/prefix de-duplication (minimum overlap `MIN_STITCH_OVERLAP` so a lone
  backtick/newline is never trusted) and a repair pass that collapses a doubled
  ` ```ai-agent-edit ` marker created at the seam.
- **No premature finalization.** A `done && truncated` chunk does NOT flip the
  message out of `isStreaming`; the edit pills and `maybeAutoOpenDiff` fire only
  after truncation is fully resolved (or the cap is hit), never on an in-flight
  partial. If still truncated after the cap, the message persists `truncated`
  and renders a manual **Continue** affordance (`.ai-agent-truncation-continue`);
  reloading an old session never re-triggers auto-continue.

### 6.3 Diff Viewer Robustness (v0.27.0)

- **Focus-gated shortcuts.** The Diff Viewer's keyboard shortcuts
  (Enter=Accept-All, Y/N, Tab/Esc) fire ONLY when focus is inside the diff's own
  CodeMirror editor or its floating toolbar (`shouldHandleDiffShortcut`). The
  previous document-global handler applied edits when the user pressed Enter in
  the chat input while a diff was open. `DiffViewer.show` calls `cmView.focus()`
  on open so a pill-click review (focus in the sidebar) still gets working
  shortcuts.
- **Typed open result.** `DiffViewer.show` returns `{ opened, reason }`
  (`no_changes | editor_not_ready`); callers surface the exact reason as a Notice
  instead of returning silently.
- **Order-independent multi-edit.** Multiple proposals for one file are matched
  against the ORIGINAL text (not the running result) and composed as
  non-overlapping splices, so applying one edit can no longer break another's
  SEARCH. Skipped proposals are reported as either "not found" or "overlapping",
  and a same-target re-entrant Review request coalesces silently instead of
  raising "a diff review is already opening".

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
- The vault-local backend runner applies a command-class resource policy. Normal
  metadata/search/config commands have a 2-minute timeout and 16 MiB combined
  stdout/stderr limit. Long pipeline/import/model/job commands have a 60-minute
  timeout and 64 MiB combined limit. Exceeding either bound fails visibly,
  terminates the subprocess, escalates to a forced kill after a bounded grace
  period, and settles the caller exactly once. Long commands must not inherit
  the normal-command bounds.

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
chat crop context must not leave durable images under `05_Assets`. Any temporary
crop file used for backend transcription must live under
`<repo>/.cache/vaults/<vault-key>/pdf_crops/` and be removed in a `finally` block.

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
  pack_id?: string | null;        // PACK-<UUID8> for ContextService-backed routes
  snapshot?: Record<string, unknown> | null;
  budget?: Record<string, unknown> | null;
  prompt_trace_ids?: string[];    // PTR-<UUID8>
  source_span_ids?: string[];     // SPAN-<UUID8>
  community_report_ids?: string[];// REP-<UUID8>
  memory_path_ids?: string[];     // MPATH-<UUID8>
  insight_candidate_ids?: string[];// INS-<UUID8>
  warnings?: string[];
}
```

On `ok=false` provider results, these additive fields remain populated whenever
the ContextService/QTR already selected them. MCP compaction and plugin
normalization must not discard top-level `prompt_trace_ids`, `warnings`, or the
failure reason. Sources & Trace renders the concise `error` alongside the
retained trace instead of treating the request as an empty successful answer.

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
- a **Save to 02_Wiki** action, when the caller provides an `onPromote` callback,
  bound to the answer's own trace and `source_span_ids`.

Rules:

- The panel must degrade gracefully: missing curation-native fields render nothing rather
  than erroring, so an older/partial backend response still shows the v0.2.2 trace.
- Insight-candidate promotion and any backprop action are explicit user actions;
  the panel must not auto-promote or auto-patch.
- Promoting a historical answer must use that answer's embedded trace. If the
  trace has no explicit question, the chat sidebar falls back to the user message
  immediately preceding that answer rather than the newest user message globally.
- Historical trace panels may keep locator navigation and Save to 02_Wiki
  promotion available, but mutating context-pack controls (expand, verify,
  refetch, feedback) must render only for the latest active answer so old panels
  cannot mutate the live query state.
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
- Runtime snapshots can contain machine-local absolute paths because they live
  only in the current device's repo cache.
- Dashboard must not edit repo-cache `state.sqlite`, `.curator/Collections/`,
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
  (default hotkey `Cmd+Shift+K`) while text is selected — opens one persistent
  popover containing only a free-text query input and a submit control. No
  preset/quick-action buttons are present.
- Multiple quick-query popovers may coexist. Opening a new quick query for a new
  selection must not remove existing popovers; each popover owns its own
  selected passage, answer, title/minimized state, drag position, and follow-up
  memory.
- Once spawned, the popover is detached from selection scroll tracking. It is
  positioned once near the selection, then remains fixed relative to its owner
  window unless the user drags the header.
- The header title updates to the latest submitted question. A minimize control
  collapses the body while preserving the answer, input, and follow-up state.
- Selections made inside the plugin's own button/popover must not re-trigger the
  surface.

### 13.2 Context And Follow-ups

- The selected passage is always supplied as the current turn's
  `<primary_focus_selection>`.
- The plugin should refresh active Obsidian context before each quick-query
  request and may include the active Markdown/PDF page, nearby PDF window pages,
  and available Markdown/PDF outline as background context. Background context
  must be marked as supplementary and must not override the selected passage.
- If the selected PDF passage is a pointer with an explicit page locator (for
  example `Section 11.1.2, p281`) or a bare numbered object (for example
  `(3.5)`) and the Incurator PDF viewer is open, quick query may fetch distant
  candidate pages on demand even when they are outside the nearby page window.
  The fetch path must match sidechat: try backend PDF context first using the
  richest available portable identity (`source_id`, file hash, vault relpath, or
  Zotero attachment key; a local absolute path is only a per-device call hint),
  then fall back to the open PDF.js viewer. To keep the popover responsive, the
  resolver must use exact ToC section matches before wider chapter fallbacks,
  fetch outline candidates in small batches, and stop as soon as the referenced
  target is found. The fetched target text is supplied in
  `<resolved_cross_references>` and must remain higher priority than generic
  current-page background.
- Follow-up questions asked in the same popover may include a short in-memory
  trace of prior quick-query turns from that popover only. Coexisting popovers
  must not share this trace. These turns are ephemeral and are not the
  chat-sidebar session history.
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

- The popover is a temporary session-local surface. Closing it (close button or
  `Escape`) discards that popover's exchange. Outside clicks must not close an
  open popover; they may only dismiss the floating trigger button. It must never
  be written into `SessionData` or the chat sidebar history and must not persist
  across Obsidian restarts.
- The query is issued through the standard `LLMClient` using the active
  provider/model. No prior chat-sidebar turns are appended.
- An in-flight quick query is aborted when its popover is dismissed.

### 13.5 Tool Isolation & Shared Prompt Registry (v0.19.0)

The popover is a read-only reading assistant. It MUST NOT be able to run scripts,
create files, or traverse the filesystem.

- **Tool policy on the wire.** `LLMClient.streamChat(messages, onChunk, opts?)`
  accepts an optional `{ toolPolicy }`. The default is `"auto"`
  (the chat sidebar's behavior, unchanged). The single decision helper
  `shouldInjectMcpTools(toolPolicy, hasMcpManager, useCli)` governs MCP
  injection: it returns `false` whenever the policy is not `"auto"`, when the
  provider routes through a CLI, or when no MCP manager is present. When MCP
  injection is refused the request body carries **no** MCP entries and
  `mcpManager.getAllTools()` is never invoked on that path. The
  non-streaming `complete()` path already injects no tools.
  **v0.41.0 amendment**: the policy union is now
  `"auto" | "none" | "local-only"`, and the popover moved from `"none"` to
  `"local-only"`. `shouldInjectMcpTools` returns `false` for both `"none"` and
  `"local-only"`, so the popover's zero-MCP guarantee is unchanged; the new
  value additionally admits the plugin-executed local PDF reader defined in
  §13.7. Every consumer of `ToolPolicy` MUST handle the union exhaustively
  (a `never`-typed default), so adding a future value is a compile error
  rather than a silent grant.
- **Shared prompt registry (`src/context/promptRegistry.ts`).** Security-critical
  prompt blocks are defined once and consumed by both surfaces so they cannot
  drift:
  - `SurfaceProfile` = `{ surface: "sidechat" | "popover", toolPolicy, allowEdits }`,
    with exported `SIDECHAT_PROFILE` (`auto` / edits-on) and `POPOVER_PROFILE`
    (`local-only` since v0.41.0, previously `none` / edits-off).
  - `boundaryConstraints(profile)` — the canonical filesystem/tool boundary text.
    For `toolPolicy: "none"` it declares zero tools and zero filesystem access;
    for `"local-only"` it declares zero MCP tools, zero filesystem access, and
    the single read-only PDF page reader of §13.7; for `"auto"` it limits access
    to the allowed roots (vault, configured Zotero folder, Zotero library). The
    popover's system prompt sources its boundary line
    from this function — it MUST NOT re-declare a hardcoded duplicate.
    This text is **documentation of** the boundary, not the enforcement of it:
    per §13.7 the enforcement is behavioral and independently tested.
  - `buildRecencyAnchor(profile, { hasPrimarySelection })` — a `<critical_invariants>`
    block appended LAST in the payload (recency-effect position) that re-asserts:
    answer only about `<primary_focus_selection>` (deferring to the existing
    pointer / `<resolved_cross_references>` rule), the read-only edit ban for
    surfaces with `allowEdits: false`, and the surface boundary. The chat sidebar
    appends this to the latest user turn (which always survives the
    `CONTINUITY_MESSAGE_LIMIT` history slice); the popover appends it after the
    question. This fixes long-session attention decay where a localized
    `Cmd+Shift+L` selection was overridden by earlier whole-document tasks.

### 13.6 CLI Tool-Scope Sandbox (v0.23.0)

§13.5 closed the HTTP/MCP-injection path, but **CLI providers were uncontrolled**:
`toolPolicy` never reached `buildCliCommand`, so a CLI-backed popover/sidechat
inherited the CLI agent's NATIVE tools (agy ran `--dangerously-skip-permissions`,
the `find_mvg_text.py`-style exploit). This section governs the CLI path.

- **`toolPolicy` threads into the CLI builder.** `streamChat`/`complete` pass
  `toolPolicy` through `streamChatViaCli`/`completeViaCli` into `buildCliCommand`.
  The popover's CLI calls run with `toolPolicy: "none"`.
- **Per-provider tool control (verified flags; NEVER a blanket permission-skip):**
  - **agy** — its own `--sandbox` is INEFFECTIVE (it still creates files) and it
    has no tool-disable flag. `--dangerously-skip-permissions` + `*_TRUST_WORKSPACE`
    are REMOVED. Containment is the OS sandbox (below); agy is REFUSED if it cannot
    be OS-sandboxed. Antigravity CLI 1.1.3+ soft-denies a tool that would require
    an interactive confirmation during `-p`/headless execution. Before launching
    agy, the plugin MUST atomically merge the single read-only rule
    `$read_file$()` into `permissions.allow` in the CLI-owned
    `~/.gemini/antigravity-cli/settings.json`. It MUST preserve unknown top-level
    keys, unknown `permissions` keys, and existing allow entries, and MUST refuse
    to overwrite malformed JSON or a non-array `permissions.allow`. This approval
    does not grant a path: non-ephemeral path visibility remains the separate
    `--add-dir` set, while the popover still receives no added workspace dirs.
    The plugin MUST NOT install `--dangerously-skip-permissions` or approve write,
    shell, network, or wildcard tools.
    The active-bundle gate above applies before this boundary: an installed
    permission hotfix does not count as active until the running bundle identity
    matches the installed bundle. Once active, the invocation-time atomic merge
    remains the compatibility boundary for Antigravity releases that require the
    explicit headless read approval.
    Antigravity CLI 1.1.5+ also requires `--effort <level>` when a base model
    slug with declared effort levels is passed through `--model`; every plugin
    chat invocation passes the selected non-empty model through `--model`,
    forwards the normalized `agentEffort`, and omits `--effort` only for
    catalogue models without an effort dimension.
  - **claude** — controlled by its tool surface (no deny-without-prompt dir sandbox):
    popover `--tools ""` (no tools); sidechat `--disallowedTools Bash Read Write Edit
    WebFetch` (only the DB-scoped MCP curator tools remain; the plugin's
    `ai-agent-edit` loop performs vault edits, so native fs tools are unnecessary).
    Image-bearing turns are the one exception (§2.1.3): `Read` is re-enabled but
    `--add-dir` is confined to the per-run `chat_images` dir, so the read grant
    cannot reach the broad allowed roots.
  - **codex** — `--sandbox read-only` (popover) / `workspace-write` + `--add-dir
    <root>` per allowed root (sidechat).
- **OS-level sandbox (`src/agent/sandboxWrapper.ts`)** wraps EVERY CLI subprocess,
  generated from the allowed roots — REQUIRED for agy (its flags don't contain it),
  defense-in-depth for the rest:
  - macOS: `sandbox-exec -p <profile>` (Seatbelt) — the profile is passed INLINE on
    the command line (no temp file → no multi-vault / concurrent-call collision). It
    denies `file-write*` everywhere, then re-allows write ONLY to: the **vault**, the
    plugin's own CLI dir (`<repo>/.cache/cli/`, see below), the CLIs' OWN narrow state
    dirs (`~/.gemini`, `~/.antigravity`, `~/.claude`, `~/.codex`), and the user's
    SPECIFIC `$TMPDIR`. The **Zotero library is NOT writable** — it is an external
    read-only reference, so granting write would let a prompt-injected agent corrupt
    or delete the user's research data; it stays readable (reads are allowed) but
    never writable. The profile does NOT grant the broad `~/.config`, `~/.cache`,
    `~/Library/Caches`, or the `/private/var/folders`/`/private/tmp` roots — those
    would let the agent drop a `~/.config/autostart` script or overwrite another
    app's config. Validated to block nested-child writes + the `~/.config/autostart`
    persistence attack. Reads are allowed (security-critical harm is creation/writes;
    read-restriction breaks the CLI).
  - Linux: `bwrap` — `--ro-bind / /` + `--tmpfs /tmp` + `--bind-try <write-root>` per
    writable root (vault + CLI dirs; NOT Zotero). `/tmp` is NEVER re-bound over the
    tmpfs (that would expose the host `/tmp` read-write). If `bwrap` is absent, **agy
    is REFUSED** with a one-line install hint (`apt/dnf install bubblewrap`); Claude
    and Codex are NOT refused — see the degradation rule below. Windows: out of scope.
  - **Unavailable-sandbox degradation** — when no OS sandbox is available (Linux
    without `bwrap`, macOS without `sandbox-exec`, Windows/other): **agy is refused**
    (its own `--sandbox` is ineffective, so it would have ZERO containment), but
    **Claude/Codex proceed under their own flag-based containment** (Claude's tool
    denylist / `--tools ""`; Codex's `--sandbox read-only|workspace-write`). This is a
    WEAKER posture than the OS write-deny floor (notably Claude's denylist can be
    bypassed by a tool not on the list), so the plugin emits a `console.warn` when it
    drops the OS layer. This degradation is the explicit trade-off for keeping
    Claude/Codex usable on platforms without an OS sandbox.
  - **Plugin CLI dir** — device-local CLI byproducts (codex output, generated
    `claude_mcp.json`, temp images) live in `<incuratorRepoPath>/.cache/cli/`.
    If the repo path is unavailable, the operation fails visibly. They never
    fall back to the vault, OS temp dir, or `~/.incurator`. CLI subprocess
    `TMPDIR`/`TEMP`/`TMP` are pointed at that
    same CLI cache root's `tmp/` directory.

- **Antigravity settings migration.** The plugin does not use Gemini CLI's
  user-writable TOML policy directory to configure Antigravity. If the obsolete
  `~/.gemini/policies/incurator-read.toml` created by Incurator v0.36.3 exists,
  the plugin may remove it only when its bytes begin with the exact
  Incurator-generated marker. A same-named user-authored file is preserved.
  - **Automatic** — the plugin generates the profile/binds with no manual user setup.
    The READ/visibility set (`--add-dir`) is `allowedRoots()` = realpath-resolved
    vault + Zotero + `storage/` (empty/undefined dropped — never `--add-dir ""`); the
    WRITE set (`sandboxWriteRoots()`) is the vault only, plus the plugin CLI dir.
- **Roots** — READ/visibility = vault + configured Zotero folder + its `storage/`
  (CLI tools may read these). WRITE = the vault only (+ the plugin CLI dir for the
  CLI's own output). The agent cannot create files or run scripts outside the write
  set, and cannot modify the Zotero library at all.
- External user-configured `mcpServers` are the user's own trust boundary and are
  NOT sandboxed by this mechanism (documented limitation).

### 13.7 Local PDF Reader Tools (v0.41.0)

§13.5 and §13.6 closed every path by which a reading surface could reach the
filesystem, the vault, or a script. They also left the model unable to *act* on
what it already knows: the document outline is injected into the prompt with
page numbers (`formatOutline`, ≤80 entries), so the model can reason "that is in
Appendix 4, around p.617" but has no way to obtain that page. Its only remaining
move is to tell the user to navigate there, which defeats the purpose of the
reading assistant. §13.7 supplies the missing actuator without reopening any
boundary closed by §13.5/§13.6.

- **Relationship to deterministic resolution.** These tools are a *fallback*,
  never the primary path. The v0.40.3 deterministic resolver — printed→physical
  page mapping, outline-bounded range fetch, caption/definition index, BM25 over
  seen pages, adjacent-equation probing, fail-closed verification — runs first
  and unchanged. The tools exist for the four cases it structurally cannot
  cover: multi-hop chains discovered only after a page is read; targets named in
  the question rather than the selection (the popover resolves the selection
  before the question is known); the fail-closed residue that v0.40.3
  deliberately produces instead of wrong context; and unnumbered/prose
  references that no pattern in the closed regex table matches.

- **Closed tool set.** Exactly two names may ever be exposed:
  `fetch_pdf_page(page_number)` and `search_pdf_anchor(query)`. They are
  plugin-executed local tools, NOT MCP tools: they are never registered with an
  MCP server, never routed through `mcpManager`, and never reach the filesystem,
  the vault, the Zotero library, or a shell. Execution wraps only the existing
  page-fetch and document-index accessors, scoped to the PDF the user already
  has open.

- **Emission preconditions (fail closed).** Local tools are emitted only when
  the captured request context reports an active PDF, a known positive page
  count, and a stable document identity. If any is missing, no local tool is
  emitted at all — an unbounded or unscoped fetch tool is strictly worse than no
  tool. A markdown-only turn therefore never sees a PDF tool.

- **`search_pdf_anchor` is conditional, not general.** It is emitted only for a
  document *proven* to have no embedded outline (common for papers), where the
  model has no map and cannot know which page to request. A document whose
  outline is merely not yet parsed counts as having an outline, so the tool is
  withheld. It MUST NOT be presented as a general search surface: BM25, the
  caption index, and outline resolution already run deterministically.

- **Typed failures, never thrown turns.** Out-of-range page numbers,
  unparseable arguments, an exhausted fetch budget, and a mid-request document
  identity change each produce a typed `role: "tool"` error message that the
  model can answer around. No local tool failure may abort the turn, and a
  document identity change MUST NOT be resolved against the new document.

- **Budgets.** Rounds remain bounded by the existing tool-loop recursion limit,
  which continues to drop tools on the final turn to force an answer. A separate
  per-request page-fetch budget caps the total pages fetched across all rounds;
  exhaustion is a typed error, not silence.

- **CLI providers are excluded.** Providers routed through a CLI agent
  (Antigravity `agy`, Claude, Codex) receive neither MCP nor local tools; they
  keep the deterministic path only. This preserves §13.6's sandbox contract
  unchanged.

- **Enforcement is behavioral, not textual.** The popover's zero-MCP guarantee
  MUST be locked by tests asserting that MCP injection is refused for the
  popover policy under every combination of MCP-manager presence and CLI
  routing, and that a popover tool array contains only the two local names
  above. Prompt wording (§13.5 `boundaryConstraints`) documents the boundary;
  it does not enforce it.

- **One policy source per surface.** A surface MUST pass its `SurfaceProfile`'s
  `toolPolicy` to `streamChat`/`complete` rather than repeating a literal, and
  both its streaming and non-streaming paths MUST agree. A literal that drifts
  from the profile is a silent failure in both directions: it can strand a
  capability the system prompt advertises (the model is told it has a page
  reader it was never given, and may fabricate having consulted a page), or it
  can grant a surface more than its profile allows.

- **Every `ToolPolicy` gate is exhaustive.** Three decisions key off
  `ToolPolicy`: MCP injection, local-tool injection, and the CLI-sandbox
  `ephemeral` flag of §13.6 (which governs `--add-dir` roots, Claude's
  `--tools`/disallowed-tools, and Codex's `--sandbox` mode). All three MUST be
  exhaustive over the union with a `never`-typed default, so a newly added
  policy value is a compile error rather than a silent grant. `"local-only"`
  is ephemeral for §13.6 purposes: the local reader is plugin-executed and
  hands a CLI agent no native tools and no filesystem roots.

- **Document identity is pinned across every await.** The active PDF view and
  its document id MUST be resolved once, before any await, and re-verified
  before use — the viewer fallback must never re-resolve whichever document
  happens to be active after a backend round-trip, since page bounds were
  validated against the original document. Likewise the outline state that
  gates `search_pdf_anchor` MUST be written under the viewer's render-token
  guard, so a resolution completing after the user navigated away cannot make
  the gate prove the wrong thing for the current document.

---

## 14. LaTeX-preserving copy (chat sidebar + quick-query popover + note Reading View) (v0.5.4)

Selecting part of a rendered assistant reply (chat sidebar or quick-query
popover) or a note (Reading View) and copying it (`Cmd/Ctrl+C`, or `Cmd/Ctrl+X`)
places the formulas' LaTeX **source** (`$...$` / `$$...$$`) on the clipboard
instead of the empty MathJax SVG.

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

- The chat sidebar and quick-query popover render each assistant reply from a
  source string the plugin holds. Immediately after each
  `MarkdownRenderer.render(...)` resolves, the plugin stamps every rendered
  `.math` element with its source as `data-tex` and its kind as
  `data-tex-display` = `"inline" | "block"`, in document order.
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

## 15. Context Pack Client Contract (Plan F target, v0.13.0)

The Obsidian plugin consumes the same normalized backend context pack that
external MCP agents receive for equivalent request and snapshot inputs. The local
plugin path still uses hidden `wiki plugin ...` JSON commands; it does not start
or depend on `wiki mcp`.

The default local JSON command is:

```bash
wiki plugin context fetch --query "<question>" --workspace-path "<vault-or-workspace>" --limit-tokens <n>
```

It returns the `context_fetch` pack without an `answer` field. `wiki plugin
query` remains available for explicit backend synthesis, but ordinary provider
grounding uses the pack command.

Follow-up operations use the same root pack and snapshot:

```bash
wiki plugin context expand --pack-id PACK-... --handle EXP-... --expected-snapshot-id SNAP-...
wiki plugin context verify --pack-id PACK-... --verification-handle VER-... --expected-snapshot-id SNAP-...
```

The plugin must pass the snapshot id from the displayed pack and must surface
`snapshot_conflict` responses as degraded/refetch-required state instead of
mixing evidence across snapshots.

Reviewed or pending feedback against a served pack is appended with:

```bash
wiki plugin context feedback --trace-id QTR-... --pack-id PACK-... \
  --feedback-type incorrect --statement "<observation>" \
  --client obsidian --purpose ground --target-item-id <record-id> \
  --reviewed-span-id SPAN-...
```

`--feedback-type` is one of `relevant`, `irrelevant`, `incorrect`, `stale`,
`insufficient`, `duplicate`, `new_insight`, `correction`, or
`promotion_request`. `--trace-id` is required alongside `--pack-id`; the backend
looks up the root `QTR-*` directly and then verifies that the requested `PACK-*`
belongs to that trace. The command returns an append-only `FBK-*` event id, the
`review_status`, and `ranking_or_truth_mutated: false`. Feedback never mutates
ranking, truth status, source files, or generated records; the event is
quarantined until a separately reviewed policy applies it (SYSTEM_BEHAVIOR
§31.6). An unknown `--feedback-type` returns `ok: false` with
`error_type: invalid_feedback_type` and appends nothing.

### 15.1 Normalized Pack Shape

`IncuratorClient` must accept a versioned context pack with:

- `pack_id`, `trace_id` (`QTR-*`), and `retrieval_execution_id` (`RTR-*`);
- `snapshot.snapshot_id` plus source/DB/search/dependency/policy/model/tokenizer
  identity fields;
- selected route, stop reason, applied policy filters, budget accounting,
  coverage state, warnings, and explicit omissions;
- evidence items with record id/hash, kind, layer, summary/claim, support and
  freshness state, `source_span_ids`, structured locator, token cost, expansion
  handle, and verification handle;
- `next[]` expansion handles for omitted or lower-detail evidence.

Older query result fields remain additive compatibility fields. When sidechat
uses `wiki plugin context fetch`, it preserves the returned pack on the trace
payload as `context_pack`. Sources & Trace renders the exact pack used for
provider grounding, including pack id, snapshot, budget, coverage/degraded
state, evidence item summaries, locators, expansion handles, verification
handles, and omitted `next[]` handles, rather than reconstructing a separate
trace view from partial ids.
Locators are clickable and resolve their open target by source kind:
- An external Reference Mode source (`external_uri` present) is not in the vault;
  its `relpath` is only an in-vault stub. The panel opens the real file at
  `external_uri`, never the stub. A reference **PDF** (`source_kind` `vault_pdf`
  or an `external_uri` ending in `.pdf`) opens in the plugin's external PDF
  viewer at the cited `page_number`; other external references open through the
  system handler. On desktop, local filesystem references MUST use Electron
  `shell.openPath` (or `shell.openExternal` for URLs) rather than raw
  `window.open`, with `window.open` only as a compatibility fallback.
- A vault source (no `external_uri`) opens its `relpath`. A registered/vault PDF
  jumps to the cited page via Obsidian's native viewer using the `#page=N`
  anchor; other notes use their heading/block anchor when present.
If verification succeeds, the returned verified item replaces the matching
displayed item (`verification_handle`) in the retained context pack before the
trace panel re-renders. If an expansion or verification operation returns
`snapshot_conflict`, the
client must retain the conflict metadata (`expected_snapshot_id`,
`current_snapshot_id`, `resolution`) on the displayed pack, mark the pack as
stale/refetch-required, and offer a refetch action. Refetch re-runs
`wiki plugin context fetch` for the original question and replaces the displayed
pack; it must not merge old and new snapshot evidence.

Each evidence item also exposes a feedback affordance: 👍 (`relevant`) / 👎
(`irrelevant`) buttons plus a "Report…" menu for `incorrect`, `stale`,
`insufficient`, and `duplicate`. Selecting one dispatches a single
`context:feedback` event carrying the trace id, pack id, snapshot id, targeted
item `record_id`, and reviewed `source_span_ids`; the client calls
`wiki plugin context feedback`. Feedback is acknowledgement-only — it never
mutates the displayed pack, ranking, or truth state.

### 15.2 Provider Context Budgeting

The plugin calculates the provider-side remaining budget after system prompt,
chat history, selected/pinned/local Markdown context, PDF text/image context,
attachments, and tool overhead. It requests the backend pack with only that
remaining backend-evidence budget. Client-local selected/open-note/PDF/image
context keeps priority over backend evidence.

### 15.3 Default Grounding Behavior

For normal sidechat turns, the plugin grounds the selected provider with evidence
items from the pack. It must not inject a backend synthesized answer by default.
Backend synthesis may be requested only as an explicit mode and must cite the
same `pack_id`/`trace_id` snapshot.

### 15.4 Snapshot Conflict UX

If backend expansion or verification returns `snapshot_conflict`, the plugin
must not display mixed-epoch evidence. It should keep the stale pack visibly
degraded and request a refetch/rebase before using expanded evidence.
