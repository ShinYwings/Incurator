# Active Relay State

**STATUS: ACTIVE**

**Active Branch**: `feature/popover-tool-scope`
**Target Draft**: `.agents/drafts/popover_tool_scope.md`

## Next Action for Executors (Claude Code / Codex)
1. Read `.agents/drafts/popover_tool_scope.md` completely.
2. Search and analyze the codebase related to `quickQueryContext.ts`, `systemPrompt.ts`, and `llmClient.ts` to identify where MCP tools are injected and how system prompts differ between Sidechat and Popover.
3. Author a new `PLAN_TEMPLATE.md` in `.agents/plans/` that unifies the prompt generation and introduces a flag to disable tool injection for the Popover.
4. Stop and request human review of the plan.
