# v0.14.1 / v0.15.0 Diff Viewer Overhaul & Sync Fixes — Master Implementation Plan

Date: 2026-06-19
Status: DRAFT — Arena debate concluded; awaiting user approval before implementation.
Arena: `.agents/plans/diff_viewer_overhaul_arena/`

## 1. Objective

Fix the **reproduced, still-live** defects in the sidechat AI-agent Diff Viewer
without churning the recently-stabilized "Inverted Pure-Decoration" engine
(`plugin/src/ui/diffViewer.ts`, which already carries 34 documented bug fixes
from the v0.11.0 overhaul).

Definition of done: every change traces to a defect **reproduced in P0** against
the active testbed; the LIVE set is user-confirmed; Tier A surgical fixes ship
with tests; disk is never written before Accept; the agent never claims edits
were "applied."

## 2. Explicit Non-Goals

- **No whole-module rewrite** of the diff engine. The inverted-decoration model
  stays.
- **No `ChatMessage` schema change / migration.** Proposal status is **derived**
  at render time, not persisted.
- **No prompt-architecture refactor.** Bugs 8 (model-output variance) and 10
  (token truncation) are deferred to roadmap item 6, except one client-side
  hard guard against whole-document REPLACE blocks.
- No side-by-side diff, no floating modal, no backend/DB/CLI changes.
- No re-fixing defects that P0 proves already fixed.

## 3. Strict Quality Conditions & Release Gates

- P0 triage table committed and **user-approved** before any fix code.
- For every shipped fix, a `.test.ts` reproducing the defect (red→green).
- `show()` provably never calls `editor.replaceRange` on open (test-pinned).
- Toolbar re-anchoring reuses singleton teardown with **no listener leak**
  (test-pinned).
- Derived proposal status is computed from stored `msg.content` + the live file
  via `findSearchBlock`, never from a drift-prone recomputed hash.
- `npx tsc --noEmit` clean; `npx vitest run -c ./plugin/vitest.config.ts` green.
- Testbed smoke: propose → review → accept/reject → next-turn cycle verified.
- Docs updated: `PLUGIN_SCHEMA.md` (§6 Diff Viewer) + `PLUGIN_GUIDE.md` then
  `PLUGIN_GUIDE_KR.md`.

## 4. Locked Design Decisions (Arena Consensus)

1. **Triage-first.** P0 classifies all 11 defects LIVE / PARTIAL / FIXED with
   testbed reproduction. Fix phases are provisional until the table is approved.
2. **Tier A (ship): reproduced LIVE surgical fixes** —
   - **Bug 3 (cursor):** after Accept-All, restore the cursor to the first
     changed hunk line (cached at `show()`), not `finalEndPos` (bottom).
   - **Bug 11 (hover):** on null `coordsAtPos`, `scrollIntoView` the hunk then
     recompute coords next frame; only if still null, dock the bar to the editor
     pane (editor-relative), never screen-top. Re-anchoring reuses `close()`
     teardown.
   - **Bug 2 / 9 (multi-file & pill state):** a module-level `reviewInFlight`
     guard serializes `reviewFileEditProposals` so the singleton can't be
     re-pointed mid-`show()`; each pill shows a **derived** per-proposal status.
   - **Bug 7 (path):** extend `resolveVaultFile` with a final case-insensitive,
     whitespace-stripped basename scan over `getMarkdownFiles()` before failing.
3. **Bug 4 (agent desync) = derived status + framing**, no schema:
   - Status derived from live file + matcher (`pending` / `applied` /
     `not_found`), self-healing across reload and accept→next-turn.
   - One-line addition to the v0.14.0 `getEditLoopContract()` post-edit REVIEWED
     wording: edits are *proposed, pending review/Accept in the Diff Viewer* —
     the agent must not say "applied."
4. **Bug 6 already structurally fixed** (inverted model); add regression tests
   only.
