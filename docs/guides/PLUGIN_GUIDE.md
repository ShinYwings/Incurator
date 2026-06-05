# Obsidian Plugin Guide (incurator-agent)

> The Incurator Obsidian plugin brings an AI assistant directly into your Obsidian Vault.  
> Use it standalone or connect it to the Curator backend (wiki CLI) for knowledge-graph-backed answers.

[한국어 가이드](PLUGIN_GUIDE_KR.md)

---

## 1. Installation

Plugin installation is now handled interactively via the **`wiki init` wizard** when creating a vault.

```bash
# 1. Install backend dependencies
./setup.sh

# 2. Initialize vault and auto-install plugin
wiki init /path/to/vault
```

During `wiki init`, if you choose to build the plugin, the output (`main.js`, `manifest.json`, `styles.css`) is copied to  
`<vault>/.obsidian/plugins/incurator-obsidian-agent/` automatically.

In Obsidian, go to **Settings → Community Plugins → Installed Plugins** and enable `AI Agent`.

> **Note:** If you need to build the plugin manually, run `npm install` and `npm run build` inside the `plugin/` directory.

---

## 2. Chat Sidebar

### Opening

| Method | Action |
| --- | --- |
| Click the bot ribbon icon in the left sidebar | Toggle chat sidebar |
| `Cmd+Shift+;` | Toggle chat sidebar |

### Features

- **Multi-turn conversation**: Session history is preserved. Create and switch between multiple sessions.
- **Codex-style sidebar**: New chat and conversation history live in the top thread header; history opens as an in-sidebar searchable drawer.
- **Streaming responses**: Enabled by default; can be turned off in settings.
- **Context references**: Attach text, PDF pages, or image snippets to your messages.
- **Plan mode**: With `chatMode: plan`, the AI presents a step-by-step plan before acting.
- **Incurator integration**: When connected to a Curator backend, traceable DAG evidence is injected as context.

---

## 3. Inline Edit (`Cmd+K`)

Select text in a Markdown editor then press `Cmd+K` to open the inline prompt widget.

- **No selection**: The whole document is used as context for the edit command.
- **With selection**: Only the selected region is targeted.
- **Result display**: Changes are shown as an inline diff; choose Accept or Reject.
- **Chat edit review**: When sidechat proposes Markdown SEARCH/REPLACE edits,
  use **Review in file** to open the target note in source mode and review the
  proposed hunks inside the Markdown editor before accepting or rejecting them.
- **Diff mode**: Choose `inline` or `side-by-side` in settings.

```text
Select text in editor
       │
       │ Cmd+K
       ▼
Inline prompt widget (enter command)
       │
       ▼
LLM generates suggestion → Diff shown → Accept / Reject
```

---

## 4. Line Reference (`Cmd+Shift+L`)

Adds the currently viewed content to the chat as a context reference.

| View type | Behavior |
|-----------|----------|
| **Markdown file** | Adds text near the cursor as a context reference |
| **PDF viewer** (with selection) | Adds selected text to context |
| **PDF viewer** (no selection) | Adds the full current page as context (text/image/both per `pdfCaptureMode`) |

Text selection in the Incurator PDF viewer starts only on actual text spans. Dragging over empty PDF margins does not create a selection region.

When sidechat sends a message, context added explicitly through selection,
line reference, or PDF snipping is treated as the primary focus. Pinned purple
context and automatically visible tabs remain background grounding unless the
question explicitly asks about them. A pinned or attached context chip can be
toggled invisible/excluded; it stays visible in the chip row but is not sent to
the model until toggled visible again.

When a selected Markdown line range is attached and the user asks to fix,
rewrite, polish, translate, or otherwise modify that selected text, the
assistant should return an `ai-agent-edit` SEARCH/REPLACE proposal. If the user
only asks a question about the selection, the assistant answers normally and
does not propose an edit.

When the latest request uses a selected PDF/text region as an example and asks
to change all similar Markdown-file occurrences, the selected region is treated
as a clue, not as the only edit target. The plugin sends the full content of
open Markdown tabs as edit-target context so the assistant can find matching
HTML/Markdown lines across the file, preserve the existing syntax form, and
propose SEARCH/REPLACE hunks for review in the Markdown editor.

### Markdown Position Restore

When Obsidian shuts down, the plugin saves the active editing-mode Markdown file's cursor and scroll position as the last workspace position. After restarting Obsidian, the plugin waits for the workspace layout and retries restoring that file and position.

