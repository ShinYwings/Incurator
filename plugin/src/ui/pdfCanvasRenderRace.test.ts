import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { join } from "path";

/**
 * v0.41.1 regression: PDF.js throws
 * "Cannot use the same canvas during multiple render() operations"
 * when a second `render()` starts while the first still owns the canvas.
 *
 * `ExternalPdfView` REUSES each page's canvas across zoom/scroll re-renders and
 * document swaps, so the render task must be tracked and cancelled — the
 * `renderToken` guard alone only stops work scheduled *after* the bump, never a
 * task already inside PDF.js.
 */
const viewSource = () =>
  readFileSync(join(__dirname, "pdf", "ExternalPdfView.ts"), "utf8");

describe("ExternalPdfView canvas render race", () => {
  it("does not fire-and-forget page.render()", () => {
    const src = viewSource();
    // The old shape awaited the promise inline with no handle to cancel.
    expect(src).not.toContain(
      "await page.render({ canvasContext: ctx, viewport: hiResViewport }).promise"
    );
  });

  it("keeps a cancellable handle on the in-flight task per page", () => {
    const src = viewSource();
    expect(src).toContain("pageRenderTasks");
    expect(src).toContain("const task = page.render(");
    expect(src).toContain("this.pageRenderTasks.set(pageNum, task)");
  });

  it("frees the canvas before starting the next render of that page", () => {
    const src = viewSource();
    expect(src).toContain("await this.cancelPageRender(pageNum)");
    // Cancellation must be awaited, otherwise the canvas is not yet released.
    expect(src).toContain("await previous.promise");
  });

  it("cancels every in-flight render on document swap, reload, and close", () => {
    const src = viewSource();
    const cancelAllCalls = src.match(/this\.cancelAllPageRenders\(\)/g) ?? [];
    // renderPdf (document swap), reloadFromDisk, and onClose.
    expect(cancelAllCalls.length).toBeGreaterThanOrEqual(3);
  });

  it("declares the render task as cancellable in the PdfPage contract", () => {
    const src = viewSource();
    expect(src).toContain("interface PdfRenderTask");
    expect(src).toContain("cancel: () => void");
  });
});
