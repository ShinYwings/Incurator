import { describe, it, expect, vi } from "vitest";
import { resolveSelectionReferencesAsync } from "./pdfReferenceContext";

/**
 * Reading page 1 of a long paper and asking about equation (24) on page 27.
 *
 * The adjacent probe only reaches currentPage +/-2, so page 27 was never
 * fetched, the reference failed closed, and the provider was left to locate the
 * page with its own tool call. A headless CLI provider cannot prompt for tool
 * permission, so it returned nothing at all:
 *
 *   "no output produced — a tool required the 'command' permission that
 *    headless mode cannot prompt for, so it was auto-denied"
 */

// How a PDF actually renders a numbered display equation: the math on the
// line, the label at the right margin.
const PAGE_27 = [
  "where the Plucker line is defined by two points, and",
  "    P_0 = v_1 \\times v_2                                    (24)",
  "gives the colinearity constraint used in Section 5.",
].join("\n");

function source() {
  return {
    outline: [],
    windowPages: [{ pageNum: 1, text: "Introduction. We revisit line mapping." }],
    pageNum: 1,
    pageCount: 30,
  };
}

describe("distant equation references", () => {
  it("resolves an equation dozens of pages away via the document-wide locator", async () => {
    const fetched: number[] = [];
    const fetchPageText = vi.fn(async (pageNum: number) => {
      fetched.push(pageNum);
      return pageNum === 27 ? PAGE_27 : `filler page ${pageNum}`;
    });
    const locatePages = vi.fn(async () => [27]);

    const resolved = await resolveSelectionReferencesAsync(
      "수식 (24)에서 P_0는 3d point여야 colinearity 알 수 있지 않아?",
      source(),
      fetchPageText,
      locatePages
    );

    expect(locatePages).toHaveBeenCalled();
    expect(fetched).toContain(27);
    const eq = resolved.find((r) => r.query.kind === "equation");
    expect(eq?.method).not.toBe("unresolved");
  });

  it("still fails closed when no locator is supplied", async () => {
    // Callers without a backend keep the previous behaviour rather than
    // receiving a resolved-looking reference with no content.
    const fetchPageText = vi.fn(async (pageNum: number) => `filler page ${pageNum}`);

    const resolved = await resolveSelectionReferencesAsync(
      "수식 (24)에서 P_0는 3d point여야 하지 않아?",
      source(),
      fetchPageText
    );

    const eq = resolved.find((r) => r.query.kind === "equation");
    expect(eq?.method).toBe("unresolved");
  });

  it("does not call the locator when the adjacent probe already found it", async () => {
    // The cheap path must stay cheap: no extra backend search for an equation
    // that is one page away.
    const fetchPageText = vi.fn(async (pageNum: number) =>
      pageNum === 2 ? "    x = A b                (24)" : `filler ${pageNum}`
    );
    const locatePages = vi.fn(async () => [27]);

    await resolveSelectionReferencesAsync(
      "equation (24) 설명해줘",
      source(),
      fetchPageText,
      locatePages
    );

    expect(locatePages).not.toHaveBeenCalled();
  });

  it("survives a locator that throws", async () => {
    const fetchPageText = vi.fn(async (pageNum: number) => `filler ${pageNum}`);
    const locatePages = vi.fn(async () => {
      throw new Error("backend down");
    });

    const resolved = await resolveSelectionReferencesAsync(
      "수식 (24)", source(), fetchPageText, locatePages
    );

    const eq = resolved.find((r) => r.query.kind === "equation");
    expect(eq?.method).toBe("unresolved");
  });

  it("bounds how many located pages it will fetch", async () => {
    const fetched: number[] = [];
    const fetchPageText = vi.fn(async (pageNum: number) => {
      fetched.push(pageNum);
      return `no equation here, page ${pageNum}`;
    });
    // A bad hit list must not turn one question into dozens of page fetches.
    const locatePages = vi.fn(async () => [11, 12, 13, 14, 15, 16, 17, 18]);

    await resolveSelectionReferencesAsync(
      "수식 (24)", source(), fetchPageText, locatePages
    );

    const fromLocator = fetched.filter((p) => p >= 11 && p <= 18);
    expect(fromLocator.length).toBeLessThanOrEqual(3);
  });
});
