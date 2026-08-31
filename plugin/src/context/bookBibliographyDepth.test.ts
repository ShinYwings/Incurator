import { describe, expect, it, vi } from "vitest";
import { resolveSelectionCitations } from "./citationContext";

/**
 * A book puts its index AFTER its bibliography.
 *
 * The tail scan was a flat six pages, which is right for a paper — references
 * are the last thing in one. A book's back matter routinely runs twenty pages or
 * more past the bibliography, so six never reached the heading and a reference
 * lookup returned nothing on exactly the document kind where doing it by hand is
 * most tedious.
 */
describe("finding a bibliography in a long book", () => {
  const PAGES = 400;
  const BIB_PAGE = 370; // 30 pages of index follow it

  function book() {
    return vi.fn(async (pageNum: number) => {
      if (pageNum === BIB_PAGE) {
        return "References\n[1] Kalman. A New Approach to Linear Filtering.\n[2] Thrun et al. Probabilistic Robotics.";
      }
      if (pageNum > BIB_PAGE) return `Index\nabsorption, ${pageNum}\nacceleration, ${pageNum}`;
      return `Chapter text on page ${pageNum}.`;
    });
  }

  it("reaches a bibliography that the index pushed away from the end", async () => {
    const citations = await resolveSelectionCitations(
      "",
      { documentId: "book-1", pageCount: PAGES },
      book(),
      "what is reference 1?"
    );
    expect(citations.map((c) => c.entry).join("\n")).toContain("Kalman");
  });

  it("does not turn one question into an unbounded scan", async () => {
    const fetch = book();
    await resolveSelectionCitations(
      "",
      { documentId: "book-2", pageCount: 900 },
      fetch,
      "reference 1?"
    );
    // Bounded at 40 back plus the continuation window, not 900.
    expect(fetch.mock.calls.length).toBeLessThanOrEqual(45);
  });

  it("still scans only a few pages for an ordinary paper", async () => {
    const fetch = vi.fn(async () => "no bibliography here");
    await resolveSelectionCitations(
      "",
      { documentId: "paper-1", pageCount: 12 },
      fetch,
      "reference 1?"
    );
    expect(fetch.mock.calls.length).toBeLessThanOrEqual(8);
  });
});
