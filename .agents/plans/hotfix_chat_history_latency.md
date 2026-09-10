# v0.82.2 Hotfix Plan — Bound Sidechat Provider History

## Problem

With Knowledge Off, automatic retrieval is skipped, but `ChatSidebarView` still
places every persisted user and assistant message into each provider payload.
Long sessions therefore pay input and attention cost unrelated to knowledge
lookup. The live active session measured about 202,000 characters.

## Decision

Keep complete sessions and their persistence behavior unchanged. Before building
`LLMMessage[]`, select a contiguous suffix of at most four non-system messages
(two recent turns), bounded by a character budget. Retain the existing six-item
compact continuity summary for older context. Explicit context attached to the
retained messages remains available.

## Verification

- Pure helper tests prove suffix ordering, message and character limits, latest
  message retention, and input immutability.
- Existing sidebar/context tests remain green.
- Update the plugin schema and English/Korean guide to document provider prompt
  history bounds and the fact that persisted history is retained.
- Run plugin Vitest, TypeScript, production build, and backend consistency checks.