The last workspace position is stored as a separate snapshot; per-file positions are kept only as a secondary cache for up to 100 file paths.

---

## 5. PDF Snipping (`Cmd+Shift+X`)

Drag-select a region of a PDF to capture it as an image.

1. Open a PDF in the Incurator viewer (right-click `.pdf` → Open with Incurator)
2. Press `Cmd+Shift+X` to enter snipping mode
3. Drag over the desired area — it is captured as an image
4. The captured image is automatically attached to the chat sidebar context

> **Note**: Snipping only works in the Incurator PDF viewer (`EXTERNAL_PDF_VIEW_TYPE`).  
> For Obsidian's built-in PDF viewer, use `Cmd+Shift+L` to reference the whole page.

PDF snips are sent as image context when the selected model supports vision. If
the active model is text-only, sidechat keeps the snip attached but tells the
model that image details are unavailable instead of silently ignoring the crop.
When the latest message already carries a user-selected crop/image, the plugin
uses that local image context as the fast path and skips backend whole-PDF
context/RAG calls for that turn.

---

## 6. PDF Processing Settings

The plugin offers three capture modes when using a PDF as context.

| `pdfCaptureMode` | Description |
|------------------|-------------|
| `text` | Extract text layer only (fast, token-efficient) |
| `image` | Capture page as image (requires vision-capable model) |
| `both` | Send text + image together (default, most accurate) |

### Additional PDF options

| Setting | Default | Description |
|---------|---------|-------------|
| `pdfWindowRadius` | `1` | Pages before/after current page to include |
| `pdfOutlineEnabled` | `true` | Include PDF table of contents in context |
| `pdfRagEnabled` | `true` | Enable RAG search across the full PDF |
| `pdfRagTopK` | `5` | Number of top RAG results to retrieve |
| `pdfVisionFallback` | `true` | Auto-switch to image mode when text layer is absent |
| `pdfFullDocumentIndex` | `true` | Index the entire PDF for better RAG accuracy |

PDF context is assembled in this order:

1. Local PDF.js page text and attached crop/image context.
2. Backend PDF window/outline context only when local viewer text/window/image
   context is unavailable.
3. Optional backend whole-PDF RAG only when backend PDF context is being used,
   `pdfRagEnabled=true`, and the source is tracked.

The chat sidebar logs backend PDF context, PDF RAG, and Curator query timings to
the developer console so slow turns can be diagnosed without guessing which
stage is blocking.

Treat PDF chat and PDF knowledge refinement as separate workflows:

- Normal chat over an open PDF uses the viewer fast path. It answers from the
  current page, nearby page text, selected text, or crop image without requiring
  durable Incurator ingestion or a blocking backend PDF context call.
- Purple context chips and **Add to Incurator** start durable knowledge
  refinement. They register the PDF as a source, create instant L1 context, and
  queue L2/L3 build jobs.
- Queued L2/L3 jobs run through **Incurator Dashboard > Jobs > Run queued** or
  the CLI command `wiki jobs run`. This keeps the PDF viewer responsive while
  long LLM-heavy refinement runs as explicit background work.
- In the Jobs tab, queued jobs can be cancelled before a worker claims them, and
  completed, failed, or cancelled jobs can be requeued with **Rerun**.

---

## 7. AI Provider Settings

The plugin supports Antigravity, Claude, OpenAI Codex, Ollama, and DeepSeek. In settings, provider and model can be adjusted separately. In the chat sidebar footer, a single model menu switches both at once using `Provider · Model` labels. Reasoning/effort appears only for models whose backend catalogue entry declares effort levels.

The Settings page shows the selected model's context window on the **Model**
row instead of as a separate setting.

> [!NOTE]
> The **Incurator Dashboard → Overview → LLM Provider** card also edits the vault's (`​.curator/config.yml`) Primary/Fallback models. Each model dropdown is paired with an **effort dropdown** that shows only the levels the selected model exposes (models with no effort show `—`). Applying saves to `llm.primary_effort` / `llm.fallback_effort`. The model list is bundled from the backend's single-source `data/models.json` catalogue when the plugin is built, so model names do not depend on MCP startup.

### 7.1 Antigravity (default)

Accesses Google Gemini models via the Antigravity CLI (`agy`).

