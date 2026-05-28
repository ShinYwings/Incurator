import { describe, it, expect, vi } from "vitest";
import { withVisionFallback } from "./pdfCapture";
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
