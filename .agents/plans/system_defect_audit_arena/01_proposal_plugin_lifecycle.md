# plugin_lifecycle Proposal: Cancellation, Window-Ownership, and Shared-Cache Lifecycle Defects
Date: 2026-08-04 | Agent Persona: Plugin Lifecycle Auditor

> **Document structure.** This file holds TWO independent inspector passes over the same
> domain. **Pass B (below, findings PL-1..PL-4)** is the current pass. **Pass A (retained
> verbatim at the bottom, findings F1..F4)** is the earlier pass; it is preserved in full
> because its findings are distinct from Pass B's and have not been refuted. The two passes
> **disagree on one point** — Pass A's "judged clean" list asserts that
> `beginRequest`/`endRequest` satisfy §1.4 because "the owner-signal listener is removed on
> settle"; **PL-1 refutes that for the CLI branch**, where the listener is removed at
> *launch*. Where the passes conflict, PL-1 carries the executable evidence.

---

# PASS B — Current inspection

Scope inspected: `plugin/src/agent/llm/LLMClient.ts`, `plugin/src/agent/llm/messageUtils.ts`,
`plugin/src/agent/llm/localPdfTools.ts`, `plugin/src/agent/syncScheduler.ts`,
`plugin/src/ui/quickQueryPopover.ts`, `plugin/main.ts` (lifecycle wiring only),
`plugin/src/types.ts` (effort normalization only).
Specs read: PLUGIN_SCHEMA §1.4 (L256-282), §2.2 (L771-851), §13.5/§13.6/§13.7 (L2034-2273).
CAND-06 (sidechat `workspacePath`) is out of scope by instruction and is not restated.

## 1. Core Logic & Implementation

### PL-1 [P2] `complete()` ends the request before the CLI transport settles, tearing off the caller's abort listener mid-flight

`plugin/src/agent/llm/LLMClient.ts:1229-1327`

```ts
  async complete(
    messages: LLMMessage[],
    opts?: { model?: string; toolPolicy?: ToolPolicy; signal?: AbortSignal }
  ): Promise<string> {
    const controller = this.beginRequest(opts?.signal);
    try {
      ...
      if (this.shouldUseCli(messages)) {
        return this.completeViaCli(messages, toolPolicy, model, controller.signal);   // :1250
      }
      ...
    } finally {
      this.endRequest(controller);                                                    // :1326
    }
  }
```

`return <promise>` inside `try { } finally { }` is **not** awaited: the `finally` block runs
as soon as the return completion is produced, i.e. *before* `completeViaCli`'s promise
settles. Verified empirically with a scratch Node script (`return later(50)` in try/finally):
observed order `finally-ran -> t+10 -> inner-settled`. The non-CLI branches below are safe
only because they genuinely `await` (`await fetch`, `await this.withAbort(...)`) before
returning.

`endRequest` is precisely the wrong thing to run early:

```ts
  private beginRequest(ownerSignal?: AbortSignal): AbortController {   // :704
    const controller = new AbortController();
    if (ownerSignal) {
      const abortFromOwner = () => controller.abort(ownerSignal.reason);
      ...
        ownerSignal.addEventListener("abort", abortFromOwner, { once: true });
        this.requestAbortCleanup.set(controller, () => {
          ownerSignal.removeEventListener("abort", abortFromOwner);
        });
    }
    if (!ownerSignal) {
      this.foregroundRequestControllers.add(controller);
      this.foregroundRequestController = controller;
    }
    return controller;
  }

  private endRequest(controller: AbortController): void {              // :724
    this.requestAbortCleanup.get(controller)?.();     // <-- detaches the owner abort listener
    this.requestAbortCleanup.delete(controller);
    this.foregroundRequestControllers.delete(controller);
    if (this.foregroundRequestController === controller) {
      const remaining = Array.from(this.foregroundRequestControllers);
      this.foregroundRequestController = remaining[remaining.length - 1] ?? null;
    }
  }
```

`shouldUseCli` (`:1330-1333`) returns `true` for every provider except `ollama`/`deepseek`,
so the defective branch is the **default** one for antigravity / claude / codex.

**Failure scenario A — caller signal (Quick Query popover, non-streaming).**
`plugin/src/ui/quickQueryPopover.ts:535-538` uses `complete()` whenever
`settings.streamingEnabled` is false — a user-facing toggle (`plugin/src/settings.ts:382-384`;
default `true` at `plugin/src/types.ts:182`):

```ts
        raw = await this.plugin.llmClient.complete(messages, {
          toolPolicy: POPOVER_PROFILE.toolPolicy,
          signal: requestController.signal,
        });
```

