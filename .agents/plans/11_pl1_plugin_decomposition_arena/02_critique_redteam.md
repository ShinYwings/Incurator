# Critique On PL-1 Proposals

Date: 2026-07-09 | Agent Persona: Red Team

## 1. Vulnerabilities & Flaws

- The largest risk is TypeScript private-state extraction. Moving methods out of
  `ChatSidebarView` or `ExternalPdfView` can force broad public accessors or
  `any` casts that reduce safety.
- Existing source-contract tests read specific files. If facades become tiny,
  those tests can fail even when behavior is correct. If snippets are left as
  comments to satisfy tests, the refactor becomes misleading.
- Circular imports are likely:
  - `chatSidebar.ts` imports `ExternalPdfView`.
  - PDF trace rendering imports from `externalPdfView`.
  - LLM client imports prompt/tool types while UI surfaces call LLM methods.
- `main.ts` is listed as a target, but decomposing it in the same release could
  multiply risk after three already-large splits.
- Moving `LLMClient` provider adapters can break tests that inspect
  `llmClient.ts` for sandbox strings and CLI flags.

## 2. Suggested Alternatives

- Keep class orchestration files real, not empty wrappers, until helpers have
  been extracted and tested.
- Convert source-contract tests to target the new owner modules in the same
  commit that moves the code. Never satisfy source tests with inert comments.
- Put shared cross-domain types in `src/types.ts` or local `types.ts` modules
  with one-way imports. UI modules may import from LLM/types, but LLM modules
  must not import UI.
- Defer substantial `main.ts` decomposition to the final phase and only extract
  clearly isolated startup helpers if prior phases are green.
