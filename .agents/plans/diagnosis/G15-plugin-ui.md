# Diagnosis: G15-plugin-ui
Coverage: Read `plugin/src/ui/diffViewer.ts`, `diffKeyGuard.ts`, `quickQueryPopover.ts`, `inlinePrompt.ts`, `incuratorDashboardModal.ts`, `incuratorQueryTrace.ts`, `incuratorQueryTraceLocator.ts`, `externalPdfView.ts`, `externalPdfState.ts`, `externalPdfRegistry.ts`, `externalPdfAnnotationStyle.ts`, `pdfCaptureService.ts`, `zoteroWizardModal.ts`, `zoteroRepairModal.ts`, `ingestDestinationModal.ts`, `gitSidechatCommands.ts`; read targeted tests `quickQueryPopover.test.ts`, `diffViewerSource.test.ts`, `incuratorDashboardModal.test.ts`, `zoteroWizardModal.test.ts`, `externalPdfState.test.ts`, `externalPdfPersistence.test.ts`, `externalPdfViewSource.test.ts`, `pdfCaptureService.test.ts`, `incuratorQueryTraceLocator.test.ts`. Excluded `chatSidebar.ts` body; only used `rg` to confirm DiffViewer callsites.

## Findings

### [G15-1] (a,h,i) S2 — Closing one UI request can abort unrelated LLM work
- Loc: `plugin/src/ui/quickQueryPopover.ts:552`, `plugin/src/ui/quickQueryPopover.ts:559`, `plugin/src/ui/inlinePrompt.ts:58`
- Evidence: Quick query intentionally supports multiple independent child popovers (`childPopovers` at `quickQueryPopover.ts:127`), but each session calls the singleton `this.plugin.llmClient.abort()` when its popover closes while processing. `InlinePromptWidget.close()` also always calls `this.plugin.llmClient.abort()` even after success paths call `this.close()` before opening the diff. Because the LLM client is plugin-global, closing one quick query or inline prompt can cancel a different active quick query, sidebar request, or inline edit.
- Fix sketch: Move cancellation to a per-request handle, e.g. `llmClient.streamChat(..., { signal })` or a returned `cancel()` function owned by the UI session. Only abort when the session that started the request is still active. In inline prompt, abort only if a current inline request exists.
- Blast radius: `llmClient` request API, quick query, inline prompt, any sidebar code sharing the same client cancellation state.
- Suggested PR: `fix/plugin-ui-request-cancellation`

### [G15-2] (h,c) S2 — Quick query popout selection can detach listeners from the wrong window
- Loc: `plugin/src/ui/quickQueryPopover.ts:181`, `plugin/src/ui/quickQueryPopover.ts:222`, `plugin/src/ui/quickQueryPopover.ts:270`, `plugin/src/ui/quickQueryPopover.ts:274`
- Evidence: `handleSelectionChange()` assigns `this.activeDoc = doc` before `showButton()` calls `removeButton()`. `attachRepositionListeners()` binds scroll/resize to `this.activeWin`, and `detachRepositionListeners()` also removes from the current `this.activeWin`. If a trigger button was attached in one Obsidian window/popout and the next selection arrives from another, the previous listener is removed from the new window instead of the old one.
- Fix sketch: Store `repositionWin` alongside `repositionHandler` and always detach from that stored window, or remove the old button/listeners before mutating `activeDoc`. Add a small test with two fake windows.
- Blast radius: Quick query trigger lifecycle, popout window support, scroll/resize handler cleanup.
- Suggested PR: `fix/plugin-ui-quickquery-popout-listeners`

### [G15-3] (a,e,b) S2 — DiffViewer singleton contract is bypassed by inline prompt
- Loc: `plugin/src/ui/diffViewer.ts:113`, `plugin/src/ui/diffViewer.ts:117`, `plugin/src/ui/diffViewer.ts:147`, `plugin/src/ui/inlinePrompt.ts:240`
- Evidence: `DiffViewer` documents a strict singleton to prevent duplicate DOM/listener instances, but its constructor is public and `InlinePromptWidget` uses `new DiffViewer(this.plugin)` directly. That bypasses `DiffViewer.getInstance()` and can coexist with the singleton instance used elsewhere, reintroducing multiple key handlers/toolbars/decorations for the same document.
- Fix sketch: Make the constructor private if TypeScript constraints allow it, route inline prompt through `DiffViewer.getInstance(this.plugin)`, and add a source-contract test that forbids `new DiffViewer(` outside the class.
- Blast radius: Inline edit diff review, keyboard shortcut focus gating, diff toolbar cleanup.
- Suggested PR: `fix/plugin-ui-diffviewer-singleton`

