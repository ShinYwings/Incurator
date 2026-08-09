import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const source = readFileSync(join(__dirname, "pdf", "ExternalPdfView.ts"), "utf-8");

describe("ExternalPdfView device-portable restore contract", () => {
  it("re-resolves Zotero-backed restored views through backend key lookup", () => {
    expect(source).toContain("resolvePortableStatePath");
    expect(source).toContain("resolveAssetSource");
    expect(source).toContain("zoteroAttachmentKey");
    expect(source).toContain("resolveZoteroViaBackend");
    expect(source).not.toContain("resolveZoteroLocally");
    expect(source).toContain("return resolved.absPath");
    expect(source).toContain("path: resolvedPath");
  });
});

describe("Convert-to-LaTeX (v0.22.0: latexModel setting removed)", () => {
  it("no longer references the removed latexModel plugin setting", () => {
    expect(source).not.toContain("settings.latexModel");
    expect(source).not.toContain("ollama pull ${resolvedModel");
  });

  it("routes the conversion through the backend PDF extraction model", () => {
    expect(source).toContain("this.plugin.incuratorClient.transcribePdfRegion({ text: rawText })");
    expect(source).not.toContain("this.plugin.llmClient.complete");
  });
});

describe("ExternalPdfView scroll performance", () => {
  it("coalesces scroll work through requestAnimationFrame", () => {
    expect(source).toContain("private scrollFrame: number | null = null");
    expect(source).toContain("scheduleScrollWork(token)");
    expect(source).toContain("requestAnimationFrame(() =>");
    expect(source).toContain("this.updateCurrentPage()");
    expect(source).toContain("void this.onScrollLazyRender(token)");
  });

  it("cancels pending scroll frames on close", () => {
    expect(source).toContain("cancelAnimationFrame(this.scrollFrame)");
  });

  it("invalidates in-flight PDF renders as soon as the view closes", () => {
    // v0.41.1: bumping the token stops work scheduled after it, but a task
    // already inside PDF.js keeps owning its canvas, so close must also cancel
    // the live render tasks before anything else runs.
    expect(source).toMatch(
      /async onClose\(\): Promise<void> \{\s*this\.renderToken\+\+;\s*this\.cancelAllPageRenders\(\);\s*this\.clearTimers\(\);/
    );
  });
});

describe("Convert-to-LaTeX unmapped-glyph routing (v0.52.3)", () => {
  it("routes a selection carrying unmapped glyphs to the image path", () => {
    // A PDF whose maths font has no /ToUnicode yields U+0000 per glyph, so the
    // symbols exist only in the pixels. v0.52.1 stripped them and shipped a
    // confidently wrong equation to the clipboard; the count must decide the
    // channel instead.
    expect(source).toContain("const unmapped = countUnmappedGlyphs(raw)");
    expect(source).toMatch(
      /if \(unmapped > 0\) \{\s*const crop = rect \? this\.cropRectToBase64\(rect\) : null;/
    );
  });

  it("never falls back to text when the crop is unavailable", () => {
    // Falling back would send text already known to be missing its symbols,
    // which is the silent corruption this release exists to remove.
    const branch = source.slice(
      source.indexOf("const unmapped = countUnmappedGlyphs(raw)"),
      source.indexOf("const text = sanitizePdfSelectionText(raw)")
    );
    expect(branch).toContain("the page image could ");
    expect(branch).not.toContain("convertSelectionToLatex(");
  });

  it("measures the selection rect while the selection is still live", () => {
    // Both entry points must snapshot geometry up front: opening or clicking a
    // menu can collapse the DOM selection, and reading the rect at click time
    // would leave the text decision and the pixels describing two moments.
    expect(source).toContain(".onClick(() => this.convertSelectionToLatexFromRaw(raw, rect))");
    expect(source).toContain("const rect = this.captureSelectionRect();");
    expect(source).toContain(
      "void this.convertSelectionToLatexFromRaw(raw, this.captureSelectionRect());"
    );
    // The old click-time read must not come back.
    expect(source).not.toContain("cropCurrentSelectionToBase64");
  });

  it("unions only the line rects that sit on the anchored page", () => {
    // range.getBoundingClientRect() on a selection running onto the next page
    // spans both pages and the gap, so cropping it swallows every unselected
    // line down to the page edge while still dropping the overflow.
    expect(source).toContain("range.getClientRects()");
    expect(source).toContain("const mid = r.top + r.height / 2;");
    expect(source).toContain("if (mid < pageRect.top || mid > pageRect.bottom) continue;");
  });

  it("gives the clipboard path its own failure wording", () => {
    // transcribePdfCrop's default ends with "Attached crop fallback.", which is
    // true only for the chat snip. Nothing is attached when copying.
    expect(source).toContain("LaTeX conversion failed while reading the page image");
    expect(source).toContain("Nothing was copied.");
  });
});
