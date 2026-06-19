import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { join } from "path";
import { describe, expect, it } from "vitest";

describe("chat sidebar context chip source contract", () => {
  it("lets pending purple chips remove to zero and exposes eye toggles", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");

    expect(source).toContain("this.pendingContextRefs.splice(i, 1)");
    expect(source).not.toContain("this.pendingContextRefs.length <= 2");
    expect(source).toContain("ai-agent-context-chip-visibility");
    expect(source).toContain('setIcon(visibilityBtn, shouldIncludeContext(ref) ? "eye" : "eye-off")');
    expect(source).toContain('this.activeContextExcludedKeys.has(key)) ref.includeInPrompt = false');
    expect(source).toContain('if (!shouldIncludeContext(ref)) chip.addClass("is-excluded")');
    expect(source).toContain("this.activeContextExcludedKeys.add(activeKey)");
    expect(source).toContain("this.activeContextExcludedKeys.delete(activeKey)");
  });

  it("recognizes bare SEARCH/REPLACE edits against whole-file Markdown context", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");

    expect(source).toContain("getEditTargetContextForMessage");
    expect(source).toContain('ref.type === "file"');
    expect(source).toContain("bareBlockRegex");
    expect(source).toContain("Review edit");
    expect(source).toContain("multiProposals.length > 0");
    // Preview is built with the same ambiguity-safe matcher as apply, so the
    // shown diff equals what would be written (no exact-only split/join).
    expect(source).toContain("findSearchBlock(modifiedFullText, proposal.search)");
    expect(source).toContain("editor.lineCount() - 1");
    expect(source).not.toContain("fullText.indexOf(multiProposal.search)");
  });

  it("only binds a workspace when the active note is inside one (no first-curate fallback)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");

    // Must not default to the first curate.yml found in the vault.
    expect(source).not.toContain("let targetCurate = curateFiles[0]");
    expect(source).toContain("a conversational chat never binds an unrelated workspace");
    expect(source).toContain("client.fetchContext(query");
  });

  it("injects full open Markdown files as edit targets for global similar replacements", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");

    expect(source).toContain("isMarkdownEditRequest");
    expect(source).toContain("buildOpenMarkdownEditTargetContext");
    expect(source).toContain("<open_markdown_edit_targets>");
    expect(source).toContain("Full Markdown file content:");
    expect(source).toContain("Use this full file content to find every similar occurrence");
    expect(source).toContain("tab.selectedText?.trim()");
  });

  it("injects Markdown outlines as background structure for selected-context answers", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");

    expect(source).toContain("buildMarkdownOutline");
    expect(source).toContain("<markdown_outlines>");
    expect(source).toContain("<markdown_outline document=");
    expect(source).toContain('active="true"');
  });

  it("auto-opens the diff once per message under a safe focus gate, not on history re-render", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");

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

  it("does not yank the chat view to the bottom when generation completes", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");

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
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");
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
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");
    // Zotero identity is a durable property of the context ref, not inferred by
    // scanning open external-PDF leaves (which breaks when the tab is closed).
    expect(source).toContain("const isZoteroPdf = Boolean(ref.zoteroAttachmentKey);");
    expect(source).not.toContain("(leaf.view.getState() as any)?.zoteroAttachmentKey");
    expect(source).not.toContain("leaf.view.getState() as ExternalPdfState");
  });

  it("shows an inert Added badge for built sources (PLUGIN_SCHEMA §4.1.1)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");

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
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");
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
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");
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
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");

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

  it("handles snapshot-conflict refetch from Sources & Trace", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");

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
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");

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

  it("allows distinct crop images from the same PDF page to coexist as separate context refs", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");

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
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");

    // When a primary user ref has an image but no text (e.g. a scanned-PDF crop
    // or a dragged image), it must still emit a <primary_focus_selection> anchor
    // so the model treats the attached image as the core subject instead of the
    // weak, ignorable "(Image context attached below.)" fallback.
    expect(source).toContain("} else if (ref.imageBase64 && isPrimaryUserContext(ref)) {");
    expect(source).toContain("The user cropped/attached the image shown below as the primary focus");
  });

  it("PDF crop (snip-to-chat) attaches region-scoped text as the crop content, not empty or full-page", () => {
    const dir = fileURLToPath(new URL("../../", import.meta.url));
    const mainSource = readFileSync(join(dir, "main.ts"), "utf8");

    const snipBlock = mainSource.slice(
      mainSource.indexOf("pdfView.startSnippingMode((base64: string, pageNum: number, regionText: string)"),
      mainSource.indexOf("hotkeys: [{ modifiers: [\"Mod\", \"Shift\"], key: \"x\" }]")
    );
    expect(snipBlock).toContain("regionText");
    // The crop content is the region-scoped text, NEVER hard-coded empty again…
    expect(snipBlock).toContain("content: regionText,");
    expect(snipBlock).not.toContain('content: "",');
    // …and the regression of pulling the whole page text must not return.
    expect(snipBlock).not.toContain('getActivePdfContext("text")');
  });
});
