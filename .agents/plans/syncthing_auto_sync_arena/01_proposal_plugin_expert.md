# Plugin Expert Proposal: Correct Triggers, fs.watch, Non-Blocking Status UI

Date: 2026-06-07 | Agent Persona: Frontend / Plugin Expert

Integration surface (verified against current code):
- `plugin/main.ts` → `ObsidianAIAgent` (`onload`, `addRibbonIcon`, `onLayoutReady`,
  `registerEvent`, `registerInterval`, `settings.incuratorEnabled`).
- `plugin/src/agent/incuratorClient.ts` → `IncuratorClient.callBackendJson([...])`,
  `pickRecord`.
- Backend CLI: `wiki db autosync --json`, `wiki db export --json`,
  `wiki db import <path> --json`.

## 1. Core Logic & Implementation

### 1.1 The RIGHT export trigger (not `vault.on("modify")`)

Markdown note saves are NOT DB mutations. The DB changes when the backend ingests.
Therefore:

- **Do not** auto-export on `vault.on("modify")`.
- Auto-export is owned by the **backend**, fired at the end of mutating CLI commands
  when `auto_sync.enabled` (DB Architect §1.2). The plugin only needs to call
  `wiki db autosync` (which exports self after importing peers) at well-defined moments:
  1. on Obsidian load (after `onLayoutReady`),
  2. when the real-time watcher sees a peer file change,
  3. on the manual ribbon button,
  4. after the plugin itself drives a backend mutation (e.g., a promotion).

### 1.2 Real-time peer detection via Node `fs.watch`

Obsidian's `vault.on(...)` does **not** reliably observe the hidden `.curator/` dir, so
use the Node API (available in Obsidian desktop):

```ts
import { watch, FSWatcher } from "fs";
private syncWatcher: FSWatcher | null = null;

private startSyncWatcher() {
  if (this.settings.autoSyncEnabled === false) return;
  const dir = this.incuratorClient.resolveSyncDir(); // <vault>/.curator/sync
  this.syncWatcher = watch(dir, { persistent: false }, (_evt, filename) => {
    if (!filename || !filename.endsWith(".jsonl")) return;
    if (this.incuratorClient.isOwnDeviceFile(filename)) return; // never react to self
    this.scheduleDebouncedImport(); // 3–5s debounce; coalesce bursts from Syncthing
  });
  this.register(() => this.syncWatcher?.close());
}
```

- Debounce coalesces Syncthing's chunked delivery into one import pass.
- Always ignore the device's own file (loop safety at the UI layer too).

### 1.3 Non-blocking status UI

All import/export run in the backend subprocess (`callBackendJson`), so the UI thread
never parses JSONL. Surface progress with the existing status-bar pattern:

- Status bar: `⟳ Syncing…` while a subprocess is in flight; `✓ Synced · 12↓ 3↑` after.
- A `Notice` only when peers actually delivered changes (`inserted+updated+deleted > 0`),
  matching Zotero's quiet behavior. No noise on no-op syncs.

### 1.4 Modals (driven by backend signals)

- **Conflict modal**: if `wiki db autosync --json` returns `conflict_files: [...]`
  (DB Architect `detect_conflict_files`), show a modal: "Sync conflict files detected.
  These are safe to merge (LWW). [Merge & archive] / [Show files]". Merging = import them
  as ordinary peer files, then move to `.curator/sync/_archive/`.
- **Mismatch modal**: backend returns `local_unexported: true` (local max(updated_at) >
  device's `last_export_ts`) AND a newer peer arrived → "You have local changes not yet
  exported, and new remote data arrived. [Export mine first, then import] (recommended) /
  [Import anyway]". LWW makes either safe, but exporting first preserves intent.

### 1.5 Settings (additive, all default-safe)

```ts
autoSyncEnabled: boolean;     // default true
autoSyncOnLoad: boolean;      // default true
autoSyncWatch: boolean;       // default true (fs.watch)
autoSyncNotify: boolean;      // default true (Notice on real changes only)
```

Plus the manual ribbon button (restored, but now calling `wiki db autosync`, not the
old hardcoded-date import).

## 2. Pros & Cons

**Pros**
- Triggers map to real DB-mutation events, not unrelated keystrokes.
- `fs.watch` covers the Syncthing download-lag race directly (late file → live import).
- UI never blocks; matches Zotero's quiet, status-driven UX.

**Cons / limits**
- `fs.watch` semantics vary by OS (macOS/Linux/Windows); needs the debounce + a periodic
  `registerInterval` fallback poll (e.g., every 60 s) for platforms where `watch` misses
  events.
- Obsidian mobile has no Node `fs` — auto-watch is desktop-only; mobile falls back to
  on-load + manual button. Must feature-detect and degrade, not crash.
