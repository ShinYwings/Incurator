import { describe, expect, it } from "vitest";
import { spawn } from "node:child_process";
import {
  countUnmappedGlyphs,
  hasUnmappedGlyphs,
  isUnreadableSelection,
  sanitizePdfSelectionText,
} from "./pdfSelectionText";

const NUL = String.fromCharCode(0);

/**
 * The real text layer pdf.js produces for equation (3) of "3D Line Mapping
 * Revisited", page 4 — measured, not invented. Its CMMI10 subset carries no
 * /ToUnicode, so every lambda arrives as U+0000.
 */
const EQUATION_3 =
  `${NUL} = (${NUL} 1, ${NUL} 2) with a single constraint: ` +
  `min ${NUL} 2 R 2 ${NUL} T A ${NUL} + b T ${NUL}, ` +
  `s.t. ${NUL} T Q ${NUL} + q T ${NUL} = 0. (3)`;

describe("countUnmappedGlyphs", () => {
  it("counts every glyph the PDF could not map", () => {
    expect(countUnmappedGlyphs(EQUATION_3)).toBe(10);
  });

  it("is zero for a clean prose selection", () => {
    expect(countUnmappedGlyphs("Due to the low-dimensionality of the problem")).toBe(0);
  });

  it("does not count ordinary Unicode maths as unmapped", () => {
    expect(countUnmappedGlyphs("λ ∈ ℝ², Σ, ∇²")).toBe(0);
  });

  it("handles an empty selection", () => {
    expect(countUnmappedGlyphs("")).toBe(0);
  });
});

describe("hasUnmappedGlyphs", () => {
  it("flags the measured equation selection", () => {
    expect(hasUnmappedGlyphs(EQUATION_3)).toBe(true);
  });

  it("does not flag prose", () => {
    expect(hasUnmappedGlyphs("Cheirality tests are applied to all proposals")).toBe(false);
  });
});

describe("sanitizePdfSelectionText", () => {
  it("removes ONLY the code point spawn rejects", () => {
    expect(sanitizePdfSelectionText(`x${NUL}^2`)).toBe("x^2");
  });

  it("keeps other C0 controls, DEL, and C1 — none of them break spawn", () => {
    const text = `abcd`;
    expect(sanitizePdfSelectionText(text)).toBe(text);
  });

  it("preserves tabs and newlines", () => {
    expect(sanitizePdfSelectionText("a\tb\nc")).toBe("a\tb\nc");
  });

  it("preserves Unicode maths, Greek, and CJK verbatim", () => {
    const text = "λ₁ ≤ Σ ∇², 고유값, ∫₀^∞";
    expect(sanitizePdfSelectionText(text)).toBe(text);
  });

  it("preserves combining marks", () => {
    const nfd = "Plücker";
    expect(sanitizePdfSelectionText(nfd)).toBe(nfd);
  });

  it("trims surrounding whitespace", () => {
    expect(sanitizePdfSelectionText("  $x$  ")).toBe("$x$");
  });

  it("handles an empty input", () => {
    expect(sanitizePdfSelectionText("")).toBe("");
  });
});

describe("the regression this exists to prevent", () => {
  it("stripping the equation's unmapped glyphs destroys every lambda", () => {
    // This is what v0.52.1 sent to the model, and why a wrong equation landed
    // on the clipboard looking plausible. The assertion documents the damage;
    // the fix is that this string is never sent — the crop is sent instead.
    const stripped = sanitizePdfSelectionText(EQUATION_3);
    expect(stripped).not.toContain("λ");
    expect(stripped).toContain("T A");
    expect(hasUnmappedGlyphs(EQUATION_3)).toBe(true);
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

describe("the spawn boundary", () => {
  it("throws synchronously on a NUL byte in an argv entry", () => {
    expect(() => spawn("/bin/echo", [`x${NUL}y`])).toThrow(/null bytes/);
  });

  it("accepts other control characters, so stripping them was never needed", () => {
    const child = spawn("/bin/echo", ["abcd"]);
    expect(child.pid).toBeGreaterThan(0);
    child.kill();
  });
});