Timeline with provider `antigravity`: `beginRequest` attaches `abortFromOwner` to the
popover's signal → `completeViaCli` spawns `agy` (8–12 s typical; `--print-timeout` defaults
to 300 s) → the `finally` fires immediately → `endRequest` runs the stored cleanup and
**removes `abortFromOwner`**. The user then presses `Escape` or the close button;
`removePopover()` (`quickQueryPopover.ts:632-636`) calls
`this.requestAbortController?.abort()`; the owner signal aborts and **nobody is listening**.
`controller.signal` never aborts, so `execFileAsync(..., { signal })` in `completeViaCli`
(`:1965-1972`) never kills the sandboxed subprocess. This violates §13.4 ("An in-flight quick
query is aborted when its popover is dismissed") and §1.4 ("Every public provider request owns
a locally captured `AbortController` **for its complete lifetime**").

**Failure scenario B — no caller signal (foreground mis-cancellation).** `editText()`
(`:2650-2653`) calls `this.complete(messages)` with no signal, so `beginRequest` installs it
as `foregroundRequestController`. `endRequest` then runs instantly and restores the pointer to
the previously-remaining controller. Concretely: sidebar stream S is running (foreground); the
user fires an inline edit E while S streams; E is foreground for microseconds, then foreground
reverts to S. The user presses Stop intending to cancel E — `abort()` (`:700-702`) aborts **S**
instead, and E keeps running. §1.4's "when a newer request finishes, an older still-active
request becomes foreground again" is being applied at *launch* time rather than at *finish*
time.

**Existing coverage check.** `plugin/src/agent/llmClient.test.ts:258-278` ("preserves
non-streaming Ollama AbortError") is the only `complete()`+signal abort test and it pins
`provider: "ollama"` — the branch that never reaches `completeViaCli`. No test in the plugin
greps `endRequest` at all. The CLI branch is unpinned.

**Fix direction.** `return await this.completeViaCli(...)` at both `:1250` and `:1318` (the
401/403 CLI-retry fallback has the identical shape). Add a regression test driving `complete()`
with a stubbed CLI provider plus an owner signal, asserting the child-process signal aborts.

---

### PL-2 [P2] Quick-query reposition listeners are detached against the *current* `activeDoc`, leaking capture-phase listeners on every other Obsidian window

`plugin/src/ui/quickQueryPopover.ts:125-146, 191-194, 232-253, 284-294`

```ts
  private activeDoc: Document = document;                    // :125
  private get activeWin(): Window {                          // :144
    return this.activeDoc.defaultView ?? window;
  }
  ...
  private attachRepositionListeners(): void {                // :268
    if (this.repositionHandler) return;
    const handler = () => { ... };
    this.repositionHandler = handler;
    this.activeWin.addEventListener("scroll", handler, true);
    this.activeWin.addEventListener("resize", handler);
  }

  private detachRepositionListeners(): void {                // :284
    if (!this.repositionHandler) return;
    this.activeWin.removeEventListener("scroll", this.repositionHandler, true);
    this.activeWin.removeEventListener("resize", this.repositionHandler);
    this.repositionHandler = null;
  }
```

`detachRepositionListeners` resolves the window *lazily at detach time*. The sibling
`detachDragListeners` (`:453-457`) does it correctly by storing `this.dragState.win` at attach
time — that is the intended pattern, applied one place and missed in the other.

The mouse/keyboard selection path mutates `activeDoc` **before** tearing down the old button:

```ts
    this.activeDoc = doc;                 // :191
    this.anchorRange = range.cloneRange();
    this.capturedSelection = text.slice(0, MAX_SELECTION_LENGTH);
    this.showButton(rect);                // :194 → showButton() line 233 calls this.removeButton()
```

`showButton` opens with `this.removeButton()` (`:233`), which calls
`detachRepositionListeners()` (`:294`) — but `activeWin` is already the **new** document's
window.

Multi-window is explicitly supported, not hypothetical (`plugin/main.ts:302-307`):

```ts
      this.app.workspace.on("window-open", (_workspaceWindow, win: Window) => {
        registerQuickQueryDom(win.document);
```

and `registerQuickQueryDom` (`main.ts:215-222`) calls
`this.quickQuery.handleSelectionChange(doc)` with that popout document.

**Failure scenario.** Select text in the main window → "Ask AI" button appears; `scroll`
(capture) + `resize` listeners are added on the **main** window. Pop a note out and select text
there → `handleSelectionChange(popoutDoc)` sets `activeDoc = popoutDoc`, then
`removeEventListener` is issued against the **popout** window. The main window's two listeners
are now unreachable (`repositionHandler` was nulled) and leak permanently. Every main-window
scroll still runs the stale closure, which now sees `this.buttonEl` = the popout's button and
repositions it against the popout window's `innerWidth/innerHeight` — scrolling one window
visibly jitters the "Ask AI" button in another. Toggle N times, accumulate N listener pairs.
`unload()` → `close()` → `removeButton()` (`:148-160`) detaches only against the last
`activeDoc`, so the leak **survives disabling the plugin**: each leaked closure pins a dead
`QuickQueryPopover`, its `capturedSelection`, and an `anchorRange` holding nodes of a detached
document.

The bug is a missed application of a guard that already exists in the sibling entry point:
`openForCurrentSelection` calls `this.removeButton()` at `:215` **before**
`this.activeDoc = ownerDoc` at `:216`, and `plugin/src/ui/quickQueryPopover.test.ts:165-174`
pins exactly that ordering — but only for `openForCurrentSelection`. `handleSelectionChange`
has no such test and does the reverse. The only reposition test
(`quickQueryPopover.test.ts:211-219`) is a source-substring assertion about the handler body
and says nothing about which window is unsubscribed.

**Fix direction.** Store the window used at attach time (`this.repositionWin = this.activeWin`
alongside `this.repositionHandler`, mirroring `dragState.win`) and detach against it;
additionally reorder `handleSelectionChange` to call `this.removeButton()` before reassigning
`this.activeDoc`, matching `openForCurrentSelection`. Extend the existing ordering test to
cover `handleSelectionChange`.

---

### PL-3 [P2] The startup sweep of `chat_images` is repo-scoped, not vault-scoped, so loading a second vault deletes another vault's in-flight image payload

`plugin/src/agent/llm/LLMClient.ts:2295-2299, 2321-2331`, constructor `:627-628`

```ts
  private cliCacheBase(): string {                                  // :2295
    const configured = expandPath((this.settings.incuratorRepoPath || "").trim());
    if (configured) return join(configured, ".cache", "cli");
    throw new Error("Incurator CLI cache requires incuratorRepoPath.");
  }
  ...
  private sweepStaleChatImages(): void {                            // :2325
    try {
      rmSync(join(this.cliCacheBase(), "chat_images"), { recursive: true, force: true });
    } catch { /* best-effort */ }
  }
```

The sweep runs unconditionally in the `LLMClient` constructor:

```ts
    // Best-effort startup sweep of crash-leftover chat image temp dirs (v0.28.0).
    this.sweepStaleChatImages();                                    // :628
```

`cliCacheBase()` keys **only** on `incuratorRepoPath`. Every other device-local plugin cache in
this codebase is vault-scoped — `plugin/main.ts:950-953` and `:982-988` use
`vaultMachineCacheDir(repoPath, this.vaultRoot)` for `pdf_crops` and `runtime/*.json`.
`chat_images` is the outlier, and it is removed with `recursive: true` at the **parent** level,
not per stale run-id subdir, with no liveness or age check.

**Failure scenario.** One device, two Obsidian vaults, both configured with the same Incurator
repo (the normal setup — the repo is the backend, not the vault). In vault A the user sends a
`Cmd+Shift+X` crop to claude or agy: `contentToCliText` (`:2567-2598`) writes
`<repo>/.cache/cli/chat_images/<run-id>/img_0.png`, the prompt says "Read the image file at
<path>", and `buildCliCommand` passes `--add-dir <run-id dir>` with `Read` re-enabled
(`:2213-2226`). The CLI round trip is 8–12 s (up to `--print-timeout 300s`). Inside that window
the user opens or reloads vault B; its plugin constructs an `LLMClient` and `rmSync`s the whole
`chat_images` tree, including vault A's **live** run dir. Vault A's provider then resolves the
referenced path to nothing and answers from the caption text alone — a silently degraded image
turn with no error surfaced anywhere, contradicting §2.1.3's "Read the image file at <path>"
channel contract. The same `rmSync` also races a second window of a single vault after
"Reload app without saving".

§2.1.3 says "stale `chat_images/*` dirs are swept on plugin load" — the spec is equally
under-specified about *which* dirs count as stale, so both need reconciling.

**Fix direction.** Either scope the chat-image root per vault
(`vaultMachineCacheDir(repoPath, vaultRoot)/chat_images`, consistent with `pdf_crops`), or
sweep per-subdir behind an age/liveness guard (skip run dirs younger than the CLI timeout), and
amend §2.1.3 with the staleness rule. Note this path feeds the Seatbelt/bwrap write-root
generation and `--add-dir`, so a relocation needs `sandboxWrapper` re-verification — it is not
a one-liner.

---

### PL-4 [P3] `SyncScheduler.dispose()` cancels the debounce timer but leaves the queued follow-up armed, so a sync pass can run after plugin unload

*(Pass A saw this and explicitly declined to file it, calling it "too thin". I am filing it
because `dispose()` is not just missing `pending = false` — it installs no disposed state at
all, so `fire()`, `schedule()`, and `runNow()` all remain fully live after teardown.)*

`plugin/src/agent/syncScheduler.ts:47-69`

```ts
  private async fire(): Promise<void> {
    if (this.running) {
      this.pending = true;
      return;
    }
    this.running = true;
    try {
      await this.run();
    } finally {
      this.running = false;
      if (this.pending) {
        this.pending = false;
        void this.fire();          // :59 — re-entry is not gated on disposal
      }
    }
  }

  dispose(): void {                // :64
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }
```

**Failure scenario.** Auto-sync pass P1 is running (`runAutoSyncPass` →
`incuratorClient.dbAutosync()`, a backend subprocess). The `fs.watch` callback
(`plugin/main.ts:2413-2416`) or the 60 s fallback poll (`main.ts:2378-2382`) fires and sets
`pending = true`. The user disables the plugin or closes the vault; the unload hook
(`main.ts:2384-2387`) runs `this.syncWatcher?.close(); this.syncScheduler?.dispose();` —
`timer` is null, so `dispose()` is a no-op. P1 completes and its `finally` launches P2 **after**
`onunload`, spawning another `wiki db autosync` subprocess and calling
`this.syncStatusBar?.setText(...)` on a detached status-bar element (`main.ts:2428-2439`).

A second, smaller instance of the same ordering class: `startSyncWatcher()` is called from
inside `onLayoutReady` (`main.ts:2369-2374`), while the
`this.register(() => this.syncWatcher?.close())` teardown is registered earlier at
`main.ts:2384`. If the plugin is disabled before layout-ready, teardown sees
`syncWatcher === null` and the watcher created afterwards is never closed.

`plugin/src/agent/syncScheduler.test.ts` covers debounce coalescing, the no-overlap /
one-pending invariant, and `runNow` cancelling the debounce — it has **no** `dispose()` test.

**Fix direction.** Add `private disposed = false;` set in `dispose()`; clear `pending` there;
early-return from `fire()`/`schedule()`/`runNow()` when disposed. Move the watcher teardown
registration to where the watcher is actually created (or have teardown re-read
`this.syncWatcher` after layout-ready).

---

## 2. Pros & Cons

### What I judged CLEAN (checked against spec, found conforming)

- **CLI sandbox argument construction (§13.6).** `buildCliCommand` (`LLMClient.ts:2150-2288`)
  matches the spec verbatim: agy keeps `--sandbox` with no
  `--dangerously-skip-permissions`/trust-workspace and an empty `--add-dir` when ephemeral
  (`:2191-2205`); claude uses `--tools ""` for the popover and
  `--disallowedTools Bash Read Write Edit WebFetch` for text-only sidechat (`:2213-2217`); the
  image-turn exception drops only `Read` and confines `--add-dir` to `imageRunDir` instead of
  the broad roots (`:2223-2226`); codex uses `read-only` / `workspace-write` (`:2271`); empty
  roots are dropped before use (`:2356`). No drift found.
- **`ToolPolicy` exhaustiveness (§13.5 v0.41.0 amendment).** `shouldInjectMcpTools`,
  `isEphemeralToolPolicy`, and `shouldInjectLocalTools` (`messageUtils.ts:15-77`) all carry
  `const exhaustive: never` defaults, and `"local-only"` is ephemeral for sandbox purposes, so
  the local PDF reader does not relax the v0.23.0 posture.
- **Local PDF reader fail-closed gating (§13.7).** `canFetch`/`canSearch`
  (`localPdfTools.ts:99-112`) require active PDF + positive page count + stable `documentId`,
  treat `outlineState: "unknown"` as "present" so `search_pdf_anchor` is withheld, and
  `runLocalPdfTool` (`LLMClient.ts:643-660`) re-checks
  `runner.describeContext().documentId !== captured.documentId` at execution time and refuses
  rather than reading a swapped document. This is the "state carried across document identity
  changes" hazard for the *tool* path, and it is handled. (Pass A's F1 shows the *popover
  cross-reference* path is a different story.)
- **`_chatImagePaths` / `_chatImageRunDir` intra-process race.** I specifically hunted for a
  text-only turn inheriting `Read` + `--add-dir` from a concurrent image turn. It cannot
  happen: `messagesToCliPrompt` resets both fields (`:2548-2552`) and `buildCliCommand` reads
  them with **no intervening `await`** in either `streamChatViaCli` (`:1348-1371`) or
  `completeViaCli` (`:1945-1962`), so the window is fully synchronous, and each call captures
  `imageRunDir` into a local before any await. Independently reached the same conclusion as
  Pass A.
- **Popover trace isolation (§13.2).** `turns` is a per-instance field and each selection
  spawns a fresh `QuickQueryPopover` child (`quickQueryPopover.ts:299-310`), so coexisting
  popovers do not share a trace. `removePopover` aborts only its own controller and never calls
  `llmClient.abort()` (`:632-636`) — exactly what §1.4 demands. The child's `activeDoc` is
  snapshotted at construction (`:302`) and never mutated, so PL-2 is confined to the root
  manager instance's trigger-button listeners; the popover's own capturing `keydown` listener
  is detached correctly.
- **Antigravity `--effort` (§13.6).** I suspected drift because `buildCliCommand:2186` omits
  `--effort` purely on `!settings.agentEffort` with no catalogue lookup, but
  `normalizePluginModelEffort` (`types.ts:239-260`) runs on both load paths (`main.ts:1707`,
  `:1719`, `:1746`) and on every model change (`settings.ts:81,169,200`;
  `ChatSidebarView.ts:4871`), so a model *with* an effort dimension always ends up with a
  non-empty `agentEffort`. Not a defect. (Same conclusion as Pass A, reached independently.)

### What I could NOT verify

- **Runtime reproduction.** All four findings are static-analysis results (the only thing I
  executed was a 10-line scratch Node script confirming `try { return promise } finally {}`
  ordering — no repo code, no `wiki` command, no testbed, no Obsidian). PL-2 and PL-3 in
  particular deserve a manual repro before scheduling.
- **PL-1 scenario B end-to-end.** I did not instrument the live foreground pointer to confirm
  "Stop cancels the wrong request". The claim follows from `beginRequest`/`endRequest` plus the
  verified `try/finally` semantics, but `ChatSidebarView`'s own `isGenerating` guard
  (`:988-990`, `:1077`, `:1195-1196`) may mask some interleavings.
- **§2.2 `SessionData`.** I did not audit `sessionStore.ts`/`sessionData.ts` against the
  L823-849 fail-closed contract; the budget went to the cancellation and listener paths. Pass A
  reports it clean with test backing, which I did not independently re-verify.
- **Vision / transcribe / zotero abort paths.** `transcribePdfCrop` (`main.ts:940-972`) accepts
  no `AbortSignal` at all and cannot be cancelled, but it is a short backend call with a correct
  `finally` temp-dir cleanup, so I did not raise it. Whether §1.4's "every public provider
  request" is meant to cover this plugin→backend hop is a spec-reading question the given ranges
  do not settle.
- **`ChatSidebarView.ts` (~4.9k lines)** was grepped for abort/stream/`isGenerating` only, never
  read end-to-end.

### Cost / risk of the proposed fixes

- **PL-1** is a two-token change (`return await`) plus a test; near-zero regression risk and it
  closes a real cancellation hole. Highest value per line in this pass.
- **PL-2** is confined to `QuickQueryPopover` (one new field + one reorder) with an existing
  sibling pattern to copy; low risk.
- **PL-3** is the only one carrying a design decision (vault-scope the dir vs. age-guard the
  sweep) and it touches sandbox write-root generation — budget review time accordingly, and pair
  it with a §2.1.3 spec amendment.
- **PL-4** is hygiene; batch it with any other unload-ordering cleanup rather than shipping it
  alone.
- PL-1, PL-3 and Pass A's F2/F3/F4 all live in the same ~400-line CLI region of
  `LLMClient.ts` — group them into one change so the block is reviewed once.

---
---

# PASS A — Earlier inspection (retained verbatim)

# plugin_lifecycle Proposal: Four Lifecycle/Boundary Defects in the Obsidian Plugin
Date: 2026-08-04 | Agent Persona: Plugin Lifecycle Auditor

Scope audited: `plugin/src/agent/llm/LLMClient.ts`, `plugin/src/agent/llm/{localPdfTools,messageUtils}.ts`,
`plugin/src/agent/{sandboxWrapper,syncScheduler,mcpClient}.ts`, `plugin/src/ui/quickQueryPopover.ts`,
`plugin/src/ui/chat/ChatSidebarView.ts` (fetch path only), `plugin/src/utils/{sessionStore,durableJsonStore}.ts`,
`plugin/src/context/{promptRegistry,pdfReferenceContext}.ts`, `plugin/main.ts` (lifecycle regions).
Specs read: PLUGIN_SCHEMA §1.4 (256–282), §2.1.3/§2.2 (771–851), §13.2–§13.7 (2034–2273).
Known-and-excluded: CAND-01..06 (in particular CAND-06, the sidechat `workspacePath` binding).

## 1. Core Logic & Implementation

### F1 [P1] Quick Query cross-reference fetch is not pinned to a document identity — a tab switch mid-resolution splices pages from the *wrong* PDF into the answer

`main.ts` already owns the guard, and its own comment names the exact hazard:

```ts
// plugin/main.ts:1772-1786
  async fetchActivePdfPage(
    pageNum: number,
    expectedDocumentId?: string
  ): Promise<string | undefined> {
    const pdf = this.activeContext.pdfPage;
    // Pin the viewer and its identity BEFORE any await. The viewer fallback
    // below must never re-resolve to whatever document happens to be active
    // after the backend round-trip: a tab switch during that await would
    // otherwise read a page out of the wrong PDF, using bounds that were
    // validated against the original one (PLUGIN_SCHEMA §13.7).
    const pinnedView = this.app.workspace.getActiveViewOfType(ExternalPdfView);
    const pinnedDocumentId = pinnedView?.getDocumentId();
    if (expectedDocumentId !== undefined && pinnedDocumentId !== expectedDocumentId) {
      return undefined;
    }
```

The guard is **opt-in**: it is a no-op when `expectedDocumentId` is `undefined`. The local
PDF tool runner opts in —

```ts
// plugin/main.ts:1859-1860
      fetchPage: (pageNum: number) =>
        this.fetchActivePdfPage(pageNum, this.getActivePdfDocumentId()),
```

— but the Quick Query popover, the surface §13.2 is written about, does **not**:

```ts
// plugin/src/ui/quickQueryPopover.ts:484-492
        resolvedReferencesBlock = await resolveSelectionReferencesBlockAsync(
          this.capturedSelection,
          {
            ...activeContext.pdfPage,
            searchIndex: this.plugin.getActivePdfDocumentIndex(),
            searchDocumentId: this.plugin.getActivePdfDocumentId(),
          },
          (pageNum) => this.plugin.fetchActivePdfPage(pageNum)   // ← no identity
        );
```

`resolveSelectionReferencesBlockAsync` is a *multi-round* resolver — it fetches wanted pages,
re-scans, then walks outline candidates in batches (`pdfReferenceContext.ts:285-401`,
`fetchPages()` called at 355, 366, 401), i.e. many sequential awaits. Each of those awaits
re-enters `fetchActivePdfPage`, which re-reads `this.activeContext.pdfPage` (line 1776) — a
field that Obsidian's workspace events repoint the moment the user switches tabs.

Contrast the sidechat, which does not have this defect: it builds a fetcher closed over a
*captured* identity (`ChatSidebarView.ts:1782-1794` passes `sourcePath`, `sourceStatus?.sourceId`,
`pdf.fileHash`, `pdf.zoteroAttachmentKey` to `client.getPdfContext`), so its fetches stay bound
to one document. §13.2 requires "The fetch path must match sidechat" — it does not.

**Failure scenario (concrete).** User selects, in paper A p.12, "…as shown in Theorem 4.2
(p. 31)"; presses the Quick Query hotkey; asks "what does that theorem actually assume?".
The resolver starts fetching. A CLI provider round trip is 8–12 s and the resolver itself
issues several backend calls, so there is a real window. During it the user clicks the tab
holding paper B. `activeContext.pdfPage` now points at B. The next
`fetchActivePdfPage(31)` returns **page 31 of paper B**, which is inserted into
`<resolved_cross_references>` — the block §13.2 declares "must remain higher priority than
generic current-page background". The model then answers about paper A's Theorem 4.2 using
paper B's text, with no visible signal that the two came from different documents. The
recency anchor (`buildRecencyAnchor`, §13.5) actively *reinforces* the wrong text by telling
the model to defer to `<resolved_cross_references>`.

**Fix direction.** Capture the popover's document identity once (at `openPopover`/`runQuery`
entry, alongside `capturedSelection`) and pass it as `expectedDocumentId` on every
`fetchActivePdfPage` call, exactly as the tool runner does; abandon the resolved block (fall
back to sync inline resolution) when the guard returns `undefined`. Add a popover test that
flips `getActivePdfDocumentId()` between fetches and asserts no foreign page text reaches the
block. Consider making `expectedDocumentId` a required parameter so a future call site cannot
silently opt out of the guard again.

