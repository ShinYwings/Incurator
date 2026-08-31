import { describe, expect, it } from "vitest";
import { contextPriorityInstruction } from "./chatContextPriority";

/**
 * Instruction about blocks the turn cannot contain is dilution, not safety.
 *
 * The POINTER SELECTIONS paragraph names `<resolved_cross_references>`,
 * `<resolved_citations>` and `read_pdf_page_image`. On a markdown-note turn none
 * of those exist — every resolver that produces them is gated on an open PDF —
 * yet it rode on every note turn regardless.
 *
 * v0.54.1 removed a universal rule for exactly this reason: a paragraph naming
 * strings that never appear crowds out the instructions that do apply, and
 * naming a tool primes the model to reach for it. This release has already paid
 * for that once, when a promised page-fetch tool sent the model to a URL reader
 * it was not allowed to use.
 */
describe("the pointer instruction matches the document in hand", () => {
  it("tells a PDF turn about the blocks a PDF turn actually gets", () => {
    const pdf = contextPriorityInstruction(true, "pdf");
    expect(pdf).toContain("resolved_cross_references");
    expect(pdf).toContain("read_pdf_page_image");
  });

  it("does not name PDF-only blocks on a markdown turn", () => {
    const md = contextPriorityInstruction(true, "markdown");
    expect(md).not.toContain("read_pdf_page_image");
    expect(md).not.toContain("resolved_cross_references");
    expect(md).not.toContain("unresolved_cross_references");
  });

  it("tells a markdown turn about the pointer it does have", () => {
    expect(contextPriorityInstruction(true, "markdown")).toContain(
      "resolved_wikilinks"
    );
  });

  it("says nothing about pointers when there is no document", () => {
    const none = contextPriorityInstruction(true, "none");
    expect(none).not.toContain("POINTER SELECTIONS");
  });

  it("keeps the primary-focus rule on every kind, because it always applies", () => {
    for (const kind of ["pdf", "markdown", "none"] as const) {
      expect(contextPriorityInstruction(true, kind), kind).toContain(
        "primary_focus_selection"
      );
    }
  });

  it("makes a markdown turn materially shorter than a PDF turn", () => {
    const pdf = contextPriorityInstruction(true, "pdf").length;
    const md = contextPriorityInstruction(true, "markdown").length;
    expect(pdf - md).toBeGreaterThan(1000);
  });
});
