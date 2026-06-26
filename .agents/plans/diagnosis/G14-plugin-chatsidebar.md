# Diagnosis: G14-plugin-chatsidebar
Coverage: `plugin/src/ui/chatSidebar.ts` read in full (4834 LOC); narrow cross-checks in `docs/guides/PLUGIN_GUIDE.md`, `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`, `docs/guides/SYNC_IGNORE_GUIDE.md`, and `plugin/src/ui/chatSidebarSource.test.ts`.

## Findings

### [G14-1] (a,c,h) S1 - Context-build failures can leave a stuck streaming assistant turn
- Loc: `plugin/src/ui/chatSidebar.ts:999`, `plugin/src/ui/chatSidebar.ts:1016`, `plugin/src/ui/chatSidebar.ts:1046`, `plugin/src/ui/chatSidebar.ts:1047`, `plugin/src/ui/chatSidebar.ts:1054`
- Evidence: `handleSend()` persists the user message and a blank streaming assistant message before context assembly. It then calls `this.setPrepareStatus("Preparing context...")` and awaits `this.buildLLMMessages(capturedActiveCtx)` before entering the `try` block that catches stream failures. `buildLLMMessages()` can call backend/PDF/context code, so a thrown context error bypasses the catch/finally path, leaving `assistantMsg.isStreaming = true` in memory/session and producing an unhandled promise rejection from UI event handlers.
- Fix sketch: Move context assembly inside the same guarded turn lifecycle as streaming, or add a dedicated `try/catch/finally` around `buildLLMMessages()`. On failure, mark the assistant message non-streaming, render a visible context-preparation error, clear `prepareStatusText`, reset `isGenerating`/button state, and persist the session. Add a Vitest behavioral test with a mocked `buildIncuratorProviderContext()` or `IncuratorClient` rejection.
- Blast radius: Chat send path, PDF/context provider assembly, session persistence, streaming button state.
- Suggested PR: `fix/plugin-chat-context-build-error-state`

### [G14-2] (a,h,i) S1 - Manual continuation on an old assistant message renders into the last assistant bubble
- Loc: `plugin/src/ui/chatSidebar.ts:1153`, `plugin/src/ui/chatSidebar.ts:1161`, `plugin/src/ui/chatSidebar.ts:1180`, `plugin/src/ui/chatSidebar.ts:1209`, `plugin/src/ui/chatSidebar.ts:1219`, `plugin/src/ui/chatSidebar.ts:4021`
- Evidence: `continueTruncatedMessage()` explicitly supports continuing an old truncated message by temporarily slicing `this.messages` around that message. But every streamed continuation chunk calls `renderAssistantMessage(assistantMsg)`, and `renderAssistantMessage()` updates `querySelectorAll(".ai-agent-chat-msg-assistant")` then takes `allMsgEls[allMsgEls.length - 1]`. If the continued message is not the last assistant message, the old message object receives new content while the visible DOM updates the newest assistant bubble.
- Fix sketch: Give rendered message nodes a stable `data-message-id` in `renderMessage()` and have `renderAssistantMessage(msg)` locate that node by id. If missing, fall back to `renderMessages(false)`. Add a regression test for continuing a non-terminal truncated assistant message.
- Blast radius: Streaming rendering, manual continuation, historical message actions, auto-open diff after continuation.
- Suggested PR: `fix/plugin-chat-targeted-message-render`

### [G14-3] (a,g,i) S2 - Markdown post-processing races the asynchronous renderer, so answer links can fail to bind
- Loc: `plugin/src/ui/chatSidebar.ts:2689`, `plugin/src/ui/chatSidebar.ts:2690`, `plugin/src/ui/chatSidebar.ts:2732`, `plugin/src/ui/chatSidebar.ts:2760`, `plugin/src/ui/chatSidebar.ts:2804`, `plugin/src/ui/chatSidebar.ts:2805`, `plugin/src/ui/chatSidebar.ts:3057`
- Evidence: `renderAssistantMarkdown()` fires `MarkdownRenderer.render(...).then(stampMathSourceData)` but returns `void`. Later, `renderAssistantMessageContent()` schedules `attachAssistantAnswerLinkNavigation(contentEl)` with `setTimeout(..., 0)` and immediately attaches the LaTeX copy handler. If MarkdownRenderer takes longer than one tick, generated links do not exist when navigation binding runs. Re-renders also keep old renderer promises working on detached wrappers, wasting CPU.
- Fix sketch: Make `renderAssistantMarkdown()` return the render promise and centralize post-render hooks. Bind answer-link navigation and LaTeX copy after all markdown sections for that message have rendered, and ignore stale completions with a render generation token or `wrapper.isConnected` check.
- Blast radius: Assistant answer rendering, PDF/vault answer-link navigation, LaTeX copy behavior, message re-render performance.
- Suggested PR: `fix/plugin-chat-markdown-render-lifecycle`