---

### F2 [P2] `syncAgyMcpConfig` silently overwrites a malformed `~/.gemini/settings.json` and writes it non-atomically, while its sibling in the same call refuses to

```ts
// plugin/src/agent/llm/LLMClient.ts:2518-2546
  private syncAgyMcpConfig(): void {
    const geminiDir = join(homedir(), ".gemini");
    ...
    const settingsPath = join(geminiDir, "settings.json");
    let existing: Record<string, unknown> = {};
    try {
      existing = JSON.parse(readFileSync(settingsPath, "utf-8"));
    } catch { /* file missing or malformed — start fresh */ }

    const merged = { ...existing, admin: {...}, mcpServers };

    writeFileSync(settingsPath, `${JSON.stringify(merged, null, 2)}\n`);
    syncAgyHeadlessReadPermission(geminiDir);
  }
```

Two problems, both visible against the function it calls on the very next line, which handles
the *sibling* file (`~/.gemini/antigravity-cli/settings.json`) exactly as §13.6 demands:

```ts
// plugin/src/agent/llm/LLMClient.ts:73-84 (syncAgyHeadlessReadPermission)
    try { parsed = JSON.parse(readFileSync(settingsPath, "utf-8")); }
    catch (error) {
      throw new Error(
        `Antigravity CLI settings are malformed; refusing to overwrite ${settingsPath}: ...`);
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error(`Antigravity CLI settings must be a JSON object; refusing to overwrite ...`);
    }
// ...and it commits via temp-file + rename (lines 118-127)
```

