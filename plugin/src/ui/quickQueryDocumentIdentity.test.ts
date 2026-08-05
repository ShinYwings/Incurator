import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { join } from "path";

/**
 * v0.42.2 regression (Arena Gate G0, plugin Pass-A F1 [P1]).
 *
 * `fetchActivePdfPage(pageNum, expectedDocumentId?)` guards document identity
 * ONLY when an expected id is supplied:
 *
 *   if (expectedDocumentId !== undefined && pinnedDocumentId !== expectedDocumentId)
 *     return undefined;
 *
 * The local PDF tool runner opts in (`main.ts`). Quick Query did not — it called
 * `fetchActivePdfPage(pageNum)` with one argument. Cross-reference resolution
 * issues several SEQUENTIAL backend round-trips (~0.2 s each, measured), so a
 * tab switch mid-flight let later fetches read pages out of the newly active
 * PDF and splice them into the answer.
 *
 * Worse: the resolver writes every fetched page back into the index under the
 * `searchDocumentId` it was given, so foreign page text contaminated the
 * ORIGINAL document's BM25 index and affected later queries too.
 */
const popoverSource = () =>
  readFileSync(join(__dirname, "quickQueryPopover.ts"), "utf8");
const mainSource = () =>
  readFileSync(join(__dirname, "..", "..", "main.ts"), "utf8");

describe("Quick Query pins the PDF document identity", () => {
  it("passes an expected document id to every page fetch", () => {
    const src = popoverSource();
    // The one-argument form is the bug.
    expect(src).not.toMatch(/fetchActivePdfPage\(pageNum\)\s*$/m);
    expect(src).toContain("this.plugin.fetchActivePdfPage(pageNum, pinnedDocumentId)");
  });

  it("reads the identity once, before the first await", () => {
    const src = popoverSource();
    expect(src).toContain(
      "const pinnedDocumentId = this.plugin.getActivePdfDocumentId();"
    );
    // The index we write into must be the SAME identity we fetch against,
    // otherwise foreign text still lands under this document's id.
    expect(src).toContain("searchDocumentId: pinnedDocumentId,");
    expect(src).not.toContain(
      "searchDocumentId: this.plugin.getActivePdfDocumentId(),"
    );
  });

  it("keeps the guard opt-in contract it relies on", () => {
    // If this ever becomes unconditional the popover's fix is redundant, not
    // wrong — but the assertion documents why the argument is required today.
    const src = mainSource();
    expect(src).toContain(
      "if (expectedDocumentId !== undefined && pinnedDocumentId !== expectedDocumentId)"
    );
  });

  it("matches how the local PDF tool runner already opts in", () => {
    const src = mainSource();
    expect(src).toContain(
      "this.fetchActivePdfPage(pageNum, this.getActivePdfDocumentId())"
    );
  });
});
