import { describe, it, expect, vi } from "vitest";
import {
  extractPdfPageTextFromDom,
  extractRegionTextFromSpans,
  withVisionFallback,
  type RegionTextSpan,
} from "./pdfCapture";
import type { PdfPageContext } from "../types";

function makeCtx(overrides: Partial<PdfPageContext> = {}): PdfPageContext {
  return {
    pageNum: 1,
    text: "some text",
    isScannedLike: false,
    textQuality: {
      score: 0.9,
      charCount: 100,
      wordCount: 20,
      lineCount: 5,
      brokenCharRatio: 0,
      whitespaceRatio: 0.1,
      isScannedLike: false,
      source: "pdfjs",
    },
    ...overrides,
  };
}

describe("withVisionFallback", () => {
  it("returns null when ctx is null", () => {
    expect(withVisionFallback(null, "text", true, () => "img")).toBeNull();
  });

  it("returns ctx unchanged when captureMode is not 'text'", () => {
    const ctx = makeCtx({ isScannedLike: true });
    const fn = vi.fn(() => "base64img");
    const result = withVisionFallback(ctx, "both", true, fn);
    expect(result).toBe(ctx);
    expect(fn).not.toHaveBeenCalled();
    expect(ctx.imageBase64).toBeUndefined();
  });

  it("returns ctx unchanged when visionFallback is false", () => {
    const ctx = makeCtx({ isScannedLike: true });
    const fn = vi.fn(() => "base64img");
    const result = withVisionFallback(ctx, "text", false, fn);
    expect(result).toBe(ctx);
    expect(fn).not.toHaveBeenCalled();
    expect(ctx.imageBase64).toBeUndefined();
  });

  it("returns ctx unchanged when page is not scanned-like", () => {
    const ctx = makeCtx({ isScannedLike: false });
    const fn = vi.fn(() => "base64img");
    const result = withVisionFallback(ctx, "text", true, fn);
    expect(result).toBe(ctx);
    expect(fn).not.toHaveBeenCalled();
    expect(ctx.imageBase64).toBeUndefined();
  });

  it("attaches image when mode=text, fallback=true, scanned-like=true", () => {
    const ctx = makeCtx({ isScannedLike: true });
    const result = withVisionFallback(ctx, "text", true, () => "mybase64");
    expect(result).toBe(ctx);
    expect(ctx.imageBase64).toBe("mybase64");
  });

  it("does not attach when getImageBase64 returns undefined", () => {
    const ctx = makeCtx({ isScannedLike: true });
    withVisionFallback(ctx, "text", true, () => undefined);
    expect(ctx.imageBase64).toBeUndefined();
  });

  it("calls getImageBase64 exactly once when conditions are met", () => {
    const ctx = makeCtx({ isScannedLike: true });
    const fn = vi.fn(() => "img");
    withVisionFallback(ctx, "text", true, fn);
    expect(fn).toHaveBeenCalledTimes(1);
  });
});

describe("extractPdfPageTextFromDom", () => {
  it("trusts substantial text-layer span text instead of marking it scanned-like", () => {
    const warningSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const text =
      "This rendered PDF text layer contains enough selectable words to answer from text context " +
      "without falling back to image capture. The viewer should keep this as normal DOM text.";
    const spans = text.split(" ").map((word) => ({ textContent: word }));
    const textLayer = {
      querySelectorAll: () => spans,
      innerText: "",
      textContent: text,
    };
    const pageEl = {
      dataset: {},
      querySelector: (selector: string) =>
        selector === ".textLayer" ? textLayer : null,
      innerText: "",
    };

    const result = extractPdfPageTextFromDom(pageEl as unknown as HTMLElement);

    expect(result.text).toContain("rendered PDF text layer");
    expect(result.textQuality.source).toBe("obsidian-text-layer");
    expect(result.textQuality.isScannedLike).toBe(false);
    warningSpy.mockRestore();
  });
});

describe("extractRegionTextFromSpans", () => {
  // A 200x200 crop box at the page origin.
  const crop = { left: 0, top: 0, right: 200, bottom: 200 };

  function span(
    text: string,
    left: number,
    top: number,
    width = 40,
    height = 12
  ): RegionTextSpan {
    return { text, left, top, right: left + width, bottom: top + height };
  }

  it("returns only the text inside the crop, in reading order", () => {
    const spans = [
      span("world", 60, 10),
      span("hello", 10, 10),
      span("second", 10, 40),
      span("line", 60, 40),
    ];
    expect(extractRegionTextFromSpans(spans, crop)).toBe("hello world\nsecond line");
  });

  it("excludes spans whose vertical midpoint is outside the crop band", () => {
    const spans = [
      span("inside", 10, 100),
      // top:300 — entirely below a 200-tall crop; midpoint 306 is outside.
      span("below", 10, 300),
      // a line clipped at the bottom edge: top 196, midpoint 202 > 200 → excluded.
      span("clipped", 10, 196),
    ];
    expect(extractRegionTextFromSpans(spans, crop)).toBe("inside");
  });

  it("excludes spans that do not overlap horizontally", () => {
    const spans = [
      span("keep", 10, 10),
      // left:400 — to the right of the 200-wide crop.
      span("faraway", 400, 10),
    ];
    expect(extractRegionTextFromSpans(spans, crop)).toBe("keep");
  });

  it("returns an empty string when the region has no selectable text (scanned page)", () => {
    expect(extractRegionTextFromSpans([], crop)).toBe("");
    expect(extractRegionTextFromSpans([span("   ", 10, 10)], crop)).toBe("");
    expect(extractRegionTextFromSpans([span("offscreen", 999, 999)], crop)).toBe("");
  });

  it("groups rows by their own rendered height (zoom-independent)", () => {
    // Larger spans (height 40) at a high zoom: a 20px top delta must NOT break a row.
    const spans = [
      span("BIG", 10, 10, 80, 40),
      span("ROW", 100, 18, 80, 40), // same visual row, 8px lower
      span("NEXT", 10, 70, 80, 40), // clearly a new row
    ];
    expect(extractRegionTextFromSpans(spans, crop)).toBe("BIG ROW\nNEXT");
  });
});