1. **Silent destruction of user config.** `catch { start fresh }` means any parse failure —
   a hand-edited file with a trailing comma, a JSONC-style `//` comment (Gemini-family CLIs
   tolerate those), a partially-synced file — causes the plugin to *replace* the user's whole
   `~/.gemini/settings.json` with `{admin, mcpServers}`. Every unrelated key (theme, auth
   selection, telemetry, context file names) is gone, with no Notice, no `console.warn`, and
   nothing in the log. This is the §32 observable-degradation anti-pattern applied to a file
   the plugin does not own, and it directly contradicts the posture §13.6 states for the
   sibling file ("MUST refuse to overwrite malformed JSON").
2. **Non-atomic commit.** `writeFileSync` straight onto the live path. A crash, a full disk,
   or an Obsidian quit mid-write leaves a truncated `settings.json`; on the next launch the
   `catch` above swallows the truncation and finishes the job by overwriting it. Note the
   plugin's own durable-store contract (§2.2, implemented in
   `utils/durableJsonStore.ts::atomicWriteVaultText`) is temp-write + rename, and
   `syncAgyHeadlessReadPermission` uses temp + `renameSync` for the file next door.

**Failure scenario (concrete).** A user adds `"theme": "GitHub"` plus a `// my servers`
comment to `~/.gemini/settings.json` for their standalone Gemini CLI usage. They then send one
antigravity-backed chat message from Obsidian. `buildCliCommand` → `syncAgyMcpConfig` (line
2184) parses, fails, starts fresh, and writes a two-key file. Their Gemini CLI config is
destroyed and nothing tells them. No test pins this: the only test that mentions
`syncAgyMcpConfig` (`llmCliLifecycle.test.ts:57`) stubs it out.

