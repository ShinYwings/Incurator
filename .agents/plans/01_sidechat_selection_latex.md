# Master Implementation Plan — Sidechat Selection & LaTeX Robustness

Date: 2026-06-11
Status: **DRAFT — awaiting user approval before any code** (Universal Strict Workflow Step 4)
Branch: `feature/sidechat-selection-latex` (from `master` @ afe8e60)
Arena: `.agents/plans/sidechat_selection_arena/` (00_problem, 01_proposal, 02_critique_redteam, 03_specialists)
Source: `.agents/drafts/sidechat_selection_latex.md`

## Strict quality condition
- A drag-selection spanning a rendered formula, sent via Ask AI, includes the
  formula as `$...$`/`$$...$$` LaTeX — independent of the Live-Preview SVG↔text
  swap timing.
- NON-math selections produce byte-identical captured text to today (math-gated
  fast path returns raw `selection.toString()`).
- Keyboard (Shift+Arrow/Home/End, Ctrl/Cmd+A) selections surface the Ask AI
  button; ordinary typing/navigation does not; shrinking back to a caret hides it.
- `npx vitest` + `tsc` green; new unit tests for the extractor branches.

## Locked design decisions (Arena Consensus)
1. **Reuse, don't rebuild.** Add ONE exported helper `selectionToTextWithLatex`
   in `utils/textUtils.ts` that calls the existing private `extractTextWithLatex`
   on `selection.getRangeAt(0).cloneContents()` ONLY when the fragment contains
   `mjx-container, span.math`; otherwise returns raw `selection.toString()`.
   Keep `extractTextWithLatex` private (export surface = just the new helper).
2. **Timing-independent capture.** Reading the MathJax `annotation[...x-tex]`
   works in both SVG and swapped-text states, so symptom 1 is fixed at the
   read-method level; the `setTimeout(0)` defer stays but is no longer load-bearing.
3. **Route both capture sites** (`handleSelectionChange`, `openForCurrentSelection`)
   through the helper. No other capture logic (rect, anchorRange, MAX length) changes.
4. **Keyboard trigger = `keyup`, gated** (NOT `selectionchange`). Fire
   `handleSelectionChange` only on `shift`+(Arrow*/Home/End) or Ctrl/Cmd+A.
   Register per document AND every popout, mirroring the existing `mouseup` path.
5. **Whole-formula over-capture on partial drag is INTENDED** (a half-formula is
   useless); a cloned `mjx-container` with no `annotation` yields "" (no crash).
6. **Symptom 3 (partial editor LaTeX copy) is DEFERRED to Icebox** — needs the
   heavy KaTeX-swap/overlay route; out of this batch.

## Contracts preserved
- `QuickQueryPopover` public API, `MAX_SELECTION_LENGTH`, popout registration,
  PDF capture (hits the no-math fast path → unchanged).
- `attachLatexCopyHandler` / chat copy untouched.

## Evidence Ledger
- **Rollback anchor**: `master` @ `afe8e60` (PR #17 merge). Branch already cut.
- **Repo reality (verified 2026-06-11)**: capture via `selection.toString()` at
  `quickQueryPopover.ts:141,175`; extractor at `textUtils.ts:135-171` (private);
  trigger registration `main.ts:137-157` (mouseup + mousedown only).
- **Dirty worktree**: only this plan's files on the feature branch.
- **Rollback**: pure plugin/TS, no DB/destructive ops → `git revert` the merge.

## Execution Phases (TDD + vitest/tsc green per gate)
- **P1 — `selectionToTextWithLatex` (pure, TDD-first)** in `utils/textUtils.ts`
  + `textUtils.test.ts` cases: math selection → `$...$`/`$$...$$`; non-math →
  identical to `toString()`; empty/no-range → ""; mjx-container missing annotation
  → no crash. Gate: vitest + tsc.
- **P2 — Wire capture** into `quickQueryPopover.ts` (both sites). Update the
  popover source-assertion test. Gate: vitest + tsc.
- **P3 — Keyboard trigger** in `main.ts` `registerQuickQueryDom` (keyup, gated,
  per popout). Gate: vitest + tsc.
- **P4 — Docs + version + release**: `PLUGIN_GUIDE` (+`_KR`) Ask-AI/quick-query
  section (LaTeX-preserving capture + keyboard trigger); spec title bump IF the
  version line moves (see Q1); move symptom 3 to ROADMAP Icebox; CHANGELOG;
  version bump; delete plan+arena; release commit; push; PR.

## Open questions for the user (answer before P1)
1. **Version**: bug-fix-heavy with one new behavior. Patch **v0.5.1** (fix bundle)
   or Minor **v0.6.0** (new keyboard-trigger behavior)? — NOTE: a minor bump (0.6)
   also requires bumping all 4 spec titles + `ACTIVE_VERSION` (the line we just
   learned about); a patch (0.5.1) does NOT.
2. **Symptom 3** (partial editor LaTeX copy via Cmd+C): confirm DEFER to Icebox
   for now (recommended), or include the KaTeX/overlay work in this batch?
