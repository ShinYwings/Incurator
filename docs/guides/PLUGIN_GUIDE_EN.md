# Obsidian Plugin Guide (incurator-agent)

> The Incurator Obsidian plugin brings an AI assistant directly into your Obsidian Vault.  
> Use it standalone or connect it to the Curator backend (wiki CLI) for knowledge-graph-backed answers.

[한국어 가이드](PLUGIN_GUIDE.md)

---

## 1. Installation

```bash
# Full install from project root
./setup.sh

# Or build the plugin only
cd plugin
npm install
npm run build
```

`setup.sh` copies the build output (`main.js`, `manifest.json`, `styles.css`) to  
`<vault>/.obsidian/plugins/obsidian-ai-agent/` automatically.

In Obsidian, go to **Settings → Community Plugins → Installed Plugins** and enable `AI Agent`.

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
- **Incurator integration**: When connected to a Curator backend, Exhibition search results are injected as context.

---

## 3. Inline Edit (`Cmd+K`)

Select text in a Markdown editor then press `Cmd+K` to open the inline prompt widget.

- **No selection**: The whole document is used as context for the edit command.
- **With selection**: Only the selected region is targeted.
- **Result display**: Changes are shown as an inline diff; choose Accept or Reject.
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

---

## 7. AI Provider Settings

The plugin supports three AI providers. In settings, provider and model can be adjusted separately. In the chat sidebar footer, a single model menu switches both at once using `Provider · Model` labels. Reasoning/effort appears only for Codex and Claude.

### 7.1 Antigravity (default)

Accesses Google Gemini models via the Gemini CLI (`agy`).

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

---

## 8. MCP Server Configuration

Configure the plugin to use external MCP tools.

Go to **Settings → AI Agent → MCP Servers** and add a server:

```json
{
  "name": "incurator",
  "command": "wiki",
  "args": ["mcp"],
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

With `incuratorEnabled: true`, the plugin connects to the Curator backend.

### How it works

```text
User types a chat message
      │
      │ (Incurator integration active)
      ▼
IncuratorClient calls search_curator via MCP
      │
      ▼
Exhibition search results injected as system context
      │
      ▼
LLM generates answer grounded in Exhibition content
```

### Incurator settings

| Setting | Default | Description |
|---------|---------|-------------|
| `incuratorEnabled` | `true` | Enable Curator backend integration |
| `incuratorDefaultDestination` | `04_Resources` | Default destination folder for PDF imports |
| `incuratorDefaultImportMode` | `reference` | Import mode for files (`copy` / `reference`) |
| `incuratorStatusPolling` | `true` | Poll for source processing status updates |

`Use Incurator backend` controls whether the plugin uses Incurator MCP tools. When enabled, the plugin automatically creates the default `incurator` server (`wiki mcp`) with the current vault path as `VAULT_ROOT` and immediately tries to connect. The setting shows a status bar directly underneath: disabled, connected, waiting, or not configured. The generic MCP Servers section remains available for other MCP servers or advanced edits to the generated Incurator server.

### PDF → Curator registration flow

When Incurator integration is on and you reference a PDF:

```text
Cmd+Shift+L (or Cmd+Shift+X) captures PDF content
      │
      │ MCP: curator_import_source
      ▼
Source registered in Curator backend
      │
      │ L1 → L2 → L3 processing (background)
      ▼
wiki curate → L4 Exhibition updated
      │
      ▼
Searchable via search_curator
```

---

## 10. Sync Notes

### Session history (`sessions.json`)

Plugin data is split into two files.

| File | Contents | Cross-device sync |
| --- | --- | --- |
| `data.json` | Settings such as provider, model, and MCP servers | Recommended only when paths match |
| `sessions.json` | Chat conversation history | Supported |

In v0.2.1, the plugin re-reads the latest on-disk `sessions.json` before saving and merges by session id. This preserves distinct sessions created on Linux and macOS. Deleted sessions are recorded in `deletedSessionIds` tombstones so an older synced file does not resurrect them later. If the same session is edited on both devices concurrently, the copy with the newer `updatedAt` timestamp wins.

If the backend executable path differs per device, or one device does not have Incurator installed, keep `data.json` local instead of synchronizing it. In that setup, add `data.json` to `.stignore`, not `sessions.json`.

```text
.obsidian/plugins/incurator-obsidian-agent/data.json
```

If `wiki` is not available on PATH on macOS, configure **Settings > AI Agent > PDF & Incurator** with a per-device launcher:

| Setting | Value |
| --- | --- |
| `Incurator MCP command` | `/opt/homebrew/bin/uv` |
| `Incurator MCP args` | `["--directory", "/Users/<you>/Workspace/Incurator/backend", "run", "wiki", "mcp"]` |

On startup, the Obsidian plugin automatically records Syncthing device names and
the current device's backend launcher hint in `.curator/devices.json`. This
registry lets Linux/macOS path differences be visible without synchronizing
plugin `data.json`. `wiki devices sync` is a manual repair command when the
automatic refresh is unavailable.

See [SYNC_IGNORE_GUIDE_EN.md](SYNC_IGNORE_GUIDE_EN.md) for the full synchronization setup.

---

## 11. Zotero Integration

When a Zotero data directory is configured, clicking a `zotero://open-pdf/library/items/<KEY>?page=X` link in a Markdown note opens the PDF directly in the built-in viewer — no Zotero app required.
- If the link contains a `?page=X` parameter, the viewer will automatically scroll to that page.
- If the link contains `annotation=<KEY>&viewer=obsidian`, the existing PDF view is reused and navigated to that page and annotation location; the annotation area is shown as an empty outline box so the PDF content remains visible.
- If the link contains `viewer=zotero`, the plugin lets the link open in Zotero instead.
- Clicking multiple Zotero links for the same PDF will re-use the existing split view rather than opening new ones.

### Setup

Go to **Settings > AI Agent > Zotero Integration > Zotero data directory** and enter the path to your Zotero data folder.

| OS | Default path |
| --- | --- |
| macOS | `~/Zotero` |
| Linux | `~/Zotero` |
| Windows | `C:\Users\<username>\Zotero` |

The directory must contain a `storage/` subfolder.

### Import Zotero Item

Leaving the `Import Zotero Item` search box blank shows recently modified Zotero items ordered by `dateModified`. The Zotero directory setting may contain multiple comma-separated data directories; the plugin checks each path's `zotero.sqlite` in order.

### Zotero link flow

```text
Click zotero:// link in a Markdown note
      │
      │ (Zotero data directory is configured)
      ▼
Plugin intercepts click (prevents Zotero app from opening)
      │
      │ Scans storage/<ATTACHMENTKEY>/*.pdf
      ▼
Resolves PDF path → opens in built-in viewer (split view)
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

## Related Docs

- [Full Workflow](WORKFLOW.md) — How the entire system fits together
- [MCP User Guide](MCP_USER_GUIDE_EN.md) — Connecting AI agents via MCP
- [User Guide](USER_GUIDE_EN.md) — wiki CLI command reference
