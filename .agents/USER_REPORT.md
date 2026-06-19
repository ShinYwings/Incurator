# User Report

This document is a **plain Inbox (backlog) log** that records bugs reported by the user, required features, ideas, etc., in chronological order without any filtering.

Agents must check this document and triage the received items into the `To-Do (Queuing)` area or `Icebox` area of `.agents/ROADMAP.md`. Once the triage is complete, **immediately delete** the item from this document.

## 📝 User Inbox

### 2026-06-19 — Persistent Quick Query Popover: review findings (quickQueryPopover.ts)

Reviewer findings on existing `plugin/src/ui/quickQueryPopover.ts` (v0.5.4, 449
LOC), tied to the persistent-popover upgrade (`.agents/drafts/persistent_popover.md`
Constraints 1/2/4 + ROADMAP item: "immune to outside clicks, freely draggable,
minimizable"). Separate track from Plan G (PDF handling). Preserve verbatim:

1. **Memory leak / state-mutation order (`openForCurrentSelection`).** Lines
   181-184 mutate `this.activeDoc`/`this.anchorRange` BEFORE `openPopover(rect)`
   runs its cleanup (lines 265-266 call `removeButton()`/`removePopover()` →
   `detachRepositionListeners()`). `detachRepositionListeners()` uses the
   `this.activeWin` getter; since `activeDoc` was already reassigned, it removes
   listeners from the NEW window — listeners on the previous window leak (zombie
   listener across popout windows). Fix: run all teardown (removeButton,
   removePopover) strictly BEFORE reassigning `activeDoc`/`anchorRange`.
2. **Event-target text-node crash (`handleDocumentClick`, line 436).**
   `const el = target instanceof Element ? target : null` — clicking a raw text
   node yields `null`, bypassing the `.closest()` check and dismissing the UI.
   `isInsideOwnUi` (line 190) handles this via `node?.parentElement`. Fix:
   `target instanceof Node ? target.parentElement : null`. ALSO (Constraint 1 /
   click-away immunity) `handleDocumentClick` must stop dismissing `popoverEl`
   entirely.
3. **Scroll-pinning coupling violation (`attachRepositionListeners`, line 242).**
   The scroll/resize handler repositions BOTH the trigger button and the popover
   to follow `anchorRange`. Constraint 2: the popover must abandon automatic
   scroll-repositioning once spawned (fixed palette). Fix: handler updates only
   `this.buttonEl`; `popoverEl` positioned once on creation, then ignores
   background scroll.
4. **Missing DOM ref for dynamic title (Constraint 4, line 277).** Title span is
   created inline without capture, so `runQuery()` can't update it. Fix: capture
   `this.titleEl` and `this.titleEl.setText(question)` on submit.
5. **Missing drag & minimize state.** No drag coords (startX/startY/currentX/
   currentY) or minimized boolean. Fix: header `mousedown`/`mousemove`/`mouseup`
   for absolute positioning + a minimize control toggling `.minimized` (hide
   input/answer containers, keep header).

Related: `.agents/drafts/popover_tool_scope.md` (popover MCP tool-injection /
prompt-duplication / path-sandboxing) is a SEPARATE, more serious popover concern
— do not conflate; plan separately.

Recommendation: this is a substantial review-requested feature with a ready
draft → give it its own Arena plan (briefing = persistent_popover.md + these 5
findings). The two pure bugs (#1 teardown order, #2 text-node) are entangled with
the feature constraints (#2's immunity rewrites the same method), so fold them
into that plan rather than hot-patching.