### [G14-4] (a,h) S2 - Sources & Trace mutations rely on a mutable singleton trace without pack guards
- Loc: `plugin/src/ui/chatSidebar.ts:152`, `plugin/src/ui/chatSidebar.ts:1816`, `plugin/src/ui/chatSidebar.ts:2947`, `plugin/src/ui/chatSidebar.ts:2975`, `plugin/src/ui/chatSidebar.ts:2987`, `plugin/src/ui/chatSidebar.ts:3007`, `plugin/src/ui/chatSidebar.ts:3027`
- Evidence: Expand/verify/refetch handlers mutate `this.lastQueryTrace.context_pack` through `mergeContextExpansion()`, `mergeContextVerification()`, `markContextSnapshotConflict()`, and `replaceContextPack()`. The event detail carries `pack_id`/`snapshot_id`, but the merge methods do not verify that the currently stored singleton still matches those ids. A new send resets or replaces `lastQueryTrace` while an async action is in flight, so a late response can no-op or patch the wrong current trace.
- Fix sketch: Thread the expected `pack_id` and `snapshot_id` into merge/replace methods and apply only if `this.lastQueryTrace?.pack_id` and snapshot still match. Disable or cancel trace actions while a new assistant turn is generating. Prefer per-message trace state over a view-level singleton for interactive panels.
- Blast radius: Query trace panel, context expansion/verification/refetch, feedback UX, promotion trace correctness.
- Suggested PR: `fix/plugin-chat-trace-pack-guards`

### [G14-5] (a,f) S2 - Model changes do not persist the spec-required reasoning-effort reset
- Loc: `plugin/src/ui/chatSidebar.ts:4662`, `plugin/src/ui/chatSidebar.ts:4676`, `plugin/src/ui/chatSidebar.ts:4686`, `plugin/src/ui/chatSidebar.ts:4743`, `plugin/src/ui/chatSidebar.ts:4763`, `plugin/src/ui/chatSidebar.ts:4768`, `plugin/src/ui/chatSidebar.ts:4771`; `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:581`
- Evidence: The spec says plugin model controls must offer only declared efforts and changing the model must reset effort to that model's `default_effort`. `onModelSelectChange()` changes provider/model and saves settings before `syncReasoningControl()`. `syncReasoningControl()` computes a display fallback when the stored effort is invalid, but it only assigns `this.reasoningSelectEl.value`; it does not write the normalized effort back to provider-specific settings.
- Fix sketch: During model/provider changes, resolve the selected model option, compute the valid effort/default, update the corresponding setting (`codexReasoningEffort`, `claudeEffort`, or `agentEffort`), then save once. Add tests for switching from a high-effort model to a model with a narrower effort set.
- Blast radius: Provider/model switching, LLM client request options, settings persistence, cross-model consistency.
- Suggested PR: `fix/plugin-model-effort-normalization`

### [G14-6] (c,f,g) S2 - Status bar performs synchronous filesystem polling on the UI thread and hides stale/error states
- Loc: `plugin/src/ui/chatSidebar.ts:240`, `plugin/src/ui/chatSidebar.ts:413`, `plugin/src/ui/chatSidebar.ts:416`, `plugin/src/ui/chatSidebar.ts:418`, `plugin/src/ui/chatSidebar.ts:419`, `plugin/src/ui/chatSidebar.ts:423`, `plugin/src/ui/chatSidebar.ts:424`, `plugin/src/ui/chatSidebar.ts:436`; `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:646`, `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:649`, `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:662`
- Evidence: `onOpen()` starts a 2s interval. `updateStatusBar()` uses `existsSync()` and `readFileSync()` against `.curator/runtime/jobs.json` on every tick, declares but never reads `statusPath`, and swallows all parse/read errors. The spec says missing/stale snapshots should be treated as unknown/waiting and the plugin may read runtime snapshots after backend refresh. Current behavior silently renders nothing for missing/stale/corrupt snapshots and can jank the UI on large or contended files.
- Fix sketch: Extract a status snapshot reader shared with the dashboard, use async adapter/backend-refresh flow, show a compact unknown/stale/error state, and log parse failures once. Remove the unused `statusPath` or actually incorporate status freshness/version information.
- Blast radius: Chat header status bar, runtime snapshot semantics, dashboard/status consistency, perceived responsiveness.
- Suggested PR: `fix/plugin-chat-status-snapshot-reader`

