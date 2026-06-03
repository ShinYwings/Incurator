# Plugin ↔ Backend Local Sharing Plan

Date: 2026-06-02

## Goal

Remove the Obsidian plugin's dependency on MCP for Incurator-internal backend
metadata and find a simpler local sharing boundary for plugin/backend
coordination.

The immediate trigger is the model catalogue issue: the plugin needs
`backend/src/curator/data/models.json`, but fetching a local backend-owned
configuration list through MCP tool discovery is slower and more fragile than a
direct local protocol.

## Current Evidence

- `backend/src/curator/data/models.json` is already the backend source of truth.
- Backend exposes it through `curator.models.get_available_models()` and the MCP
  tool `get_available_models`.
- Plugin `IncuratorClient` currently wraps `MCPManager` and discovers/calls MCP
  tools for local operations:
  - `get_available_models`
  - `curator_get_version`
  - `check_source_status`
  - `curator_import_source`
  - `curator_rebind_source`
  - `fetch_document_section`
  - `curator_search_sources`
  - `curator_query`
  - `promote_exhibition`
  - Zotero resolver tools
- Plugin startup previously started the generated Incurator MCP server
  (`wiki mcp`) and then asked MCP for model metadata. v0.2.2 now uses bundled
  model metadata, runtime snapshots, and hidden `wiki plugin ...` JSON commands.
- Existing docs/specs currently define the plugin/backend boundary as MCP, so
  this is an architecture change and must update specs, guides, tests, and code
  together.

## Revised Decision

Do not add `wiki plugin-ipc`.

For static or slowly changing backend-owned metadata, use direct shared
artifacts:

- The model catalogue is static package metadata. The plugin should import
  `backend/src/curator/data/models.json` at build time and bundle it into
  `main.js`.
- Runtime model dropdowns should read the bundled catalogue synchronously.
- The backend still uses the same JSON file through `curator.models`.
- The MCP `get_available_models` tool may remain for external agents, but the
  plugin must not depend on it.

For dynamic backend state, do not treat "same device" as permission to bypass
backend ownership. Split the state by mutation risk:

- Read-only UI state can be exposed as shared files under `.curator/`, such as
  JSON status snapshots written by the backend and read by the plugin.
- Backend-owned mutations must still go through an explicit backend API boundary.
  If we reject long-lived plugin IPC and MCP, the remaining simple boundary is
  explicit CLI commands for user actions, not hidden background tool calls.
- Direct plugin writes to `.curator/state.sqlite` remain prohibited.

## Why Shared Memory Is Not the First Choice

True shared memory requires both sides to have live processes and a platform
specific synchronization protocol:

- Node/Electron and Python need a common shared-memory or memory-mapped file
  layout.
- Locking, crash recovery, versioning, and cleanup become harder than the data
  being shared.
- It does not help static metadata like `models.json`, because no backend
  process needs to be alive.
- It is not a good persistence boundary for Obsidian plugin reloads or backend
  CLI runs.

For this project, "shared local artifact" is the practical version of the same
idea: the backend writes/owns durable files, and the plugin reads those files
directly when the data is safe to read.

## Immediate Implementation: Model Catalogue

Use build-time sharing:

1. Add a plugin helper that imports:

   ```typescript
   import modelsJson from "../../../backend/src/curator/data/models.json";
   ```

2. Normalize the backend JSON shape into plugin `ModelCatalogue`.
3. Initialize `availableModels` from that bundled catalogue.
4. Make `refreshAvailableModels()` reload the bundled catalogue, not MCP.
5. Remove model-dropdown loading/retry behavior tied to Incurator MCP startup.
6. Keep backend tests guarding `models.json` shape.
7. Add plugin tests that prove the bundled catalogue contains backend model IDs.

This means model names appear even when:

- MCP is disabled.
- no backend process is running.
- tool discovery has not finished.

The tradeoff is rebuild coupling: changing `backend/src/curator/data/models.json`
requires rebuilding/redeploying the plugin bundle. That is acceptable for model
catalogue metadata.

## Dynamic Backend Alternatives

### Option A — Shared Status Snapshots

Backend writes read-only JSON snapshots:

- `.curator/runtime/source_status.json`
- `.curator/runtime/jobs.json`
- `.curator/runtime/model_catalogue.json` if build-time bundling is not enough

Plugin reads them through the Obsidian vault adapter. This is fast and needs no
process, but it is only suitable for read-only UI.

### Option B — Direct SQLite Read-Only

Plugin opens `.curator/state.sqlite` read-only for status dashboards.

Downside: the plugin currently has no SQLite dependency. Adding one to an
Obsidian plugin increases bundle/native compatibility risk. Prefer JSON
snapshots first.

### Option C — Explicit CLI Per User Action

For mutations such as import/rebind/promote/query:

