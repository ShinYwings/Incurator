# Critique on provider and catalogue proposals
Date: 2026-09-10 | Agent Persona: Replica integrity / runtime reviewer

## 1. Vulnerabilities & Flaws

B's Codex message identity diagnosis is strong, but concatenating progress and final text can leave a complete earlier edit proposal followed by a revised final proposal. A parser that consumes every edit fence could offer obsolete edits twice. The final return value should have authoritative last-message semantics, and visible streaming must reconcile distinctly from proposal extraction. Test a progress item containing an edit fence, then final revised fence. Handling a shorter final answer cannot merely append twice at close.

Antigravity policy prompts do not enforce tool removal. Avoid claiming the search toggle enforces OFF if globally discovered MCP tools remain callable. A tool-free direct context policy that still reads an explicitly attached local image is a capability distinction that must be documented. Granting command(wiki) while saying never use any command is an inconsistent model instruction; say MCP/native permitted operations explicitly or narrow the grant if a verified provider interface permits it. Do not blindly retry a denied command, since a deny may reveal missing evidence and retries worsen the latency user reported.

D's updated catalogue needs persisted-setting behavior: removing 3.5 from display while retaining its stored default still invokes a unavailable model. Use the already existing unavailable-model migration if it targets retired IDs while preserving user custom IDs. Confirm bundled catalogue loading and schema fields agree with live model discovery. A new flagship should not silently replace every supported explicit user selection. Capability data such as reasoning effort must come from each runtime, not an API model page describing a different CLI contract.

## 2. Suggested Alternatives

Keep separate item-aware streaming and authoritative final output for proposal extraction; tests must pass the actual extractMultiEditProposals consumer, not just assert an event's substring. Keep the agy workaround claim bounded until a live constrained call proves it handles the report. Refresh catalogue once per configured explicit refresh/build rather than querying remotely per chat. Use exact retirement migration for 3.5 and defaults consistently across backend constants and plugin.

## 3. Defense of C scope

Root lifecycle correction plus a narrow terminal-audit transport invariant is necessary: changing only export output leaves the writer corrupt, changing only the writer leaves existing offline peer snapshots unimportable, and deleting retired rows discards intentionally retained audit data. The proposed rule does not relax live provenance checks. No Qt-specific environment change is justified; user has now confirmed the precise unmapped-source error.
