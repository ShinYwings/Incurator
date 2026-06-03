# Zotero Backend/Plugin Redesign Plan

## Goal

Redesign Zotero integration so Incurator handles missing Zotero installs,
missing or moved Zotero data directories, linked-file base-directory changes,
and Obsidian PDF viewer path handoff without scattering Zotero state across
plugin settings and backend assumptions.

## Current State

Backend:

- `backend/src/curator/zotero_tools.py`
  - Expands `custom_paths` into `zotero.sqlite` candidates.
  - Searches `~/Zotero`, plugin-provided paths, backend config roots, and some
    Zotero/ZotMoov prefs-derived paths.
  - Provides hidden plugin JSON commands:
    - `wiki plugin zotero search`
    - `wiki plugin zotero metadata`
    - `wiki plugin zotero annotations`
    - `wiki plugin zotero resolve-pdf`
- `backend/src/curator/zotero.py`
  - Reads Zotero SQLite by copying DB to a temp file.
  - Resolves attachment paths for `storage:`/`attachments:`/absolute paths.
- `backend/src/curator/plugin_api.py`
  - Provides `pdf_context(file_path=...)`, which requires a readable absolute
    PDF path.

Plugin:

- `plugin/main.ts`
  - Calls backend Zotero commands with `--custom-paths` from
    `settings.zoteroBasePath`.
  - Opens Zotero links through `resolveZoteroPdf(attachmentKey)`.
- `plugin/src/settings.ts`
  - Stores `zoteroBasePath`, defaulting to `~/Zotero`.
- `plugin/src/ui/chatSidebar.ts`
  - For PDF question context, converts known vault-relative paths to absolute
    paths and calls `client.getPdfContext`.
  - External/Zotero PDF view usually has an absolute path in view state.
  - Obsidian's native PDF view only works when the view exposes a vault `TFile`.

## Official Zotero Constraints

From Zotero documentation:

- Zotero library data is stored in `zotero.sqlite` within the active Zotero data
  directory.
- Direct SQLite access is allowed only read-only. Writing directly risks
  corruption and bypasses Zotero validation.
- Stored attachments live under the Zotero data directory, normally in
  `storage/<attachment-key>/...`.
- Linked files store paths outside Zotero storage. Linked attachment base
  directory is per-device and is specifically intended for multi-computer setups
  where the same linked files live under different parent paths.
- Zotero data directory may be custom and moving it does not copy old data
  automatically.

Implication for Incurator:

- Backend may read Zotero DB and attachment files.
- Backend must never mutate Zotero DB.
- Zotero data directory and linked attachment base directory are per-device
  discovery facts, not vault-global truth.

## Source Of Truth Strategy

Use backend as the Zotero authority.

Plugin responsibilities:

- UI, user approval, and active viewer context.
- Passing `zotero://` attachment keys or open PDF paths to backend.
- Showing setup/repair prompts returned by backend.
- Storing only temporary UI choices and wizard profile templates.

Backend responsibilities:

- Discover Zotero installation/data roots.
- Validate whether `zotero.sqlite` exists and looks usable.
- Resolve attachment keys to absolute paths.
- Track per-device Zotero roots in backend-owned runtime/config state.
- Read annotations/metadata read-only.
- Register resolved PDFs as Incurator reference sources.

Avoid making `settings.zoteroBasePath` the canonical integration state. It can
remain as a UI override, but backend discovery/config should decide.

## Proposed Backend State

Add a backend-owned Zotero integration snapshot:

```text
.curator/runtime/zotero.json
```

Shape:

```json
{
  "ok": true,
  "state": "ready",
  "updated_at": 1780357000,
  "device_id": "KDZ...",
  "data_dir": "/Users/shin/Zotero",
  "db_path": "/Users/shin/Zotero/zotero.sqlite",
  "storage_dir": "/Users/shin/Zotero/storage",
  "linked_attachment_base_dir": "/Users/shin/Library/CloudStorage/...",
  "roots_checked": [],
  "issues": []
}
```

Possible states:

