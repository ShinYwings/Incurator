# RELAY

**Branch:** `hotfix/chat-history-latency`

## Status

READY — sidechat provider history is bounded in v0.82.2.
Root cause: ChatSidebarView serialized the entire persisted message history into every provider prompt; the active session was 205,948 counted characters.
Fix: provider prompts now use a contiguous suffix of at most four non-system messages and 48,000 counted characters; full sessions and compact continuity remain intact.
Validation: plugin 1290 passed / 3 skipped, backend 1967 passed / 7 skipped / 4 xfailed, ruff, mypy, tsc, build, and live-session reduction check passed. Release commit is next.
Original E4 draft remains untracked and untouched.
