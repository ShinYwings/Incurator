# Problem Briefing: Sidechat Analyse/Review/Update Loop Regression

Date: 2026-06-19

## User Report

The Obsidian sidechat agent should follow an explicit edit loop:

```text
analysed -> reviewed -> updated -> reviewed
```

The reported failure is that the sidechat jumps from tool/model preparation into
file-edit proposals without a distinct observable review phase. In the example,
the agent edited a note about apparent contours and camera pose without first
showing a concrete self-review of the logic gap and edit plan.

## Current Repository Reality

- Sidechat prompt assembly lives in `plugin/src/context/systemPrompt.ts`.
- Dynamic sidechat prompt context is assembled in `plugin/src/ui/chatSidebar.ts`
  via `buildLLMMessages`.
- Markdown mutation is proposed with `ai-agent-edit` blocks and reviewed through
  the sidechat/Diff Viewer path.
- Existing prompt text says "First understand..." but does not require an
  observable pre-edit review checkpoint or a post-edit review checkpoint.
- Plugin guide/spec document sidechat context priority and edit review behavior,
  but not this explicit analyse/review/update/review loop.

## Core Defect

The current contract lets providers produce an `ai-agent-edit` block immediately
after internal reasoning. Since internal reasoning is hidden, the user cannot see
whether the agent actually:

1. analysed the requested logical defect;
2. reviewed its planned edit against the selected/open file context;
3. proposed the update;
4. reviewed the proposed update for scope, consistency, and missing steps.

## Constraints

- Do not make the plugin directly mutate files before the user accepts a diff.
- Do not expose private chain-of-thought. The visible loop must be concise,
  task-facing review text, not hidden reasoning.
- Do not force the loop for pure Q&A with no file mutation.
- Do not rewrite the entire prompt architecture here; that remains a later
  roadmap item.
- Add tests before implementation.

## Definition Of Done

- Sidechat edit proposals have a testable prompt contract requiring a visible
  `Analysed`, `Reviewed`, `Updated`, `Reviewed` structure.
- Sidechat renderer/review flow preserves that structure without dumping raw
  edit blocks into chat.
- Docs/specs describe the behavior.
- Plugin tests cover the contract and the sidechat edit rendering path.
