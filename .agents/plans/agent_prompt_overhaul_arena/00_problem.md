# 00 — Problem Briefing: Agent Prompt Architecture & Context Overhaul (v0.19.0)

Date: 2026-06-20 | Milestone: Roadmap item 2 | Branch: `release/v0.19.0`

## Source drafts (Briefing inputs)
- `.agents/drafts/chat_context_decay.md`
- `.agents/drafts/popover_tool_scope.md`
- `.agents/drafts/prompt_architecture_refactoring.md`

These three drafts are **three symptoms of one disease**: the plugin's prompt
construction is fragmented across isolated, hand-concatenated strings with no
shared registry, no surface-aware tool policy, and no recency anchoring.

## The three observed failures

### F1 — Chat context decay (`chat_context_decay.md`)
In long sessions (especially after early whole-document edits), `Cmd+Shift+L`
(`incurator-obsidian-agent:line-reference`) injects a localized excerpt, but the
agent ignores it and reverts to whole-file modification. Root cause: the
`<primary_focus_selection>` / `editableSelectionInstruction` directives sit near
the **top** of a large payload, so their relative attention weight is diluted by
historical whole-document context. There is no end-of-payload (recency-effect)
re-assertion of the localized task.

### F2 — Popover tool/sandbox scope violation (`popover_tool_scope.md`)
The inline Quick Query popover causes the agent to spawn scripts (e.g. a
hallucinated `find_mvg_text.py`) and traverse the filesystem. Root cause:
`LLMClient.streamChat` unconditionally injects the **entire MCP toolset**
(`mcpManager.getAllTools()`) for every non-CLI caller; the popover
(`quickQueryPopover.ts:452`) has no way to opt out. The popover is meant to be an
ephemeral, zero-side-effect reading assistant.

### F3 — Prompt duplication & brittleness (`prompt_architecture_refactoring.md`)
`chatSidebar.ts` builds its prompt via `buildBaseSystemPrompt` in
`systemPrompt.ts`; the popover uses a completely separate hardcoded string in
`quickQueryContext.ts:128`. Any boundary rule fixed in one is missing in the
other. `ai-agent-edit` formatting rules are monolithic blocks, hard to maintain,
and inconsistent across models.

## Verified code reality (grounding, not assumption)
- `plugin/src/context/systemPrompt.ts` — `BASE_INSTRUCTIONS`,
  `EXTERNAL_INCURATOR_MCP_ADDENDUM`, `PLAN_MODE_ADDENDUM`, `getEditLoopContract`,
  `editableSelectionInstruction`, `wrapLatestUserMessageForLanguageBridge`.
- `plugin/src/context/quickQueryContext.ts` — independent `systemText` literal
  (lines 128–150) + `buildQuickQueryMessages`.
- `plugin/src/context/chatContextPriority.ts` — `contextPriorityInstruction`
  already encodes the "primary_focus_selection is the absolute core subject" rule
  (shared by both surfaces conceptually, but only the popover imports it).
- `plugin/src/agent/llmClient.ts:644-673` — `streamChat` → `getAllTools()` →
  injects tools for every caller unless `shouldUseCli` or no `mcpManager`.
- `plugin/src/ui/quickQueryPopover.ts:452` — calls `streamChat(messages, onChunk)`
  with no tool-policy argument.
- `plugin/src/ui/chatSidebar.ts:1157,1185,1301,1461` — assembles base prompt +
  `editableSelectionInstruction` + appends `<primary_focus_selection>` and slices
  history to `CONTINUITY_MESSAGE_LIMIT` (6).

## What "done" means
1. One shared, composable prompt registry feeds BOTH sidechat and popover; their
   common boundary/format/language/math rules come from the same blocks.
2. The popover executes with tools HARD-disabled (zero side effects), proven by a
   unit test that asserts no tools are passed on the popover path.
3. A recency-anchor block re-asserts the localized task (primary selection focus,
   no whole-file edit, surface tool policy) at the END of the payload, fixing F1.
4. No behavioral regression in the sidechat edit loop, language bridge, or
   incurator MCP usage. All existing prompt tests still pass; new tests cover the
   builder and the tool-policy gate.

## Open questions for the Arena
- Can the plugin enforce *hard* filesystem path sandboxing on arbitrary external
  MCP servers, or is that out of our trust boundary? (red_teamer to rule on.)
- Builder shape: pure functional block-composition vs. a profile object. Which
  minimizes churn against the heavy existing `chatSidebar.ts` caller?
- Does centralizing change the *text* the model sees (risking output drift), or
  must v0.19.0 be a behavior-preserving refactor + additive anchor only?
