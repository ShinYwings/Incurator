# Syncthing Device Auto-Detection Plan

## Goal

Make Incurator's `.curator/devices.json` accurately track the Syncthing state
for the active vault across realistic lifecycle scenarios:

- A user adds an existing vault folder to Syncthing on the current device.
- A user accepts/registers that vault on a new device.
- A device is removed from the shared folder.
- The vault folder is removed from Syncthing on one device.
- A Syncthing device is renamed.
- Syncthing is installed but not running.
- Syncthing is running with HTTPS/self-signed GUI certificate.
- Obsidian starts before Syncthing finishes receiving the vault.

## Relevant Current Contracts

- `docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.2.2.md`
  - Section 13 defines `.curator/devices.json` as sync-friendly device metadata.
  - Syncthing facts are limited to device ids, names, shared folder ids, labels,
    and local folder paths.
  - Backend launch paths are not Syncthing facts; each local Incurator instance
    writes its own backend/platform hint.
- `docs/guides/SYNC_IGNORE_GUIDE.md`
  - The Obsidian plugin currently refreshes `.curator/devices.json` on startup.
  - `wiki devices sync` is the manual repair/debug command.

## Official Syncthing API Notes

Syncthing exposes a local REST API on the GUI port. It requires the API key from
the local configuration and accepts `X-API-Key` or bearer auth. When HTTPS uses a
Syncthing-generated/self-signed certificate, clients need an equivalent of
`curl -k`.

Useful endpoints:

- `GET /rest/system/status`
  - Local runtime facts, including the local device id (`myID`).
- `GET /rest/config`
  - Full active config.
- `GET /rest/config/folders`
  - Current folder configs.
- `GET /rest/config/devices`
  - Current device configs.
- `GET /rest/cluster/pending/folders`
  - Folders offered by remote devices but not accepted locally.
- `GET /rest/cluster/pending/devices`
  - Remote devices known as pending.
- `GET /rest/events`
  - Blocking long-poll stream. Can be filtered by event type and resumed by
    `since=<lastSeenID>`.

## Source Of Truth Strategy

Use a layered discovery model:

1. **Runtime REST API, if Syncthing is running.**
   - Read `config.xml` only to discover GUI address, TLS mode, and API key.
   - Call `/rest/system/status` for `myID`.
   - Call `/rest/config/folders` and `/rest/config/devices` for active config.
   - Call pending endpoints for device/folder offers that are not active yet.
2. **Static `config.xml`, if REST is unavailable.**
   - Parse folders/devices from disk.
   - Infer local device id by hostname only as fallback.
   - Mark `syncthing.runtime_available=false`.
3. **Existing `.curator/devices.json`, only for Incurator-owned hints.**
   - Preserve backend/platform hints for device ids that remain active.
   - Preserve current device backend/platform if local id is known.
   - Do not preserve stale devices as active just because they existed before.

## Registry Shape

Extend `.curator/devices.json` without breaking current readers:

```json
{
  "version": 1,
  "updated_at": 1780356898,
  "local_device_id": "DEVICE-ID",
  "syncthing": {
    "runtime_available": true,
    "config_path": ".../config.xml",
    "gui_address": "https://127.0.0.1:8384",
    "config_version": "51",
    "folders": [],
    "devices": [],
    "pending_folders": [],
    "pending_devices": [],
    "last_event_id": 123
  },
  "devices": {
    "DEVICE-ID": {
      "device_id": "DEVICE-ID",
      "name": "MacOS",
      "state": "active",
      "syncthing": {},
      "platform": {},
      "backend": {},
      "updated_at": 1780356898
    }
  }
}
```

Device `state` values:

- `active`: device appears in the active Syncthing folder sharing list.
- `pending`: device/folder appears in Syncthing pending endpoints but is not
  active for the vault yet.
- `removed`: optional short-lived tombstone if needed for UI explanation, not
  required for normal pruning.

Prefer pruning removed devices from `devices` by default, matching the current
v0.2.2 contract.

## Scenario Handling

### Current Device Adds Existing Vault To Syncthing

Detection:

- REST/config shows a folder whose resolved path equals the vault root.
- `/rest/system/status.myID` identifies the local device.

Registry behavior:

- Create/update `syncthing.folders`.
- Add all folder device ids as `active`.
- Mark local device with backend/platform hints.

### New Device Accepts The Vault

Detection:

- On the new device, once the folder is accepted, REST/config has a folder path
  matching the local vault root.
- Before acceptance, pending folder endpoints may show the remote offer, but
  there may be no local path matching the vault root yet.