5. **Tier B (gated):**
   - **Bug 5 (unified view):** CSS + render-ordering polish ONLY, with an honest
     caveat that widget-block added lines are not pixel-perfect vscodium gutters.
     A CM6 gutter rewrite is OUT of scope (stop condition).
   - **Bug 8 / 10:** deferred to item 6, except a single client-side guard that
     rejects a REPLACE rewriting more than a threshold fraction of the file
     (anti-whole-doc-rewrite) with an honest notice.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions:** prompt-architecture refactor (item 6), side-by-side diff,
  persisted proposal schema, backend changes.
- **Stop Conditions:**
  - Stop if P0 shows the LIVE set differs materially from the hypothesis →
    re-scope with the user.
  - Stop if Bug 5 requires a CM6 gutter rewrite to satisfy "unified view."
  - Stop if derived status is too slow on large transcripts → revisit a
    persisted field as a separate planned change (do not inline it here).

## 6. Evidence Ledger

- **Current repository reality (verified 2026-06-19):**
  - `plugin/src/ui/diffViewer.ts` (675 lines): inverted-decoration singleton;
    `show()` never writes on open (L99, L140–170); nav uses `scrollIntoView`
    (L414–428); toolbar clamp + `rect.top+80` fallback (L331–334, L547–564);
    Accept-All `setCursor(finalEndPos)` (L487) = the Bug 3 source.
  - `plugin/src/ui/chatSidebar.ts`: `reviewFileEditProposals` (L3525–3613) filters
    by canonical path and applies into one `modifiedFullText` via `findSearchBlock`,
    shows one multi-hunk diff; `resolveVaultFile` (L3499–3523); pills via
    `renderInlineMultiDiff`.
  - `plugin/src/utils/editMatch.ts`: `findSearchBlock` exact→line-trim→anchored,
    null on ambiguity.
  - `plugin/src/context/systemPrompt.ts`: v0.14.0 `getEditLoopContract()` owns the
    post-edit REVIEWED wording to amend for Bug 4.
- **Current dirty worktree:** clean on `feature/diff-viewer-plugin-overhaul`
  (current with origin/master incl. merged PR #35 / v0.14.0).
- **Rollback:** all changes are plugin-local + one prompt string + docs; revert
  the commits to restore current behavior. No data migration.
- **Version anchor:** repo at 0.14.0. Target **v0.14.1** for Tier A only; promote
  to **v0.15.0** only if P0 forces material Tier B rendering changes.

## 7. Execution Phases (TDD + CI gate at each phase)

- **P0 — Empirical triage (HARD GATE, no fix code).** Reproduce each of the 11
  defects in the active testbed (incl. the Bug 4 propose→accept→next-turn cycle
  and multi-provider output for 8/10). Commit a LIVE/PARTIAL/FIXED table to this
  ledger. **STOP for user approval of the LIVE set.**
- **P1 — Contract/docs spec.** Update `PLUGIN_SCHEMA.md` §6 (derived proposal
  status, toolbar anchoring contract, path-resolution fallback, anti-whole-doc
  guard) + the Bug-4 prompt wording note. Guides updated after code (P5).
- **P2 — TDD (red).** Failing tests: cursor-restore target; no-write-on-open;
  review-in-flight serialization; derived status (`pending`/`applied`/`not_found`);
  path-resolution fallback; whole-doc-REPLACE guard.
- **P3 — Tier A implementation (green).** Bug 3, 11, 2/9, 7 + Bug 4 derived
  status & prompt wording + the anti-whole-doc guard.
- **P4 — Tier B (only if P0-approved).** Bug 5 CSS/ordering polish within the
  stated caveat; otherwise skip.
- **P5 — Validation + docs.** `tsc`, `vitest`, testbed smoke (propose → review →
  accept/reject → next-turn). Update `PLUGIN_GUIDE.md` → `PLUGIN_GUIDE_KR.md`.
- **P6 — Release.** Bump manifest/package/pyproject + spec titles + spec-sync
  `ACTIVE_VERSION` to the chosen version; CHANGELOG; mark roadmap item 2 done;
  delete this plan + arena; final `chore(release)` commit; push + PR.
