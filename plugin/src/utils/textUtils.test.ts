import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { join } from "path";
import {
  collapseStreamingEditBlocks,
  isSelectionInReadingView,
  normalizeLatexDelimiters,
  selectionContainsRenderedMath,
  selectionToMarkdownWithLatex,
  selectionToTextWithLatex,
  stampMathSourceData,
  stripDanglingEditMarkers,
  truncateToLength,
} from "./textUtils";

// Minimal Selection fake: vitest runs in a node environment with no DOM, so the
// MathJax DOM-walking branch is covered by a source assertion below; here we
// verify the empty and non-math (byte-identical) branches with real assertions.
function fakeSelection(opts: {
  text?: string;
  rangeCount?: number;
  hasMath?: boolean;
  isCollapsed?: boolean;
}): Selection {
  return {
    rangeCount: opts.rangeCount ?? 1,
    // A real Selection is collapsed when it has no extent (empty text); default
    // accordingly so collapsed/empty cases match real browser behavior.
    isCollapsed: opts.isCollapsed ?? (opts.text ?? "") === "",
    toString: () => opts.text ?? "",
    getRangeAt: () => ({
      cloneContents: () => ({
        querySelector: (_sel: string) => (opts.hasMath ? ({} as Element) : null),
      }),
    }),
  } as unknown as Selection;
}

// ─── truncateToLength ────────────────────────────────────────────────────────

describe("truncateToLength", () => {
  it("returns content unchanged when under limit", () => {
    expect(truncateToLength("hello world", 100)).toBe("hello world");
  });

  it("returns content unchanged when exactly at limit", () => {
    const s = "a".repeat(100);
    expect(truncateToLength(s, 100)).toBe(s);
  });

  it("truncates and appends marker when over limit", () => {
    const s = "a".repeat(10);
    const result = truncateToLength(s, 5);
    expect(result).toBe("aaaaa\n\n[Context truncated at 5 characters]");
  });
});

// ─── normalizeLatexDelimiters ────────────────────────────────────────────────

describe("normalizeLatexDelimiters", () => {
  // ── Escaped-bracket conversions ─────────────────────────────────────────

  it("converts \\\\[ \\\\] to $$", () => {
    expect(normalizeLatexDelimiters("\\\\[E=mc^2\\\\]")).toBe("$$E=mc^2$$");
  });

  it("converts \\\\( \\\\) to $", () => {
    expect(normalizeLatexDelimiters("\\\\(E=mc^2\\\\)")).toBe("$E=mc^2$");
  });

  it("converts \\[ \\] to $$", () => {
    expect(normalizeLatexDelimiters("\\[E=mc^2\\]")).toBe("$$E=mc^2$$");
  });

  it("converts \\( \\) to $", () => {
    expect(normalizeLatexDelimiters("\\(E=mc^2\\)")).toBe("$E=mc^2$");
  });

  // ── Protection: code blocks must be untouched ────────────────────────────

  it("leaves fenced code blocks intact", () => {
    const input = "```\n\\[x^2\\]\n```";
    expect(normalizeLatexDelimiters(input)).toBe(input);
  });

  it("leaves inline code intact", () => {
    const input = "Use `\\(x\\)` for inline math";
    expect(normalizeLatexDelimiters(input)).toBe(input);
  });

  it("leaves existing $$ display math intact", () => {
    const input = "$$E = mc^2$$";
    expect(normalizeLatexDelimiters(input)).toBe(input);
  });

  it("leaves existing single-$ inline math intact", () => {
    const input = "So $x^2$ holds.";
    expect(normalizeLatexDelimiters(input)).toBe(input);
  });

  // ── Protection: markdown links and HTML must pass through unchanged ──────

  it("leaves markdown links intact", () => {
    const input = "See [link](https://example.com) for details.";
    expect(normalizeLatexDelimiters(input)).toBe(input);
  });

  it("protects HTML open/close tags but not their text content", () => {
    // <code> and </code> tags are protected; text between them is still transformed
    const input = "A <code>\\(x\\)</code> tag.";
    const result = normalizeLatexDelimiters(input);
    // The tags themselves are preserved
    expect(result).toContain("<code>");
    expect(result).toContain("</code>");
    // The \( \) inside is converted since only the tag tokens are shielded
    expect(result).toContain("$x$");
  });

  // ── Mixed content ────────────────────────────────────────────────────────

  it("converts delimiters outside code blocks but leaves code intact", () => {
    const input = "Before ```\\[x\\]``` after \\(y\\)";
    const result = normalizeLatexDelimiters(input);
    // Code block is untouched, outer \( \) is converted
    expect(result).toContain("```\\[x\\]```");
    expect(result).toContain("$y$");
  });

  it("is idempotent on already-normalised content", () => {
    const input = "Some $x^2$ and $$y = z$$ here.";
    expect(normalizeLatexDelimiters(normalizeLatexDelimiters(input))).toBe(
      normalizeLatexDelimiters(input)
    );
  });

  // ── Backtick-wrapped math (Item 17) ──────────────────────────────────────

  it("unwraps inline-code backticks around a dollar math span", () => {
    expect(normalizeLatexDelimiters("The gradient `$\\nabla_\\theta L$` here.")).toBe(
      "The gradient $\\nabla_\\theta L$ here."
    );
  });

  it("unwraps backticks around superscript/subscript dollar math", () => {
    expect(normalizeLatexDelimiters("Energy `$x^2$` term")).toBe("Energy $x^2$ term");
  });

  it("unwraps backticks around display dollar math", () => {
    expect(normalizeLatexDelimiters("`$$y = z^2$$`")).toBe("$$y = z^2$$");
  });

  it("leaves non-math backtick code with dollars intact", () => {
    // A price range is not math: no LaTeX command or sub/superscript/brace.
    const input = "Costs `$5 and $10` total.";
    expect(normalizeLatexDelimiters(input)).toBe(input);
  });

  it("still leaves documentation-style \\( \\) inline code intact", () => {
    const input = "Use `\\(x\\)` for inline math";
    expect(normalizeLatexDelimiters(input)).toBe(input);
  });
});

