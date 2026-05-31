# Cross-Agent Relay Protocol Implementation Plan

## Goal Description
Implement a standardized "Relay Protocol" to solve context fragmentation and hallucination issues when switching between different AI coding agents (Antigravity, Claude Code, Cursor/Codex) due to rate limits or tool specialization. By maintaining a shared state file (`.agents/relay.md`), agents can seamlessly hand off work, share architectural decisions, and track step-by-step progress without losing context.

## Proposed Changes

### 1. New Artifact: `.agents/relay.md` Template
We will create a standard template file at `.agents/relay.md`. 
Agents will **overwrite** this file rather than archiving it, keeping the workspace clean and relying on Git for history.

**Structure**:
```markdown
# Agent Relay Handoff

**Last Updated:** [Timestamp]
**Last Agent:** [Antigravity | Claude Code | Cursor/Codex]

## Current Active Goal
[Brief description of the overarching goal]

## Active Plan Reference
[Link to the specific plan in `.agents/plans/...`]

## Progress Status
- [x] Completed Step 1
- [x] Completed Step 2
- [ ] Next Step 3 (Pending)

## Critical Context & Blockers
- [Context] Any environment states (e.g., VAULT_ROOT=testbed)
- [Context] Key decisions made in the last session
- [Blocker] What caused the handoff (e.g., rate limit, missing tool)

## Immediate Next Action for the Next Agent
[Explicit instruction on what the next agent should do immediately upon waking up]
```

### 2. Rule Updates
#### [MODIFY] `AGENTS.md` and `CLAUDE.md`
Add a new Core Rule section: **Core Rule: Cross-Agent Relay Protocol**.
- **On Wakeup**: Agents MUST read `.agents/relay.md` before taking action if they detect an active multi-agent workflow or are instructed to resume work.
- **Update Frequency**: 
  - Agents MUST update `.agents/relay.md` at the **end of every session**.
  - Agents MUST always update the file whenever a `/goal` or an implementation plan is active.
- **Format**: Overwrite the file using the defined structure.

## Verification Plan
1. Write the initial template to `.agents/relay.md`.
2. Update `AGENTS.md` and `CLAUDE.md`.
3. Provide a test payload in the relay file representing this current task's state.