```bash
# Login
agy login
# Or use the plugin command: Login to Antigravity CLI
```

| Model | Description |
|-------|-------------|
| `gemini-3.5-flash` | Default. Fast and efficient |
| `gemini-3.1-pro` | High-quality reasoning |
| `gemini-3-flash` | Previous-generation Flash |

`antigravityPrintTimeoutSec`: Maximum wait time for CLI response (default 300 seconds)

### 7.2 Claude

Accesses Anthropic models via Claude Code CLI (`claude`).

```bash
# Login
claude login
# Or use the plugin command: Login to Claude CLI
```

`claudeEffort`: Choose from `low` / `medium` / `high` / `xhigh` / `max`

### 7.3 OpenAI Codex

Accesses GPT models via OpenAI Codex CLI (`codex`).

```bash
# Login
codex login
# Or use the plugin command: Login to OpenAI Codex CLI
```

`codexReasoningEffort`: Choose from `low` / `medium` / `high` / `xhigh`

| Model | Description |
| --- | --- |
| `gpt-5.5` | Default. Powerful reasoning |
| `gpt-5.4` | Everyday coding tasks |
| `gpt-5.4-mini` | Fast, lightweight tasks |
| `gpt-5.3-codex` | Coding-specialized model |

### 7.4 Ollama (Local)

Connects directly to a local Ollama server via HTTP. No authentication required, fully offline.

```bash
# Start the Ollama server
ollama serve

# Pull a model
ollama pull qwen2.5:7b
```

Settings:

- **Ollama host**: Server address (default: `http://localhost:11434`)
- **Model**: Type a model name directly or click **Fetch models** to list installed models
- Vision support varies by model (e.g. `gemma3:12b` supports vision, `qwen2.5:7b` does not)

### 7.5 DeepSeek API

Connects to DeepSeek's OpenAI-compatible API with an API key. It does not use
OAuth or a browser CLI login.

Settings:

- **API key**: Store a device-local key in plugin settings, or leave it blank and
  set `DEEPSEEK_API_KEY` in the Obsidian process environment.
- **Model**: Choose from the backend catalogue. As of 2026-06-01 the current
  DeepSeek API model ids are `deepseek-v4-flash` and `deepseek-v4-pro`.
- Legacy aliases `deepseek-chat` and `deepseek-reasoner` are not preferred
  because DeepSeek schedules them for deprecation on 2026-07-24.

Quota or capacity errors from any provider are rendered directly in sidechat so
the user can switch provider/model or configure a fallback instead of seeing an
empty answer.

---

## 8. MCP Server Configuration

Configure the plugin to use external MCP tools. This section is for non-Incurator
tool servers and external agent integrations. The local Incurator backend
integration uses backend commands instead of starting `wiki mcp`.

Go to **Settings → AI Agent → MCP Servers** and add a server:

```json
{
  "name": "my-external-tools",
  "command": "example-mcp-server",
  "args": [],
  "env": {
    "VAULT_ROOT": "/path/to/your/vault"
  },
  "enabled": true
}
```

> **Important**: `VAULT_ROOT` must point to your Vault directory (where `.curator/` lives).  
> Do not set it to the wiki system (Incurator code) path or a testbed path.

---

## 9. Incurator Integration

With `incuratorEnabled: true`, the plugin can use Curator backend features.

### How it works

```text
User types a chat message
      │
      │ (Incurator integration active)
      ▼
IncuratorClient calls hidden backend JSON commands
(`wiki plugin source ...`, `wiki plugin pdf ...`, `wiki plugin query`)
      │
      ▼
Traceable DAG evidence injected as system context
      │
      ▼
LLM generates answer grounded in retrieved evidence
```

### Incurator settings

| Setting | Default | Description |
|---------|---------|-------------|
| `incuratorEnabled` | `true` | Enable Curator backend integration |
| `incuratorRepoPath` | `""` | Absolute path to the Incurator repository for 1-Click Auto-Updates |
| `incuratorDefaultDestination` | `04_Resources` | Default folder for PDF reference stubs or explicit copy imports |
| `incuratorDefaultImportMode` | `reference` | Add mode for files (`reference` creates a link stub; `copy` copies into the vault) |
| `incuratorStatusPolling` | `true` | Poll for source processing status updates |

