# Diagnosis: G13-plugin-agent
Coverage: `plugin/src/agent/incuratorClient.ts`, `plugin/src/agent/incuratorClient.test.ts`, `plugin/src/agent/incuratorClientV031.test.ts`, `plugin/src/agent/llmClient.ts`, `plugin/src/agent/llmClient.test.ts`, `plugin/src/agent/mcpClient.ts`, `plugin/src/agent/sandboxWrapper.ts`, `plugin/src/agent/sandboxWrapper.test.ts`, `plugin/src/agent/syncScheduler.ts`, `plugin/src/agent/syncScheduler.test.ts`; reference-only: `plugin/main.ts`, `plugin/src/settings.ts`, `plugin/src/types.ts`, `plugin/src/ui/chatSidebar.ts`, `plugin/src/ui/quickQueryPopover.ts`, `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`.

Category coverage: (a) bugs: G13-1, G13-3, G13-4, G13-8; (b) redundancy: G13-9; (c) error-handling smells: G13-5, G13-6, G13-7; (d) legacy/dead code: G13-9; (e) architectural debt: G13-9; (f) docs/code drift: G13-11; (g) performance hotspots: G13-5, G13-10, G13-12; (h) robustness/weaknesses: G13-2, G13-4, G13-8; (i) UI/UX friction: G13-6, G13-12.

## Findings

### [G13-1] (a,h) S2 — Non-streaming CLI calls bypass GUI PATH augmentation
- Loc: `plugin/src/agent/llmClient.ts:1251`, `plugin/src/agent/llmClient.ts:1672`
- Evidence: streaming CLI calls spawn with `env: this.getAugmentedEnv(env)`, which prepends GUI CLI search paths. `completeViaCli()` uses `execFileAsync(..., { env: { ...process.env, ...env } })`, so non-streaming inline edit / quick-query / complete paths can fail to find `agy`, `claude`, or `codex` in GUI-launched Obsidian even when streaming works.
- Fix sketch: use `this.getAugmentedEnv(env)` in `completeViaCli()` and add a focused test that stubs `execFile` and asserts augmented `PATH`.
- Blast radius: non-streaming `complete()`, inline edit when streaming is disabled, quick query when streaming is disabled, any future non-streaming CLI feature.
- Suggested PR: `fix/plugin-cli-env-parity`

### [G13-2] (a,h,i) S2 — A single shared abort controller is unsafe for concurrent requests and MCP tool loops
- Loc: `plugin/src/agent/llmClient.ts:571`, `plugin/src/agent/llmClient.ts:594`, `plugin/src/agent/llmClient.ts:799`, `plugin/src/agent/llmClient.ts:752`
- Evidence: `LLMClient` stores one class-level `abortController`, overwrites it at every `_streamChatSingleTurn()`, and clears it in `finally`. A quick-query stream and sidebar stream can overlap; the later request replaces the earlier controller, and the earlier `finally` can clear the later one. During MCP tool execution after a model tool-call turn, `_streamChatSingleTurn()` has already cleared the controller, so `abort()` cannot stop `mcpManager.callTool()`.
- Fix sketch: create a per-request controller/token for `streamChat()` and pass it through all turns and tool calls; either reject concurrent calls explicitly or track request IDs so `abort()` targets the active stream requested by the UI.
- Blast radius: Stop generating, quick-query dismissal, sidebar streaming, HTTP-provider MCP tool calls.
- Suggested PR: `fix/plugin-llm-abort-isolation`

### [G13-3] (a,h) S2 — HTTP MCP tool-call names are lossy and can call the wrong tool
- Loc: `plugin/src/agent/llmClient.ts:717`, `plugin/src/agent/llmClient.ts:757`, `plugin/src/agent/llmClient.ts:769`
- Evidence: exposed function names are built as `` `${t.serverName}__${t.name}`.replace(/[^a-zA-Z0-9_-]/g, "_") `` and later split back into `serverName` / `toolName`. This loses original characters such as `.`, `/`, spaces, and any name containing `__`, so `mcpManager.callTool(serverName, toolName, args)` may not match the registered server/tool.
- Fix sketch: keep a `Map<exposedFunctionName, { serverName, toolName }>` for the request and use it when executing returned tool calls; validate collisions when generating names.
- Blast radius: DeepSeek/Ollama HTTP tool calling with custom MCP servers.
- Suggested PR: `fix/http-mcp-tool-name-map`