**Fix direction.** Reuse the validated pattern: parse strictly, throw a descriptive error (or
at minimum `logger.warn` + skip the write) on malformed/non-object content, and commit via
temp file + rename. Add a spec sentence to §13.6 covering `~/.gemini/settings.json` (the
section currently only governs `~/.gemini/antigravity-cli/settings.json`) so the two files are
held to one rule.

---

### F3 [P3] Non-streaming CLI path leaks the per-run chat-image dir when pre-spawn setup throws — §2.1.3 "Cleanup robustness" is implemented on the streaming path only

§2.1.3: "Cleanup … MUST also run if pre-spawn setup (`getCliCwd`/`buildCliCommand`) throws
synchronously before any child spawns, since no `close`/`error` event fires in that case."

Streaming path — correct, and explicitly tested:

```ts
// plugin/src/agent/llm/LLMClient.ts:1348-1378 (streamChatViaCli)
      const prompt = this.messagesToCliPrompt(messages);
      const imageRunDir = this._chatImageRunDir;
      try {
        cwd = this.getCliCwd();
        ...
        ({ command, args, env, stdin } = this.buildCliCommand(...));
      } catch (err) {
        // Synchronous setup failed before any child spawn, so neither "close"
        // nor "error" will fire — clean the image dir here so it never leaks.
        this.cleanupChatImageDir(imageRunDir);
        reject(...);
```

