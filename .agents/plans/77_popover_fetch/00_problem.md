# v0.77.0 Briefing — the popover's tool contract is fiction on the CLI path

## The report

2026-08-31, user, reading a paper in the Quick Query popover, asking for a
reference's title:

> jetski: no output produced — a tool required the "read_url" permission that
> headless mode cannot prompt for, so it was auto-denied. Add an allow-rule under
> permissions.allow in settings.json (e.g. $read_url$()). Alternatively, re-run
> with --dangerously-skip-permissions to auto-approve all tools.

The user got nothing. Not a partial answer, not an explanation — an empty turn.

## Measured facts

Established 2026-08-31 against the user's live configuration and the current
tree. None of this is inferred.

1. `incurator_fetch` IS registered in `~/.gemini/config/mcp_config.json`
   (confirmed: servers are `['incurator', 'incurator_fetch']`).
2. It exposes `fetch_url` (`LLMClient.ts:154`) and carries an SSRF guard —
   IPv4-mapped unmapping, DNS pinning — shipped earlier in this cycle.
3. `mcp(*)` is granted (`AGY_MCP_PERMISSION`, `LLMClient.ts:119`). Scoped
   `mcp(...)` rules grant nothing, which is why the wildcard is used.
4. **No prompt text anywhere mentions `fetch_url`.** `grep -rn fetch_url` over
   `plugin/src` and `backend/src` returns only the tool's own definition and one
   dispatch check. The model is never told the tool exists.
5. `boundaryConstraints` tells the popover, verbatim: *"You have NO filesystem
   access and NO MCP tools."* (`promptRegistry.ts`, `case "local-only"`).
6. That statement is FALSE on the agy path. `syncAgyMcpConfig()` is called
   unconditionally inside `case "antigravity"` of `buildCliCommand`
   (`LLMClient.ts:2658`). The `ephemeral` flag computed just above it only
   empties `--add-dir`. agy reads its own MCP registry, so the popover's
   zero-MCP guarantee never reached it.
7. `shouldInjectMcpTools` returns false for `local-only` — but it also returns
   false for `"auto"` when `useCli` is true. It governs the tools the PLUGIN
   injects into a message stream, which is a different thing from the tools a
   CLI agent loads for itself. The guarantee it documents is real for API
   providers and vacuous for CLI ones.

So the model was told it had nothing, needed a URL, and picked the built-in
`read_url` — the one URL tool that is not in the allow-list.

## This is the fourth of its kind

v0.53.1, v0.56.1 and v0.71.0 were all "a tool agy needed was auto-denied". Those
three were missing permissions. This one is not: the permission and the server
are both present. Adding a fourth grant would be the wrong shape of fix, and
`read_url` in particular is the unguarded fetcher that `incurator_fetch` was
built to replace on a path that processes untrusted paper content.

## The product decision, already taken

Put to the user because it is product shape, not engineering: seal the popover
so the promise becomes true, or change the promise to match reality.

**User chose reality (2026-08-31): the popover may use the guarded `fetch_url`,
and the prompt must say so.**

## Constraints on any solution

- `read_url` MUST NOT be granted.
- The popover keeps `allowEdits: false` and no filesystem roots. Only the
  network tool changes, and only the guarded one.
- API providers (Claude, DeepSeek, Ollama) genuinely have no MCP tools in the
  popover. Their wording must stay correct — a single unconditional string
  cannot serve both, which is the root of item 6 above.
- `syncAgyMcpConfig` writes ONE global file. Rewriting it per-spawn to scope the
  popover would race the sidebar. Whatever is done must not introduce that race.
- A denied tool must not produce an empty turn. That half is not the product
  decision and holds regardless.