### [G13-4] (h) S1 — OS sandbox grants every provider write access to every CLI state directory
- Loc: `plugin/src/agent/sandboxWrapper.ts:47`, `plugin/src/agent/sandboxWrapper.ts:59`, `plugin/src/agent/llmClient.ts:2068`
- Evidence: `cliRuntimeWriteDirs()` always allows `~/.gemini`, `~/.antigravity`, `~/.claude`, and `~/.codex` for every sandboxed CLI. `wrapWithOsSandbox()` uses that plan for all providers. A compromised `agy` turn, for example, can write into `~/.codex` or `~/.claude` even though those are unrelated to the active provider. The comments correctly avoid broad `~/.config`, but this cross-provider allowlist is still larger than the stated "CLIs' OWN dirs" boundary.
- Fix sketch: make runtime write dirs provider-specific: Antigravity gets only `.gemini` / `.antigravity`, Claude gets `.claude`, Codex gets `.codex`, plus the plugin CLI cache and temp dir. Add tests proving cross-provider dirs are absent.
- Blast radius: CLI sandbox security, prompt-injection containment, provider CLI config/auth files.
- Suggested PR: `fix/sandbox-provider-runtime-dirs`

### [G13-5] (c,h) S2 — MCP shutdown sends a non-specific cancellation instead of closing stdin
- Loc: `plugin/src/agent/mcpClient.ts:156`, `plugin/src/agent/mcpClient.ts:160`, `plugin/src/agent/mcpClient.ts:163`
- Evidence: shutdown sends `notifications/cancelled` with `{}` and waits for process exit, then kills after 2 seconds. Cancellation is request-specific, while stdio server shutdown should be driven by closing the child's input stream. Because `stdin.end()` is never called, well-behaved servers may not see EOF and will be terminated rather than gracefully exiting.
- Fix sketch: on shutdown, reject/cancel pending requests by ID, call `this.process.stdin?.end()`, wait for exit, then escalate from `SIGTERM` to `SIGKILL` only if needed.
- Blast radius: external MCP server cleanup, plugin unload, Obsidian reload, long-running tool processes.
- Suggested PR: `fix/mcp-stdio-shutdown`

### [G13-6] (c,g,h) S3 — MCP request timeout handles are never cleared
- Loc: `plugin/src/agent/mcpClient.ts:207`, `plugin/src/agent/mcpClient.ts:239`
- Evidence: `sendRequest()` creates a 30-second `setTimeout`, but the timeout handle is not stored or cleared when a response resolves/rejects. Completed requests leave timers alive until they expire; high tool-call volume creates unnecessary timer churn.
- Fix sketch: store the timer in each pending entry and clear it on response, error, timeout, and process exit.
- Blast radius: custom MCP tool loops, long sidechat sessions with many tool calls.
- Suggested PR: `fix/mcp-request-timeout-cleanup`

### [G13-7] (c,h,i) S2 — Backend JSON failures are collapsed to `null`, erasing actionable errors
- Loc: `plugin/src/agent/incuratorClient.ts:797`, `plugin/src/agent/incuratorClient.ts:801`, `plugin/src/agent/incuratorClient.ts:261`, `plugin/src/agent/incuratorClient.ts:427`
- Evidence: `callBackendJson()` catches every backend runner failure, logs to console, and returns `null`. Callers then return generic empty states such as "backend command is not available" or `null`, so UI code cannot distinguish disabled backend, command missing, invalid JSON, command exit error, or a real empty result. `registerSource()` also catches all unexpected errors and returns `null`, which conflicts with the plugin schema requirement that failed source registration surface as an error state and visible failure.
- Fix sketch: return a typed backend boundary result `{ ok, data?, error, command }` from the runner wrapper and normalize each public method to preserve `error_type` / `message` while still returning graceful empty values when disabled.
- Blast radius: source registration/status, PDF context, Zotero repair flows, context fetch/feedback, autosync status.
- Suggested PR: `refactor/incurator-client-result-boundary`

