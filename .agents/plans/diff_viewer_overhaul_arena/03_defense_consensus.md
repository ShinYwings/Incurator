# Defense & Consensus

Date: 2026-06-19 | Agent Persona: system_synthesizer (The Closer)

## Resolved conflicts

The red_teamer's critiques are accepted almost wholesale. Consensus:

1. **P0 empirical triage is a HARD GATE, not a formality.** The plan stops after
   P0 and requires user sign-off on the LIVE/PARTIAL/FIXED classification before
   any fix code. The triage table is the deliverable; the fix phases are
   provisional until it lands. (Resolves redteam #1.)

2. **Milestone is split into Tier A (ship) and Tier B (gated/deferred).**
   - **Tier A — reproduced LIVE surgical fixes:** Bug 3 (cursor restore), Bug 11
     (hover anchor), Bug 2/9 (review-in-flight serialization + per-pill derived
     status), Bug 7 (path-resolution fallback scan). These touch behavior, not
     architecture.
   - **Tier B — gated:** Bug 5 (unified-view polish) is admitted as **CSS +
     ordering only**, with an explicit honest caveat that it is NOT pixel-perfect
     vscodium (widget blocks don't inherit CM6 gutters — redteam #2 accepted). A
     true CM6 gutter rewrite is OUT of scope. Bug 8 & Bug 10 (prompt determinism /
     token budgeting) are **deferred to roadmap item 6**, except one client-side
     hard guard: reject a single REPLACE that rewrites > a threshold of the file.

3. **Bug 4 fix is DERIVED status, not a persisted schema change.** We adopt the
   red_teamer's alternative: compute each proposal's status at render time from
   the live file + `findSearchBlock` (SEARCH still matches → `pending`; REPLACE
   already present and SEARCH gone → `applied`; neither → `not_found`). This is
   self-healing across reload and the accept→next-turn cycle, and **adds NO
   `ChatMessage` schema field, NO migration.** The state_sync_specialist's
   persisted map is rejected on those grounds. (Resolves redteam against both.)

4. **Bug 4 multi-turn cycle must be in P0 reproduction.** Explicitly test
   propose → accept-in-viewer → next-turn-context-rebuild, confirming the rebuilt
   open-tab snapshot reflects the accepted file (not a stale turn-1 cache).

5. **Agent never says "applied."** One-line wording addition to the existing
   v0.14.0 `getEditLoopContract()` post-edit REVIEWED phase: edits are *proposed,
   pending your review/Accept in the Diff Viewer*. No new prompt system; no
   collision with item 6.

6. **No whole-module rewrite.** The inverted-decoration engine and its 34 prior
   fixes stand. Every change traces to a P0-reproduced LIVE defect.

## Locked outcome

- Version: **fix/minor** → target **v0.14.1** if Tier A only (behavioral fixes,
  no schema, no public-contract change); promote to **v0.15.0** only if P0
  forces Tier B unified-view work that changes user-facing rendering materially.
- No DB/backend schema work. Plugin-only + the one-line prompt wording + docs.
- Toolbar re-anchoring MUST reuse singleton teardown (tested for listener leak).
- Derived status MUST be computed from stored `msg.content` + live file, never
  from a recomputed hash that could drift against the tolerant matcher.

## Stop conditions carried into the Master Plan

- Stop if P0 shows the LIVE set differs materially from the hypothesis → re-scope
  with the user.
- Stop if Bug 5 needs a CM6 gutter rewrite to satisfy "unified view."
- Stop if derived status proves too slow on large transcripts (only then revisit
  a persisted field as a separate planned change).