### [G15-4] (a,i) S3 — Inline prompt drops no-change/editor-not-ready diff results
- Loc: `plugin/src/ui/diffViewer.ts:178`, `plugin/src/ui/diffViewer.ts:180`, `plugin/src/ui/diffViewer.ts:184`, `plugin/src/ui/inlinePrompt.ts:240`
- Evidence: `DiffViewer.show()` returns `{ opened: false, reason: "no_changes" }` or `"editor_not_ready"` so callers can explain why no diff opened. Inline prompt ignores the return value after closing its prompt, so a no-op model response or missing CM6 editor produces no notice and no prompt UI.
- Fix sketch: Capture the `DiffOpenResult` in inline prompt. Surface "no changes" and "editor not ready" notices, and consider reopening/enabling the prompt for editor readiness failures.
- Blast radius: Inline edit UX only.
- Suggested PR: `fix/plugin-ui-inline-diff-result`

### [G15-5] (a,i) S2 — Inline edit strips meaningful whitespace from model output
- Loc: `plugin/src/ui/inlinePrompt.ts:228`, `plugin/src/ui/inlinePrompt.ts:265`
- Evidence: `stripCodeFences()` calls `text.trim()` before matching fences and returns `trimmed` for non-fenced output. It also returns `fenceMatch[1].trim()`. For code, Markdown tables, YAML, lists, or selected text with leading/trailing blank lines, this silently changes the proposed edit before the user sees the diff.
- Fix sketch: Preserve exact output by default. Detect full-output code fences with a non-destructive regex, unwrap only the fence delimiters, and avoid trimming the captured content except for one optional final newline introduced by the fence wrapper.
- Blast radius: Inline edit output fidelity and diff expectations.
- Suggested PR: `fix/plugin-ui-inline-preserve-whitespace`

### [G15-6] (h,g) S2 — Dashboard Jobs tab can stack polling intervals
- Loc: `plugin/src/ui/incuratorDashboardModal.ts:144`, `plugin/src/ui/incuratorDashboardModal.ts:150`, `plugin/src/ui/incuratorDashboardModal.ts:159`, `plugin/src/ui/incuratorDashboardModal.ts:1232`
- Evidence: `switchTab()` clears `jobsTimer` only when switching away from Jobs. Re-entering or re-rendering the Jobs tab while already active, including `this.switchTab("jobs")` after cancel/rerun actions, calls `renderJobs()` and installs another 2s interval without clearing the existing one.
- Fix sketch: Clear any existing `jobsTimer` before starting `renderJobs()`, or make the Jobs panel own a single polling controller that is idempotent on render.
- Blast radius: Dashboard Jobs tab, backend `wiki status --json` load, detached DOM writes from stale pollers.
- Suggested PR: `fix/plugin-dashboard-single-jobs-poller`

### [G15-7] (h,a) S2 — External PDF text extraction can mutate stale page/index state
- Loc: `plugin/src/ui/externalPdfView.ts:937`, `plugin/src/ui/externalPdfView.ts:997`, `plugin/src/ui/externalPdfView.ts:1001`, `plugin/src/ui/externalPdfView.ts:1256`
- Evidence: `renderPagesInRange()` token-checks before and after `await this.renderPageCanvas(...)`, but `renderPageCanvas()` starts `extractPageTextFromPdfJs(...).then(...)` without awaiting or token-checking the continuation. If reload, zoom rerender, or doc switch happens after canvas render but before text extraction resolves, the stale continuation can write text layers, set `pageTextCache`, and upsert the `documentIndex` for the wrong render generation.
- Fix sketch: Pass the render token and doc id into `renderPageCanvas()` / `extractPageTextFromPdfJs()`, await extraction, and bail before mutating DOM/cache/index if token/doc changed or the page element disconnected.
- Blast radius: External PDF context capture, PDF RAG hits, Zotero highlight layers, reload/zoom correctness.
- Suggested PR: `fix/plugin-pdf-render-token-guards`

