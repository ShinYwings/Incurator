# PL-1 Briefing: Plugin God-file Decomposition

Date: 2026-07-09

## Problem

The Obsidian plugin has four large files that now carry unrelated concerns:

- `plugin/main.ts` - 2,224 LOC
- `plugin/src/ui/chatSidebar.ts` - 4,895 LOC
- `plugin/src/agent/llmClient.ts` - 2,382 LOC
- `plugin/src/ui/externalPdfView.ts` - 1,909 LOC

The target release, v0.35.0, is a pure structural refactor. It must not change
UI layout, chat/session persistence, backend command contracts, MCP behavior,
Obsidian view lifecycle hooks, or provider semantics.

## Ground Truth From Repository

- `npx vitest run -c ./plugin/vitest.config.ts` currently passes:
  65 test files, 669 tests.
- Existing tests import the old entrypoints directly:
  - `plugin/src/agent/llmClient.test.ts` imports `./llmClient`.
  - `plugin/main.ts` imports `ChatSidebarView`, `LLMClient`, and
    `ExternalPdfView` from their current paths.
  - source-contract tests read `chatSidebar.ts`, `llmClient.ts`, and
    `externalPdfView.ts` as text, so extraction must either preserve those
    snippets in facades or move the assertions to the new owning modules.
- `PLUGIN_SCHEMA.md` defines plugin/backend command contracts and plugin
  authority boundaries. PL-1 must preserve those contracts.

## Required Output

Create an Arena-derived implementation plan in `.agents/plans/` that defines
safe extraction seams, strict no-behavior-change gates, characterization tests,
and incremental phases. Do not implement code until the plan is approved.
