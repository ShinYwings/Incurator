# Frontend/Architecture Proposal: Triage-First, Surgical Diff Viewer Repair

Date: 2026-06-19 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

The draft asks for a "complete redesign," but the code shows a recently
stabilized inverted-decoration engine. A full rewrite would re-introduce the
exact leak/race bugs the v0.11.0 "Bug 1–34" comments record fixing. I propose a
**triage-first repair**, not a rewrite.

### Phase structure

**P0 — Empirical triage (mandatory, no code).** For each of the 11 reported
defects, write a reproduction note against the active testbed scenario and
classify: `LIVE` / `FIXED` / `PARTIAL`. Output: a triage table committed to the
evidence ledger. Only `LIVE`/`PARTIAL` items get design work. My pre-triage
hypothesis from reading the code:

| # | Defect | Hypothesis | Where |
|---|--------|-----------|-------|
| 1 | nav scroll | FIXED (scrollIntoView) | diffViewer.ts:414 |
| 2 | multi-file opens first | PARTIAL — singleton `.show()` races on rapid clicks | chatSidebar:3525 |
| 3 | cursor teleports to bottom | LIVE for Accept-All (`setCursor(finalEndPos)`) | diffViewer.ts:487 |
| 4 | agent desync | LIVE (semantic, not disk) | conversation read-back |
| 5 | inline unified view | PARTIAL — added lines are widgets, not true unified rows | diffViewer.ts:52 |
| 6 | premature disk write | FIXED (inverted model never writes on open) | diffViewer.ts:99 |
| 7 | file-not-found | PARTIAL — `getAbstractFileByPath` only; no case/trim-suffix retry | chatSidebar:3499 |
| 8 | model output variance | DEFER to item 6 / shipped v0.14.0 contract | systemPrompt.ts |
| 9 | selection mismatch | PARTIAL — single-file multi-hunk already unified; cross-file pill state can desync | chatSidebar:3530 |
| 10 | token truncation | PARTIAL — v0.14.0 scoping helps; add hard guard | — |
| 11 | hover misplacement | LIVE — null-coords fallback dumps toolbar to `rect.top+80` | diffViewer.ts:562 |

### Locked targets (the LIVE/PARTIAL set)

- **Bug 3 (cursor):** after Accept-All, restore the cursor to the *first* changed
  hunk line (cached at `show()` time) instead of `finalEndPos`. Single-hunk
  accept already re-renders with `preserveIdx`; keep that.
- **Bug 11 (hover):** when `coordsAtPos` returns null (hunk scrolled out of
  viewport), first `scrollIntoView` the hunk, then recompute coords on the next
  frame; only fall back to a *docked* in-editor bar (top-right of the editor
  pane, not `position:fixed` screen-top) if coords still fail. Anchor the toolbar
  relative to the editor's scroll DOM, not `document.body`.
- **Bug 2 / 9 (multi-file & pill state):** serialize `reviewFileEditProposals`
  behind a single in-flight guard so a second pill click cannot race the
  singleton's `close()`/`show()`. Render an explicit per-file/per-proposal status
  on each pill (`pending` / `reviewing` / `applied` / `not-found`) read from a
  message-scoped state map, so clicking pill B never inherits pill A's state.
- **Bug 7 (path):** extend `resolveVaultFile` with a final case-insensitive and
  trailing-whitespace-stripped basename scan over `getMarkdownFiles()` before
  giving up.
- **Bug 5 (unified view):** keep the inverted-decoration engine but make the
  rendering read as a true unified hunk: removed lines (in-buffer, red gutter)
  immediately followed by the added widget (green gutter) — already close; the
  work is CSS + ensuring ordering, not an engine rewrite.
- **Bug 4 (agent desync):** the agent must never assert "applied." After emitting
  edits, the assistant turn should state the edits are *proposed, pending your
  review in the Diff Viewer*. This is a one-line addition to the v0.14.0
  `getEditLoopContract()` post-edit REVIEWED phase wording — NOT a new system.

### Deferred (push to item 6)

- **Bug 8, Bug 10** beyond a simple guard: model-output determinism and token
  budgeting are prompt-architecture concerns the v0.14.0 contract already half
  owns. Re-opening the prompt here collides with item 6. We add only a
  **single hard guard**: if a single REPLACE would rewrite > N% of the file,
  reject it client-side with an honest notice (anti-whole-doc-rewrite), and log.

## 2. Pros & Cons

**Pros:** keeps the stabilized engine; every change traces to a reproduced LIVE
defect; no churn on the 34 prior fixes; avoids prompt-architecture collision.

**Cons:** the user asked for a "redesign" and may perceive triage-first as
under-delivering; the inline-unified polish (Bug 5) is CSS-bounded and may not
fully match vscodium's gutter feel; cross-file pill-state map is new state that
must be carefully torn down to avoid leaks.
