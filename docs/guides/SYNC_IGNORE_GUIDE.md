# Syncthing & Git Sync Ignore Guide

This guide provides a collection of ignore settings useful when synchronizing your knowledge base (Vault) across multiple devices or managing it with Git.

---

## 1. .stignore (Syncthing Exclusive)

When using Syncthing for real-time synchronization, you must exclude the following items to prevent database locking issues or unnecessary conflicts.

```text
// Ignore internal Git repository (Most Important)
.git
.git/
.gitmodules

// OS and Tool-related temporary files
.DS_Store
Thumbs.db
.idea/
.vscode/
.venv/
__pycache__/
*.pyc
.env

// SQLite temporary files (For Incurator project)
*.sqlite-*
*.db-*

// Ignore dependency folders to reduce Syncthing load
node_modules/
**/node_modules/

// Incurator plugin: keep settings local when backend executable paths differ
// sessions.json supports session-level merge-on-save in v0.2.1 and may sync
.obsidian/plugins/incurator-obsidian-agent/data.json

// Incurator backend: per-device DB and internal search state
// Vault files synchronize through Syncthing; DB-native search rows rebuild per device
.curator/state.sqlite

// Incurator runtime: volatile status and job files
// Syncing these causes massive conflicts and battery drain
.curator/runtime/

// Incurator auto-sync: per-device local marks (device_id, peer high-water marks)
// Must stay local — syncing it makes devices overwrite each other's marks and
// trigger re-import storms. NOTE: do NOT exclude .curator/sync/ — those dev-*.jsonl
// knowledge snapshots are exactly what Syncthing must carry between devices.
.curator/sync_state.json

// Agent & Testbed (Optional)
.claude/
testbed/
```

> [!IMPORTANT]
> Cross-device auto-sync (`wiki db autosync`) relies on Syncthing carrying the
> `.curator/sync/dev-<device_id>.jsonl` snapshot files. Keep `.curator/sync/`
> **synced**; only `.curator/state.sqlite` and `.curator/sync_state.json` are
> device-local. See USER_GUIDE "Cross-Device Knowledge Sync" and SYSTEM_BEHAVIOR §13.1.

> **Note**: `sessions.json` may be synchronized in v0.2.1 because the plugin merges by session id before saving and records delete tombstones in `deletedSessionIds`. Keep `data.json` local if settings contain per-device paths such as MCP commands, backend executable paths, or Zotero paths.

### Obsidian Plugin Deployment Across macOS/Linux

The Incurator Obsidian plugin is deployed into the active vault as `.obsidian/plugins/incurator-obsidian-agent/main.js`, `manifest.json`, and `styles.css`. If Syncthing does not ignore the whole `.obsidian/plugins/incurator-obsidian-agent/` folder, deploying from Linux with `plugin/deploy.sh` will synchronize those built files to macOS.

Keep per-device files such as `data.json` ignored when backend paths differ. Settings that contain absolute paths, such as backend command paths, may differ between Linux and macOS and should be configured on each device.

If Incurator is not installed globally on macOS, set `Backend command` and
`Backend arguments` in the Obsidian plugin settings to a macOS-specific launcher.
See the session sync section in `PLUGIN_GUIDE.md` for a `uv` example.

### Syncthing Device Registry

On startup, the Obsidian plugin reads the local Syncthing `config.xml` and
records the devices that share the current vault in `.curator/devices.json`.
Syncthing knows device ids, device names, folder ids, folder labels, and the
current machine's folder path.

Backend executable paths are not Syncthing data, so Incurator records them as
per-device entries.

Normal use does not require a command. Syncthing synchronizes the plugin build
outputs, and each device refreshes the registry when the Obsidian plugin loads.
The CLI commands below are only for repair or terminal inspection.

On each refresh, `.curator/devices.json` is reconciled against the current
Syncthing folder membership. Backend hints for still-present devices are kept,
but device ids no longer shared with the vault are removed so old machines do
not keep appearing in the dashboard.