Source badges are layer-aware. `L1 ready` means instant section context is
available, `L2 ready` means Atoms exist, `Indexed` means L3 Concepts are ready
for concept-grounded answers, and `Synthesized` means shared L4 Synthesis is
available. Any layer error is shown as an error instead of a healthy badge.

### 1-Click Auto-Update

The Incurator backend and the Obsidian plugin may be updated at different frequencies. When the plugin checks the backend version and detects a mismatch, it displays an **[Update Incurator Backend]** banner at the top of the chat window.
If you have configured the `incuratorRepoPath` in the plugin settings, clicking this button will automatically execute a background update (`git pull && ./setup.sh`). Reload the plugin or restart Obsidian after the update.

`Use Incurator backend` controls whether the plugin uses local Incurator backend
commands. When enabled, the plugin discovers the `wiki` binary, reads backend
runtime snapshots, and calls hidden `wiki plugin ...` JSON commands for source,
PDF, query, promotion, and Zotero operations. The generic MCP Servers section
remains available for other MCP servers; the plugin does not auto-start
Incurator MCP for same-device backend access.

### PDF → Curator registration flow

When Incurator integration is on and you reference a PDF:

```text
Cmd+Shift+L (or Cmd+Shift+X) captures PDF content
      │
      │ backend source registration command
      ▼
Source registered in Curator backend
      │
      │ L1 → L2 → L3 processing (background)
      ▼
Shared L4 Synthesis is available after build
      │
      ▼
Searchable via query/search tools
```

The purple PDF chip is the refinement control. Clicking **Add source** does not
wait for the whole DAG to finish; it registers the source, creates L1, and queues
L2/L3. Use **Dashboard > Jobs > Run queued** when you want to actively drain the
queued build work, or leave the queue for a backend worker to process.

For ordinary workspace/domain questions with no primary selected text, line
range, PDF page, or crop image attached to the latest user turn, sidechat calls
`wiki plugin query` directly. If the backend has L3 grounding, the response
includes a compact trace so the Sources & Trace panel can link the supporting
evidence. If the latest turn is focused on a
selected crop or editable Markdown region, sidechat skips `wiki plugin query`
and answers from that selected context instead.

For PDFs opened from Zotero or another external location, **Add to Incurator**
uses Reference Mode by default. The backend leaves the PDF in place, creates a
small markdown reference stub under `04_Resources/`, and stores the real PDF
path as device-local backend source metadata. The generated stub does not embed
the absolute PDF path by default, so it can sync to another device where Zotero
or external PDFs live elsewhere. For Zotero PDFs, the stub includes portable
Zotero identity and a `zotero://open-pdf/library/items/<key>` link so it is
clearly a Zotero-backed reference. Copying a PDF into the vault is an explicit
exception, not the default.

Zotero setup and repair are backend-owned. The plugin asks hidden backend JSON
commands for Zotero status, initialization, metadata, annotations, and PDF
attachment resolution, then presents any required user choice or repair action.

The dashboard **Reset** action asks for two confirmations before clearing the
local database and generated L1-L4 content.

Dashboard status should come from backend-owned shared snapshots under
`.curator/runtime/`, not from plugin-owned state. The backend is the only writer
for those JSON files; the plugin reads them to render source counts, job state,
index health, and backend version. Missing snapshots are treated as waiting or
unknown state, not as an empty backend.

Dashboard buttons such as Add, Build, Sync, Lint, Reindex, Reset, LLM Apply, and
Persona Save run backend commands for mutations. The plugin does not directly
edit backend-owned `.curator` state for those actions.

Zotero search, metadata refresh, PDF path resolution, annotation loading, source
status/import/rebind, PDF context/search, query, and promotion use the hidden
plugin-local backend API (`wiki plugin ...`). This keeps durable backend state
and local filesystem/database resolution in backend code without requiring the
plugin to discover or call Incurator MCP tools, and without exposing plugin
plumbing as normal human-facing `wiki` commands.

---

## 10. Sync Notes

### Session history (`sessions.json`)

Plugin data is split into two files.

| File | Contents | Cross-device sync |
| --- | --- | --- |
| `data.json` | Settings such as provider, model, and MCP servers | Recommended only when paths match |
| `sessions.json` | Chat conversation history | Supported |
| `.curator/runtime/*.json` | Backend-written dashboard/status snapshots | Supported as generated state |