Non-streaming path — the identical prologue sits **outside** the `try`, so its `finally` cannot
see a pre-spawn throw:

```ts
// plugin/src/agent/llm/LLMClient.ts:1945-1964, 2008-2013 (completeViaCli)
    const prompt = this.messagesToCliPrompt(messages);   // ← writes the PNGs
    const imageRunDir = this._chatImageRunDir;
    const cwd = this.getCliCwd();                        // ← can throw
    ...
    const { command, args, env } = this.buildCliCommand(...);   // ← can throw
    try {
      const { stdout, stderr } = await execFileAsync(...);
      ...
    } finally {
      if (outputFile && existsSync(outputFile)) unlinkSync(outputFile);
      this.cleanupChatImageDir(imageRunDir);             // ← never reached on a pre-spawn throw
    }
```

`buildCliCommand` really does throw before spawn on live paths: `syncAgyMcpConfig` →
`syncAgyHeadlessReadPermission` throws on malformed antigravity CLI settings (lines 76, 81,
93, 103), `cliCacheBase()` throws without `incuratorRepoPath` (line 2298), and
`wrapWithOsSandbox` throws when agy cannot be OS-sandboxed (line 2443). The existing test only
pins the streaming half — `llmClient.test.ts:1002-1007` asserts the literal
`"this.cleanupChatImageDir(imageRunDir);\n        reject("`, i.e. the streaming
indentation — so the non-streaming gap is invisible to CI.

