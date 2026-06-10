# Agent Edit & Diff Viewer Reliability Plan

## Context
Triaged from USER_REPORT on 2026-06-11. Supersedes the smaller "Diff Viewer
UI/UX Improvement" bullet previously held in `minor_quick_wins.md`. The
`ai-agent-edit` apply path is unreliable: SEARCH/REPLACE matching fails, diffs
don't render in the `.md` file, edit scope is wrong, and the diff UX is
inconvenient. User tagged the worst parts [hotfix].

## Observed Symptoms (verbatim evidence to preserve)
- `ai-agent-edit` "keeps failing SEARCH matching" → no diff appears in the `.md`
  file, no hover.
- Inserting an image (`![alt text](image.png)`) produces garbage artifacts such
  as a stray heading + `>>>>` lines in the output.
- Edit-scope bug: the request was "add section 4 from the chat answer to Overall
  note's 1.3", but the agent appended the **entire** answer instead of just
  section 4. Behavior varies by model reasoning strength (a weaker model
  produced no diff; a stronger model produced a diff but wrong scope).
- Diff UX gaps: no edit counter (e.g. `1/8`), no animated next/prev navigation
  arrows between hunks.
- Diff is gated behind a "Review diff" button — user wants the diff to render
  immediately.
- Diffs are being written into `00_System/Agent Diffs/` — user wants this
  stopped. Benchmark how VSCode/VSCodium builds its in-memory diff view (study
  the VSCodium repository) instead of creating on-disk diff files.

## Requirements
1. **Robust SEARCH/REPLACE matching** in the agent-edit apply path (whitespace /
   fuzzy / anchor tolerance) so edits reliably locate their target block.
2. **Precise edit scope** — when the user references a specific numbered section
   of a chat answer, edit only that section, not the whole message.
3. **Immediate diff rendering** (drop the "Review diff" gate).
4. **Hunk navigation UX**: edit counter (`n/total`) and prev/next navigation.
5. **No on-disk diff files** in `00_System/Agent Diffs/`; use an in-memory /
   ephemeral diff view modeled on VSCodium's approach.
6. **Image-insertion artifact fix** (no stray heading/`>>>>` injection).

## Files Likely Involved
- Plugin agent-edit / SEARCH-REPLACE apply logic (`plugin/src/**`,
  `ai-agent-edit`)
- `plugin/src/ui/diffViewer.ts`, `plugin/styles.css`
- Wherever `00_System/Agent Diffs/` files are written

## Notes
- This is plugin-only TS work → needs `.test.ts` coverage (CLAUDE.md test
  mandate).
- Reference VSCodium diff-view implementation as a benchmark before designing.
