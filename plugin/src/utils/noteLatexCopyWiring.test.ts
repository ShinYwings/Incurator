import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { join } from "path";

// The reading-view stamping post-processor and note-view copy/cut interceptor live
// in main.ts `onload`, which cannot be instantiated under the node test env (no
// Obsidian Plugin runtime / no DOM). Assert the wiring at the source level.

const root = fileURLToPath(new URL("../../", import.meta.url));
const main = readFileSync(join(root, "main.ts"), "utf8");

describe("reading-view math source stamping (main.ts)", () => {
  it("registers a markdown post-processor that stamps section source as data-tex", () => {
    expect(main).toMatch(/registerMarkdownPostProcessor\(\(el, ctx\)/);
    expect(main).toContain("ctx.getSectionInfo(el)");
    // stamps the section's source lines (lineStart..lineEnd) onto the math elements
    expect(main).toMatch(/slice\(info\.lineStart, info\.lineEnd \+ 1\)/);
    expect(main).toMatch(/stampMathSourceData\(el, source\)/);
  });
});

describe("note reading-view LaTeX copy/cut wiring (main.ts)", () => {
  it("registers BOTH copy and cut, capture-phase", () => {
    expect(main).toMatch(/registerNoteLatexCopyDom\s*=\s*\(doc: Document\)/);
    expect(main).toMatch(/registerDomEvent\(doc, "copy", handle, \{ capture: true \}\)/);
    expect(main).toMatch(/registerDomEvent\(doc, "cut", handle, \{ capture: true \}\)/);
  });

  it("is registered on the main document AND every popout (window-open)", () => {
    expect(main).toContain("registerNoteLatexCopyDom(document);");
    expect(main).toMatch(/window-open[\s\S]*?registerNoteLatexCopyDom\(win\.document\)/);
  });

  it("gates strictly: reading-view AND math, else native clipboard is untouched", () => {
    // Order matters: both guards return BEFORE preventDefault, so Live Preview /
    // source mode and non-math selections are never intercepted.
    expect(main).toMatch(/if \(!isSelectionInReadingView\(sel\)\) return;/);
    expect(main).toMatch(/if \(!selectionContainsRenderedMath\(sel\)\) return;/);
    const readingIdx = main.indexOf("if (!isSelectionInReadingView(sel)) return;");
    const mathIdx = main.indexOf("if (!selectionContainsRenderedMath(sel)) return;");
    const preventIdx = main.indexOf("e.preventDefault();", mathIdx);
    expect(readingIdx).toBeGreaterThan(-1);
    expect(mathIdx).toBeGreaterThan(readingIdx);
    expect(preventIdx).toBeGreaterThan(mathIdx);
  });

  it("copies the selection as Markdown-with-LaTeX", () => {
    expect(main).toMatch(/selectionToMarkdownWithLatex\(sel, htmlToMarkdown\)/);
    expect(main).toMatch(/e\.clipboardData\.setData\("text\/plain", md\)/);
  });
});