**Failure scenario.** An image-bearing turn dispatched with `streamingEnabled: false` on a
Linux box without `bwrap` and provider `antigravity`: `contentToCliText` writes
`<repo>/.cache/cli/chat_images/<run-id>/img_0.png`, `wrapWithOsSandbox` then throws the
"cannot be safely sandboxed" refusal, and the decoded user crop survives on disk until the next
plugin load runs `sweepStaleChatImages()`. Spec: "No temp image survives a completed send."
Severity is P3 rather than P2 only because today's `complete()` call sites
(`quickQueryPopover.ts:535`, `LLMClient.editText:2653`) do not carry image parts — the guard is
latent, not currently firing. It is one image-capable `complete()` caller away from being live.

**Fix direction.** Move `getCliCwd()`/`buildCliCommand()` inside the `try` (or wrap them in
their own try/catch that calls `cleanupChatImageDir(imageRunDir)` and rethrows), and generalize
the test to assert cleanup-on-pre-spawn-throw for both CLI entry points rather than matching a
single indented source literal.

---

### F4 [P3] The documented "macOS without `sandbox-exec`" degradation branch is unreachable — the path is hardcoded, never probed

§13.6: "**Unavailable-sandbox degradation** — when no OS sandbox is available (Linux without
`bwrap`, macOS without `sandbox-exec`, Windows/other): **agy is refused** … but **Claude/Codex
proceed** … the plugin emits a `console.warn` when it drops the OS layer."

`buildSandboxPlan` is a pure function that decides on an *injected* path
(`sandboxWrapper.ts:151-153`: `if (!args.sandboxExecPath) return { unavailable: true, reason:
"sandbox-exec unavailable on macOS." }`). The caller never probes:

```ts
// plugin/src/agent/llm/LLMClient.ts:2427-2434 (wrapWithOsSandbox)
    const plan = buildSandboxPlan({
      platform: process.platform,
      allowedRoots: roots,
      home: realOr(homedir()),
      tmpdir: realOr(this.cliTempDir()),
      sandboxExecPath: process.platform === "darwin" ? "/usr/bin/sandbox-exec" : "",
      bwrapPath: process.platform === "linux" ? this.resolveBwrap() : "",
      provider,
    });
```

The Linux arm resolves `bwrap` for real (`resolveBwrap()`, lines 2393-2405, a PATH scan with
`existsSync`); the macOS arm asserts a constant. So on a macOS host where `/usr/bin/sandbox-exec`
is absent or non-executable (it has been deprecated by Apple for years; hardened/managed images
and future releases can remove it), `plan.unavailable` is `false`, the refusal at line 2442 and
the `logger.warn` at 2449 never fire, and the plugin instead spawns
`/usr/bin/sandbox-exec -p <profile> agy …` which fails with `ENOENT`. The user sees the generic
classifier message `"antigravity CLI is not installed or not found on PATH.\n\nInstall the CLI
first, then retry."` (`completeViaCli:2000-2003`) — a diagnosis that is simply false and sends
them to reinstall the wrong binary. The sandbox tests only exercise the pure function with an
injected path (`sandboxWrapper.test.ts:72,104`), so nothing covers the caller.

**Fix direction.** Mirror `resolveBwrap()`: probe `/usr/bin/sandbox-exec` with `existsSync` (or
an `accessSync(..., X_OK)`), memoized like `_bwrapPath`, and pass `""` when absent so the
documented refusal/degradation branch actually runs. Cheap, and it converts a misleading
"CLI not installed" into the spec's real message.

---

## 2. Pros & Cons

### What I judged clean (checked, no finding)