### [G14-7] (e) S2 - `ChatSidebarView` is a 4834-line god-class with too many ownership domains
- Loc: `plugin/src/ui/chatSidebar.ts:118`, `plugin/src/ui/chatSidebar.ts:180`, `plugin/src/ui/chatSidebar.ts:610`, `plugin/src/ui/chatSidebar.ts:971`, `plugin/src/ui/chatSidebar.ts:1284`, `plugin/src/ui/chatSidebar.ts:1638`, `plugin/src/ui/chatSidebar.ts:2571`, `plugin/src/ui/chatSidebar.ts:3121`, `plugin/src/ui/chatSidebar.ts:4375`, `plugin/src/ui/chatSidebar.ts:4662`
- Evidence: One `ItemView` owns DOM construction, drag/drop, native file attachment, PDF splitting, prompt/context construction, backend source status, query trace mutation, Markdown rendering, diff review, session storage, model controls, and utility encoding. The class also imports filesystem APIs, backend client APIs, prompt policy, diff logic, PDF capture, provider formatting, session summarization, and text utilities. This makes small fixes high-risk because state like `messages`, `lastQueryTrace`, `pendingContextRefs`, and render lifecycle are shared across unrelated workflows.
- Fix sketch: Split along existing seams without changing behavior: `ChatSessionController`, `ChatMessageRenderer`, `ContextChipController`, `PdfDropController`, `ProviderContextBuilder`, `SourceStatusController`, and `EditReviewController`. Keep `ChatSidebarView` as composition/root wiring. Start with pure/helper extraction where tests already exist.
- Blast radius: Entire chat sidebar. Refactor needs phased PRs with behavior-preserving tests before moving mutating flows.
- Suggested PR: `refactor/plugin-chat-sidebar-controllers`

### [G14-8] (b,e) S3 - Source-mode Markdown opening and drop handling are duplicated across several paths
- Loc: `plugin/src/ui/chatSidebar.ts:3417`, `plugin/src/ui/chatSidebar.ts:3428`, `plugin/src/ui/chatSidebar.ts:3659`, `plugin/src/ui/chatSidebar.ts:3674`, `plugin/src/ui/chatSidebar.ts:3853`, `plugin/src/ui/chatSidebar.ts:3864`, `plugin/src/ui/chatSidebar.ts:610`, `plugin/src/ui/chatSidebar.ts:648`, `plugin/src/ui/chatSidebar.ts:839`, `plugin/src/ui/chatSidebar.ts:4295`
- Evidence: Opening a Markdown file in source mode with a two-frame mount delay appears in `applyInlineEdit()`, `reviewAssistantEdit()`, and `reviewFileEditProposalsImpl()`. Drag/drop parsing is spread across sidebar drop, global PDF split drop, generic data-transfer drop, and chip-row drop. Prior bug comments show many fixes were made in one path at a time, which is a redundancy smell for regression risk.
- Fix sketch: Extract `openMarkdownSourceLeaf(file, preferredPath)` and `parseDroppedContext(dataTransfer, mode)` helpers with unit tests. Route legacy single-range edit and multi-edit review through the same source-mode opener.
- Blast radius: Inline edit review, DiffViewer mount timing, PDF/file drag/drop, context chips.
- Suggested PR: `refactor/plugin-chat-edit-drop-helpers`

