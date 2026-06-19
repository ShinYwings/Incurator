# Prompt/State-Machine Proposal: Observable Edit Loop

Date: 2026-06-19 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

Introduce a small prompt contract for sidechat Markdown mutations:

~~~~text
Analysed:
- Target file/section and user intent.

Reviewed:
- Scope check against selected/open Markdown context.
- Why this edit is enough and what is intentionally not edited.

Updated:
```ai-agent-edit
...
```

Reviewed:
- Post-update checklist: SEARCH matches existing text, replacement is scoped,
  no unrelated rewrites, remaining caveats.
~~~~

Implementation should be minimal:

1. Add a pure helper in `plugin/src/context/systemPrompt.ts`, for example
   `sidechatEditLoopInstruction(hasEditTarget: boolean): string`.
2. Append it from `chatSidebar.buildLLMMessages` only when the latest request is
   a Markdown edit request and there is an editable line range or open Markdown
   edit target.
3. Keep existing `ai-agent-edit` parsing and Diff Viewer behavior. The `Updated`
   section supplies the edit block; chat rendering already removes raw blocks and
   renders review pills.
4. Add tests to `systemPrompt.test.ts`.
5. Add focused rendering tests if an existing `chatSidebar` test harness can
   validate that text before/after edit blocks remains visible while raw blocks
   stay collapsed.

## 2. Pros & Cons

Pros:

- Smallest change that creates an observable loop.
- Keeps file mutation controlled by existing Diff Viewer acceptance.
- Does not require a new schema, backend API, or state table.
- Avoids exposing hidden reasoning by requiring concise review summaries.

Cons:

- Prompt-only enforcement can be ignored by weak providers.
- Without parser-level validation, malformed responses may still skip a section.
- A stricter renderer gate would be stronger but may block useful edits from
  providers that use slightly different wording.