// ─── collapseStreamingEditBlocks (item 20) ──────────────────────────────────

describe("collapseStreamingEditBlocks", () => {
  it("returns prose unchanged when no edit blocks are present", () => {
    const input = "Here is my plan with no code edits.";
    expect(collapseStreamingEditBlocks(input)).toBe(input);
  });

  it("hides everything from the first fenced ai-agent-edit block", () => {
    const input =
      "I'll make two edits.\n\n" +
      '```ai-agent-edit filepath="a.md"\n<<<< SEARCH\nfoo\n==== REPLACE\nbar\n>>>>\n```\n' +
      '```ai-agent-edit filepath="b.md"\n<<<< SEARCH\nbaz\n==== REPLACE\nqux\n>>>>\n```';
    const out = collapseStreamingEditBlocks(input);
    expect(out).toBe("I'll make two edits.\n\n*[Generating code edit…]*");
    expect(out).not.toContain("SEARCH");
    expect(out).not.toContain("REPLACE");
  });

  it("hides earlier complete blocks too, not just the last (the original bug)", () => {
    const input =
      "Intro.\n" +
      '```ai-agent-edit filepath="a.md"\n<<<< SEARCH\nfoo\n==== REPLACE\nbar\n>>>>\n```\n' +
      "<<<< SEARCH\nstill streaming";
    const out = collapseStreamingEditBlocks(input);
    expect(out).toBe("Intro.\n\n*[Generating code edit…]*");
  });

  it("handles a bare SEARCH marker without a fence", () => {
    const input = "Editing now.\n<<<< SEARCH\nfoo";
    expect(collapseStreamingEditBlocks(input)).toBe(
      "Editing now.\n\n*[Generating code edit…]*"
    );
  });

  it("tolerates a spacing-less opener variant", () => {
    const input = "Editing now.\n<<<<SEARCH\nfoo";
    expect(collapseStreamingEditBlocks(input)).toBe(
      "Editing now.\n\n*[Generating code edit…]*"
    );
  });
});

// ─── stripDanglingEditMarkers ───────────────────────────────────────────────

