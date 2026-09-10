# RELAY

**Branch:** `hotfix/chat-history-latency`

## Status

ACTIVE — investigating sidechat latency with Knowledge Off.
Root cause: ChatSidebarView serializes the entire persisted message history into every provider prompt; the active session is ~202k characters.
Plan: cap provider history to recent turns while preserving full sessions and compact continuity context, add regression tests/docs, bump to v0.82.2, validate plugin/backend gates.
Original E4 draft remains untracked and untouched.
