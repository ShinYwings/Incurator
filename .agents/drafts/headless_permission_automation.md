# Draft: Headless Agent Fetch MCP Auto-Injection

## Status: IMPLEMENTED (Gemini, 2026-08-24) — needs Executor review

## What was done

The Antigravity CLI in headless mode auto-denies `curl`, `pdfinfo`, and any
shell utility not in the `command(wiki)` whitelist. Users saw
`permission check failed for command "curl ..."` errors with no workaround
short of manually editing `~/.gemini/antigravity-cli/settings.json`.

### Changes made (unstaged, no commit)

**`plugin/src/agent/llm/LLMClient.ts`** (+150 lines)
- Added `FETCH_MCP_SERVER_SCRIPT`: a zero-dependency Node.js MCP stdio server
  embedded as a string constant. Exposes a single `fetch_url` tool (GET-only,
  30s timeout, 100KB truncation, 1-hop redirect follow).
- Modified `syncAgyMcpConfig()`: on every agy CLI invocation, writes the
  script to `~/.gemini/incurator/fetch_mcp_server.js` and registers it as
  `incurator_fetch` in the agy `settings.json`. Skips injection if the user
  already has a server with that key.
- **[2026-08-24 PM Fixes applied]**: 
  - Added strict URL scheme validation (`http://` or `https://` only) for both initial request and redirects.
  - Implemented streaming body length limits (stops accumulating at 100KB) to prevent unbounded memory exhaustion.
  - Added file-state cache (`existsSync` & `readFileSync`) in `syncAgyMcpConfig()` to prevent redundant rewrites of the static script on every CLI invocation.

**`plugin/src/agent/llmClient.test.ts`** (+28 lines)
- Syntax validity test (shebang-stripped `new Function()` parse)
- `fetch_url` tool definition presence
- GET-only enforcement (no `.request()`, no `method:`)
- Source contract: `syncAgyMcpConfig` contains the injection logic

### Validation

- `tsc --noEmit`: clean
- `vitest`: 1115/1115 passed, 0 failed

## What the Executor should verify

1. The embedded script actually works end-to-end: spawn it via `node`, send
   MCP `initialize` + `tools/call` with a real URL, confirm it returns HTML.
2. Whether `pdfinfo` still needs a separate solution (the fetch server only
   covers URL fetching, not local PDF metadata inspection — but
   `LocalPdfToolRunner` may already handle that use case).
3. Version bump and CHANGELOG if this ships as part of v0.71.0.
4. Whether the docs need updating (PLUGIN_SCHEMA, guides).
