# Relay State — ACTIVE (2026-06-11)

## Goal
ROADMAP #1 (was #2): **Agent Edit & Diff Viewer Reliability**. Target `v0.5.0`.
Branch: `feature/agent-edit-diff-reliability` (from master @ e268809, post-PR#16).

## Plan Reference
- Master Plan: `.agents/plans/01_agent_edit_diff_viewer.md`
- Arena debate: `.agents/plans/agent_edit_diff_arena/` (problem, proposal, redteam critique, specialists)
- Source draft: `.agents/drafts/agent_edit_diff_viewer.md`

## Analysis & Reasoning (key finding)
The DiffViewer is ALREADY a VSCodium-style in-memory CM6 diff with full hunk UX
(n/total counter, ↑/↓ nav, per-hunk + global accept/reject, Y/N/Enter/Esc). The
reported failures are at the EDGES, not the engine:
- exact-only SEARCH matching (`indexOf`/`includes`/`split`) aborts before any
  diff renders → headline bug + the "no counter/arrows" symptom;
- brittle block parser leaks `<<<<`/`====`/`>>>>` markers into rendered text;
- a "Review Diff" click-gate + a redundant on-disk artifact under
  `00_System/Agent Diffs/`;
- under-constrained REPLACE scope (whole answer appended).
Plan = edge-harden only (unified 3-tier matcher exact→line-trim→anchored with
ambiguity guards; faithful marker stripping; immediate hard-gated auto-open;
artifact off-by-default; scope prompt + non-blocking large-replacement warning).
NO DiffViewer rewrite, NO schema/RAG impact (schema_guardian + source_pair_analyst cleared).

## Progress Status
- ✅ Investigation, Arena debate, Master Plan authored.
- ✅ ROADMAP cleaned (#1 install shipped v0.4.4/PR#16 removed; this is now #1 ACTIVE).
- ⏸️ **AWAITING USER APPROVAL of the plan + 3 open questions (version / auto-open
  aggressiveness / artifact default) before writing any code (Workflow Step 4).**

## Critical Context / Blockers
- Do NOT start P1 until the user approves the plan and answers the 3 questions.
- Touched files (plugin-only TS): `chatSidebar.ts`, `diffViewer.ts`,
  `context/editArtifact.ts`, `context/systemPrompt.ts`, `utils/textUtils.ts`,
  new `utils/editMatch.ts`, `types.ts`.

## Immediate Next Action
On approval: P1 — TDD the pure `editMatch.findSearchBlock` matcher + tests, gate
on vitest/tsc, then P2 wire all three apply/preview paths.
