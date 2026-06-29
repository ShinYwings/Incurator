import { describe, expect, it, vi } from "vitest";
import {
  resolveSelectionReferences,
  resolveSelectionReferencesAsync,
  resolveSelectionReferencesBlock,
  resolveSelectionReferencesBlockAsync,
} from "./pdfReferenceContext";
import { PdfDocumentIndexService } from "./pdfDocumentIndex";
import type { PdfWindowPage } from "../types";

// ── helpers ──────────────────────────────────────────────────────────────────

function page(pageNum: number, text: string): PdfWindowPage {
  return { pageNum, text };
}

// ── sync resolver ─────────────────────────────────────────────────────────────

describe("resolveSelectionReferences", () => {
  it("returns [] when text has no references", () => {
    const result = resolveSelectionReferences("plain sentence with no refs", {
      windowPages: [page(1, "some text")],
    });
    expect(result).toHaveLength(0);
  });

  it("uses passed searchIndex instead of building a fresh one from windowPages", () => {
    const fullIndex = new PdfDocumentIndexService();
    // Page 50 is in the full index (seen earlier), but NOT in windowPages
    fullIndex.upsertDocument("doc", [page(50, "Equation 3.1 energy balance formula"), page(1, "intro")]);
    const result = resolveSelectionReferences("see Eq. 3.1 for details", {
      windowPages: [page(1, "intro")],
      pageNum: 1,
      searchIndex: fullIndex,
      searchDocumentId: "doc",
    });
    const eq = result.find((r) => r.query.kind === "equation");
    expect(eq).toBeDefined();
    // Should have found page 50 via the full index
    expect(eq?.targetPage).toBe(50);
  });

  it("returns empty resolved block when no references resolve", () => {
    const block = resolveSelectionReferencesBlock("no refs here", {
      windowPages: [page(1, "text")],
    });
    expect(block).toBe("");
  });
});

// ── async resolver ────────────────────────────────────────────────────────────