### [G15-8] (h,c) S2 — External PDF close does not invalidate pending render continuations
- Loc: `plugin/src/ui/externalPdfView.ts:478`, `plugin/src/ui/externalPdfView.ts:879`, `plugin/src/ui/externalPdfView.ts:880`, `plugin/src/ui/externalPdfView.ts:913`
- Evidence: `onClose()` clears zoom debounce and one animation frame but does not increment `renderToken`. `renderPdf()` schedules untracked `setTimeout()` callbacks for page jump, annotation scroll, highlight reset, and scroll handler installation. Closing a view during load leaves those callbacks with a still-valid token and permission to call `goToPage()`, `syncState()`, or mutate detached elements.
- Fix sketch: Increment `renderToken` in `onClose()`, track timeout ids in `clearTimers()`, and gate delayed continuations on both token and `this.contentEl.isConnected`.
- Blast radius: External PDF view lifecycle, layout persistence, popout/leaf close behavior.
- Suggested PR: `fix/plugin-pdf-close-cancels-render`

### [G15-9] (g,i) S2 — External PDF open still does synchronous file IO and all-page metadata scanning
- Loc: `plugin/src/ui/externalPdfView.ts:797`, `plugin/src/ui/externalPdfView.ts:856`, `plugin/src/ui/externalPdfView.ts:858`, `plugin/src/ui/externalPdfView.ts:1237`
- Evidence: `loadPdfData()` uses `readFileSync()` for path-backed PDFs in the renderer process, then `renderPdf()` serially calls `pdf.getPage(i)` for every page to create placeholders even though canvas rendering is lazy. Large Zotero PDFs can freeze Obsidian before the first page becomes usable.
- Fix sketch: Use async `fs.promises.readFile` or a file-handle/URL path supported by pdf.js. Virtualize page placeholders or lazily populate base dimensions around the viewport, with a coarse estimated height until measured.
- Blast radius: External PDF open performance, Zotero external-reference workflows, memory pressure.
- Suggested PR: `perf/plugin-pdf-nonblocking-open`

### [G15-10] (h,c) S2 — Snipping mode leaks a global Escape listener on cancel/close
- Loc: `plugin/src/ui/externalPdfView.ts:513`, `plugin/src/ui/externalPdfView.ts:540`, `plugin/src/ui/externalPdfView.ts:546`, `plugin/src/ui/externalPdfView.ts:597`
- Evidence: `startSnippingMode()` adds `document.addEventListener("keydown", handleKeyDown)` and removes it only on Escape or mouseup. `cancelSnippingMode()` only removes overlay elements; `onClose()` does not clean the snip key handler. A toolbar cancel, reload, view close, or programmatic `cancelSnippingMode()` can leave a stale global listener alive. It also binds to global `document` rather than the PDF view owner document.
- Fix sketch: Store a snip cleanup callback and owner document, call it from `cancelSnippingMode()` and `onClose()`, and prefer Obsidian `registerDomEvent()` where possible.
- Blast radius: PDF snipping, popout keyboard behavior, view lifecycle cleanup.
- Suggested PR: `fix/plugin-pdf-snipping-cleanup`

### [G15-11] (a,i) S2 — Zotero import modal closes after failed imports
- Loc: `plugin/src/ui/zoteroWizardModal.ts:406`, `plugin/src/ui/zoteroWizardModal.ts:491`
- Evidence: The Import button awaits `this.doImport()` and then unconditionally calls `this.close()`; `doImport()` catches all exceptions, logs them, and shows a failure notice without rethrowing. Result: metadata/template/folder/write failures still close the modal and discard the user's form context.
- Fix sketch: Make `doImport()` return `true` on success and `false` on handled failure, or rethrow after showing the notice. Close only on success and re-enable the Import button on failure.
- Blast radius: Zotero import wizard UX and tests around failed import paths.
- Suggested PR: `fix/plugin-zotero-import-failure-lifecycle`

### [G15-12] (c,i) S3 — Zotero repair async failures are not surfaced
- Loc: `plugin/src/ui/zoteroRepairModal.ts:159`, `plugin/src/ui/zoteroRepairModal.ts:161`, `plugin/src/ui/zoteroRepairModal.ts:174`
- Evidence: Refresh is invoked as `void this.refresh()` with no catch. Save wraps `initZotero()` in `try/finally` but has no `catch`, so a rejected backend call re-enables the button but shows no user-visible error. `refresh()` itself awaits `getZoteroStatus()` without any failure handling.
- Fix sketch: Catch both refresh and save failures, render an inline error row plus a `Notice`, and preserve the user's typed paths.
- Blast radius: Zotero setup/repair modal only.
- Suggested PR: `fix/plugin-zotero-repair-errors`

