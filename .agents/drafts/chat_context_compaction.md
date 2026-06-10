# Chat Session Context Compaction Plan

## Context
Triaged from USER_REPORT on 2026-06-11. New feature for the Obsidian sidechat
agent: full-session context awareness plus a user-driven compaction control
with a live token-usage indicator.

## Observed Request (verbatim intent to preserve)
- Confirm whether the Obsidian agent currently uses the **entire chat session
  history** when answering. If it doesn't, make it do so (research current
  note-specialized techniques before implementing).
- If/once session-wide context exists, add a **chat compaction** capability.
- Show a **circular progress bar** (Claude Code style) in real time, below the
  query input, indicating how full the session is relative to the max context
  (max token length).
- Clicking that progress button **compacts the current chat session's
  conversation history**.

## Requirements
1. **Fact-check**: Does the sidechat agent already feed the full session history
   to the model? Inspect the message-assembly path. Sessions live in plugin
   `sessions.json` (per Shared Architecture Memory — chat history is NOT in the
   vault).
2. **Research** latest note-specialized context-management / compaction
   techniques before designing (don't reinvent).
3. **Token-usage meter**: circular progress bar under the query box, live, vs.
   the model's max context window.
4. **Compaction action**: clicking the meter summarizes/compacts the session
   history to reclaim context budget.

## Files Likely Involved
- Plugin sidechat session manager (`sessions.json` read/write)
- Sidechat message-assembly / prompt-builder
- Sidechat UI (query input area, new circular progress component)
- Model max-context lookup (per provider/model)

## Notes
- Plugin-heavy TS work, possibly with a backend compaction/summarize call →
  needs `.test.ts` (and `pytest` if backend summarize endpoint added).
- The circular-progress UI overlaps conceptually with the Vault Quota circle bar
  in `stabilization.md` — share the component if practical.
