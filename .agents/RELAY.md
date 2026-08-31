# RELAY

**Branch:** `release/v0.77.0`
**Goal:** The Quick Query popover can follow a reference to a URL, through the
guarded fetch path, and a denied tool no longer kills the turn.

## Why

User report 2026-08-31: asking the popover for a reference title on a paper
returned nothing at all —

> jetski: no output produced — a tool required the "read_url" permission that
> headless mode cannot prompt for, so it was auto-denied.

## What the investigation found

Everything needed was already installed. `incurator_fetch` is registered in
`~/.gemini/config/mcp_config.json`, exposes `fetch_url`, carries an SSRF guard,
and `mcp(*)` permits it. **Nothing anywhere tells the model that tool exists** —
`grep fetch_url` finds no prompt text at all. So the model reaches for agy's
built-in `read_url`, which is not in the allow-list, and the turn dies.

Underneath that sits the real defect: `boundaryConstraints` tells the popover
"You have NO filesystem access and NO MCP tools." That is true for API providers,
where the plugin decides what tools to inject. It is **false for the agy CLI
path**, because `syncAgyMcpConfig()` runs unconditionally in the antigravity
branch — `ephemeral` only empties `--add-dir`. agy loads its own MCP registry, so
the popover's zero-MCP guarantee never applied to it.

## Decision (user, 2026-08-31)

Asked, because it is product shape rather than engineering: seal the popover, or
make the contract match reality. **User chose reality** — the popover may use the
guarded `fetch_url`, and the prompt says so.

Not `read_url`: an unguarded URL fetcher on the path that processes untrusted
paper content is what `incurator_fetch` exists to avoid. Granting a fourth
permission is the wrong shape of fix.

## Plan

`.agents/plans/77_popover_fetch/`

## Status

- [x] Cause located and confirmed against the user's live config
- [x] Product decision taken to the user
- [ ] Plan written
- [ ] Implementation
- [ ] Code review skill, then CI, then merge

## Next

Author the plan, then implement.
