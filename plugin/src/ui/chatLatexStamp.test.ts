import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { join } from "path";

// The chat-sidebar LaTeX source stamping is wired inside ChatSidebarView, which
// cannot be instantiated under the node test env (no Obsidian runtime / no DOM).
// Assert the wiring at the source level; the stamping logic itself is unit-tested
// in textUtils.test.ts (stampMathSourceData) and mathSource.test.ts.

const src = readFileSync(
  fileURLToPath(new URL("./chatSidebar.ts", import.meta.url)),
  "utf8"
);

describe("chat-sidebar LaTeX source stamping wiring (chatSidebar.ts)", () => {
  it("imports the shared stamping helper", () => {
    expect(src).toMatch(/import\s*\{[^}]*\bstampMathSourceData\b[^}]*\}\s*from\s*"\.\.\/utils\/textUtils"/);
  });

  it("stamps each assistant render with its exact source after the render resolves", () => {
    // Must stamp AFTER MarkdownRenderer.render resolves (the .math spans exist
    // then) and with the SAME source string that was rendered.
    expect(src).toMatch(
      /renderAssistantMarkdown\(source: string, wrapper: HTMLElement\)[\s\S]*?MarkdownRenderer\.render\(this\.app, source, wrapper, "", this\)\.then\(\(\) =>[\s\S]*?stampMathSourceData\(wrapper, source\)/
    );
  });

  it("routes assistant prose renders through the stamping helper (not raw render)", () => {
    // Every assistant-prose MarkdownRenderer.render must go via the helper so the
    // formulas get a data-tex stamp; assert the call sites use it.
    expect(src).toMatch(/this\.renderAssistantMarkdown\(processedContent, mdWrapper\)/);
    expect(src).toMatch(/this\.renderAssistantMarkdown\(processedBefore, mdWrapper\)/);
  });
});
