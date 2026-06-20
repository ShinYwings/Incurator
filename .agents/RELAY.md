# Cross-Agent Relay State

## Goal
Prepare the next roadmap milestone after PR #42 merge:
**Obsidian Agent UI/UX & Context Architecture Overhaul**.

## Branch
`release/v0.19.0` from `master` at merge commit
`87906047696f69c23f5b04610797166ce4e18f6b`.

## Current State
- PR #42 (`feature/external-source-links`, v0.18.0) is merged into `master`.
- Local `master` was fast-forwarded to `origin/master`.
- `git push origin master` returned `Everything up-to-date`.
- `USER_REPORT.md` is empty.
- Active roadmap focus is item 2: Obsidian Agent UI/UX & Context Architecture
  Overhaul.

## Plan Reference
**Plan authored — awaiting user approval (do NOT code yet).**
- Master plan: `.agents/plans/19_agent_prompt_overhaul.md`
- Evidence ledger: `.agents/plans/19_roadmap_evidence.md`
- Arena debate: `.agents/plans/agent_prompt_overhaul_arena/` (00_problem,
  01_proposal_lead_architect, 02_critique_redteam, 02_critique_domain_specialists)

Briefing drafts (now synthesized into the plan):
- `.agents/drafts/chat_context_decay.md`
- `.agents/drafts/popover_tool_scope.md`
- `.agents/drafts/prompt_architecture_refactoring.md`

## Immediate Next Action
**STOP — waiting for user approval of `19_agent_prompt_overhaul.md`.**
On approval, execute phases P0→P5 (TDD + CI each phase): golden-master baseline +
decay fixture → spec/docs (PLUGIN_SCHEMA + spec-title bump to v0.19) → registry
module → behavior-preserving sidechat re-route → popover unify + tool-policy gate
+ recency anchor → testbed smoke. Then bump to v0.19.0 and open the PR.

---

### Update (2026-06-20, Claude Code) — Versioning policy clarified

User flagged that nearly every release bumped Minor (Y) regardless of content,
and asked when Major (X) should ever move. Confirmed correct: Step 2 of the
Universal Strict Workflow said only "decide Patch/Minor/Major" with **no
criteria**, so Minor became the default. Concrete precedent: v0.17.0 was a pure
`### Fixed` batch (clickable DAG wikilinks) and should have been `0.16.2`.

Fix applied (rule edit, no code, no version bump): added explicit **0.x SemVer
criteria** to Step 2 in BOTH canonical rule files, kept in sync per the Agent
Rule Synchronization contract:
- `AGENTS.md` (line ~179) and `CLAUDE.md` (line ~187).
- Patch = backward-compatible fixes / perf / internal refactor, no new
  capability or schema change (Fixed-only batch → Patch).
- Minor = any new feature / CLI / MCP tool / plugin setting / config field /
  schema change; in 0.x breaking changes also ride Minor.
- Major = first stable 1.0 public release; deliberate product decision, X stays
  `0` until the user calls it.

No follow-up needed; main v0.19.0 goal above is unaffected.
