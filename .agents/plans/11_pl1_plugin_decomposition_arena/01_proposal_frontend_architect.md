# Frontend Proposal: Facade-First Plugin Module Split

Date: 2026-07-09 | Agent Persona: Frontend Architect

## 1. Core Logic & Implementation

Use compatibility facades at the current import paths:

- `src/ui/chatSidebar.ts`
- `src/agent/llmClient.ts`
- `src/ui/externalPdfView.ts`

Each facade keeps public exports stable while implementation moves under:

- `src/ui/chat/`
- `src/agent/llm/`
- `src/ui/pdf/`

Proposed chat slices:

- `ui/chat/types.ts` - `MultiEditProposal`, local renderer/state types.
- `ui/chat/contextRefs.ts` - context ref keys, status badge helpers, Zotero
  cache epoch helpers.
- `ui/chat/messageRendering.ts` - assistant markdown, edit blocks, phase
  rendering, answer-link handlers.
- `ui/chat/sessionDrawer.ts` - session list/search/title/preview helpers.
- `ui/chat/dragDrop.ts` - PDF/file drop detection and split-drop guideline.
- `ui/chat/ChatSidebarView.ts` - remaining ItemView lifecycle and orchestration.

Proposed LLM slices:

- `agent/llm/types.ts` - provider adapter interfaces and internal option types.
- `agent/llm/adapters.ts` - OpenAI, DeepSeek, Ollama, Claude, Antigravity
  adapter classes and `ADAPTERS`.
- `agent/llm/messageUtils.ts` - OpenAI content normalization, finish-reason
  mapping, MCP result display, quota helpers.
- `agent/llm/cliRuntime.ts` - CLI command construction, output parsing, MCP
  config sync, sandbox wrapping.
- `agent/llm/LLMClient.ts` - public `LLMClient` class that composes helpers.

Proposed PDF slices:

- `ui/pdf/types.ts` - `ExternalPdfState`, PDF.js outline/page/document types.
- `ui/pdf/toc.ts` - ToC flattening, printed-page resolution helpers.
- `ui/pdf/toolbar.ts` - toolbar button construction and state rendering.
- `ui/pdf/snipping.ts` - snip-region text/canvas extraction helpers.
- `ui/pdf/rendering.ts` - page visibility/render scheduling helpers.
- `ui/pdf/ExternalPdfView.ts` - ItemView lifecycle and orchestration.

`main.ts` should remain the Obsidian plugin entrypoint, but plugin startup can
move into `src/app/` services only after the three target god-files are stable.

## 2. Pros & Cons

Pros:

- Current import paths stay stable for `main.ts`, tests, and external code.
- Each extraction phase can be verified independently.
- Source-contract tests can be moved to the module that owns the asserted code.

Cons:

- Facades add temporary indirection.
- Class methods that touch private state may require extracting pure helpers
  before class delegation is possible.