### [G14-9] (d,b) S3 - Dead or legacy code remains in the god-file
- Loc: `plugin/src/ui/chatSidebar.ts:419`, `plugin/src/ui/chatSidebar.ts:3451`, `plugin/src/ui/chatSidebar.ts:3476`, `plugin/src/ui/chatSidebar.ts:3659`, `plugin/src/ui/chatSidebar.ts:4600`
- Evidence: `statusPath` is assigned and unused. `createNewFile()` and `warnIfLargeReplacement()` have no references in `plugin/src/ui/chatSidebar.ts` or other plugin TypeScript files. `deleteCurrentChatSession()` is also unreferenced while `deleteChatSessionById()` implements the visible delete flow. The "Legacy single-range edit path" still carries separate review/apply behavior beside the newer SEARCH/REPLACE flow.
- Fix sketch: Confirm no external reflective calls, then remove unreferenced helpers or move legacy compatibility behind explicit tests. If single-range edit remains supported, document it as a compatibility contract and route it through the shared diff-review path.
- Blast radius: Bundle size, maintainability, edit review compatibility, session drawer delete behavior.
- Suggested PR: `chore/plugin-chat-dead-code-prune`

### [G14-10] (c,h) S2 - Fire-and-forget async event handlers can create unhandled rejections and stale UI state
- Loc: `plugin/src/ui/chatSidebar.ts:313`, `plugin/src/ui/chatSidebar.ts:349`, `plugin/src/ui/chatSidebar.ts:358`, `plugin/src/ui/chatSidebar.ts:371`, `plugin/src/ui/chatSidebar.ts:378`, `plugin/src/ui/chatSidebar.ts:388`, `plugin/src/ui/chatSidebar.ts:2367`, `plugin/src/ui/chatSidebar.ts:2421`, `plugin/src/ui/chatSidebar.ts:2605`, `plugin/src/ui/chatSidebar.ts:4554`
- Evidence: Several event listeners call async methods without `void ...catch(...)` or disabled/loading state. Examples include `this.handleSend()`, settings saves from mode/model/reasoning controls, `updateIncuratorBackend()`, session deletion, and status refresh. `refreshIncuratorStatus()` has a `finally` but no `catch`; if backend status throws, the promise rejects from a render-triggered badge refresh.
- Fix sketch: Add a small `runUiTask(label, fn, opts)` helper that catches errors, shows an appropriate Notice for user-triggered failures, logs debug details once, and protects controls from double-click reentry where needed.
- Blast radius: Chat send, model/settings controls, status badges, update banner, session drawer.
- Suggested PR: `fix/plugin-chat-ui-task-errors`

### [G14-11] (g) S2 - Large binary/image paths perform expensive base64 conversion and full inline rendering
- Loc: `plugin/src/ui/chatSidebar.ts:539`, `plugin/src/ui/chatSidebar.ts:540`, `plugin/src/ui/chatSidebar.ts:2660`, `plugin/src/ui/chatSidebar.ts:2662`, `plugin/src/ui/chatSidebar.ts:4190`, `plugin/src/ui/chatSidebar.ts:4193`, `plugin/src/ui/chatSidebar.ts:4826`, `plugin/src/ui/chatSidebar.ts:4829`
- Evidence: Vault images are read into an `ArrayBuffer`, converted to base64 through repeated string concatenation in `arrayBufferToBase64()`, then embedded directly in context chips and historical message ref thumbnails as data URLs. Large pasted/scanned PDF crops or images can inflate session state, DOM attributes, and render cost. Native file attachments use FileReader, but vault binary conversion is still a hot synchronous JS loop after the async read.
- Fix sketch: Use chunked conversion or Electron/Node `Buffer` where available, cap image byte size before storing in session context, and consider object URLs/thumbnails for chip display while keeping provider payload separate.
- Blast radius: Image/PDF crop attachments, session file size, chat rendering, provider vision payloads.
- Suggested PR: `perf/plugin-chat-image-payload-limits`

### [G14-12] (i,f) S3 - Sidebar copy and controls expose inconsistent product language and undocumented micro-flows
- Loc: `plugin/src/ui/chatSidebar.ts:276`, `plugin/src/ui/chatSidebar.ts:755`, `plugin/src/ui/chatSidebar.ts:2819`, `plugin/src/ui/chatSidebar.ts:2823`, `plugin/src/ui/chatSidebar.ts:3145`, `plugin/src/ui/chatSidebar.ts:3150`, `plugin/src/ui/chatSidebar.ts:4629`; `docs/guides/PLUGIN_GUIDE.md:42`, `docs/guides/PLUGIN_GUIDE.md:79`, `docs/guides/PLUGIN_GUIDE.md:306`
- Evidence: The guide documents major sidebar features, but some in-file micro-flows and copy are inconsistent: a Korean-only deletion notice appears in the English UI path, drop/split labels and action buttons rely on text glyphs, and the header status bar behavior is not described in the plugin guide's sidebar feature list. This is not a crash, but it creates a rough UX surface in a frequently used view.
- Fix sketch: Do a copy/UI pass after functional fixes: standardize English/Korean guide coverage, replace glyph-in-text controls with existing icon button patterns where practical, and document the status bar and split-PDF drop behavior if retained.
- Blast radius: Chat sidebar UI, plugin guide EN/KR sync, styles and accessibility labels.
- Suggested PR: `docs-ui/plugin-chat-sidebar-polish`

