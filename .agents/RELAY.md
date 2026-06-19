# Cross-Agent Relay State

## Status
Initializing Milestone 2: Diff Viewer Plugin Overhaul & Sync Fixes.
The draft analysis exists at `.agents/drafts/diff_viewer_plugin.md`.

## Active Plan
- Branch: `feature/diff-viewer-plugin-overhaul` (from master)
- Target: Diff Viewer Plugin Overhaul & Sync Fixes.
- Phase: Plan synthesized (Arena concluded) -> awaiting user approval.
- Arena: `.agents/plans/diff_viewer_overhaul_arena/` (problem, 2 proposals,
  redteam critique, synthesis).
- Master plan: `.agents/plans/02_diff_viewer_overhaul.md`.

## Critical Context
The draft's 11 bugs predate the v0.11.0 Diff Viewer Overhaul (inverted
pure-decoration engine, 34 documented fixes) and the v0.14.0 edit-loop work.
Arena consensus: triage-first. P0 = reproduce all 11 in testbed and classify
LIVE/PARTIAL/FIXED, then STOP for user sign-off on the LIVE set before any fix.
Tier A surgical fixes (Bug 3 cursor, 11 hover, 2/9 race+derived pill status, 7
path) → v0.14.1; Tier B (Bug 5 unified-view polish, 8/10 prompt) gated/deferred
to item 6. No schema change — proposal status is DERIVED, not persisted.

## Immediate Next Action
Get user approval of `02_diff_viewer_overhaul.md`. On approval, begin P0
empirical triage (no fix code yet) and stop again for sign-off on the LIVE set.
