# v0.77.0 Evidence Ledger

Written before the first code change.

## Rollback anchor

`master` at `b0c0dfe` (v0.76.0). Branch `release/v0.77.0`.

## Reality as measured, 2026-08-31

All established by reading the tree and the user's live config. `agy` was never
invoked.

| Claim | Where | Verified |
|---|---|---|
| Local PDF tools are never injected on the CLI path | `messageUtils.ts:60-77` — `if (useCli) return false` under `local-only` | read |
| antigravity routes through the CLI | `shouldUseCli`, `LLMClient.ts:1788` | read |
| The popover prompt promises a page-fetch tool anyway | `promptRegistry.ts` `case "local-only"` | read |
| The popover claims "NO MCP tools" | same string | read |
| That claim is false for agy | `syncAgyMcpConfig()` unconditional in `case "antigravity"`, `LLMClient.ts:2658`; `ephemeral` only empties `--add-dir` | read |
| `incurator_fetch` is registered for the user | `~/.gemini/config/mcp_config.json` → `['incurator', 'incurator_fetch']` | read |
| The popover feeds only the selection to citation resolution | `quickQueryPopover.ts:537` | read |
| The sidebar feeds the typed message | `ChatSidebarView.ts:1455` | read |
| Bibliography heading regex is English-only | `citationResolver.ts:45` | read |
| Denial stderr is promoted to the answer | `LLMClient.ts:2166-2172`, filter at `messageUtils.ts:296-304`, empty-check at `LLMClient.ts:2224-2241` | read |
| agy has no per-invocation MCP config flag | static `strings` on the installed binary; `agyPermissionLive.test.ts:52-55` | inspected, not executed |

## The fetch guard, measured

Ran the shipped `fetch_mcp_server.js` over JSON-RPC directly — our own node
script, not `agy`:

| Target | Result |
|---|---|
| `http://127.0.0.1:8731/` | blocked |
| `http://localhost:8731/` | blocked |
| `http://[::ffff:127.0.0.1]:8731/` | blocked |
| `http://169.254.169.254/latest/meta-data/` | blocked |
| `file:///etc/passwd` | refused — "Only http:// and https:// URLs are supported" |

Redirect targets are re-checked (`checkUrl` on `res.headers.location`) and the
pinned lookup is reused for the redirect hop. Only 301/302 are followed; 303/307/
308 are not — a capability gap, not a hole. Noted for ROADMAP.

This matters only because the release leaves `fetch_url` reachable; nothing here
depends on it.

## Pre-change baseline

- backend pytest 1884 passed / 7 skipped
- plugin vitest 1151 passed / 3 skipped
- `tsc --noEmit` clean, ruff clean, mypy clean over 132 files

## Post-change results

_(filled in per phase)_
