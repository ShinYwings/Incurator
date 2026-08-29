# RELAY — IDLE

## Last shipped

**v0.71.0 (#187) — the Antigravity CLI can finally call an Incurator tool.**

Three independent breakages stood between the plugin and a callable agy tool,
each fatal alone, all measured against agy 1.1.22 rather than reasoned about:

1. The MCP server was registered in `~/.gemini/settings.json`; agy reads
   `~/.gemini/config/mcp_config.json`, which was empty.
2. Calling any MCP tool needs an `mcp` permission and only the wildcard is
   honoured — `mcp(incurator_fetch)` and `mcp(fetch_url)` were auto-denied.
3. The registered command was the bare name `wiki`, a shell alias a spawned
   process cannot find, so the server never started.

Never fetch-specific: the whole curator surface `command(wiki)` exists to spawn
was registered the same wrong way. It explains v0.53.1, v0.56.1, and the fetch
server itself — three permission fixes that shipped granting nothing.
Verified after: headless agy called `curator_status` and returned 3,512 pages.

Also: the `prompt_runs` cap, session retention, and the review fixes (sign-out
that never reached the encrypted store, a mid-stream quota kill firing on prose,
a throwing snapshot wedging plugin persistence, L4 status counting uncited
reports, a cleared `.cache/` overwriting an accurate ledger).

## What this round changed about how to work here

**Code review before CI is a mandatory workflow step** (CLAUDE.md step 8). It
had been skipped for sixteen releases; the first run found six issues including
a fleet-wide data-loss path.

**Verification has to touch the real thing.** Nearly every bug this round shared
one shape — a check that never reached its target:

- the fetch server's tests asserted on the script *string*; every defect passed
- a binary test asserted an SSRF refusal, so it never exercised binary handling
- a registry test mocked `os.homedir` too late, so nothing was written and three
  "must be absent" assertions passed vacuously
- both suites were rewriting the developer's real `~/.gemini` and nothing said so

So: **mutate the fix and confirm the test fails.** Every fix this round was
checked that way. Guards now exist in `backend/tests/conftest.py` and
`plugin/vitest.setup.ts` so a home-directory leak is loud instead of silent.

**Run the FULL backend suite before the PR**, not just touched files — 734e420
broke an exact-equality assertion that only the full run caught.

## Open

`.agents/USER_REPORT.md` holds three filed items: the provider key transiting as
CLI argv, `is_knowledge_question` gating nothing in the funnel, and the
pytest-wrote-to-real-home finding (now fixed, entry can be retired).

Next: `.agents/ROADMAP.md` Phase D — D1 (`graph_entities`/`source_spans`
surrogate-id transport). Phase D items are stored-contract changes: one per
release, each with a migration rehearsal and rollback drill.