- `not_installed`: no Zotero profile/config/db candidates found.
- `not_configured`: Zotero may exist, but no valid data directory was found.
- `db_missing`: candidate data dir exists but `zotero.sqlite` is missing.
- `db_unreadable`: DB exists but cannot be opened/read.
- `attachments_missing`: DB is readable but a requested attachment cannot be
  resolved locally.
- `ready`: DB and roots are usable.
- `moved`: previous DB/root path is broken but a likely replacement was found.

Persist durable per-device settings in `.curator/devices.json` or backend
config, not plugin `data.json`, for example:

```json
{
  "devices": {
    "DEVICE-ID": {
      "zotero": {
        "data_dir": "...",
        "linked_attachment_base_dir": "...",
        "last_ok_at": 1780357000
      }
    }
  }
}
```

Do not sync one device's absolute Zotero path as authoritative for another
device. If stored in `.curator/devices.json`, it must be nested under that
device id.

## Init Flow

### `wiki init`

Do not require Zotero.

Behavior:

- Initialize vault normally.
- Run a non-fatal Zotero probe.
- Write `.curator/runtime/zotero.json` if possible.
- If missing, show: "Zotero not configured; use plugin Zotero setup or
  `wiki zotero init` later."

Rationale:

- Many users do not use Zotero.
- A new synced device might not have Zotero installed yet.
- Failing `wiki init` because Zotero is missing is wrong.

### `wiki zotero init` or Hidden Plugin `wiki plugin zotero init`

Add a backend-owned setup command.

Inputs:

- Optional `--data-dir`
- Optional `--linked-base-dir`
- Optional `--auto`

Outputs:

- JSON diagnosis:
  - roots checked,
  - chosen DB,
  - linked base dir,
  - warnings,
  - next action.

Rules:

- If exactly one valid DB is found, accept it.
- If multiple DB candidates are found, return choices; plugin asks user.
- If a previous configured path is missing but another candidate has a valid DB,
  return `state=moved` and require user confirmation before updating config.
- If only `storage/` exists without `zotero.sqlite`, report `db_missing`; do not
  try to reconstruct Zotero metadata from storage alone.

### Plugin First Run

On startup or when user opens Zotero import/search:

1. Plugin calls `wiki plugin zotero status`.
2. If `ready`, plugin enables Zotero search/import.
3. If not ready, plugin opens setup UI using backend-provided candidates.
4. User approval calls `wiki plugin zotero init --data-dir ...`.

The plugin should not be responsible for discovering platform-specific Zotero
profile internals beyond presenting backend choices.

## Attachment Resolution

Backend resolution order:

1. If an open PDF absolute path was passed by plugin and exists, use it.
2. If Zotero attachment key is passed:
   - read DB row from `itemAttachments.path`;
   - resolve `storage:` under Zotero data dir;
   - resolve `attachments:`/relative linked paths under linked attachment base
     dir first, then configured roots;
   - accept existing absolute paths;
   - if missing, scan known roots for likely matching filename/key only as a
     repair candidate, not silently as truth.
3. If no key but hash/path exists, use Incurator source registry rebind logic.

When resolved path differs from cached source path:

- return a rebind proposal;
- plugin asks user;
- backend applies rebind and updates Incurator source, not Zotero DB.

## PDF Question Path Handoff

Current status:

- Backend PDF context is available via `wiki plugin pdf context --file-path`.
- Plugin `IncuratorClient.getPdfContext()` calls that command.
- External/Zotero PDF view stores an absolute path in view state, so backend can
  read those files if `resolveZoteroPdf()` succeeds.
- Obsidian native PDF view only works if the plugin can derive a vault `TFile`
  path and convert it to an absolute path.
- If the native viewer does not expose a filesystem path, backend cannot read
  the PDF; plugin falls back to PDF.js viewer-captured text/image context.

Problem not fully solved:

- The backend cannot read "a PDF from Obsidian" unless plugin passes a real
  filesystem path or the PDF bytes.
- Current design passes paths, not bytes.

Recommended fix:

- Add backend command `wiki plugin pdf context` support for one of:
  - `--source-id`
  - `--zotero-attachment-key`
  - `--vault-relpath`
  - optional future stdin/temp-file bytes for pathless viewer content.