- **Request-lifetime / foreground-pointer contract (§1.4).** `beginRequest`/`endRequest`
  (`LLMClient.ts:704-732`) satisfy the spec precisely: a caller-signal request is *not* added to
  `foregroundRequestControllers` (so it cannot replace the sidebar's foreground pointer), the
  owner-signal listener is removed on settle via the `requestAbortCleanup` WeakMap, and
  `endRequest` re-promotes the newest remaining controller when the foreground one finishes.
  `streamChat`/`complete` both re-check `controller.signal.aborted` before *and* after
  `beforeProviderLaunch()` (lines 870-878, 1235-1249), which is exactly the "cancelled during
  asynchronous context preparation must settle before any transport launches" clause.
- **Per-call image state is not actually racy.** `_chatImageRunDir`/`_chatImagePaths` are
  instance fields, which looked like a cross-request hazard, but both CLI entry points run
  `messagesToCliPrompt` → `buildCliCommand` in one synchronous stretch and capture
  `imageRunDir` into a local before any `await` (lines 1348-1371, 1945-1962). Two overlapping
  sends cannot swap each other's dirs, and a text-only turn cannot inherit another turn's
  `--add-dir`. I could not construct an interleaving; I dropped this claim.
- **§2.2 durable session store.** `sessionStore.ts` + `durableJsonStore.ts` conform: four-state
  classification, per-(adapter,path) promise queue serializing all read/merge/writes, merge
  inside `adapter.process`, `SessionStoreBlockedError` on corrupt/unreadable, temp+rename with
  temp cleanup only for first creation, and a generic `process` rejection propagating without
  being reclassified as corrupt. Well covered by `sessionStore.test.ts`.
- **§13.5/§13.7 tool gating.** `shouldInjectMcpTools`, `isEphemeralToolPolicy`, and
  `shouldInjectLocalTools` are all exhaustive over `ToolPolicy` with `never`-typed defaults
  (`messageUtils.ts:15-77`); `canFetch`/`canSearch` fail closed on missing page count or
  document identity and treat `outlineState: "unknown"` as "has an outline"
  (`localPdfTools.ts:99-112`); `runLocalPdfTool` refuses when
  `runner.describeContext().documentId !== captured.documentId` (`LLMClient.ts:653-660`).
- **Popover selection identity.** Each opened popover is a fresh instance whose
  `capturedSelection`/`anchorRange` are snapshotted at open time (`quickQueryPopover.ts:299-310`),
  so a later mouseup on the manager instance cannot retarget an open popover. Timers and the
  capturing `keydown` listener are torn down in `removePopover` (624-649), and
  `ChatSidebarView.onClose` clears both `statusPollInterval` and `thinkingTimer` (419-427).
- **MCP child-process writes** are all guarded by `stdin?.writable` checks
  (`mcpClient.ts:246,282`), per §1.4's "optional child-process streams must be checked".
- **Effort-settings migration.** The edge I suspected (a stored empty `agentEffort` on a model
  that declares effort levels) is closed: `migrateUnavailableModelDefaults` and
  `refreshAvailableModels` both call `normalizePluginModelEffort` on load
  (`main.ts:1707,1719,1746`), which fills the catalogue default.

### What I could NOT verify (limits of this pass)

- **No runtime execution.** Every finding is static: read-only audit, no `wiki` command, no
  testbed, no Obsidian instance. F1's window width (how often a user can switch tabs inside the
  resolver's await chain) is argued from the recorded 8–12 s CLI round-trip and the resolver's
  multi-round structure, not measured.
- **`ChatSidebarView.ts` was sampled, not read end-to-end** (~4.9k lines; token budget). I read
  the fetch path (1760-1800), the lifecycle/timer regions (415-427, 4185-4227), and grepped its
  listener inventory. A view-lifetime defect outside those regions would have been missed.
- **`ExternalPdfView`/PDF.js render-token teardown was not re-audited** — the arena briefing
  lists it as already fixed in v0.42.0 (§1.4.1/§1.4.2), so I deliberately spent the budget
  elsewhere. F1's `getDocumentId()` semantics are taken from its call sites, not from the view.
- **Windows** paths are out of scope for the sandbox spec and I did not evaluate them.
- **One observation I am NOT filing as a finding** (too thin, and arguably by design):
  `SyncScheduler.dispose()` (`syncScheduler.ts:64-69`) clears the debounce timer but leaves
  `pending === true`, so a follow-up `fire()` queued by a mid-run trigger still executes after
  the plugin's `register()` teardown ran (`main.ts:2384-2387`) — one extra `wiki db autosync`
  subprocess and possibly a `Notice` after unload. Harmless in practice (the backend call is
  idempotent), but a one-line `this.pending = false` in `dispose()` would close it if the batch
  is touching that file anyway.

### Cost/benefit of the proposed fixes

F1 is the only one with user-visible knowledge-correctness impact and should be batched first;
it is a small, local change (thread one string through two call sites) with a cheap regression
test. F2 is small and self-contained, but it also needs a spec sentence — code-only would leave
the same doc gap that allowed the divergence. F3 and F4 are each a few lines and are best done
together with F2 since all three live in `LLMClient.ts`'s CLI region; grouping them avoids three
separate reviews of the same 400-line block. None of the four requires a schema change, a
migration, or a version-line spec-title bump.
