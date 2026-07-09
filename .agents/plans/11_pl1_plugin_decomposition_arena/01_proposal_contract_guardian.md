# Contract Proposal: Preserve Plugin Surfaces And Persistence

Date: 2026-07-09 | Agent Persona: Contract Guardian

## 1. Core Logic & Implementation

PL-1 must preserve these surfaces:

- Obsidian view types:
  - `CHAT_VIEW_TYPE`
  - `EXTERNAL_PDF_VIEW_TYPE`
  - `EXTERNAL_PDF_CONTEXT_EVENT`
- Public classes:
  - `ChatSidebarView`
  - `LLMClient`
  - `ExternalPdfView`
- Public helper exports currently imported by tests or modules:
  - `ADAPTERS`
  - `shouldInjectMcpTools`
  - `sanitizeOpenAIMessages`
  - `normalizeOpenAIContent`
  - `mapOpenAIFinishReason`
  - quota/status/CLI parsing helpers in `llmClient.ts`
- Persisted DTO shapes:
  - `PluginSettings`
  - `SessionData`
  - `ExternalPdfState`
  - external PDF registry/session fields
- Backend command strings and JSON envelopes used through `IncuratorClient`.

Add characterization tests before moving code:

- Export-surface tests for each facade.
- Source-import tests that assert `main.ts` still imports the same public
  entrypoints or their facades.
- Persistence tests around sessions and external PDF state.
- A no-cycle check over `plugin/src` if a lightweight local script can be added
  without new dependencies; otherwise rely on `tsc --noEmit` and focused import
  tests.

## 2. Pros & Cons

Pros:

- Locks the behavior that users and tests observe.
- Prevents the common TypeScript refactor failure: changing private module paths
  while accidentally changing public exports.

Cons:

- Some tests that currently inspect source text must be rewritten as part of
  extraction, creating extra churn even when behavior is unchanged.
