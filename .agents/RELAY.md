# Cross-Agent Relay State

## Status
RAG & Knowledge Quality Stabilization is complete. Plan F / PR #34
(`feature/agent-context-service`, v0.13.0) has been merged into `master`.
Roadmap cleanup is complete: `.agents/plans/` has been cleared of shipped RAG
planning residue, and active follow-up priorities are ordered in
`.agents/ROADMAP.md`. Fix-like regressions and cleanup/validation tasks are
intentionally queued before the larger RAG post-stabilization hardening program.

## Active Plan
- Branch: `feature/edit-loop-state-machine` (from origin/master, target v0.14.0)
- `.agents/plans/01_sidechat_loop_regression.md` (REVISED — scope expanded)
- Arena: `.agents/plans/sidechat_loop_regression_arena/` (round 04 = scope override)
- Status: DRAFT (REVISED). User rejected the minimal prompt-only plan and
  requested all four expansions (parser/hard-enforcement, wider triggers,
  visible UI phases, re-scope). Now a Minor feature → v0.14.0. Awaiting user
  approval of the revised plan before implementation.

## Immediate Next Action
Get user approval of the REVISED enforced-state-machine plan, then implement
P1–P7 (spec/guide → TDD → prompt block → validator → UI+gate → CI → release).