- Plugin spawns `wiki <command> --json ...` only after explicit user action.
- No long-lived backend process.
- No MCP tool discovery.

This is slower than a daemon but much simpler and aligned with "do not keep a
backend process around."

### Option D — True Shared Memory / mmap

Not recommended for current scope. It adds synchronization complexity without
removing the need for a backend execution boundary for mutations.

## Updated Recommendation

Phase 1: fix models with build-time `models.json` sharing. Remove all plugin
runtime calls to `get_available_models`.

Phase 2: add backend-written JSON status snapshots for read-only plugin status
panels.

Phase 3: replace remaining plugin MCP mutation/query calls with explicit
JSON-emitting CLI commands, one command per user-approved action.

MCP remains only for external agents.

## Superseded IPC Proposal

The following IPC process proposal is preserved as rejected context. Do not
implement it unless the architecture decision changes.

## Rejected: Dedicated Plugin IPC Process

Use a direct local child-process JSON-RPC transport for Obsidian plugin ↔ backend.

MCP remains supported for:

- Claude Code, Antigravity, Cursor/Codex, Gemini, and other external agent
  runtimes.
- User-visible MCP configuration for non-Incurator custom servers.
- External agent workflows documented in `MCP_USER_GUIDE`.

The plugin uses IPC first for Incurator-owned backend calls and falls back to MCP
only when IPC is unavailable or the backend is too old to support it.

## Why Not Read `models.json` Directly From the Plugin?

Direct file reads would be fast for `models.json`, but they would solve only one
symptom and create a second source/path problem:

- Installed backend package data may not live under the repo path the plugin can
  infer.
- Future backend-owned metadata may need normalization logic, version checks, or
  package-resource loading.
- Other plugin calls still need backend code for database state, source status,
  Zotero path resolution, and query synthesis.

The correct boundary is not "plugin reads backend files"; it is "plugin calls a
backend-owned local API without MCP ceremony."

## Transport Shape

Add a backend command:

```bash
wiki plugin-ipc
```

Transport:

- child process spawned by Obsidian plugin with stdio pipes
- newline-delimited JSON-RPC 2.0
- no MCP initialize handshake
- no `tools/list`
- no tool-name discovery
- fixed method names and typed payloads

Example request:

```json
{"jsonrpc":"2.0","id":1,"method":"models.available","params":{}}
```

Example response:

```json
{"jsonrpc":"2.0","id":1,"result":{"ok":true,"providers":{"antigravity":[...]}}}
```

This keeps process management simple and cross-platform. Unix sockets or named
pipes are unnecessary until multiple plugin windows/processes need to share one
long-lived backend daemon.

## Method Map

Initial IPC methods should mirror the current plugin-facing surface, not the
entire MCP tool list:

| IPC method | Backend implementation source |
| --- | --- |
| `backend.version` | same logic as `curator_get_version` |
| `models.available` | `curator.models.get_available_models()` |
| `source.status` | same core function as `check_source_status` / `curator_source_status` |
| `source.import` | same core function as `curator_import_source` |
| `source.rebind` | same core function as `curator_rebind_source` |
| `document.section.fetch` | same core function as `fetch_document_section` |
| `document.window.fetch` | same core function as PDF window/context tools |
| `document.search` | same core function as `curator_search_sources` |
| `query.curator` | same core function as `curator_query` |
| `exhibition.promote` | same core function as `promote_exhibition` |
| `zotero.pdf.resolve` | same core function as `curator_resolve_zotero_pdf` |
| `zotero.metadata.get` | same core function as Zotero metadata tool |
| `zotero.annotations.get` | same core function as Zotero annotations tool |

Do not duplicate behavior inside the IPC layer. Extract shared Python functions
from `mcp_server.py` where needed so MCP and IPC call the same code.

## Backend Implementation Plan

1. Add `backend/src/curator/plugin_ipc.py`.
   - Implement a small JSON-RPC stdio loop.
   - Use one request per line and one response per line.
   - Return JSON-RPC errors for unknown methods, invalid params, and backend
     exceptions.
   - Include `workspace_path` / `vault_root` handling consistently with MCP.

2. Add `wiki plugin-ipc` Typer command in `backend/src/curator/cli.py`.
   - Respect `VAULT_ROOT`.
   - Keep stdout reserved for JSON-RPC.
   - Send logs to stderr only.

3. Extract shared backend service functions where the current MCP code embeds
   logic inline.
   - Minimum first pass can support `backend.version` and `models.available`.
   - Broader migration should move source status/import/query/Zotero calls next.

4. Keep `wiki mcp` unchanged for external agents.

## Plugin Implementation Plan

1. Add `plugin/src/agent/incuratorIpcClient.ts`.
   - Spawn `wiki plugin-ipc` using the same command resolution currently used by
     `ensureIncuratorBackend`.
   - Send JSON-RPC requests with timeouts.
   - Maintain ready/available state independent of `MCPManager`.
   - Shutdown child process on plugin unload.

