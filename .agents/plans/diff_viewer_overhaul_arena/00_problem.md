# 00 — Problem Briefing: Diff Viewer Plugin Overhaul & Sync Fixes

Date: 2026-06-19
Source draft: `.agents/drafts/diff_viewer_plugin.md`
Milestone: Roadmap item 2.

## The reported defects (verbatim from the user draft)

1. Navigation arrows (↑/↓) fail to scroll to the target hunk.
2. Multi-file edits: only the first file is reviewable; subsequent file buttons
   silently open the first file's diff.
3. Accepting a diff teleports the cursor to the bottom of the document instead
   of staying at the accepted hunk.
4. **Desync / race**: the backend agent assumes its edits were applied
   immediately, but the user hasn't accepted them yet — the agent hallucinates
   success or edits stale context.
5. UI/UX is clunky — user wants an **inline unified diff** like vscodium.
6. **Premature application**: "Could not find SEARCH text" errors, and edits are
   written to disk *before* the user clicks Accept.
7. File-not-found on existing files (path resolution failure).
8. **Inconsistent `reviewInEditor` output**: varies by model — batched, split,
   or no edit block at all (falls back to raw diff).
9. **Selection mismatch**: with multiple edit items, selecting one highlights all
   diffs; fixing one makes the rest fail with "not found search text".
10. **Token-limit truncation**: Gemini etc. truncate when rewriting whole docs.
11. **Hover misplacement**: Accept/Cancel toolbar jumps to the top of the screen
    instead of anchoring near the diff.

## CRITICAL CONTEXT — current code reality (verified 2026-06-19)

The draft's bug list **predates two shipped milestones** that already touched
this exact surface. Before any redesign, the Arena must reconcile the draft
against what the code does *today*:

- **v0.11.0 Diff Viewer Overhaul** rewrote `plugin/src/ui/diffViewer.ts` (675
  lines) into an **"Inverted Pure-Decoration" model** documented in-file as
  fixes for "Bug 1–34":
  - `show()` **never writes `modifiedText` to the buffer on open**; it keeps the
    original text and renders removed lines as CSS line-decorations + added lines
    as virtual `AddedWidget` block widgets (diffViewer.ts:97–104, 140–170).
    → directly targets **Bug 6 (premature application)** and the disk side of
    **Bug 4**.
  - Hunk nav already dispatches `EditorView.scrollIntoView(pos, {y:"center"})`
    (diffViewer.ts:414–428). → claims to fix **Bug 1**.
  - Toolbar position is computed from `coordsAtPos` and clamped
    `Math.max(20, Math.min(coords.top-68, innerHeight-80))` with a
    `rect.top+80` fallback when coords are null (diffViewer.ts:331–334, 547–564).
    → partial **Bug 11** handling; the fallback is the suspected residual.
  - Singleton (`getInstance`) with `offref`'d listeners → leak fixes (Bug 16/23/31).
- **`reviewFileEditProposals(targetFilepath, allProposals)`**
  (chatSidebar.ts:3525–3613) already:
  - filters `allProposals` to the clicked file by canonical vault path
    (chatSidebar.ts:3529–3533) → targets **Bug 2 / Bug 9** mapping;
  - applies every proposal into ONE `modifiedFullText` via the ambiguity-safe
    `findSearchBlock` matcher and shows a single multi-hunk diff
    (chatSidebar.ts:3584–3608);
  - counts partial failures and warns instead of silently corrupting (Bug 34).
- **`findSearchBlock`** (utils/editMatch.ts) is the unified matcher: exact →
  line-trim → anchored, returning `null` on ambiguity (never guesses). → the
  engine behind **Bug 6/9** "could not find".
- **`resolveVaultFile`** (chatSidebar.ts:3499–3523) already normalizes
  backslashes, base-path prefixes, leading slash, and `decodeURIComponent`. →
  targets **Bug 7**.
- **v0.14.0 edit-loop state machine** added scoped-edit enforcement: the prompt
  contract requires minimal SEARCH/REPLACE blocks and an Analysed→Reviewed→
  Updated→Reviewed loop. → partially mitigates **Bug 8 (consistency)** and
  **Bug 10 (token truncation)**.

## The real question for the Arena

Given the above, the danger is **re-fixing already-fixed bugs** and churning a
675-line module that was just stabilized. The Arena must decide:

1. Which of the 11 are **still live**, which are **already fixed**, which are
   **partial** — and demand *empirical reproduction in the testbed* before any
   code is designed (not assertion from the draft).
2. For genuinely-live defects, what is the **minimal, surgical** fix versus the
   user's stated desire for a "complete redesign" of the inline view + hover UI.
3. How bugs 8 & 10 relate to roadmap item 6 (prompt-architecture refactor) and
   the shipped v0.14.0 contract — and whether they belong in THIS milestone at
   all or should be deferred to avoid scope collision.
4. Agent↔user **state desync (Bug 4)** at the semantic level: even with the
   no-disk-write model, does the agent's conversation believe edits are applied?
   Where is the source of truth the agent reads back?

## Constraints inherited from the draft (user-approved via /grill-me)

- Inline **unified** view (no side-by-side, no floating modal) for the diff body.
- Edits are **UI proposals only**; disk is untouched until explicit Accept.
- Strict 1:1 mapping between a clicked review button and the hunk it renders.
- Accurate CM6 line-offset nav; clean cursor restoration after Accept.
- Robust path resolution.
- Enforce minimal scoped edit blocks to dodge token truncation.
- Deterministic `reviewInEditor` output across models.
