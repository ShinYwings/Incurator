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

## P0 Triage — DONE (awaiting sign-off)
Results: `.agents/plans/diff_viewer_overhaul_arena/04_P0_triage.md`.
- FIXED (2): #1 nav, #6 premature write (regression tests only).
- LIVE (2): #3 cursor-on-Accept-All, #11 hover anchor.
- PARTIAL (7): #2 race, #4 framing, #5 polish, #7 path, #8 defer→item6,
  #9 pill status, #10 (warn exists).
Caveat: code-trace + unit-suite reproduction only; no live-Obsidian click test.

## Immediate Next Action
Get user sign-off on the LIVE/Tier-A set in 04_P0_triage.md. On approval, run
P1 (docs/spec) → P2 TDD → P3 Tier A fixes. Tier B (#5; #8/#10) gated.