2. Refactor `IncuratorClient` into a transport-neutral facade.
   - Preferred transport: `IncuratorIpcClient`.
   - Fallback transport: existing MCP-backed client for backward compatibility.
   - Preserve existing public methods used by UI code.

3. Start IPC instead of Incurator MCP during plugin startup.
   - Continue starting user-configured non-Incurator MCP servers.
   - Do not auto-register/start `wiki mcp` solely for plugin-internal calls.
   - Leave settings UI for external MCP servers intact.

4. Update model catalogue loading.
   - `refreshAvailableModels()` calls `models.available` through IPC.
  - No Incurator MCP fallback remains for plugin-local backend operations.
   - The UI should still show loading and retry when the backend process is
     starting.

## Documentation Updates

Required before code lands:

- `docs/specs/plugin_schema/PLUGIN_SCHEMA_v0.2.2.md`
  - Replace "plugin wraps MCP" with "plugin uses local backend JSON commands
    and does not use Incurator MCP fallback."
  - Add `PluginBackendTransport` contract.
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.2.2.md`
  - Define MCP as external-agent interface and IPC as plugin-local interface.
- `docs/specs/curator_schema/SCHEMA_v0.2.2.md`
  - Clarify that payload contracts must be shared between IPC and MCP where they
    expose the same operation.
- `docs/guides/PLUGIN_GUIDE.md` and `_KR.md`
  - Explain that the plugin starts a local backend IPC process.
  - Keep custom MCP server configuration documented separately.
- `docs/guides/MCP_USER_GUIDE.md` and `_KR.md`
  - Clarify that MCP is still for external agents, not required for normal
    plugin/backend operation.

## Test Plan

Backend:

- `backend/tests/test_plugin_ipc.py`
  - starts the IPC loop against stdin/stdout or invokes request handlers
  - verifies `backend.version`
  - verifies `models.available` returns providers from `models.json`
  - verifies unknown method returns JSON-RPC error
- Existing `backend/tests/test_v021_models.py` remains the source-of-truth guard.

Plugin:

- `plugin/src/agent/incuratorClient.test.ts`
  - verifies backend JSON commands are used for version, source status,
    import/register, PDF context/search, query, and promotion
  - verifies no Incurator MCP fallback is needed

Smoke:

```bash
backend/.venv/bin/pytest backend/tests/test_plugin_cli.py backend/tests/test_v021_models.py -q
cd plugin && npm test -- --run src/agent/incuratorClient.test.ts src/utils/backendCommandBoundary.test.ts
cd plugin && env OBSIDIAN_PLUGIN_DIR= npm run build
```

If a real Obsidian smoke is available, verify:

- model dropdown shows backend models immediately after plugin load
- Incurator MCP server is not required for the model dropdown
- external/custom MCP servers still start

## Migration Strategy

Phase 1: IPC for lightweight metadata

- Add IPC command and client.
- Route `backend.version` and `models.available` through IPC.
- Route source/query/Zotero operations through hidden backend JSON commands.
- This directly fixes the model-list fragility with minimal blast radius.

Phase 2: IPC for plugin-owned source/document operations

- Move source status/import/rebind/document fetch/search to IPC.
- Keep payloads identical to existing MCP responses.

Phase 3: IPC for query/promote/Zotero

- Move `curator_query`, `promote_exhibition`, and Zotero tools to IPC.
- Keep MCP equivalents as public external-agent wrappers over the same backend
  service functions.

## Risks and Guardrails

- Do not let the plugin write `.curator/state.sqlite` directly. IPC is a backend
  API boundary, not permission to bypass backend ownership.
- Do not remove MCP. External agents need it.
- Keep stdout clean for JSON-RPC in `wiki plugin-ipc`; all human logs must go to
  stderr.
- Avoid a daemon/socket design in the first pass. A child-process stdio protocol
  is enough and easier to debug.
- Keep method names stable and versioned enough for plugin/backend mismatch
  detection.

## Open Decisions

These should be aligned before implementation. `/grill-me` is recommended if we
want to lock the architecture interactively.

1. Should Phase 1 ship only `backend.version` + `models.available`, or should it
   migrate all current `IncuratorClient` methods in one larger change?
2. Should settings expose a transport mode (`auto`/`ipc`/`mcp`) for debugging, or
   should this remain internal with IPC-first fallback?
3. Resolved: same-device backend access uses clearer
   `incuratorBackendCommand` / `incuratorBackendArgs` settings. Incurator MCP is
   external-agent only.

## Recommendation

Implement Phase 1 first.

That gives the immediate benefit for model catalogue speed/reliability, proves
the transport, and avoids destabilizing source registration/query flows during
the same patch. After Phase 1 passes tests and a real plugin load, migrate the
heavier methods in Phase 2/3.