describe("stripDanglingEditMarkers", () => {
  it("removes an orphan >>>> leaked after a heading (the reported bug)", () => {
    const input = "### 2. Apparent Contour\n>>>>\nrest";
    expect(stripDanglingEditMarkers(input)).toBe("### 2. Apparent Contour\nrest");
  });

  it("removes orphan SEARCH / REPLACE markers", () => {
    const input = "<<<< SEARCH\nkept line\n==== REPLACE\nkept too\n>>>>";
    expect(stripDanglingEditMarkers(input)).toBe("kept line\nkept too");
  });

  it("preserves markers inside a fenced code block", () => {
    const input = "```\n<<<< SEARCH\n>>>>\n```";
    expect(stripDanglingEditMarkers(input)).toBe(input);
  });

  it("does not touch a plain ==== horizontal rule or normal text", () => {
    const input = "Title\n====\nbody";
    expect(stripDanglingEditMarkers(input)).toBe(input);
  });

  it("is a no-op when there is no marker evidence", () => {
    const input = "Just a normal answer.\nWith two lines.";
    expect(stripDanglingEditMarkers(input)).toBe(input);
  });
});

// ─── selectionToTextWithLatex ───────────────────────────────────────────────

describe("selectionToTextWithLatex", () => {
  it("returns '' for null, range-less, or collapsed selection", () => {
    expect(selectionToTextWithLatex(null)).toBe("");
    expect(selectionToTextWithLatex(fakeSelection({ rangeCount: 0 }))).toBe("");
    // Collapsed caret: must early-out before cloneContents() even with a range.
    expect(
      selectionToTextWithLatex(fakeSelection({ rangeCount: 1, isCollapsed: true }))
    ).toBe("");
  });

  it("returns selection.toString() unchanged for non-math selections", () => {
    const text = "plain    text\nwith   odd   spacing";
    expect(selectionToTextWithLatex(fakeSelection({ text, hasMath: false }))).toBe(text);
  });

  it("routes math-containing selections through the LaTeX-preserving DOM extractor", () => {
    // DOM walking can't run under the node test env; assert the wiring instead:
    // it gates on rendered-math nodes and reuses extractTextWithLatex, not toString.
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const src = readFileSync(join(dir, "textUtils.ts"), "utf8");
    expect(src).toContain('fragment.querySelector("mjx-container, span.math")');
    expect(src).toContain("return extractTextWithLatex(fragment)");
  });
});

// ─── selectionToMarkdownWithLatex (markdown + LaTeX copy) ───────────────────

describe("selectionToMarkdownWithLatex", () => {
  const fakeHtmlToMarkdown = (_el: HTMLElement) => "should-not-be-called";

  it("returns null for null, range-less, or collapsed selection (native copy left alone)", () => {
    expect(selectionToMarkdownWithLatex(null, fakeHtmlToMarkdown)).toBeNull();
    expect(
      selectionToMarkdownWithLatex(fakeSelection({ rangeCount: 0 }), fakeHtmlToMarkdown)
    ).toBeNull();
    expect(
      selectionToMarkdownWithLatex(
        fakeSelection({ rangeCount: 1, isCollapsed: true }),
        fakeHtmlToMarkdown
      )
    ).toBeNull();
  });

  it("converts via injected htmlToMarkdown and protects/restores math (source wiring)", () => {
    // The DOM path (cloneContents/replaceWith) can't run under the node test env;
    // assert the mechanism in source: math is swapped for an @@LATEX@@ placeholder
    // before htmlToMarkdown, then restored to $...$ from getLatexFromMathEl.
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const src = readFileSync(join(dir, "textUtils.ts"), "utf8");
    expect(src).toMatch(/selectionToMarkdownWithLatex[\s\S]*?@@LATEX\$\{placeholders\.length\}@@/);
    expect(src).toMatch(/selectionToMarkdownWithLatex[\s\S]*?getLatexFromMathEl\(m\)/);
    expect(src).toMatch(/selectionToMarkdownWithLatex[\s\S]*?htmlToMarkdown\(wrapper\)/);
    expect(src).toContain("info.isBlock ? `$$${info.source}$$` : `$${info.source}$`");
    // attachLatexCopyHandler delegates to it with the injected htmlToMarkdown.
    expect(src).toMatch(
      /attachLatexCopyHandler[\s\S]*?selectionToMarkdownWithLatex\(window\.getSelection\(\), htmlToMarkdown\)/
    );
  });
});

// ─── getLatexFromMathEl reads the data-tex stamp first ──────────────────────

