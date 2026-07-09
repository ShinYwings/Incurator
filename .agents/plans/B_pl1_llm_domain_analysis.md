# PL-1 Domain Analysis B: LLM Client

Date: 2026-07-09

## Design Constraints From Codebase

- `llmClient.ts` is 2,382 LOC and exports pure helpers, provider adapters,
  `ADAPTERS`, and `LLMClient`.
- Existing tests import `./llmClient` and source-inspect the same file for
  sandbox flags, CLI cache paths, image handling, and MCP config behavior.
- `quickQueryPopover.ts`, `inlinePrompt.ts`, `settings.ts`, `chatSidebar.ts`,
  and `main.ts` call the public `LLMClient` API.

## Docs/Specs Invariants

- Provider behavior, tool isolation, sandboxing, and streaming semantics
  described in guides/specs must remain unchanged.
- No provider/model setting names may change.

## Alternatives & Trade-offs

- Move adapters first: low UI risk, but source tests must be updated
  immediately.
- Move `LLMClient` class first: high risk because provider and CLI paths are
  intertwined.

## Final Decision

Extract pure message/provider helpers first, then adapters, then CLI runtime
helpers. Keep `src/agent/llmClient.ts` as the stable public facade.

## Implementation Pseudocode

```text
create agent/llm/messageUtils.ts
re-export helpers from llmClient.ts
move tests that inspect those helpers
create agent/llm/adapters.ts and agent/llm/cliRuntime.ts
keep LLMClient constructor/options unchanged
```
