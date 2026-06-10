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
    expect(source).toContain("const language = inferQueryLanguageMetadata(query)");
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

  it("writes proposed edits to a diff artifact note, guarded and idempotent (item 20)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");

    // Writer is guarded by the setting and only runs once per message.
    expect(source).toContain("private async maybeWriteEditArtifact(msg: ChatMessage)");
    expect(source).toContain("if (!this.plugin.settings.editArtifactEnabled) return;");
    expect(source).toContain("if (msg.editArtifactPath) return;");
    expect(source).toContain("buildEditArtifactMarkdown(");
    expect(source).toContain("await this.app.vault.create(path, content);");
    expect(source).toContain("msg.editArtifactPath = path;");
    // Invoked from the generation-complete finalize path.
    expect(source).toContain("await this.maybeWriteEditArtifact(assistantMsg);");
    // Chat renders a link pill to the artifact, additive to the Review-Diff pills.
    expect(source).toContain("this.renderEditArtifactPill(contentEl, msg);");
    expect(source).toContain('nameEl.setText("Open diff artifact");');
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
});
