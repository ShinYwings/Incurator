# Active Relay State

**STATUS: v0.28.0 implemented; opening PR.**

## Goal (DONE)

Chat Crop Vision-Passthrough — Cmd+Shift+X crops now go DIRECTLY to a
vision-capable main chat model (antigravity/claude/codex) via a scoped CLI image
channel instead of a redundant backend `plugin pdf transcribe` round-trip that, in
the default config, hits the same provider. Non-vision models (text Ollama) keep
transcribe. The deferred materialize runs after the Thinking indicator renders, so
Send no longer freezes (the residual v0.27.9 bug).

## Branch / Version

- Branch: `feature/chat-crop-vision-passthrough` (from `master`).
- Version: **v0.28.0** (Minor — new behavior + §26.2a contract change).

## Validation (all green)

- P0 live-vision probe: antigravity / claude / codex each read a scoped `.cache`
  PNG in the chat-path flag shape. PASS.
- Plugin: 635 vitest tests pass; `tsc --noEmit` clean; esbuild production build OK.
- Backend: ruff clean; mypy clean (102 files); `test_spec_sync` 10/10 (0.28.0
  across 3 manifests + 4 spec titles).

## What shipped

- `plugin/src/agent/llmClient.ts`: interactive chat image channel
  (`chat_images/<run>` temp dir, path reference, per-turn scoped Read +
  `--add-dir`, per-call cleanup + startup sweep).
- `plugin/src/ui/chatSidebar.ts`: `materializeContextRefs` vision/non-vision
  branch + `mainChatModelSupportsVision()`; `handleSend` renders thinking BEFORE
  the deferred materialize await.
- Specs: SYSTEM_BEHAVIOR §26.2a revised, PLUGIN_SCHEMA §2.1.3 added, 4 spec titles
  → v0.28.0. Guides: PLUGIN_GUIDE(.md/_KR.md).
- Tests updated/added in `chatSidebarSource.test.ts` + `llmClient.test.ts`.

## Immediate Next Action

Release commit (`chore(release): v0.28.0`, deletes the plan artifacts) → push →
open PR. After merge, truncate this file to IDLE.
