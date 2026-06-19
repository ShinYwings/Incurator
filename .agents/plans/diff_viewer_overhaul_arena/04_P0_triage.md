# P0 — Empirical Triage Results (Evidence Ledger)

Date: 2026-06-19 | Phase: P0 (no fix code written)

## Method & honesty note

These are Obsidian-UI defects; there is **no headless harness to click
Accept/Reject inside Obsidian**. Reproduction is therefore:
- **(a) Authoritative code-trace** through the exact live paths (file:line cited).
- **(b) Existing unit suite**: `editMatch.test.ts` + `chatSidebarSource.test.ts`
  = 30 tests green; full plugin suite = 443 green at v0.14.0.

**Validation gap:** interactive click-confirmation in a live vault was not
performed (no UI automation available). The static traces below are
high-confidence (the relevant logic is deterministic and cited), but the user
should spot-confirm the two `LIVE` items in their own Obsidian before P3.

## Triage table

| # | Defect | Verdict | Evidence (file:line) |
|---|--------|---------|----------------------|
| 1 | Nav arrows don't scroll to hunk | **FIXED** | `refreshHunkUI` dispatches `EditorView.scrollIntoView(pos,{y:"center"})`; `goHunk` updates index→refresh — diffViewer.ts:407–428 |
| 2 | Multi-file: later buttons open first file | **PARTIAL** | Core mapping fixed: `reviewInEditor` passes `prop.filepath`; `reviewFileEditProposals` filters by canonical path & opens that file — chatSidebar.ts:2951, 3526–3572. **Residual: no in-flight guard** → rapid pill clicks race the singleton `close()`/`show()` (async awaits at 3565–3568) |
| 3 | Accept teleports cursor to bottom | **LIVE** | `acceptAll` does `setCursor(finalEndPos)` = end of modified region; whole-file review (`selectionStart={0,0}`) ⇒ doc bottom — diffViewer.ts:480–488. (`acceptCurrentHunk` does NOT move cursor, so single-hunk accept is fine) |
| 4 | Agent desync / edits stale context | **PARTIAL** | State level FIXED: `show()` never writes before Accept (inverted model, diffViewer.ts:99,140–170) and context is re-read fresh every turn via `editor.getValue()` — main.ts:1372, 1476. **Residual: conversational framing only** — agent may say "applied"; fix = 1-line wording in v0.14.0 `getEditLoopContract()` post-edit phase |
| 5 | Inline unified view (vscodium-like) | **PARTIAL** | Already inline+unified-ish: removed lines in-buffer (red line deco) + added lines as green block widgets, no side-by-side/modal — diffViewer.ts:22–79,184–218. **Gap: widget blocks lack CM6 gutter/line-number alignment** (cosmetic; true gutter = out of scope per Arena) |
| 6 | Premature disk write before Accept | **FIXED** | `show()` performs no `replaceRange`; writes happen only in `acceptCurrentHunk`/`acceptAll` — diffViewer.ts:99,433–491. "Could not find SEARCH" is honest matcher-null (findSearchBlock), not a premature write |
| 7 | File-not-found on existing files | **PARTIAL** | `resolveVaultFile` normalizes `\`→`/`, base-path, leading slash, `decodeURIComponent` — chatSidebar.ts:3499–3523. **Missing: case-insensitive + trailing-whitespace basename fallback scan** over `getMarkdownFiles()` |
| 8 | Inconsistent `reviewInEditor` output by model | **PARTIAL → DEFER** | Parser tolerates variants (3+ markers, bare blocks) — chatSidebar.ts:3617–3650; v0.14.0 contract tightened format/scoping. Remaining determinism is prompt-architecture (roadmap item 6) |
| 9 | Selection mismatch / others fail "not found" | **PARTIAL** | Single-file multi-hunk now merged into ONE diff & accept/reject recompute from chunks (no re-search) — chatSidebar.ts:3584–3608, diffViewer.ts:505–543, so the in-session cascade is gone. **Residual: pills carry no status** → re-clicking an already-accepted file's pill re-runs `findSearchBlock` on the now-changed file ⇒ "could not find". Fix = derived per-pill status |
| 10 | Token-limit truncation (whole-doc rewrite) | **PARTIAL** | `warnIfLargeReplacement` warns (non-blocking) when REPLACE ≥40 lines & >4× matched — chatSidebar.ts:3211–3220; v0.14.0 scoping helps. **No hard client-side reject**; truncation itself is provider-side |
| 11 | Hover toolbar jumps to screen top | **LIVE** | `getScreenCoordsAt` falls back to `{top: rect.top+80}` when `coordsAtPos` returns null (hunk off-screen) — diffViewer.ts:547–564; toolbar is `position:fixed` on `document.body` (331–345), so an off-screen first hunk anchors the bar near the editor top regardless of hunk location |

## Roll-up

- **FIXED (2):** #1 nav, #6 premature write. → No work; add regression tests only.
- **LIVE (2):** #3 cursor-on-Accept-All, #11 hover anchor. → Tier A.
- **PARTIAL (7):** #2 race, #4 framing, #5 polish, #7 path, #8 (defer to item 6),
  #9 pill status, #10 (warn exists; optional hard guard).

## Recommended Tier split (for sign-off)

- **Tier A — ship (v0.14.1):** #3, #11, #2 (in-flight guard), #7 (path fallback),
  #9 (derived pill status), #4 (1-line "proposed, not applied" wording). + #1/#6
  regression tests.
- **Tier B — gated / deferred:** #5 (CSS/ordering polish only, with the no-CM6-
  gutter caveat); #8 + #10 deferred to roadmap item 6 (optionally add the #10
  hard-reject guard now if the user wants it).

## Divergence from the pre-P0 hypothesis (proposal 01)

Hypothesis held. Refinements confirmed by trace: #4 is framing-only (context is
re-read live every turn — stronger "fixed" than hypothesized); #9's in-session
cascade is resolved and the true residual is pill-status, not the matcher; #2's
core mapping is fixed and only the click-race remains.
