import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { join } from "path";
import { describe, expect, it } from "vitest";

// Source-contract tests for the inverted-decoration Diff Viewer. The viewer is
// CM6/DOM-driven and cannot be unit-rendered headlessly, so these pin the
// structural invariants the P0 triage relied on (Bug 1/6 already-fixed) and the
// v0.14.1 fixes (Bug 3 cursor, Bug 11 hover anchor).
function source(): string {
  const dir = fileURLToPath(new URL(".", import.meta.url));
  return readFileSync(join(dir, "diffViewer.ts"), "utf8");
}

describe("diff viewer source contract", () => {
  it("Bug 6: show() never writes the buffer on open — only accept paths replaceRange", () => {
    const src = source();
    const showBody = src.slice(src.indexOf("show("), src.indexOf("close(): void"));
    expect(showBody).not.toContain("replaceRange");
    // The accept paths DO write.
    expect(src).toContain("acceptCurrentHunk");
    expect(src).toContain("this.view.editor.replaceRange(this.modifiedText");
  });

  it("Bug 1: hunk navigation dispatches a real CM6 scrollIntoView", () => {
    expect(source()).toContain("EditorView.scrollIntoView(pos, { y: \"center\" })");
  });

  it("Bug 3 (v0.14.1): Accept-All restores the caret to the first changed line, not the end", () => {
    const src = source();
    expect(src).toContain("this.firstChangedLine");
    expect(src).toContain("setCursor({ line: caretLine, ch: 0 })");
    // The old bottom-teleport must be gone.
    expect(src).not.toContain("this.view.editor.setCursor(finalEndPos)");
  });

  it("Bug 11 (v0.14.1): the toolbar scrolls the first hunk into view before measuring coords", () => {
    const src = source();
    const showBody = src.slice(src.indexOf("requestAnimationFrame(() => {"));
    // scrollIntoView appears before buildToolbar in the open sequence.
    const scrollIdx = showBody.indexOf("scrollIntoView");
    const buildIdx = showBody.indexOf("this.buildToolbar(coords)");
    expect(scrollIdx).toBeGreaterThanOrEqual(0);
    expect(buildIdx).toBeGreaterThan(scrollIdx);
  });
});