In v0.2.1, the plugin re-reads the latest on-disk `sessions.json` before saving and merges by session id. This preserves distinct sessions created on Linux and macOS. Deleted sessions are recorded in `deletedSessionIds` tombstones so an older synced file does not resurrect them later. If the same session is edited on both devices concurrently, the copy with the newer `updatedAt` timestamp wins.

The sidebar conversation list derives each chat title from the first assistant
answer after the first user question. While that answer is still pending, it
uses the first user question as the temporary title. Each row also shows
relative last activity from `updatedAt`, such as `12m ago` or `3h ago`.

Deleting a chat session from the sidebar trash action is immediate. The delete
is still recorded as a tombstone in `deletedSessionIds` so synced devices do not
restore the removed session.

If the backend executable path differs per device, or one device does not have Incurator installed, keep `data.json` local instead of synchronizing it. In that setup, add `data.json` to `.stignore`, not `sessions.json`.

```text
.obsidian/plugins/incurator-obsidian-agent/data.json
```

If `wiki` is not available on PATH on macOS, configure **Settings > AI Agent > PDF & Incurator** with a per-device launcher:

| Setting | Value |
| --- | --- |
| `Backend command` | `/opt/homebrew/bin/uv` |
| `Backend arguments` | `["--directory", "/Users/<you>/Workspace/Incurator/backend", "run", "wiki"]` |

On startup, the Obsidian plugin automatically records Syncthing device names and
the current device's backend launcher hint in `.curator/devices.json`. This
registry lets Linux/macOS path differences be visible without synchronizing
plugin `data.json`. The dashboard Overview lists every device in the active
Syncthing shared-folder registry, including remote devices that have no backend
launcher configured on the current machine, and shows whether each device syncs
the Vault and/or Zotero folders. The current machine is marked as **This
device**, even when Syncthing only exposes it through the local fallback entry.
There is no standalone Devices tab. Unknown platform fields are shown as unknown
instead of guessed. `wiki devices sync` is a manual repair command when the
automatic refresh is unavailable; `wiki devices` inspects the current registry.

See [SYNC_IGNORE_GUIDE.md](SYNC_IGNORE_GUIDE.md) for the full synchronization setup.

---

## 11. Zotero Integration

When a Zotero data directory is configured, clicking a `zotero://open-pdf/library/items/<KEY>?page=X` link in a Markdown note opens the PDF directly in the built-in viewer — no Zotero app required.
- If the link contains a `?page=X` parameter, the viewer will automatically scroll to that page.
- If the link contains `annotation=<KEY>&viewer=obsidian`, the existing PDF view is reused and navigated to that page and annotation location; the annotation area is shown as an empty outline box so the PDF content remains visible.
- If the link contains `viewer=zotero`, the plugin lets the link open in Zotero instead.
- Clicking multiple Zotero links for the same PDF will re-use the existing split view rather than opening new ones.

### Setup

Go to **Settings > AI Agent > Zotero Integration > Backend Zotero status > Open setup** to inspect what the backend can actually read on this device. The setup dialog is the single Zotero data-directory entry point, defaults to `~/Zotero`, displays home-directory paths with `~` instead of an absolute `/Users/...` prefix, and can save the data directory plus an optional linked attachment root to the backend for future status checks, searches, PDF resolution, annotations, and Add-to-Incurator registration.
> **Note**: If you use the default Zotero profile location (`~/Zotero`), the backend automatically parses your `prefs.js` to auto-discover the Linked attachment root and ZotMoov destination directory. Therefore, you typically do not need to manually enter the linked attachment root in the settings dialog. It is only provided as an override for custom environments where auto-discovery fails.
When backend resolution returns checked roots or checked PDF paths, the setup
dialog shows them as candidate roots with a **Use** action so you can populate
the data-directory or linked-root field without retyping long paths.

| OS | Default path |
| --- | --- |
| macOS | `~/Zotero` |
| Linux | `~/Zotero` |
| Windows | `C:\Users\<username>\Zotero` |

The directory should contain `zotero.sqlite`; attachment PDFs may be in Zotero
`storage/` or a linked/base attachment directory. The linked attachment root is
only for Zotero DB `attachments:` paths; ordinary `storage/<KEY>/...`
attachments do not need it. If the directory moved or the database is missing,
the backend status command reports a structured state instead of making Zotero
search look like an empty library.
When a Zotero link or Add-to-Incurator action cannot resolve a PDF, the backend
returns a structured state: `db_missing`, `attachment_key_missing`, or
`attachment_file_missing`. This keeps "Zotero is unavailable", "the item key is
not in this database", and "the linked PDF file is missing from configured
roots" separate in plugin UI. The plugin opens the same Zotero setup dialog from
Settings, Dashboard, Zotero link failures, and sidechat Add-to-Incurator
failures so repair logic stays in one UI path.