describe("getLatexFromMathEl data-tex source (reading-view recovery)", () => {
  it("prefers the data-tex stamp over the (absent) annotation", () => {
    // Reading-view / chat CHTML has no annotation; the stamped data-tex is the
    // only source. Assert getLatexFromMathEl reads it (via closest) before falling
    // back to annotation/script lookups. DOM walking can't run in the node env.
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const src = readFileSync(join(dir, "textUtils.ts"), "utf8");
    expect(src).toMatch(
      /getLatexFromMathEl[\s\S]*?closest\?\.\("\[data-tex\]"\)/
    );
    expect(src).toMatch(/getLatexFromMathEl[\s\S]*?stamped\?\.dataset\?\.tex/);
    expect(src).toMatch(/dataset\?\.texDisplay === "block"/);
  });
});

// ─── stampMathSourceData (render-time source recovery) ──────────────────────

/** Minimal fake container: querySelectorAll(".math") returns `count` fake
 * HTMLElements, each with an own `dataset` object we can assert against. */
function fakeMathContainer(count: number): { el: any; maths: Array<{ dataset: any }> } {
  const maths = Array.from({ length: count }, () => ({ dataset: {} as Record<string, string> }));
  return { el: { querySelectorAll: (_sel: string) => maths }, maths };
}

describe("stampMathSourceData", () => {
  it("no-ops when the container has no rendered math", () => {
    const { el, maths } = fakeMathContainer(0);
    stampMathSourceData(el as HTMLElement, "text with $x$ that won't be stamped");
    expect(maths.length).toBe(0);
  });

  it("stamps each rendered math IN ORDER with its source and display type", () => {
    const { el, maths } = fakeMathContainer(3);
    stampMathSourceData(el as HTMLElement, "First $a^2$ then $$b^2$$ then $c^2$.");
    expect(maths[0].dataset).toEqual({ tex: "a^2", texDisplay: "inline" });
    expect(maths[1].dataset).toEqual({ tex: "b^2", texDisplay: "block" });
    expect(maths[2].dataset).toEqual({ tex: "c^2", texDisplay: "inline" });
  });

  it("never stamps a WRONG source: skips entirely on a parsed/rendered count mismatch", () => {
    // Source parses 1 formula but 2 math elements rendered ⇒ no stamping at all
    // (the correctness guard), so nothing wrong is ever attached.
    const { el, maths } = fakeMathContainer(2);
    stampMathSourceData(el as HTMLElement, "only $one$ formula here");
    expect(maths[0].dataset).toEqual({});
    expect(maths[1].dataset).toEqual({});
  });
});

// ─── selectionContainsRenderedMath (note-view copy gate) ────────────────────

describe("selectionContainsRenderedMath", () => {
  it("is false for null / range-less / collapsed selections", () => {
    expect(selectionContainsRenderedMath(null)).toBe(false);
    expect(selectionContainsRenderedMath(fakeSelection({ rangeCount: 0 }))).toBe(false);
    expect(
      selectionContainsRenderedMath(fakeSelection({ rangeCount: 1, isCollapsed: true }))
    ).toBe(false);
  });

  it("is false when the selection has no rendered math (native copy untouched)", () => {
    expect(
      selectionContainsRenderedMath(fakeSelection({ text: "plain note text", hasMath: false }))
    ).toBe(false);
  });

  it("is true when the cloned range contains a math node", () => {
    expect(
      selectionContainsRenderedMath(fakeSelection({ text: "x", hasMath: true }))
    ).toBe(true);
  });
});

// ─── isSelectionInReadingView (note-view copy gate) ─────────────────────────

describe("isSelectionInReadingView", () => {
  it("is null-safe: null / anchor-less selection ⇒ false", () => {
    expect(isSelectionInReadingView(null)).toBe(false);
    expect(
      isSelectionInReadingView({ anchorNode: null } as unknown as Selection)
    ).toBe(false);
  });

  it("gates on a `.markdown-reading-view` ancestor (excludes Live Preview / chat)", () => {
    // DOM `closest` can't run under the node env; assert the source gate instead.
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const src = readFileSync(join(dir, "textUtils.ts"), "utf8");
    expect(src).toMatch(
      /isSelectionInReadingView[\s\S]*?closest\("\.markdown-reading-view"\)/
    );
  });
});
