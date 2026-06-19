# Cross-Agent Relay State

## Status
RAG & Knowledge Quality Stabilization is complete. Plan F / PR #34
(`feature/agent-context-service`, v0.13.0) has been merged into `master`.
Roadmap cleanup is complete: `.agents/plans/` has been cleared of shipped RAG
planning residue, and active follow-up priorities are ordered in
`.agents/ROADMAP.md`. Fix-like regressions and cleanup/validation tasks are
intentionally queued before the larger RAG post-stabilization hardening program.

## Active Plan
- Branch: `feature/edit-loop-state-machine` (from origin/master, v0.14.0)
- Sidechat Edit Loop — Enforced & Observable State Machine: IMPLEMENTED.
  Plan + arena deleted (Git history is the archive).
- Done: docs/specs + EN/KR guides, `getEditLoopContract()` prompt block (wider
  triggers, anchored last), `editLoopContract.ts` validator, Diff Viewer hard
  gate, observable phase UI + blocked banner (Re-run / Override). Versions
  bumped to 0.14.0; CHANGELOG updated. tsc clean; 441 plugin tests pass.

## Immediate Next Action
Push `feature/edit-loop-state-machine` and open the PR (final release commit
already pending below). The user reviews/merges on GitHub.