### Import Zotero Item

Leaving the `Import Zotero Item` search box blank shows recently modified Zotero items ordered by `dateModified`. The Zotero directory setting may contain multiple comma-separated data directories; the plugin checks each path's `zotero.sqlite` in order.

When the import wizard opens and saved profiles exist, the first saved profile
is loaded automatically. Successfully imported items are remembered locally in a
`recentZoteroItems` LRU list so they appear before other matches in later Zotero
searches.

Output subfolders, filenames, and asset subfolders use the same Nunjucks
templating engine as Zotero note templates. Examples:

```text
{{ date | format("YYYY") }}/{{ creators | firstAuthorLast | pathSafe }}
{{ creators | firstAuthorLast }}_{{ title | pathSafe }}
{{ tags | joinTags("; ") }}
```

Rendered path segments are sanitized before files are created in the vault.

When a Zotero PDF is opened in the plugin viewer and registered from the
sidechat/purple-pin flow, Incurator registers the original file in Reference
Mode instead of copying it into the vault. The generated reference stub records
the Zotero attachment key and a Zotero open-pdf link, while the resolved local
PDF path stays in backend source metadata. The plugin shows a completion notice
when registration succeeds and an error notice when the backend cannot resolve
or register the file path. The Zotero path setting may point either to a Zotero
data directory or directly to `zotero.sqlite`; backend PDF resolution normalizes
the latter to its parent directory before checking `storage/<attachmentKey>/`.
For linked Zotero attachments, backend resolution also checks configured linked
attachment roots for `attachments:` paths.
When the plugin has a Zotero attachment key, Add-to-Incurator can pass that key
to backend source import directly; the backend resolves the PDF and records a
stable `zotero:<attachmentKey>` logical source id for the local reference row.
Repeated registration of the same Zotero attachment reuses that logical source
id instead of creating `-02` reference stubs. PDF crop/snipping context is
temporary chat context; it is sent to the selected model when possible and must
not leave durable generated images under `05_Assets`.
Zotero setup and repair are backend-owned: the plugin should call hidden JSON
commands such as `wiki plugin zotero status`, `wiki plugin zotero init`,
`wiki plugin zotero search`, and `wiki plugin zotero resolve-pdf` instead of
treating plugin settings as canonical. PDF context requests should pass the
richest identity available, such as a source id, file hash, vault relpath,
absolute path, or Zotero attachment key, so the backend can resolve moved or
reference-mode files consistently.

For chat answers, the plugin-selected provider/model writes the final sidechat
answer. Backend/Incurator calls supply retrieved context, PDF windows, source
status, or backend synthesis only when the plugin explicitly calls them. The
plugin uses a structured language bridge for every latest request: detect input
language, use English for internal search/reasoning/tool arguments, then answer
in the detected latest input language unless that latest request asks for
another output language. Previous turns, Korean Markdown context, and saved
saved metadata does not set a persistent answer language; English latest
questions receive English final answers unless the latest request asks
otherwise. When `curator_query` runs, the chat transcript keeps compact parseable
trace fields so the Sources & Trace panel can show the supporting evidence, but
stale `final_output_language` is not reused as sidechat language state.

Input-language detection is deterministic and runs fresh on every chat turn.
The plugin classifies the latest request by Unicode script — for example Korean
(한글), Chinese (汉字), Japanese (かな), Russian (Кириллица), Arabic, and others,
falling back to English for Latin script — and the same canonical detector is
used whether the turn triggers a backend curator query or a plain provider chat.
So a chat session that receives an English question answers in English, a Korean
question answers in Korean, and a Chinese question answers in Chinese, each
decided independently per message regardless of what language earlier turns used.
The detected language is the answer language directly; the model does not first
produce English and then translate in a separate pass. The three language fields
(`input_language`, `english_query`, `final_output_language`) live only in the
query JSON/trace and are never written into generated node frontmatter. A plain
chat whose active note is not inside a workspace folder is treated as outside a
workspace and resolves to `default`, never to an unrelated project workspace you
did not open.

### Zotero link flow