### [G15-13] (d,b,e) S3 — DiffViewer retains unused removed-line widget code
- Loc: `plugin/src/ui/diffViewer.ts:29`, `plugin/src/ui/diffViewer.ts:30`
- Evidence: `RemovedWidget` is defined "for CSS class compatibility", but `rg "RemovedWidget" plugin/src/ui/diffViewer.ts` only finds the class declaration and its `eq()` type reference. Removed lines are now rendered as line decorations, so this compatibility widget is dead code in a high-risk diff file.
- Fix sketch: Delete `RemovedWidget` if no CSS/test depends on its classes, or move the CSS-compatibility rationale into a test if it must remain. Keep the diff file focused on the active inverted-decoration model.
- Blast radius: Diff viewer CSS only if any stylesheet still targets `.ai-agent-diff-inline-removed-block`.
- Suggested PR: `chore/plugin-diffviewer-remove-dead-widget`

### [G15-14] (f,i) S3 — External PDF reopen copy contradicts current path persistence
- Loc: `plugin/src/ui/externalPdfView.ts:696`, `plugin/src/ui/externalPdfView.ts:700`, `plugin/src/ui/externalPdfRegistry.ts:87`
- Evidence: The empty-state copy says Obsidian's security sandbox prevents saving absolute file paths. The registry now persists path-backed docs in localStorage and `registerExternalPdfByPath()` returns/persists `path`; tests also pin path retention. When reopening fails now, the likely causes are missing path, moved/deleted file, unavailable volume, or sandbox-limited chooser path, not a blanket inability to save paths.
- Fix sketch: Update the UI copy to distinguish "no saved path" from "saved path not available", and include the compact attempted path when known.
- Blast radius: External PDF empty-state text and possibly docs/screenshots describing restore behavior.
- Suggested PR: `docs/plugin-pdf-reopen-copy-sync`

### [G15-15] (g,i,e) S3 — Query-trace external PDF links create a new registry entry every click
- Loc: `plugin/src/ui/incuratorQueryTrace.ts:464`, `plugin/src/ui/incuratorQueryTrace.ts:469`, `plugin/src/ui/externalPdfRegistry.ts:87`
- Evidence: `openExternalPdfLocator()` calls `registerExternalPdfByPath(filePath)` on every click. `registerExternalPdfByPath()` always generates a new random doc id and persists it. Repeated clicks on the same evidence locator create duplicate external-PDF registry entries and open fresh tab state rather than reusing the same document identity.
- Fix sketch: Add `getOrRegisterExternalPdfByPath(filePath, attachmentKey?)` keyed by canonical path and optional Zotero attachment key, then reuse an existing doc id when present.
- Blast radius: Query trace locator navigation, external PDF localStorage growth, repeated evidence-click UX.
- Suggested PR: `fix/plugin-trace-reuse-external-pdf-docs`

## Positives (keep / do-not-break)
- Quick query has useful pure tests for positioning, thinking-strip behavior, no-tools isolation, persistent popover lifecycle, and LaTeX-preserving selection/copy.
- Diff viewer has important source-contract tests pinning "do not write buffer on open", CM6 scroll navigation, caret restoration, and toolbar anchoring.
- External PDF state/registry helpers now have pure tests for path retention, state sync, portable Zotero-backed restore, and locator target decisions.
- Dashboard avoids stale runtime snapshot files for its core status path and has tests pinning live `wiki status --json` usage plus model-selector behavior.
- Zotero wizard helper functions for MRU profiles and recent items are isolated and unit-tested.
- Query trace locator resolution is separated into a pure helper, which makes external-reference vs vault-link behavior testable.

## Open questions for the human
- Should plugin UI support multiple simultaneous LLM requests as a product goal? Quick query's child-popover design says yes; if yes, per-request cancellation should be prioritized.
- Should external PDF document identity be path-based, Zotero-attachment-key-based, or "one tab per click"? The current trace behavior persists a new random id per click.
- Is popout window support required for quick query and external PDF snipping in Phase A fixes, or should those be validated later with a dedicated popout testbed?
- For inline edit, should the model output be treated as byte-for-byte proposed replacement except for explicit full-output fence wrappers? Current trimming is unsafe for code and structured text.
- Should the dashboard be split into panel modules during the Phase A stability work, or deferred to a later UI architecture PR after the concrete polling/lifecycle fixes land?
