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

### 2026-06-19 — Reference Mode + "pin PDF as source" bug cluster (audit)

User report (verbatim): "there's a lot of bugs the current reference mode but
also when add pdf as a source using the pin button. please deeply check and
analyse the related code ... We additionally may need some code refactoring and
audit for bug finding."

Audit findings (Claude, while doing Plan F P6 locator slice). Each preserves the
exact code location and failure mode — do NOT compress these into a summary.

**Confirmed**

1. **Reference-mode locators opened the in-vault stub, not the real file.**
   Reference sources have a NOT-NULL `relpath` pointing to an in-vault markdown
   *stub* (`04_Resources/References/<name>.md`) plus an `external_path`/
   `external_uri` pointing to the real file. Any consumer that prefers `relpath`
   over `external_uri` opens the wrong target. The Sources & Trace panel
   (`plugin/src/ui/incuratorQueryTrace.ts` `locatorTarget`) had exactly this bug.
   FIXED this session: external references now open the real file (reference PDFs
   in the plugin external PDF viewer at the cited page; others via system
   handler); vault PDFs jump via `#page=N`. **Remaining work:** audit every OTHER
   consumer of locators/relpath for the same relpath-first assumption
   (`providerContextFormat.ts`, cross-reference resolver, any `openLinkText` on a
   reference source).

2. **Locator contract gap: `vault_pdf` + `external_uri` precedence was
   unspecified.** `backend/src/curator/context_service.py:271` labels a
   reference PDF `source_kind="vault_pdf"` (the `file_type=="pdf"` check precedes
   `is_reference`). Per SYSTEM_BEHAVIOR §29.2 this is *intended* — `vault_pdf`
   covers Reference Mode PDFs — but the spec never said `external_uri` is
   authoritative for opening when both it and the stub `relpath` are present.
   That ambiguity is what let consumers open the stub. RESOLVED this session by
   the panel fix (item 1) + a SYSTEM_BEHAVIOR §29.2 / PLUGIN_SCHEMA / EN+KR guide
   clarification: when `external_uri` is present, clients MUST open the external
   file, never the stub. **Remaining:** confirm no other consumer
   (`providerContextFormat.ts`, cross-reference resolver) still prefers relpath.

3. **(Downgraded — uncertain) Possible Zotero status cache-key edge case.**
   `plugin/src/ui/chatSidebar.ts` — write key in `onIncuratorStatusClick`
   (`statusKey`, ~2147) is `sourcePath || zotero:<key>`, where `sourcePath` may
   resolve via `status.currentPath`; the badge read (`renderIncuratorStatusBadge`
   ~2048) uses only `getPdfRefSourcePath(ref)`. Common paths AGREE (read falls
   back to `ref.backendStatus` when no path, and to the same path base
   otherwise). A divergence is only plausible after a rebind where the write key
   came from `status.currentPath` ≠ the read key. Needs a concrete repro before
   touching — do not hot-patch.

4. **Fragile Zotero detection via `getState()` any-casts.**
   `plugin/src/ui/chatSidebar.ts:2188-2191` decides `isZoteroPdf` by
   `leaf.view.getState().path === sourcePath` with `as any` casts that bypass
   types; for external PDFs without a resolved `sourcePath` this never matches.

**Needs verification**

5. `isAddedState` (`chatSidebar.ts:102`) treats only `l1_ready..l4_ready` as
   "Added", so during `queued`/`running` the badge stays clickable — confirm
   that's intended vs. a dedicated building state.

6. **(Verified — NOT a bug.)** Reference-PDF page locators resolve correctly.
   Spans carry their own `page_number`
   (`backend/src/curator/pipeline/source_spans.py:94,123`) and
   `_locator_from_span` reads it from the span, independent of the
   `source_pdf_pages` stub relpath. Closed.

Recommendation: the genuinely confirmed problem (item 1, locator open target +
its contract, item 2) is FIXED on the branch this session. The remaining open
items are the plugin badge/Zotero state machine (items 3 uncertain, 4, 5) — an
intertwined refactor that should get a small Plan-F-style plan + a concrete repro
per item BEFORE coding, rather than hot-patches. Do not implement 3-5 ad hoc.