### [G13-8] (a,c,h) S2 — Response-envelope normalization can hide top-level errors and unsafe casts can leak invalid shapes
- Loc: `plugin/src/agent/incuratorClient.ts:1063`, `plugin/src/agent/incuratorClient.ts:620`, `plugin/src/agent/incuratorClient.ts:655`, `plugin/src/agent/incuratorClient.ts:678`
- Evidence: `pickRecord()` prefers nested `data`, `result`, `source`, or `status` objects before top-level fields. A backend response like `{ ok: false, error: "...", data: {} }` would drop the top-level failure and normalize the empty `data`. Several newer methods then cast raw `unknown` directly to result interfaces with `return (result as Type) ?? empty`, so a non-null scalar or wrong object shape can escape to callers.
- Fix sketch: preserve top-level `ok/error/message` before unwrapping payloads; add small schema guards per public method and tests for `{ok:false,data:{}}` and scalar responses.
- Blast radius: curation plan, prompt trace, insight list/promote, synthesis list/audit, feedback context.
- Suggested PR: `fix/incurator-json-envelope-normalization`

### [G13-9] (a,h) S2 — CLI MCP config writers can overwrite user config or generate invalid TOML
- Loc: `plugin/src/agent/llmClient.ts:2134`, `plugin/src/agent/llmClient.ts:2145`, `plugin/src/agent/llmClient.ts:2156`, `plugin/src/agent/llmClient.ts:2176`
- Evidence: `syncAgyMcpConfig()` reads `~/.gemini/settings.json` but writes a new top-level `mcpServers` object containing only plugin settings, replacing any pre-existing Gemini MCP servers. `syncCodexMcpConfig()` writes `[mcp_servers.${rawServer.name}]` without quoting or validating the table key; server names containing spaces, dots, `]`, or quotes can produce invalid TOML or unintended table structure.
- Fix sketch: use a plugin-managed namespace or merge only plugin-owned server keys in global JSON; quote TOML table keys correctly or validate server names before save.
- Blast radius: user Gemini/Codex MCP configuration, external tool availability, provider CLI startup.
- Suggested PR: `fix/cli-mcp-config-preservation`

### [G13-10] (b,d,e) S2 — `llmClient.ts` is a god-class with dead or unreachable provider paths
- Loc: `plugin/src/agent/llmClient.ts:87`, `plugin/src/agent/llmClient.ts:467`, `plugin/src/agent/llmClient.ts:555`, `plugin/src/agent/llmClient.ts:1077`, `plugin/src/agent/llmClient.ts:1512`
- Evidence: the 2,282-line client owns HTTP adapters, CLI process execution, MCP config generation, sandbox wrapping, usage accounting, stream parsing, image temp-file writing, and edit prompts. `shouldUseCli()` returns `true` for Antigravity, Claude, and OpenAI, making their HTTP adapters effectively unreachable in normal `streamChat()` / `complete()` paths; `buildCliCommand()` still contains DeepSeek/Ollama CLI branches even `shouldUseCli()` returns false for those providers. `summarizeToolInput()` is private and unused.
- Fix sketch: split into `ProviderHttpAdapters`, `CliRunner`, `CliMcpConfigSync`, `UsageTracker`, and `ToolLoop`; then either remove dead HTTP/CLI branches or expose an explicit setting that selects them.
- Blast radius: all provider chat paths, model/tool additions, tests.
- Suggested PR: `refactor/plugin-llm-client-split`

