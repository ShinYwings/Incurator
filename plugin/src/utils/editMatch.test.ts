import { describe, expect, it } from "vitest";
import { findSearchBlock } from "./editMatch";

const file = [
  "# Title",
  "",
  "## Section A",
  "Some intro text.",
  "",
  "    const x = 1;",
  "    const y = 2;",
  "",
  "## Section B",
  "More text here.",
].join("\n");

describe("findSearchBlock", () => {
  it("matches exactly and reports the real span", () => {
    const r = findSearchBlock(file, "## Section A\nSome intro text.");
    expect(r).not.toBeNull();
    expect(r!.strategy).toBe("exact");
    expect(file.slice(r!.start, r!.end)).toBe("## Section A\nSome intro text.");
  });

  it("matches despite indentation drift (line-trim) and splices the ORIGINAL text", () => {
    // Agent dropped the 4-space indentation in its SEARCH.
    const r = findSearchBlock(file, "const x = 1;\nconst y = 2;");
    expect(r).not.toBeNull();
    expect(r!.strategy).toBe("line-trim");
    // The returned span must be the file's real, indented text — not the trimmed form.
    expect(file.slice(r!.start, r!.end)).toBe("    const x = 1;\n    const y = 2;");
  });

  it("matches CRLF file content against an \\n-only SEARCH", () => {
    const crlf = "## A\r\nbody line\r\n## B";
    const r = findSearchBlock(crlf, "## A\nbody line");
    expect(r).not.toBeNull();
    expect(r!.strategy).toBe("line-trim");
  });

  it("returns null (never guesses) when the trimmed block is ambiguous", () => {
    // Both occurrences are indented differently from the search, so exact fails
    // and line-trim finds two candidates → must refuse rather than guess.
    const dup = ["  alpha", "  beta", "gamma", "    alpha", "    beta", "delta"].join("\n");
    expect(findSearchBlock(dup, "alpha\nbeta")).toBeNull();
  });

  it("returns null when the SEARCH text is not present at all", () => {
    expect(findSearchBlock(file, "nonexistent line\nanother missing")).toBeNull();
  });

  it("anchors a ≥3-line block whose middle drifted", () => {
    const r = findSearchBlock(
      file,
      "## Section A\nTOTALLY DIFFERENT MIDDLE\nSome intro text.",
    );
    // first/last anchors (## Section A / Some intro text.) are unique → one span.
    expect(r).not.toBeNull();
    expect(r!.strategy).toBe("anchored");
    expect(file.slice(r!.start, r!.end)).toBe("## Section A\nSome intro text.");
  });

  it("rejects an anchored match that balloons past 3× the search size", () => {
    // first anchor near the top, last anchor far away → span >> 3× search lines.
    const big = [
      "START",
      "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l",
      "END",
    ].join("\n");
    const r = findSearchBlock(big, "START\nMIDDLE\nEND");
    // span would be 14 lines for a 3-line search (14 > 9) → guarded to null.
    expect(r).toBeNull();
  });

  it("does not match a single line when first and last anchors are the same", () => {
    // Reviewer regression: identical anchors (closing `}`) must map to DIFFERENT
    // file lines. With only one `}` in the file, there is no valid 2-line span,
    // so the matcher must refuse rather than collapse onto that single line.
    const code = ["class A {", "}"].join("\n");
    const searchBlock = ["}", "some drifted content", "}"].join("\n");
    expect(findSearchBlock(code, searchBlock)).toBeNull();
  });

  it("anchors the span between two identical anchors on distinct lines", () => {
    // Positive counterpart: identical `}` anchors that DO appear on two separate
    // lines should match the region between them (exercises the k=i+1 start).
    const code = ["}", "  body", "}", "tail"].join("\n");
    const r = findSearchBlock(code, "}\nDRIFT\n}");
    expect(r).not.toBeNull();
    expect(r!.strategy).toBe("anchored");
    expect(code.slice(r!.start, r!.end)).toBe("}\n  body\n}");
  });

  it("returns null for empty search", () => {
    expect(findSearchBlock(file, "")).toBeNull();
  });
});