- Plugin should pass the richest identity it has:
  - external absolute path,
  - Zotero attachment key,
  - vault-relative path,
  - file hash.
- Backend resolves identity to a path using Zotero/source registry before
  returning PDF context.

This avoids plugin-side path guessing and lets backend manage moved Zotero files.

## User-Facing UX

Zotero Dashboard Card:

- `Ready`: show DB path, linked base dir, last checked, attachment root status.
- `Not installed`: show install/configure prompt.
- `Data dir missing`: show previous path and "Choose Zotero Data Directory".
- `Moved`: show old path and detected candidate, require confirmation.
- `Attachment missing`: show item/attachment key and repair candidate if found.

Import Wizard:

- Before search, call backend status.
- If not ready, route to setup instead of returning empty search.
- Empty search should mean "DB readable, no matching items", not "Zotero missing".

PDF Viewer:

- For Zotero links, keep using backend `resolve-pdf`, but error messages should
  distinguish DB missing, attachment missing, and linked base dir mismatch.
- For native PDFs without a path, show "viewer-only context" state and do not
  pretend backend RAG is available.

## Tests

Backend pytest:

- no Zotero installed -> `state=not_installed`
- default `~/Zotero/zotero.sqlite` found -> `ready`
- custom moved data dir -> `moved`
- directory exists without `zotero.sqlite` -> `db_missing`
- readable DB with `storage:` attachment -> resolves path
- readable DB with linked attachment base dir -> resolves path
- missing linked file -> returns repair candidate or `attachments_missing`
- direct SQLite access remains read-only
- `plugin pdf context --zotero-attachment-key` resolves before reading PDF

Plugin Vitest:

- Zotero search first calls backend status/init path.
- Missing Zotero opens setup state, not empty search.
- `resolveZoteroPdf` surfaces structured errors.
- PDF context request passes attachment key/vault relpath when available.

## Docs

Update in order:

1. `docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.2.2.md`
2. `docs/specs/plugin_schema/PLUGIN_SCHEMA_v0.2.2.md`
3. `docs/guides/PLUGIN_GUIDE.md`
4. `docs/guides/PLUGIN_GUIDE_KR.md`
5. `docs/guides/USER_GUIDE.md`
6. `docs/guides/USER_GUIDE_KR.md`

## Recommendation

Backend should own Zotero initialization and repair. Plugin should own UI and
user approval.

Reasons:

- Zotero DB and attachment resolution are filesystem/backend concerns.
- Backend already owns durable source registration and rebind.
- Plugin settings are device-local UI state and should not become source truth.
- Backend can provide consistent JSON diagnosis for CLI, plugin, and external
  agents.

Keep a small plugin override field for convenience, but treat it as an input to
backend probing, not as canonical state.

## 2026-06-02 Implementation Slice

Implemented first backend-owned slice:

- Added hidden plugin commands `wiki plugin zotero status` and
  `wiki plugin zotero init`.
- Changed Zotero search/metadata/annotations/resolve-pdf commands to accept the
  workspace path and backend config roots instead of requiring plugin-only
  custom paths.
- Extended `wiki plugin pdf context` so the plugin can pass a source id,
  relpath/source path, file hash, absolute file path, or Zotero attachment key.
- Kept Reference Mode canonical: synced `04_Resources/References/*.md` stubs do
  not store absolute paths, while the local backend DB keeps `external_path` for
  this device.
- Added backend tests for Zotero status/init and identity-based PDF context, plus
  a plugin client test for richer PDF context arguments.
- Added Zotero fixture DB tests for `storage:` attachments, `attachments:`
  linked roots, missing attachment keys, and missing linked files.
- `resolve-pdf` now returns structured states: `db_missing`,
  `attachment_key_missing`, and `attachment_file_missing`.

Remaining work:

- Replace the settings-level status/init buttons with a richer repair modal if
  the current lightweight UI is not enough for moved directories or linked
  attachment mismatch.
- Add user-facing candidate selection when multiple linked roots contain repair
  candidates.