### [G13-11] (f,h) S3 — Claude tool-boundary docs and CLI config generation disagree
- Loc: `docs/specs/plugin_schema/PLUGIN_SCHEMA.md:1648`, `docs/specs/plugin_schema/PLUGIN_SCHEMA.md:1697`, `plugin/src/agent/llmClient.ts:2120`
- Evidence: the schema says Claude sidechat disables native file/web tools and "only the DB-scoped MCP curator tools remain", but the code writes every enabled `settings.mcpServers` entry into Claude's MCP config. The later schema line says external user-configured MCP servers are the user's own trust boundary. The intended behavior is ambiguous: either all external MCP tools remain available by design, or Claude sidechat should filter to a DB-scoped subset.
- Fix sketch: decide the contract. If external MCP tools are allowed, update the schema wording and UI copy. If only curator tools are allowed, filter the generated Claude config by server/tool scope and test it.
- Blast radius: sidechat tool boundary, user expectations around custom MCP servers, docs/security review.
- Suggested PR: `docs-or-fix/plugin-claude-mcp-boundary`

### [G13-12] (g,h,i) S3 — CLI image attachments accumulate in cache without cleanup
- Loc: `plugin/src/agent/llmClient.ts:1969`, `plugin/src/agent/llmClient.ts:2209`, `plugin/src/agent/llmClient.ts:2217`
- Evidence: `contentToCliText()` writes image parts to `<repo>/.cache/cli/tmp_images` or OS temp and returns the path to the CLI prompt. There is no per-request cleanup after the child process exits and no startup TTL cleanup, so PDF/image chat usage can leave unbounded local cache files.
- Fix sketch: track temp files created per CLI request and delete them after process completion; add a startup TTL cleanup for stale `tmp_images` files.
- Blast radius: CLI vision fallback, PDF snips/images, local disk usage, privacy of cached captures.
- Suggested PR: `fix/cli-temp-image-cleanup`

### [G13-13] (g,i) S3 — External MCP servers auto-start noisily on plugin load
- Loc: `plugin/main.ts:807`, `plugin/src/agent/mcpClient.ts:270`, `plugin/src/agent/mcpClient.ts:274`, `plugin/src/agent/mcpClient.ts:278`
- Evidence: every configured MCP server is started 2 seconds after plugin load, independent of active provider or whether the chat sidebar will use HTTP tool injection. Each start/failure emits an Obsidian `Notice`. Users with slow/heavy local MCP servers pay startup cost and toast noise even if they only use CLI providers or quick query with `toolPolicy: "none"`.
- Fix sketch: lazy-start MCP servers when a request actually needs HTTP tool injection or when the settings UI explicitly tests/enables them; move routine status to the settings section/status bar and reserve notices for user-initiated actions.
- Blast radius: Obsidian startup experience, external MCP server resources, settings UX.
- Suggested PR: `ux/lazy-start-custom-mcp`

## Positives (keep / do-not-break)
- `shouldInjectMcpTools()` is a small pure gate with tests; keep a single decision point for `toolPolicy` and MCP injection.
- OpenAI-compatible message sanitization and finish-reason mapping have focused tests for empty assistant turns, tool-call turns, quota errors, and truncation.
- `sandboxWrapper.ts` already follows a deny-write-by-default posture, refuses unsupported Antigravity sandboxing, and has tests for avoiding broad `~/.config`, `~/.cache`, and host `/tmp` grants.
- `IncuratorClient` uses hidden `wiki plugin ...` JSON commands for same-device Incurator access and does not fall back to Incurator MCP tools, matching the main plugin contract.
- `SyncScheduler` is small, deterministic, and tested for debounce/coalescing/no-overlap behavior.
- Backend version checking uses bundled build metadata when present and records `repoPath`, which supports reliable setup/update UX.

## Open questions for the human
- Should custom external MCP servers be available automatically in sidechat, or should the default be opt-in/lazy-start per chat request?
- Are global CLI config files (`~/.gemini/settings.json`, `~/.codex/obsidian.config.toml`) acceptable for plugin-managed MCP sync, or should the plugin only write dedicated/namespaced config artifacts?
- Should Antigravity/Claude/OpenAI HTTP adapters be revived as supported modes, or removed so the provider architecture is explicitly CLI-first for those providers?
- Which exact provider runtime directories are required writable during CLI execution on macOS/Linux? The sandbox should allow only those per provider.
- Should the backend JSON runner expose structured command errors to the plugin, or should `IncuratorClient` continue treating all command failures as graceful empty results?