```bash
wiki devices
wiki devices sync
wiki devices status
```

`wiki devices` is shorthand for `wiki devices status` and lists every device
known in the registry, even when a device only has Syncthing metadata and no
backend launcher hint yet.

### Reference PDFs Across Devices

For external PDFs, **Add to Incurator** creates a lightweight markdown reference
stub under `04_Resources/` and records the real local file path in backend
source metadata. The stub may synchronize through Syncthing with the vault, but
it should not contain an absolute PDF path by default because each device may
mount its Zotero or external PDF library at a different location.

The intended sharing model is:

- `04_Resources/` reference stubs: synchronize through Syncthing with the vault;
  do not rely on Git for large/private resource libraries.
- `.curator/Collections/`: may be shared through Git as generated knowledge
  artifacts when the project chooses to version them.
- `.curator/state.sqlite*` and `.curator/runtime/`: device-local runtime/index/volatile
  state; do not sync through Syncthing or Git.
- Backend executable/repository path: device-local; do not store as shared vault
  truth.
- Zotero/external PDF originals: may synchronize through a separate Syncthing
  folder, but Incurator cannot infer that path from the vault alone. Each device
  resolves or rebinds the reference using its local Zotero/external roots.

If macOS does not have `wiki` installed globally and must launch the repository
backend through `uv`:

```bash
wiki devices sync \
  --backend-command /opt/homebrew/bin/uv \
  --backend-args '["--directory", "/Users/<you>/Workspace/Incurator/backend", "run", "wiki", "mcp"]'
```

To deploy directly on macOS, pass the macOS vault plugin path to the same script.

```bash
cd /path/to/Incurator/plugin
OBSIDIAN_PLUGIN_DIR=/Users/<you>/path/to/second_brain/.obsidian/plugins/incurator-obsidian-agent ./deploy.sh
```

After Syncthing receives the built files, or after deploying directly on macOS, reload the Incurator plugin in Obsidian or restart Obsidian.

---

## 2. .gitignore (Git Exclusive)

Settings to exclude large files or local state when managing your knowledge base with Git.

```gitignore
# ==========================================
# 1. Database & Incurator Data (Recommended for Syncthing)
# ==========================================
# It is safer to leave DB files to real-time sync tools (like Syncthing) and exclude them from Git.
*.sqlite*
*.db*
.curator/

# ==========================================
# 2. Obsidian Local State
# ==========================================
# Backup plugins and core settings with Git, but ignore temporary workspace states.
.obsidian/workspace
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.trash/

# ==========================================
# 3. Python & Agent Environment
# ==========================================
.venv/
.idea/
.vscode/
.claude/
testbed/
tests/scenarios/
build/
dist/
.ruff_cache/
.lock/
__pycache__/
*.pyc
*.swp
.env

# ==========================================
# 4. Syncthing & OS Files
# ==========================================
.stversions/
.stfolder/
*.sync-conflict-*
.DS_Store
Thumbs.db

# ==========================================
# 5. Large files (Optional)
# ==========================================
# Consider excluding large resources or assets if they are heavy.
04_Resources/
05_Assets/
```

---

## 💡 Best Practices

1.  **SQLite DB Management**: The `state.sqlite` file is heavily updated and contains device-specific embedding vectors and machine paths. Synchronizing this via **Git OR Syncthing** will result in merge conflicts, file corruption (due to WAL/SHM locks), and broken embeddings on other devices. We recommend excluding DB files entirely and letting each device rebuild its own index locally (`wiki reindex`).
2.  **Conflict Prevention**: Ensure that database files and the `.curator/runtime/` directory are properly ignored in both Git and Syncthing to prevent massive conflicts and battery drain.
3.  **Syncthing Tip**: After setting up your Vault folder in Syncthing, go to folder settings -> "Ignore Patterns" tab, and paste the contents of the `.stignore` section above.
