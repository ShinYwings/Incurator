# Problem Brief: Eliminate Manual "Repository Path" Config in Plugin

Date: 2026-06-07 | Author: main agent

## The Problem

The Obsidian plugin's settings require the user to manually enter an absolute
**"Repository path"** (`/path/to/Incurator`) for the 1-click backend/plugin
update feature to work. This is wrong for a multi-device, Syncthing-synced setup:

1. The repo path is a **machine-local absolute path**. On device A it might be
   `/home/shin/Workspace/Incurator`; on device B (macOS) `/Users/shin/Incurator`.
2. The user must remember and manually configure it on every device.
3. If it ever leaked into synced state, it would break peers (same class of bug
   we just fixed in v0.4.1 for `llm`/`search`/`external`).

## Current Reality (verified by Explore)

- `incuratorRepoPath` is stored in plugin `data.json` (`plugin/src/types.ts:105`).
- `data.json` is ALREADY excluded from Syncthing (`.stignore:28`) — so it does
  NOT leak across devices. Good. But it still must be set **manually per device**.
- The backend ALREADY knows its own location: `device_registry.backend_launcher()`
  returns `backend_root = Path(__file__).resolve().parents[2]`
  (`device_registry.py:205`).
- The status snapshot (`runtime_state.build_status_snapshot()`) reports
  `vault_root`, `wiki_binary`, `backend_version`, `collections` — but does NOT
  report the repo/source path explicitly.
- `updateIncuratorBackend()` (`main.ts:1021`) already copies built plugin files
  into the CURRENT vault via `getBasePath()`. It only needs `repoPath` to locate
  the SOURCE `plugin/main.js` + `manifest.json`.
- The plugin already caches backend command info in `devices.json` (per-device
  global cache) and reads it back to override stale synced settings.

## Decisions Locked (from user)

1. **Repo discovery = `__file__`-based auto.** Backend infers repo root from
   its own source location. If running from an editable install (`pip install -e`),
   `__file__` points at the real repo source. If running from a regular
   site-packages install, there is no repo to update → repo path is null →
   plugin hides the update button.
2. **Update scope = current open vault only.** `updateIncuratorBackend()` copies
   only into the vault Obsidian currently has open (`getBasePath()`). Other vaults
   update themselves when next opened.

## Success Criteria

- A fresh device requires ZERO manual "Repository path" entry for updates to work.
- Backend reports its repo path (or null) via a JSON command the plugin already calls.
- Plugin auto-resolves repo path from backend; manual setting becomes an optional
  override, not a requirement.
- When backend is a non-editable install (no repo), the plugin gracefully hides
  / disables the update action instead of erroring.
- No machine-local path is written into any synced artifact.

## Open Design Questions for the Arena

- Q1: How does the backend reliably detect "is this an editable/repo install vs
  site-packages"? (presence of `setup.sh` + `.git` at the inferred root?)
- Q2: Which JSON surface carries `repo_path` — `wiki plugin version`,
  the status snapshot, or `devices.json` backend block?
- Q3: How should the plugin settings UI change — remove the field, or keep it as
  a dimmed "(auto-detected: …)" override?
- Q4: Backward-compat: existing users have `incuratorRepoPath` already set. Honor
  it as an override, or always prefer backend's answer?
