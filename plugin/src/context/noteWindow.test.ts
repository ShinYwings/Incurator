import { describe, expect, it } from "vitest";
import { selectNoteWindow } from "./noteWindow";

/**
 * A long note is truncated to fit. WHERE it truncates decides whether the reader
 * gets an answer.
 *
 * The active note was cut at the first 6,000 characters. On a short note that is
 * the whole file and nothing is lost. On a research note the reader has been
 * adding to for a year, it means everything they wrote after the opening is
 * simply absent — and a question about the middle is answered from the top, or
 * not at all.
 *
 * Same defect shape as the book outline that showed page 1 to a reader on page
 * 400: truncation from the head is wrong whenever the reader is not at the head.
 */
const NOTE = [
  "# Radiance fields",
  "Opening notes on the general area.",
  "",
  "## NeRF",
  "Volume rendering through a coordinate MLP. Slow to train.",
  "",
  "## Gaussian Splatting",
  "Rasterises anisotropic Gaussians. The tile-based rasteriser is the reason it is fast.",
  "",
  "## Open questions",
  "Whether specular highlights need per-Gaussian view dependence.",
].join("\n");

const LONG = `${"filler line\n".repeat(2000)}\n## Buried section\nThe answer about tile-based rasterisation lives here.\n${"more filler\n".repeat(2000)}`;

describe("choosing which part of a long note to carry", () => {
  it("returns the whole note when it fits", () => {
    expect(selectNoteWindow(NOTE, { budget: 100_000 })).toBe(NOTE);
  });

  it("keeps the section the question is about, not just the opening", () => {
    const out = selectNoteWindow(LONG, {
      budget: 600,
      question: "what did I write about tile-based rasterisation?",
    });
    expect(out).toContain("tile-based rasterisation lives here");
  });

  it("keeps the section the reader selected from", () => {
    const out = selectNoteWindow(LONG, {
      budget: 600,
      selection: "The answer about tile-based rasterisation",
    });
    expect(out).toContain("Buried section");
  });

  it("stays within budget", () => {
    const out = selectNoteWindow(LONG, { budget: 600, question: "rasterisation" });
    expect(out.length).toBeLessThanOrEqual(900); // budget plus the elision markers
  });

  it("says where it cut, so the model does not read a gap as the end", () => {
    const out = selectNoteWindow(LONG, { budget: 600, question: "rasterisation" });
    expect(out).toContain("omitted");
  });

  it("falls back to the head when nothing matches", () => {
    const out = selectNoteWindow(LONG, { budget: 400, question: "quantum chromodynamics" });
    expect(out.length).toBeGreaterThan(0);
    expect(out).toContain("filler");
  });

  it("keeps document order", () => {
    const out = selectNoteWindow(NOTE, {
      budget: 200,
      question: "open questions about Gaussian Splatting",
    });
    const gs = out.indexOf("Gaussian Splatting");
    const oq = out.indexOf("Open questions");
    if (gs !== -1 && oq !== -1) expect(gs).toBeLessThan(oq);
  });
});
