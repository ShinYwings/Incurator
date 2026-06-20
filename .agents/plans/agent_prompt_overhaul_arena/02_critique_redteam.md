# Critique on lead_architect's Composable Prompt Registry

Date: 2026-06-20 | Agent Persona: red_teamer (The Adversary)

## 1. Vulnerabilities & Flaws

### V1 — "Strict path sandboxing, mathematically proven" is undeliverable as scoped
The draft (`popover_tool_scope.md`) demands MCP file/command tools be "mathematically
proven to reside within the allowed roots." **The plugin cannot enforce this on an
external MCP server.** Once a tool call leaves the plugin and hits a third-party
MCP process (a command runner, a filesystem server), that process does its own
I/O; we only see the result. Claiming we sandbox it would be a lie in the spec.
→ The ONLY enforceable guarantees are: (a) popover passes ZERO tools (hard, in
our process), and (b) prompt-level boundary constraints for sidechat. Anything
stronger requires the user not to register an arbitrary command-runner MCP
server, which is a config/doc concern, not code we can prove.

### V2 — Recency anchor can corrupt the edit loop
If `buildRecencyAnchor` injects "Do NOT output ai-agent-edit blocks" on the
sidechat whenever there is no primary selection, it could suppress legitimate
edit requests. The anchor's `allowEdits` must be TRUE for sidechat; the read-only
line is popover-only. Also: appending the anchor INSIDE the language-bridge
`<original_user_request>` block would make the model treat the invariant as part
of the user's literal request (and possibly echo it). The anchor must be a
SEPARATE trailing block, outside `<original_user_request>`.

### V3 — Golden-master byte-equality is too rigid for the popover
The plan intentionally STRENGTHENS the popover boundary line. A byte-for-byte
snapshot test will then fail by design. The snapshot strategy must be: freeze
sidechat output exactly; for the popover, assert the boundary phrase is PRESENT
(substring), not a frozen blob — otherwise the test blocks the very fix we want.

### V4 — `shouldUseCli` short-circuit already skips tools — double-path risk
`streamChat` line 649 already returns early (no tools) when `shouldUseCli` is
true or `mcpManager` is null. Adding `toolPolicy: "none"` creates a SECOND
no-tools path. If they diverge (e.g. CLI path formats messages differently), the
popover could behave differently depending on provider. The gate must funnel both
to the SAME single-turn execution, and a test must cover popover-with-mcpManager
AND popover-without.

### V5 — Tool-policy default is a footgun
If any future caller forgets to pass `toolPolicy`, it silently defaults to
`"auto"` (tools ON). Ephemeral surfaces (anything not the main sidechat) should
fail safe. Acceptable for v0.19.0 since only two callers exist, but the popover
test must assert `getAllTools` is never invoked on its path (spy/mock), not just
that the arg was passed.

### V6 — Cmd+Shift+L decay may not be purely a prompt problem
`chat_context_decay.md` blames attention dilution, but if early whole-document
context is still physically in the `CONTINUITY_MESSAGE_LIMIT=6` window as huge
blobs, the anchor competes with thousands of tokens. The anchor is necessary but
may be insufficient. Don't over-promise a 100% fix; the success test should use a
realistic long-context fixture, and we should explicitly defer aggressive
stale-context truncation to roadmap item 4 (Context Compaction).

## 2. Suggested Alternatives
- **Re-scope F2 honestly**: rename the goal from "sandbox MCP tools" to
  "ephemeral surfaces inject zero tools + prompt-declared boundary for sidechat."
  Put true path enforcement in Non-Goals with a doc note in PLUGIN_GUIDE about
  not exposing arbitrary command-runner MCP servers.
- **Anchor placement**: emit the anchor as its own trailing `system` or `user`
  message segment AFTER the wrapped request, gated by `allowEdits`/`toolPolicy`.
- **Test matrix**: popover(mcp present)→0 tools; popover(no mcp)→0 tools;
  sidechat(mcp present)→tools as today; sidechat edit request→edit loop intact.
- **Snapshot policy**: exact-freeze sidechat; substring-assert popover.
