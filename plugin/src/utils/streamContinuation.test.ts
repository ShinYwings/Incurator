import { describe, expect, it } from "vitest";
import {
  stitchContinuation,
  repairMangledEditFence,
  hasUnterminatedEditFence,
  buildContinuationPrompt,
  MIN_STITCH_OVERLAP,
} from "./streamContinuation";

describe("stitchContinuation", () => {
  it("appends a clean continuation that does not repeat", () => {
    expect(stitchContinuation("The quick brown", " fox jumps")).toBe("The quick brown fox jumps");
  });

  it("de-duplicates a long repeated overlap at the seam", () => {
    const existing = "Line one\nLine two\nLine three is incompl";
    const continuation = "Line three is incomplete and now finished.";
    expect(stitchContinuation(existing, continuation)).toBe(
      "Line one\nLine two\nLine three is incomplete and now finished."
    );
  });

  it("does NOT trust a too-short overlap (would delete real text)", () => {
    // overlap "e" (1 char) is below MIN_STITCH_OVERLAP → append verbatim
    const out = stitchContinuation("apple", "elephant");
    expect(out).toBe("appleelephant");
    expect(MIN_STITCH_OVERLAP).toBeGreaterThan(1);
  });

  it("returns the other side when one is empty", () => {
    expect(stitchContinuation("", "abc")).toBe("abc");
    expect(stitchContinuation("abc", "")).toBe("abc");
  });

  it("repairs a doubled ai-agent-edit fence created at the seam", () => {
    const existing = "intro\n```ai-agent-";
    const continuation = "ai-agent-edit filepath=\"a.md\"\n";
    // naive concat would give ```ai-agent-ai-agent-edit; stitch repairs it
    expect(stitchContinuation(existing, continuation)).toContain("```ai-agent-edit filepath=");
    expect(stitchContinuation(existing, continuation)).not.toContain("ai-agent-ai-agent-edit");
  });
});

describe("repairMangledEditFence", () => {
  it("collapses any number of doubled markers", () => {
    expect(repairMangledEditFence("```ai-agent-ai-agent-ai-agent-edit")).toBe("```ai-agent-edit");
  });
  it("leaves a clean marker untouched", () => {
    expect(repairMangledEditFence("```ai-agent-edit foo")).toBe("```ai-agent-edit foo");
  });
});

describe("hasUnterminatedEditFence", () => {
  it("detects an open edit block with no closing fence", () => {
    expect(hasUnterminatedEditFence('x\n```ai-agent-edit filepath="a.md"\n<<<< SEARCH\nfoo')).toBe(true);
  });
  it("returns false when the block is closed", () => {
    expect(
      hasUnterminatedEditFence('```ai-agent-edit\n<<<< SEARCH\nfoo\n==== REPLACE\nbar\n>>>>\n```')
    ).toBe(false);
  });
  it("returns false when there is no edit block at all", () => {
    expect(hasUnterminatedEditFence("just prose, no edits")).toBe(false);
  });

  it("stays unterminated when a NESTED code block closes but >>>> has not arrived", () => {
    // The REPLACE body contains a fenced python snippet; a fence-only check would
    // wrongly see the inner ``` and call the edit block closed.
    const partial =
      '```ai-agent-edit filepath="a.md"\n<<<< SEARCH\nx\n==== REPLACE\n```python\nprint(1)\n```\n';
    expect(hasUnterminatedEditFence(partial)).toBe(true);
  });

  it("is terminated when >>>> AND the outer fence both close (with nested code)", () => {
    const full =
      '```ai-agent-edit filepath="a.md"\n<<<< SEARCH\nx\n==== REPLACE\n```python\nprint(1)\n```\n>>>>\n```';
    expect(hasUnterminatedEditFence(full)).toBe(false);
  });
});

describe("buildContinuationPrompt", () => {
  it("adds mid-fence resume guidance when truncated inside an edit block", () => {
    const p = buildContinuationPrompt('```ai-agent-edit\n<<<< SEARCH\nfoo');
    expect(p).toContain("INSIDE an `ai-agent-edit` block");
    expect(p).toContain(">>>>");
  });
  it("omits fence guidance for plain-prose truncation", () => {
    const p = buildContinuationPrompt("a long answer that was cut off");
    expect(p).not.toContain("ai-agent-edit");
    expect(p).toContain("cut off");
  });
});