### [G14-13] (h,e) S3 - Existing tests mostly assert source text instead of behavior
- Loc: `plugin/src/ui/chatSidebarSource.test.ts:1`, `plugin/src/ui/chatSidebarSource.test.ts:9`, `plugin/src/ui/chatSidebarSource.test.ts:21`, `plugin/src/ui/chatSidebarSource.test.ts:138`, `plugin/src/ui/chatSidebarSource.test.ts:215`, `plugin/src/ui/chatSidebarSource.test.ts:270`
- Evidence: The main sidebar regression test reads `chatSidebar.ts` as text and asserts string containment. This catches accidental deletion of specific guard strings, but it cannot reproduce lifecycle bugs such as context-build failures, stale trace races, old-message continuation, async MarkdownRenderer timing, or status-badge rejection paths.
- Fix sketch: Keep source-contract tests for removed legacy hazards, but add small behavior-level tests around extracted pure controllers/helpers first. For DOM/view behavior, introduce a lightweight Obsidian facade or adapter tests once `ChatSidebarView` is split.
- Blast radius: Refactor safety, future regression detection, confidence in G14 fixes.
- Suggested PR: `test/plugin-chat-behavior-harness`

## Positives (keep / do-not-break)

- Streaming avoids repeated full `MarkdownRenderer` passes by rendering raw streaming text and doing one rich render after completion (`plugin/src/ui/chatSidebar.ts:2699`).
- The chat edit workflow has important safety gates: DiffViewer singleton use, review-open serialization, order-independent multi-edit matching, applied/not-found pill status, and focus-safe auto-open behavior (`plugin/src/ui/chatSidebar.ts:3799`, `plugin/src/ui/chatSidebar.ts:3881`, `plugin/src/ui/chatSidebar.ts:3926`).
- Context-priority work is valuable: recency anchor, primary-focus selection markers, edit-affordance suppression for localized questions, and background-reference wrappers all reduce cross-model drift (`plugin/src/ui/chatSidebar.ts:1309`, `plugin/src/ui/chatSidebar.ts:1326`, `plugin/src/ui/chatSidebar.ts:1448`, `plugin/src/ui/chatSidebar.ts:1497`).
- Passive PDF context does not auto-register sources, while explicit Add Source paths go through backend commands and human confirmation/default import mode (`plugin/src/ui/chatSidebar.ts:1699`, `plugin/src/ui/chatSidebar.ts:2441`, `plugin/src/ui/chatSidebar.ts:2528`).
- Zotero/reference identity handling is intentionally stronger than older path-only behavior: `assetStatusKey()`, `ZoteroPathCache`, and status-key reuse reduce cross-device/source-status drift (`plugin/src/ui/chatSidebar.ts:2239`, `plugin/src/ui/chatSidebar.ts:2258`, `plugin/src/ui/chatSidebar.ts:2333`).
- Session deletion records tombstones and message cloning clears stale streaming flags, which aligns with the sync guide's session-merge model (`plugin/src/ui/chatSidebar.ts:4576`, `plugin/src/ui/chatSidebar.ts:4650`; `docs/guides/SYNC_IGNORE_GUIDE.md:64`).

## Open questions for the human

- Should manual Continue be allowed on any historical truncated assistant message, or only on the terminal assistant turn? The code currently implies any historical message is supported.
- Should the chat header status bar remain inside the sidebar, or should status move to the dashboard/status snapshot component to avoid duplicate polling logic?
- Are `.cursorrules` and `.cursor/rules/*` intended to be injected into every sidechat provider prompt, or should that be an explicit workspace/setting-controlled behavior?
- For the god-file split, is a behavior-preserving controller extraction acceptable before user-visible UI changes, or should fixes land first and refactor later?
- What level of Obsidian UI test harness is acceptable for Phase A: source-contract tests plus pure helper tests, or a mocked DOM/view harness for `ChatSidebarView` interactions?