describe("resolveSelectionReferencesAsync", () => {
  it("resolves equation ref from outline (no fetch needed)", async () => {
    const fetch = vi.fn().mockResolvedValue(undefined);
    const result = await resolveSelectionReferencesAsync(
      "See Eq. 2.1 below",
      {
        windowPages: [page(10, "Equation 2.1 describes the formula")],
        pageNum: 10,
        outline: [],
      },
      fetch
    );
    expect(result.length).toBeGreaterThan(0);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("fetches missing page text when target page is resolved but text is absent", async () => {
    // Pass 1: BM25 on the full index finds page 42, but its text is not in windowPages/pageTextMap.
    // The async resolver should call fetchPageText(42) and re-resolve with the fetched text.
    const fullIndex = new PdfDocumentIndexService();
    fullIndex.upsertDocument("doc", [
      page(42, "Equation 7.3 wave function collapse"),
      page(1, "introduction"),
    ]);

    const fetchedText = "Equation 7.3 wave function collapse — full text on page 42";
    const fetch = vi.fn().mockImplementation(async (pn: number) => {
      if (pn === 42) return fetchedText;
      return undefined;
    });

    const result = await resolveSelectionReferencesAsync(
      "as shown in Eq. (7.3)",
      {
        windowPages: [page(1, "introduction")],
        pageNum: 1,
        searchIndex: fullIndex,
        searchDocumentId: "doc",
      },
      fetch
    );

    const eq = result.find((r) => r.query.kind === "equation");
    expect(eq?.targetPage).toBe(42);
    // After fetch, snippet should contain the fetched text
    expect(eq?.snippet).toContain("wave function");
    expect(fetch).toHaveBeenCalledWith(42);
  });

  it("fetches a distant explicit page locator for an unresolved section pointer", async () => {
    const fetch = vi.fn().mockImplementation(async (pn: number) => {
      if (pn === 281) {
        return "Section 11.1.2 Seven point correspondences. The fundamental matrix is computed from seven point pairs.";
      }
      return undefined;
    });

    const block = await resolveSelectionReferencesBlockAsync(
      "참조 대상(Section 11.1.2, p281)",
      {
        windowPages: [page(527, "This page points back to Section 11.1.2, p281.")],
        pageNum: 527,
        pageCount: 700,
        outline: [],
      },
      fetch
    );

    expect(fetch).toHaveBeenCalledWith(281);
    expect(block).toContain('label="Section 11.1.2"');
    expect(block).toContain('target_page="281"');
    expect(block).toContain("seven point pairs");
  });

  it("fetches an outline-bounded range to resolve a distant bare equation label", async () => {
    const fetch = vi.fn().mockImplementation(async (pn: number) => {
      if (pn === 112) {
        return "Seven-point algorithm\nx'^{T} F x = 0 \\quad (3.5)\nThe reduced fundamental matrix follows.";
      }
      return undefined;
    });

    const block = await resolveSelectionReferencesBlockAsync(
      "(3.5)",
      {
        windowPages: [page(527, "This later page refers only to equation (3.5).")],
        pageNum: 527,
        pageCount: 700,
        outline: [
          { title: "3 Projective Geometry and Transformations", pageNum: 100, level: 0 },
          { title: "4 Estimation", pageNum: 130, level: 0 },
        ],
      },
      fetch
    );

    expect(fetch).toHaveBeenCalledWith(112);
    expect(block).toContain('label="Equation 3.5"');
    expect(block).toContain('target_page="112"');
    expect(block).toContain("reduced fundamental matrix");
  });

  it("uses the exact ToC section before falling back to the whole chapter", async () => {
    const fetch = vi.fn().mockImplementation(async (pn: number) => {
      if (pn === 112) {
        return "Section 3.5\nx'^{T} F x = 0 \\quad (3.5)";
      }
      return undefined;
    });

    const block = await resolveSelectionReferencesBlockAsync(
      "(3.5)",
      {
        windowPages: [page(527, "This later page refers only to equation (3.5).")],
        pageNum: 527,
        pageCount: 700,
        outline: [
          { title: "3 Projective Geometry and Transformations", pageNum: 100, level: 0 },
          { title: "3.5 The fundamental matrix", pageNum: 112, level: 1 },
          { title: "3.6 Estimating F", pageNum: 115, level: 1 },
          { title: "4 Estimation", pageNum: 130, level: 0 },
        ],
      },
      fetch
    );

    const fetchedPages = fetch.mock.calls.map(([pn]) => pn);
    expect(fetchedPages).toEqual([112, 113, 114]);
    expect(fetchedPages).not.toContain(100);
    expect(block).toContain('target_page="112"');
  });

  it("does not call fetch when snippet is already present in windowPages", async () => {
    const fetch = vi.fn().mockResolvedValue(undefined);
    const result = await resolveSelectionReferencesAsync(
      "Eq. (5.1) is shown here",
      {
        windowPages: [page(5, "Equation 5.1 kinetic energy definition")],
        pageNum: 5,
      },
      fetch
    );
    const eq = result.find((r) => r.query.kind === "equation");
    expect(eq?.targetPage).toBe(5);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("fetches multiple missing pages in parallel", async () => {
    const fullIndex = new PdfDocumentIndexService();
    fullIndex.upsertDocument("doc", [
      page(10, "Figure 1.1 architecture diagram"),
      page(20, "Table 2.1 performance results"),
      page(1, "intro"),
    ]);

    const fetch = vi.fn().mockImplementation(async (pn: number) => {
      return `page ${pn} full content`;
    });

    await resolveSelectionReferencesAsync(
      "see Figure 1.1 and Table 2.1",
      {
        windowPages: [page(1, "intro")],
        pageNum: 1,
        searchIndex: fullIndex,
        searchDocumentId: "doc",
      },
      fetch
    );

    // Both pages should have been fetched (pages 10 and 20 are in the index but not in windowPages)
    const fetchedPages = fetch.mock.calls.map(([pn]) => pn).sort();
    expect(fetchedPages).toEqual(expect.arrayContaining([10, 20]));
  });

  it("returns empty array when selectedText has no references", async () => {
    const fetch = vi.fn();
    const result = await resolveSelectionReferencesAsync("plain text", { windowPages: [] }, fetch);
    expect(result).toHaveLength(0);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("resolveSelectionReferencesBlockAsync returns empty string when nothing resolves", async () => {
    const fetch = vi.fn().mockResolvedValue(undefined);
    const block = await resolveSelectionReferencesBlockAsync("no refs here", undefined, fetch);
    expect(block).toBe("");
  });
});