Registry behavior:

- Before acceptance: expose pending folder/device details, but do not claim the
  active vault is synced.
- After acceptance: local plugin/backend refresh writes this device's
  backend/platform hint under its real Syncthing device id.

### Device Removed From Folder

Detection:

- Active folder config no longer lists the device id.

Registry behavior:

- Remove that device from `devices`, unless keeping a short tombstone is later
  added for UI messaging.
- Do not preserve old backend hints for ids absent from active folder sharing.

### Vault Removed From Syncthing On Current Device

Detection:

- No REST/config folder path matches the vault root.
- `.curator/devices.json` may still exist because the vault files remain on disk.

Registry behavior:

- Set `syncthing.folders=[]`, `syncthing.devices=[]`.
- Remove `local_device_id` if the registry cannot prove the active vault is
  currently Syncthing-managed.
- Keep only an optional local backend hint if needed for non-Syncthing use, but
  mark `syncthing.runtime_available` and `managed=false` explicitly.

### Syncthing Device Renamed

Detection:

- Same device id, different device name in REST/config.

Registry behavior:

- Update `name`.
- Preserve backend/platform hints by device id.

### Syncthing Installed But Not Running

Detection:

- `config.xml` exists.
- REST calls fail.

Registry behavior:

- Parse static config.
- Mark `runtime_available=false`.
- Use hostname matching only as fallback for `local_device_id`.
- Surface a UI/CLI hint that runtime status is stale and Syncthing is not
  reachable.

### Obsidian Starts Before Vault Fully Arrives

Detection:

- Plugin may load before `.curator/` or `devices.json` is present.
- REST/config may already know the folder path.

Registry behavior:

- Plugin should retry device registry refresh after a short delay and when the
  dashboard opens.
- Backend command `wiki devices sync` remains the deterministic repair path.

## Implementation Steps

1. Backend discovery module
   - Add Syncthing REST helper functions in `backend/src/curator/device_registry.py`.
   - Keep `config.xml` parsing as fallback.
   - Add helpers for `GET /rest/config/folders`, `GET /rest/config/devices`,
     pending folders/devices, and event polling metadata.

2. Backend registry merge
   - Split discovery from merge:
     - `discover_syncthing(vault_root) -> SyncthingSnapshot`
     - `merge_device_registry(existing, snapshot, local_backend) -> registry`
   - Preserve Incurator-owned hints only for active/current ids.
   - Add `runtime_available`, `managed`, pending arrays, and local id confidence.

3. CLI behavior
   - `wiki devices sync` performs a full REST-first refresh.
   - `wiki devices` displays active, pending, and unmanaged states clearly.
   - Add a `--watch` option later only if needed; avoid a daemon for v0.2.2.

4. Plugin parity
   - Either call hidden backend JSON command for device refresh or port the same
     REST-first logic to TypeScript.
   - Prefer backend command for consistency if Obsidian can launch backend
     reliably.
   - If the plugin keeps direct writes, add TypeScript tests matching backend
     merge cases.

5. Event-driven refresh
   - Do not require long-running event polling in v0.2.2.
   - Use cheap refresh triggers:
     - plugin startup,
     - dashboard open,
     - settings save,
     - manual `wiki devices sync`.
   - Optional later enhancement: `wiki devices watch` uses `/rest/events` with
     filters for config/folder/device changes and stores `last_event_id`.

6. Tests
   - Backend pytest:
     - REST available with HTTPS self-signed context.
     - REST unavailable fallback to config.
     - folder added.
     - folder removed.
     - device removed.
     - device renamed.
     - pending folder/device surfaced but not active.
   - Plugin Vitest if direct plugin merge remains:
     - same lifecycle cases as backend.

7. Docs
   - Update system behavior spec first.
   - Update `SYNC_IGNORE_GUIDE.md` and `_KR`.
   - Update plugin guide EN/KR if plugin refresh behavior changes.

## Open Design Decision

Choose one of these boundaries before implementation:

1. Backend-only refresh.
   - Plugin asks backend to refresh device registry.
   - Pros: one implementation, better REST support in Python.
   - Cons: plugin cannot refresh devices until backend command is resolvable.

2. Dual implementation.
   - Backend CLI and plugin both perform the same merge logic.
   - Pros: plugin can refresh before backend path is known.
   - Cons: behavior can drift between Python and TypeScript.

Recommendation: backend-only for REST-rich refresh, with plugin retaining a
small static `config.xml` fallback only for first-run bootstrap.
