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
    expect(source).toContain('this.activeContextExcludedKey === key) ref.includeInPrompt = false');
    expect(source).toContain('if (!shouldIncludeContext(ref)) chip.addClass("is-excluded")');
    expect(source).toContain("this.activeContextExcludedKey = shouldIncludeContext(ref) ? activeKey : null");
  });

  it("recognizes bare SEARCH/REPLACE edits against whole-file Markdown context", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");

    expect(source).toContain("getEditTargetContextForMessage");
    expect(source).toContain('ref.type === "file"');
    expect(source).toContain("bareBlockRegex");
    expect(source).toContain("Review in file");
    expect(source).toContain("multiProposals.length > 0");
    expect(source).toContain("modifiedFullText = parts.join(proposal.replace)");
    expect(source).toContain("editor.lineCount() - 1");
    expect(source).not.toContain("fullText.indexOf(multiProposal.search)");
  });

  it("only binds a workspace when the active note is inside one (no first-curate fallback)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "chatSidebar.ts"), "utf8");

    // Must not default to the first curate.yml found in the vault.
    expect(source).not.toContain("let targetCurate = curateFiles[0]");
    expect(source).toContain("Only bind a workspace when the active note is inside one");
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
});
