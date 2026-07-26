import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { join } from "path";
import { describe, expect, it } from "vitest";

describe("chat sidebar context chip source contract", () => {
  it("resets model effort through the shared catalogue normalizer", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    expect(source).toContain("normalizePluginModelEffort(");
    expect(source).toContain("this.plugin.settings, catalogue, persist");
  });

  it("lets pending purple chips remove to zero and exposes eye toggles", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    expect(source).toContain("this.pendingContextRefs.splice(i, 1)");
    expect(source).not.toContain("this.pendingContextRefs.length <= 2");
    expect(source).toContain("ai-agent-context-chip-visibility");
    expect(source).toContain('setIcon(visibilityBtn, shouldIncludeContext(ref) ? "eye" : "eye-off")');
    expect(source).toContain("ref.includeInPrompt = this.shouldIncludeOpenTabContext(tab)");
    expect(source).toContain('if (!shouldIncludeContext(ref)) chip.addClass("is-excluded")');
    expect(source).toContain("this.activeContextExcludedKeys.add(activeKey)");
    expect(source).toContain("this.activeContextExcludedKeys.delete(activeKey)");
  });

  it("appends the recency anchor to the latest user turn for attention against context decay (v0.19.0)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    // The anchor is built from the shared registry with the sidechat profile and
    // gated on the latest turn's primary-selection state. Appended to the last
    // user message so it sits at the strongest-attention recency position.
    expect(source).toContain('import { buildRecencyAnchor, SIDECHAT_PROFILE } from "../../context/promptRegistry"');
    expect(source).toContain("buildRecencyAnchor(SIDECHAT_PROFILE, {");
    expect(source).toContain("hasPrimarySelection: lastUserHasPrimaryContext");
  });

  it("suppresses edit affordances for a localized question turn (v0.21.0)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    // The shared pure predicate gates both the editable-selection affordance and
    // the edit-review-loop contract on the same flag, so a primary-focus question
    // turn carries the recency anchor unopposed.
    expect(source).toContain("shouldSuppressEditAffordances({");
    expect(source).toContain("hasPrimarySelection: lastUserHasPrimaryContext");
    expect(source).toContain("isEditRequest: latestIsMarkdownEditRequest");
    expect(source).toContain("const editInstruction = suppressEditAffordances");
    expect(source).toContain("!suppressEditAffordances &&");
  });

  it("recognizes bare SEARCH/REPLACE edits against whole-file Markdown context", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    expect(source).toContain("getEditTargetContextForMessage");
    expect(source).toContain('ref.type === "file"');
    expect(source).toContain("bareBlockRegex");
    expect(source).toContain("Review edit");
    expect(source).toContain("multiProposals.length > 0");
    // Preview is built with the same ambiguity-safe matcher as apply, so the
    // shown diff equals what would be written (no exact-only split/join).
    // v0.24.0 (P4b): proposals match against the ORIGINAL text (order-independent),
    // not the running result, so applying edit 1 can't break edit 2's SEARCH.
    expect(source).toContain("findSearchBlock(originalFullText, proposal.search)");
    expect(source).toContain("editor.lineCount() - 1");
    expect(source).not.toContain("fullText.indexOf(multiProposal.search)");
  });

  it("only binds a workspace when the active note is inside one (no first-curate fallback)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    // Must not default to the first curate.yml found in the vault.
    expect(source).not.toContain("let targetCurate = curateFiles[0]");
    expect(source).toContain("a conversational chat never binds an unrelated workspace");
    expect(source).toContain("client.fetchContext(query");
  });

  it("injects full open Markdown files as edit targets for global similar replacements", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    expect(source).toContain("isMarkdownEditRequest");
    expect(source).toContain("buildOpenMarkdownEditTargetContext");
    expect(source).toContain("<open_markdown_edit_targets>");
    expect(source).toContain("Full Markdown file content:");
    expect(source).toContain("Use this full file content to find every similar occurrence");
    expect(source).toContain("tab.selectedText?.trim()");
  });

  it("injects Markdown outlines as background structure for selected-context answers", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    expect(source).toContain("buildMarkdownOutline");
    expect(source).toContain("<markdown_outlines>");
    expect(source).toContain("<markdown_outline document=");
    expect(source).toContain('active="true"');
  });

  it("auto-opens the diff once per message under a safe focus gate, not on history re-render", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    // The on-disk artifact feature is fully removed (no writer / pill / setting).
    expect(source).not.toContain("maybeWriteEditArtifact");
    expect(source).not.toContain("renderEditArtifactPill");
    expect(source).not.toContain("editArtifactEnabled");
    expect(source).not.toContain("editArtifactPath");

    // Safe-gated auto-open runs once per message from the completion path.
    expect(source).toContain("private async maybeAutoOpenDiff(msg: ChatMessage)");
    expect(source).toContain("if (msg.diffAutoOpened) return;");
    expect(source).toContain("if (files.size !== 1) return;");
    expect(source).toContain("if (active && active.file?.path !== target) return;");
    expect(source).toContain("await this.maybeAutoOpenDiff(assistantMsg);");
  });

  it("keeps the edit-loop contract as a hint, not a hard gate (v0.24.0 demotion)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    // Contract still appended (last) for any edit-likely turn, incl. multi-turn carry.
    expect(source).toContain("getEditLoopContract()");
    expect(source).toContain("<edit_review_loop>");
    expect(source).toContain("priorAnswerOpenedEditLoop");
    expect(source).toContain("const editLoopLikely =");

    // v0.24.0: the hard gate and blocked banner are GONE — a valid edit is always
    // reviewable regardless of phase markers. The override path is removed too.
    expect(source).not.toContain("if (loop.hasEdits && !loop.ok && !msg.editLoopOverridden)");
    expect(source).not.toContain("msg.editLoopBlocked = true;");
    expect(source).not.toContain("renderEditLoopBlockedBanner");
    expect(source).not.toContain("Override & review anyway");

    // Observable phases stay when markers are present + valid; otherwise a soft hint.
    expect(source).toContain("renderEditLoopPhases");
    expect(source).toContain("renderEditLoopHint");
    expect(source).toContain('attr: { open: "", "data-phase": phases[i].label }');
  });

  it("v0.14.1 Diff Viewer fixes: review serialization, path fallback, derived pill status", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    // Bug 2: a single in-flight guard serializes diff-review opens.
    expect(source).toContain("private reviewInFlight = false;");
    expect(source).toContain("if (this.reviewInFlight) {");
    expect(source).toContain("return false;");
    expect(source).toContain("reviewFileEditProposalsImpl");

    // Bug 7: path resolution falls back to a case-insensitive full-path scan.
    expect(source).toContain("getMarkdownFiles()");
    expect(source).toContain("f.path.toLowerCase() === wantPath");
    expect(source).not.toContain("f.name.toLowerCase() === wantBase");

    // Bug 9: pill status is derived from the live file via classifyProposalStatus.
    expect(source).toContain("classifyProposalStatus");
    expect(source).toContain("this.app.vault.cachedRead(file)");
    expect(source).toContain("✓ Applied");
    expect(source).toContain("⚠ Not found");
    expect(source).toContain("proposalStatus === \"reviewable\"");
    expect(source).toContain("stopImmediatePropagation");
  });

  it("does not yank the chat view to the bottom when generation completes", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    // renderMessages preserves the reader's scroll position unless they were
    // already near the bottom (or a caller explicitly forces a bottom scroll).
    expect(source).toContain("private renderMessages(forceScroll: boolean = true)");
    expect(source).toContain("const wasNearBottom = this.isNearBottom();");
    expect(source).toContain("if (forceScroll || wasNearBottom) {");
    expect(source).toContain("this.messagesContainer.scrollTop = prevScrollTop;");
    expect(source).toContain("private isNearBottom(threshold: number = 150): boolean");
    // The generation-complete re-render must opt out of the forced bottom scroll.
    expect(source).toContain("this.renderMessages(false);");
  });

  it("keys the source-status map by one canonical assetStatusKey (Plan G item 3)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");
    // A single refStatusKey()/assetStatusKey is used for read + write so the
    // badge never desyncs (e.g. Zotero PDF whose path resolves only after add).
    expect(source).toContain("private refStatusKey(ref: ContextRef): string");
    expect(source).toContain("assetStatusKey({");
    expect(source).toContain("this.incuratorStatusByPath.get(this.refStatusKey(");
    expect(source).toContain("const statusKey = this.refStatusKey(ref);");
    // The old path-vs-zotero:key inconsistency is gone.
    expect(source).not.toContain('`zotero:${ref.zoteroAttachmentKey}` : "")');
  });

  it("detects Zotero PDFs via durable ref identity, not UI leaves or `as any` (Plan G item 4)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");
    // Zotero identity is a durable property of the context ref, not inferred by
    // scanning open external-PDF leaves (which breaks when the tab is closed).
    expect(source).toContain("const isZoteroPdf = Boolean(ref.zoteroAttachmentKey);");
    expect(source).not.toContain("(leaf.view.getState() as any)?.zoteroAttachmentKey");
    expect(source).not.toContain("leaf.view.getState() as ExternalPdfState");
  });

  it("shows an inert Added badge for built sources (PLUGIN_SCHEMA §4.1.1)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    // l1..l4_ready all collapse to the single "Added" label.
    expect(source).toContain('return "Added"');
    expect(source).not.toContain('return "L1 ready"');
    expect(source).not.toContain('return "L4 ready"');
    // Clicking an Added badge is a no-op (no re-ingest fallthrough), and the
    // badge is styled as inert.
    expect(source).toContain("isAddedState");
    expect(source).toContain('badge.toggleClass("is-added", isAddedState(status.state))');
    expect(source).toContain("if (isAddedState(status.state)) return;");
  });

  it("never registers a PDF as a passive provider-context side effect", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");
    const providerContext = source.slice(
      source.indexOf("private async buildIncuratorProviderContext"),
      source.indexOf("private async timedContextCall")
    );

    expect(providerContext).not.toContain("registerSource(");
    expect(providerContext).not.toContain("auto-index");
    expect(providerContext).toContain("context_source=");
    expect(providerContext).toContain("pdfSourceStatuses");
    expect(providerContext).toContain("if (useBackendPdfContext && client.available");
    expect(providerContext).not.toContain("const shouldFetchBackendContext");
  });

  it("grounds default Incurator sidechat context with evidence packs, not backend answers", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");
    const providerContext = source.slice(
      source.indexOf("private async buildIncuratorProviderContext"),
      source.indexOf("private async timedContextCall")
    );

    expect(providerContext).toContain("client.fetchContext(query");
    expect(providerContext).toContain("formatCuratorContextPack");
    expect(providerContext).not.toContain("client.curatorQuery(query");
    expect(providerContext).not.toContain("formatCuratorQueryResult(queryResult, query)");
  });

  it("handles Sources & Trace expansion and verification events through IncuratorClient", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    expect(source).toContain("attachContextTraceActionHandlers");
    expect(source).toContain("handleContextTraceAction");
    expect(source).toContain("context:expand");
    expect(source).toContain("context:verify");
    expect(source).toContain("client.expandContext");
    expect(source).toContain("client.verifyContext");
    expect(source).toContain("mergeContextExpansion");
    expect(source).toContain("mergeContextVerification");
    expect(source).toContain("this.mergeContextVerification(verified, detail.handle)");
  });

  it("records Sources & Trace feedback through IncuratorClient without mutating truth", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    expect(source).toContain("context:feedback");
    expect(source).toContain("handleContextTraceFeedback");
    expect(source).toContain("client.feedbackContext");
    expect(source).toContain("Feedback recorded.");
  });

  it("handles snapshot-conflict refetch from Sources & Trace", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    expect(source).toContain("context:refetch");
    expect(source).toContain("handleContextTraceRefetch");
    expect(source).toContain("markContextSnapshotConflict");
    expect(source).toContain("contextActionError");
    expect(source).toContain("Context snapshot changed. Refetch the evidence pack.");
    expect(source).toContain('operation: "snapshot_conflict"');
    expect(source).toContain("client.fetchContext(query");
    expect(source).toContain("replaceContextPack");
    expect(source).toContain("snapshot_conflict: refetch required before expanding or verifying this pack");
  });

  it("preserves eye-off state across tab switches (active-leaf-change must not clear excluded keys)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    // The active-leaf-change handler must NOT clear activeContextExcludedKeys.
    // Previously this bug reset all eye-off state on every tab switch.
    const leafChangeBlock = source.slice(
      source.indexOf("// Refresh context chips whenever the active leaf changes."),
      source.indexOf("this.registerDomEvent(\n      window,\n      EXTERNAL_PDF_CONTEXT_EVENT")
    );
    expect(leafChangeBlock).not.toContain("activeContextExcludedKeys.clear()");
    // The eye-off mechanism itself must still work
    expect(source).toContain("this.activeContextExcludedKeys.add(activeKey)");
    expect(source).toContain("this.activeContextExcludedKeys.delete(activeKey)");
  });

  it("refreshes context chips for tab-group layout changes and supports explicit hidden-tab inclusion", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    expect(source).toContain('this.app.workspace.on("layout-change"');
    expect(source).toContain("private activeContextIncludedKeys: Set<string> = new Set();");
    expect(source).toContain("private getPromptIncludedTabs(");
    expect(source).toContain("this.activeContextIncludedKeys.add(activeKey)");
    expect(source).toContain("this.activeContextIncludedKeys.delete(activeKey)");
  });

  it("filters every prompt path through the same open-tab inclusion policy", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    expect(source).toContain("const promptTabs = this.getPromptIncludedTabs(activeCtx);");
    expect(source).toContain("const tabs = this.getPromptIncludedTabs(activeCtx);");
    expect(source).toContain("const pdfTabs = this.getPromptIncludedTabs(activeCtx).filter(");
  });

  it("turns a complete plugin update into an actual Obsidian reload", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    expect(source).toContain('btn.setText("Reload Obsidian")');
    expect(source).toContain("window.location.reload()");
    expect(source).toContain("const updateReady = await this.plugin.updateIncuratorBackend()");
  });

  it("blocks stale plugin code before mutating the chat session", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");
    const handleSend = source.slice(
      source.indexOf("private async handleSend()"),
      source.indexOf("private async executeGitSidechatCommand")
    );

    const guard = handleSend.indexOf("await this.plugin.assertActivePluginBundle()");
    const mutation = handleSend.indexOf("this.messages.push(userMsg)");
    expect(guard).toBeGreaterThanOrEqual(0);
    expect(mutation).toBeGreaterThan(guard);
  });

  it("enumerates hidden Markdown/PDF leaves without materializing hidden PDFs", () => {
    const dir = fileURLToPath(new URL("../../", import.meta.url));
    const source = readFileSync(join(dir, "main.ts"), "utf8");
    const openTabs = source.slice(
      source.indexOf("private getOpenTabContexts("),
      source.indexOf("private getLeafFile(")
    );

    expect(openTabs).toContain("isEligibleOpenTabView(viewType)");
    expect(openTabs).toContain("isVisible = rect.width > 0 && rect.height > 0");
    expect(openTabs).toContain("if (isVisible)");
    expect(openTabs).toContain("sourceIdentity");
    expect(openTabs).toContain("pageNum");
    expect(openTabs).not.toContain("if (rect.width === 0 && rect.height === 0) return");
  });

  it("allows distinct crop images from the same PDF page to coexist as separate context refs", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    // addContextRef dedup must also compare imageBase64 so that two crops from
    // the same page (same label, different base64) are both accepted.
    const addContextRefBlock = source.slice(
      source.indexOf("addContextRef(ref: ContextRef): void {"),
      source.indexOf("focusInput(): void {")
    );
    expect(addContextRefBlock).toContain("r.imageBase64 === ref.imageBase64");
  });

  it("marks an image-only primary context as primary focus (image crops must not be buried)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    // When a primary user ref has an image but no text (e.g. a scanned-PDF crop
    // or a dragged image), it must still emit a <primary_focus_selection> anchor
    // so the model treats the attached image as the core subject instead of the
    // weak, ignorable "(Image context attached below.)" fallback.
    expect(source).toContain("} else if (ref.imageBase64 && isPrimaryUserContext(ref)) {");
    expect(source).toContain("The user cropped/attached the image shown below as the primary focus");
  });

  it("PDF crop (snip-to-chat) defers VLM to send-time via pendingCropBase64, not inline transcribePdfCrop", () => {
    const dir = fileURLToPath(new URL("../../", import.meta.url));
    const mainSource = readFileSync(join(dir, "main.ts"), "utf8");

    const snipBlock = mainSource.slice(
      mainSource.indexOf("pdfView.startSnippingMode(async (base64: string, pageNum: number, regionText: string)"),
      mainSource.indexOf("hotkeys: [{ modifiers: [\"Mod\", \"Shift\"], key: \"x\" }]")
    );
    // The snip callback must use regionText as immediate content and
    // tag the ref with pendingCropBase64 for deferred VLM at send-time.
    expect(snipBlock).toContain("content: regionText,");
    expect(snipBlock).toContain("pendingCropBase64: base64,");
    expect(snipBlock).toContain("imageBase64: base64,");
    // VLM must NOT run inline in the snip callback — it's deferred to
    // materializeContextRefs at send-time.
    expect(snipBlock).not.toContain("transcribePdfCrop");
    expect(snipBlock).not.toContain('content: "",');
    // …and the regression of pulling the whole page text must not return.
    expect(snipBlock).not.toContain('getActivePdfContext("text")');
  });

  it("materializeContextRefs routes crops by main-model vision (v0.28.0): direct image vs transcribe", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    const materializeBlock = source.slice(
      source.indexOf("private async materializeContextRefs("),
      source.indexOf("private async refreshPinnedContextRef(")
    );
    // Still detects pending crops and clears the flag in both branches.
    expect(materializeBlock).toContain("out.pendingCropBase64");
    expect(materializeBlock).toContain("ref.pendingCropBase64 = undefined");
    expect(materializeBlock).toContain("delete out.pendingCropBase64");
    // v0.28.0: branch on the MAIN chat model's vision capability.
    expect(materializeBlock).toContain("mainChatModelSupportsVision()");
    // Non-vision path still transcribes via the backend and drops the image.
    expect(materializeBlock).toContain("this.plugin.transcribePdfCrop");
    expect(materializeBlock).toContain("out.imageBase64 = undefined");
    // The transcribe round-trip must be GUARDED by the vision check (not
    // unconditional): vision keeps the image for the direct channel.
    const visionIdx = materializeBlock.indexOf("mainChatModelSupportsVision()");
    const transcribeIdx = materializeBlock.indexOf("this.plugin.transcribePdfCrop");
    expect(visionIdx).toBeGreaterThanOrEqual(0);
    expect(transcribeIdx).toBeGreaterThan(visionIdx);
  });

  it("mainChatModelSupportsVision() resolves the main chat model via modelSupportsVision", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");
    const start = source.indexOf("private mainChatModelSupportsVision(");
    expect(start).toBeGreaterThanOrEqual(0);
    const helper = source.slice(start, start + 320);
    expect(helper).toContain("modelSupportsVision(");
    expect(helper).toContain("this.plugin.settings.provider");
    expect(helper).toContain("this.plugin.settings.model");
  });

  it("handleSend renders the thinking indicator BEFORE the deferred crop materialize (no Send freeze)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    // The v0.27.9 pattern (materialize inside the pre-render contextRefs literal)
    // must be gone; the refs to send are snapshotted, then materialized later.
    expect(source).not.toContain("...(await this.materializeContextRefs(this.pendingContextRefs)),");
    expect(source).toContain("const pendingForSend = this.pendingContextRefs;");

    const hs = source.indexOf("private async handleSend(");
    expect(hs).toBeGreaterThanOrEqual(0);
    const renderIdx = source.indexOf("this.renderMessages();", hs);
    const matIdx = source.indexOf("await this.materializeContextRefs(", hs);
    expect(renderIdx).toBeGreaterThan(hs);
    expect(matIdx).toBeGreaterThan(renderIdx); // materialize AFTER the thinking render
  });

  it("Convert-to-LaTeX still routes through the backend transcribe resolver (no-regress)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "pdf", "ExternalPdfView.ts"), "utf8");
    // The right-click Convert-to-LaTeX text path is OUT OF SCOPE and unchanged.
    expect(source).toContain("transcribePdfRegion({ text:");
  });

  it("passes through PDF extraction failure messages without provider-coupled stripping", () => {
    const dir = fileURLToPath(new URL("../../", import.meta.url));
    const mainSource = readFileSync(join(dir, "main.ts"), "utf8");

    // Scope the guard to the PDF extraction failure path; unrelated provider
    // checks elsewhere in main.ts must not trip this regression test.
    const pdfBlock = mainSource.slice(
      mainSource.indexOf("async transcribePdfCrop("),
      mainSource.indexOf("async readRuntimeJson(")
    );

    // The method must NOT inspect this.settings.provider to decide what to strip.
    expect(pdfBlock).not.toContain('this.settings.provider === "ollama"');
    expect(pdfBlock).not.toContain(".replace(/ollama pull\\s+\\S+/gi, \"\")");
    expect(pdfBlock).toContain("PDF extraction model failed");
  });

  it("wires the 'Save to 02_Wiki' promote action with the trace source_span_ids", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    // The trace panel gets an onPromote callback bound to this answer's own trace
    // and message, not a mutable global trace reused across history.
    expect(source).toContain("const boundTrace = traceToRender;");
    expect(source).toContain("onPromote: () => void this.promoteAnswerToWiki(boundTrace, msg)");
    expect(source).toContain("interactive: isLastMessage");
    // The handler promotes the answer with the trace's source_span_ids so the
    // 02_Wiki page lists its source documents.
    expect(source).toContain("private async promoteAnswerToWiki(");
    expect(source).toContain("this.getIncuratorClient().promoteAnswer(");
    expect(source).toContain("result.source_span_ids");
    // Falls back to the user message immediately preceding this answer and
    // reports outcome.
    expect(source).toContain("const msgIndex = this.messages.indexOf(msg);");
    expect(source).toContain("const searchSlice = msgIndex >= 0 ? this.messages.slice(0, msgIndex) : this.messages;");
    expect(source).toContain('m) => m.role === "user"');
    expect(source).toContain("res.promoted_to");
  });

  it("opens generated vault block links from assistant answers through Obsidian", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    expect(source).toContain('link.getAttribute("data-href") ?? link.getAttribute("href")');
    expect(source).toContain('if (target.kind === "vault")');
    expect(source).toContain('this.app.workspace.openLinkText(target.linkpath, "", false)');
  });

  it("G14-1: deferred materialize AND buildLLMMessages are inside the try block so a context-build failure clears isStreaming (never stuck)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    // Both the deferred crop materialize (v0.28.0) and buildLLMMessages must sit
    // INSIDE the try block that catches streaming errors, so any context-build
    // failure reaches the catch that sets isStreaming = false. Regression guard:
    // a version that placed either BEFORE the try left the assistant bubble in a
    // permanent spinning state on context failure.
    const tryIdx = source.indexOf("try {\n      // Deferred crop materialization");
    expect(tryIdx).toBeGreaterThan(-1);
    const materializeIdx = source.indexOf(
      "const materialized = await this.materializeContextRefs(pendingForSend);",
      tryIdx
    );
    const buildIdx = source.indexOf(
      "const llmMessages = await this.buildLLMMessages(capturedActiveCtx);",
      tryIdx
    );
    expect(materializeIdx).toBeGreaterThan(tryIdx);
    expect(buildIdx).toBeGreaterThan(materializeIdx);
    // The old pre-try call site must not exist.
    expect(source).not.toContain("const llmMessages = await this.buildLLMMessages(capturedActiveCtx);\n    this.prepareStatusText");
  });

  it("G14-2: renderAssistantMessage targets message by data-msg-id, not always the last bubble", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chat", "ChatSidebarView.ts"), "utf8");

    // renderMessage stamps data-msg-id only when msg.id is defined (never "undefined").
    expect(source).toContain("if (msg.id !== undefined) msgEl.dataset.msgId = msg.id");
    // renderAssistantMessage guards the query on msg.id being defined before querying.
    expect(source).toContain("msg.id !== undefined");
    expect(source).toContain('`[data-msg-id="${msg.id}"]`');
    expect(source).toContain("byId ?? allMsgEls[allMsgEls.length - 1]");
  });
});
