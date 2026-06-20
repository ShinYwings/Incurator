# v0.19.0 Evidence Ledger — Agent Prompt Architecture & Context Overhaul

Date: 2026-06-20 | Companion to `19_agent_prompt_overhaul.md`

## Rollback anchor
- Branch: `release/v0.19.0`
- Clean base commit: `344783f` (`chore(agents): prepare v0.19.0 milestone branch`)
- Rollback: `git reset --hard 344783f` (local branch only — never on shared
  history). No DB/destructive op in this milestone, so rollback is pure-Git.

## Current dirty worktree (at planning time)
- `M .agents/RELAY.md` — relay update (versioning note).
- `M AGENTS.md`, `M CLAUDE.md` — versioning-criteria rule clarification
  (separate side-task, not part of v0.19.0 code).
- New untracked: `.agents/plans/agent_prompt_overhaul_arena/*`,
  `.agents/plans/19_*.md` (this planning set).
- No source code modified yet. Implementation has NOT started.

## Current repository & schema reality (verified, not assumed)
- `state.sqlite` schema: UNTOUCHED by this plan. Prefixes `CTX/ATM/CON/SYN`
  intact. No migration.
- `plugin/src/context/systemPrompt.ts`: exports `buildBaseSystemPrompt`,
  `editableSelectionInstruction`, `getEditLoopContract`,
  `wrapLatestUserMessageForLanguageBridge`. Verified at HEAD.
- `plugin/src/context/quickQueryContext.ts`: independent hardcoded `systemText`
  (lines 128–150); imports `contextPriorityInstruction`, `resolveSelectionReferencesBlock`.
- `plugin/src/agent/llmClient.ts`: `streamChat(messages, onChunk)` →
  `getAllTools()` at line 654; early no-tools return at line 649 via
  `shouldUseCli`/no-`mcpManager`.
- `plugin/src/ui/quickQueryPopover.ts:452`: calls `streamChat(messages, onChunk)`
  — no tool-policy arg today.
- Existing tests present: `systemPrompt.test.ts`, `quickQueryContext.test.ts`,
  `quickQueryPopover.test.ts`, `llmClient.test.ts`, `chatSidebarSource.test.ts`.
- Version manifests currently agree at `0.18.0` (pyproject / package.json /
  manifest.json verified). v0.19.0 bump pending P-end.

## Pre-validation snapshots to capture in P0
- [ ] `buildBaseSystemPrompt` output for all 4 flag combos (mcp×plan) → golden.
- [ ] `buildQuickQueryMessages` baseline system text → reference.
- [ ] Long-context decay fixture reproducing F1 (red test).

## Post-validation results (to fill during implementation)
- [ ] vitest plugin suite green (incl. new tests).
- [ ] golden-master byte-equal for sidechat.
- [ ] getAllTools spy = 0 on popover path (mcp present + absent).
- [ ] decay fixture passes (no whole-file edit on primary-selection turn).
- [ ] `scripts/backend-check pytest` green incl. `test_spec_sync.py` @ v0.19.
- [ ] ruff + mypy clean.
- [ ] testbed smoke: popover no script-exec; Cmd+Shift+L honored; edit loop OK.

## Known blockers / risks
- LLM availability for end-to-end popover/sidechat smoke — if unavailable,
  document the gap and rely on unit-level assertions (`local_slm_simulator`).
- `chatSidebar.ts` is large/stateful; golden-master is the guard against drift.
