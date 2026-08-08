import { describe, expect, it } from "vitest";
import { spawn } from "node:child_process";
import { isUnreadableSelection, sanitizePdfSelectionText } from "./pdfSelectionText";

const NUL = String.fromCharCode(0);

describe("sanitizePdfSelectionText", () => {
  it("strips the NUL bytes pdf.js emits for unmapped glyphs", () => {
    expect(sanitizePdfSelectionText(`x${NUL}^2`)).toBe("x^2");
  });

  it("returns empty when every character was an artifact", () => {
    expect(sanitizePdfSelectionText(NUL.repeat(12))).toBe("");
  });

  it("preserves tabs and newlines, which carry real layout", () => {
    expect(sanitizePdfSelectionText("a\tb\nc")).toBe("a\tb\nc");
  });

  it("preserves Unicode math, Greek, and CJK verbatim", () => {
    const text = "λ₁ ≤ Σ ∇², 고유값, ∫₀^∞";
    expect(sanitizePdfSelectionText(text)).toBe(text);
  });

  it("preserves combining marks so NFD filenames and accents survive", () => {
    const nfd = "Plücker";
    expect(sanitizePdfSelectionText(nfd)).toBe(nfd);
  });

  it("strips DEL and the C1 range", () => {
    expect(sanitizePdfSelectionText("abc")).toBe("abc");
  });

  it("trims surrounding whitespace", () => {
    expect(sanitizePdfSelectionText("  $x$  ")).toBe("$x$");
  });

  it("handles an empty input", () => {
    expect(sanitizePdfSelectionText("")).toBe("");
  });
});

describe("isUnreadableSelection", () => {
  it("is true when characters were selected but none survive", () => {
    expect(isUnreadableSelection(NUL + NUL)).toBe(true);
  });

  it("is false when nothing was selected", () => {
    expect(isUnreadableSelection("   ")).toBe(false);
  });

  it("is false when some readable text survives", () => {
    expect(isUnreadableSelection(`a${NUL}`)).toBe(false);
  });
});

describe("the spawn boundary this exists to protect", () => {
  it("throws synchronously on a NUL byte in an argv entry", () => {
    expect(() => spawn("/bin/echo", [`x${NUL}y`])).toThrow(/null bytes/);
  });

  it("accepts the sanitized form of the same selection", () => {
    const child = spawn("/bin/echo", [sanitizePdfSelectionText(`x${NUL}y`)]);
    expect(child.pid).toBeGreaterThan(0);
    child.kill();
  });
});