```text
Click zotero:// link in a Markdown note
      │
      │ (Zotero data directory is configured)
      ▼
Plugin intercepts click and tries the built-in viewer first
      │
      │ Scans storage/<ATTACHMENTKEY>/*.pdf
      ▼
Resolves PDF path → opens in built-in viewer (split view)
      │
      │ If the PDF cannot be resolved locally
      ▼
Falls through to the Zotero app
      │
      ▼
Use Cmd+Shift+L to add to chat context or trigger Incurator ingest
```

### Generating Zotero links

Right-click an item in Zotero → **Copy Item Link**, or use the [Zotero Integration](https://github.com/mgmeyers/obsidian-zotero-integration) plugin to auto-generate notes that include `zotero://` links.

> **Note**: If no Zotero data directory is set, the click falls through to default behavior (browser or Zotero app).

---

## 11. Keyboard Shortcuts Summary

| Shortcut | Action |
|----------|--------|
| `Cmd+K` | Inline edit (in Markdown editor) |
| `Cmd+Shift+L` | Add current content to chat context (Markdown or PDF) |
| `Cmd+Shift+X` | Snip PDF region → attach to chat (Incurator PDF viewer only) |
| `Cmd+Shift+;` | Toggle chat sidebar |

> On macOS, `Cmd` = `⌘`. On Linux/Windows, use `Ctrl`.

---

## 12. v0.3.2 Curation-Native Interfaces

The plugin talks to the backend's v0.3.2 curation-native features through hidden
local JSON commands (never via MCP for same-device flows). The client
(`IncuratorClient`) exposes:

| Client method | Backend command | Returns |
|---|---|---|
| `getCuratePlan(workspacePath)` | `wiki plugin curate plan` | `IncuratorCuratePlan` (route, selected/excluded sources, allowed modes, validation errors) |
| `getPromptTrace(traceId)` | `wiki plugin prompt trace` | `IncuratorPromptTrace` (prompt id/version, validator status, model) |
| `listInsightCandidates(workspacePath)` | `wiki plugin insight list` | `IncuratorInsightCandidate[]` |
| `getInsightCandidate(insightId, workspacePath)` | `wiki plugin insight show` | `IncuratorInsightCandidate` with evidence/source event details |
| `promoteInsight(insightId, workspacePath)` | `wiki plugin insight promote` | `{ promotedTo }` (writes only `02_Wiki/`) |
| `rejectInsight(insightId, workspacePath, reason)` | `wiki plugin insight reject` | `{ ok, status }` |
| `listQueryTraces(workspacePath, limit)` | `wiki plugin trace list` | Recent `QTR-` trace summaries |
| `getQueryTrace(traceId, workspacePath)` | `wiki plugin trace show` | Query route, evidence ids, retrieval trace, warnings |
| `proposeCorrection(nodeId, correction, previous, workspacePath)` | `wiki plugin correction propose` | Classification/recommended action/review flag |

Query results (`CuratorQueryResult`) and the Sources & Trace panel carry the
v0.3.2 fields additively: `route`, `trace_id` (`QTR-`), `prompt_trace_ids`
(`PTR-`), `source_span_ids` (`SPAN-`), `community_report_ids` (`REP-`),
`memory_path_ids` (`MPATH-`), and `insight_candidate_ids` (`INS-`). Older/partial
backend responses simply omit them, so the panel degrades gracefully.

Rules:
- Insight-candidate promotion is an explicit user action; the plugin must confirm
  before calling `promoteInsight`, which writes only to `02_Wiki/`.
- These local commands return JSON and must not be routed through Incurator MCP
  tools (MCP is for external agents). See
  [Plugin Schema spec](../specs/plugin_schema/PLUGIN_SCHEMA_v0.3.2.md) §9–12.
- Dashboard Trace and Insights tabs are click-to-use surfaces over these commands.
  They may list/show traces and insight candidates, promote/reject candidates, and
  propose corrections, but they must never write `.curator/state.sqlite`,
  `.curator/Collections/`, `03_Notes/`, `04_Resources/`, or `06_Archives`
  directly.

---

## Related Docs

- [Full Workflow](WORKFLOW_GUIDE.md) — How the entire system fits together
- [MCP User Guide](MCP_USER_GUIDE.md) — Connecting AI agents via MCP
- [User Guide](USER_GUIDE.md) — wiki CLI command reference
