import { describe, expect, it, vi } from "vitest";
import {
  resolveSelectionReferences,
  resolveSelectionReferencesAsync,
  resolveSelectionReferencesBlock,
  resolveSelectionReferencesBlockAsync,
  resolveSelectionContextAsync,
} from "./pdfReferenceContext";
import { forgetBibliography } from "./citationContext";
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
  it("fetches the next page for a latest-user Korean equation reference", async () => {
    const fetch = vi.fn().mockImplementation(async (pn: number) => {
      if (pn === 6) {
        return [
          "Two possible solutions (A and B) exist for the rotation and skew-symmetric matrix estimates.",
          "==> equation image intentionally omitted <==",
          "The ±1 term in Eq. (10) denotes either 1 or −1 on the diagonal so that both rotation determinants equal 1.",
        ].join("\n");
      }
      return undefined;
    });

    const block = await resolveSelectionReferencesBlockAsync(
      "수식 (10)이 본문이랑 완전 다른데?",
      {
        windowPages: [
          page(5, "Previous derivation\nL_{recon} = ||x - \\hat{x}||^2 \\quad (9)"),
          page(6, "Appendix continuation — page header only"),
        ],
        pageNum: 5,
        pageCount: 20,
        outline: [],
      },
      fetch
    );

    expect(fetch.mock.calls.map(([pn]) => pn)).toEqual([6]);
    expect(block).toContain('label="Equation 10"');
    expect(block).toContain('target_page="6"');
    expect(block).toContain("±1 term in Eq. (10)");
  });

  it("declares the miss, injecting no content, when the adjacent scan finds no exact label", async () => {
    const fetch = vi.fn().mockImplementation(async (pageNum: number) => {
      const adjacentText = new Map([
        [6, "The next page discusses equation systems with 10 unknowns."],
        [4, "Earlier numerical results include 10 observations."],
        [7, "The equation discussion continues with generic prose and 10 cases."],
        [3, "Background material lists 10 variables."],
      ]);
      return adjacentText.get(pageNum);
    });

    const block = await resolveSelectionReferencesBlockAsync(
      "수식 (10)을 설명해줘",
      {
        windowPages: [
          page(5, "The equation system has 10 unknowns, but no numbered equation label is present."),
        ],
        pageNum: 5,
        pageCount: 20,
        outline: [],
      },
      fetch
    );

    expect(fetch.mock.calls.map(([pageNum]) => pageNum)).toEqual([6, 4, 7, 3]);
    // Still no content: none of the probed pages carries an exact label, so
    // nothing misleading is injected. The miss is named rather than dropped —
    // silence is what let the provider reach for a tool it could not use.
    expect(block).not.toContain("<resolved_cross_references>");
    expect(block).toContain("<unresolved_cross_references");
    expect(block).toContain('label="Equation 10"');
    expect(block).not.toContain("10 unknowns");
  });

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

  it("resolves the v0.40.3 report case: printed p581 maps via window headers, never fetching physical 581", async () => {
    // Reproduces the exact user failure: physical 276 shows printed 258
    // (offset +18). Printed 581 lives at physical 599; physical 581 is
    // Appendix A1 (tensor notation) and must never be fetched or injected.
    const fetch = vi.fn().mockImplementation(async (pn: number) => {
      if (pn === 599) {
        return "581\nA4.1 Skew-symmetric matrices\nResult A4.1. A general 3 x 3 skew-symmetric matrix S may be written as S = kUZU^T where U is orthogonal.";
      }
      if (pn === 581) {
        return "563 A1 Tensor notation\nEinstein summation and index apparatus.";
      }
      return undefined;
    });

    const block = await resolveSelectionReferencesBlockAsync(
      "From Result A4.1-(p581), which gives a block decomposition of a general skew-symmetric matrix",
      {
        windowPages: [
          page(274, "256 9 Epipolar Geometry and the Fundamental Matrix\nfundamental and essential matrices"),
          page(275, "9.6 Extraction of cameras from the essential matrix 257\nproperties of the essential matrix"),
          page(276, "258 9 Epipolar Geometry and the Fundamental Matrix\nProof. From Result A4.1-(p581), which gives a block decomposition."),
        ],
        pageNum: 276,
        pageCount: 673,
        outline: [],
      },
      fetch
    );

    expect(fetch.mock.calls.map(([pn]) => pn)).toEqual([599]);
    expect(block).toContain('target_page="599"');
    expect(block).toContain("skew-symmetric matrix S may be written");
    expect(block).not.toContain("Tensor notation");
  });

  it("recovers via identity probe + header repair when the window has no printed headers", async () => {
    const fetch = vi.fn().mockImplementation(async (pn: number) => {
      if (pn === 581) {
        return "563 A1 Tensor notation\nEinstein summation and index apparatus.";
      }
      if (pn === 599) {
        return "581\nA4.1 Skew-symmetric matrices\nResult A4.1. A general skew-symmetric matrix S may be written as S = kUZU^T.";
      }
      return undefined;
    });

    const block = await resolveSelectionReferencesBlockAsync(
      "From Result A4.1-(p581), which gives a block decomposition",
      {
        windowPages: [
          page(276, "Proof without any printed header on this text layer.\nFrom Result A4.1-(p581), which gives a block decomposition of S"),
        ],
        pageNum: 276,
        pageCount: 673,
        outline: [],
      },
      fetch
    );

    // Round 1 probes the identity guess (581); its header (563) contradicts,
    // yielding the +18 repair target 599, which verifies by its own header.
    expect(fetch.mock.calls.map(([pn]) => pn)).toEqual([581, 599]);
    expect(block).toContain('target_page="599"');
    expect(block).toContain("skew-symmetric matrix S may be written");
    expect(block).not.toContain("Tensor notation");
  });

  it("fails closed instead of injecting a contradicted identity page", async () => {
    const fetch = vi.fn().mockImplementation(async (pn: number) => {
      if (pn === 581) {
        return "563 A1 Tensor notation\nEinstein summation and index apparatus.";
      }
      return undefined;
    });

    const block = await resolveSelectionReferencesBlockAsync(
      "see p581 for the decomposition",
      {
        windowPages: [page(276, "Prose without printed headers.")],
        pageNum: 276,
        pageCount: 673,
        outline: [],
      },
      fetch
    );

    expect(block).not.toContain('target_page="581"');
    expect(block).not.toContain("Tensor notation");
  });

  it("resolves a bare theorem anchor through the aliased appendix outline range", async () => {
    const fetch = vi.fn().mockImplementation(async (pn: number) => {
      if (pn === 619) {
        return "585 A4.1 Skew-symmetric matrices\nResult A4.1. A general skew-symmetric matrix may be written as S = kUZU^T.";
      }
      return undefined;
    });

    const block = await resolveSelectionReferencesBlockAsync(
      "Result A4.1",
      {
        windowPages: [page(527, "As shown, Result A4.1 gives the decomposition.")],
        pageNum: 527,
        pageCount: 660,
        outline: [
          { title: "4 Estimation", pageNum: 130, level: 0 },
          { title: "Appendix 4 Matrix Properties and Decompositions", pageNum: 617, level: 0 },
          { title: "Appendix 5 Least-squares Minimization", pageNum: 630, level: 0 },
        ],
      },
      fetch
    );

    const fetchedPages = fetch.mock.calls.map(([pn]) => pn);
    expect(fetchedPages).toContain(619);
    expect(fetchedPages).not.toContain(623);
    expect(block).toContain('target_page="619"');
    expect(block).toContain("skew-symmetric matrix may be written");
  });

  it("does not spawn repair fetches from a consumed-but-confirmed identity page", async () => {
    // Hint transfer marks a page ref "unresolved" when a nearby theorem ref
    // consumes its target (dedup) — that is NOT a contradiction. A page whose
    // own header confirms the locator (380) must not turn incidental digits
    // ("See note 12") into repair fetches (380 + (380-12) = 748).
    const fetch = vi.fn().mockImplementation(async (pn: number) => {
      if (pn === 380) {
        return "380 The chapter continues with unrelated prose\nSee note 12";
      }
      return `page ${pn} content`;
    });

    const block = await resolveSelectionReferencesBlockAsync(
      "see Corollary 9.1 (p380)",
      {
        windowPages: [page(50, "reading page without printed headers")],
        pageNum: 50,
        pageCount: 800,
        outline: [],
      },
      fetch
    );

    expect(fetch.mock.calls.map(([pn]) => pn)).toEqual([380]);
    expect(block).toContain('target_page="380"');
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

/**
 * The funnel itself (v0.56.0).
 *
 * Both the popover and the chat sidebar reach citations and provenance only
 * through this function. The pure modules are unit-tested in isolation, which
 * says nothing about whether the wiring here actually joins them: a wrong
 * separator, a dropped block, or a `source` shape mismatch leaves every unit
 * test green and the feature dead.
 */
describe("resolveSelectionContextAsync — citations and provenance join the block", () => {
  const BIB = "References\n[8] A. Author. The cited work. In CVPR, 2023.";

  function source(documentId: string) {
    return {
      windowPages: [page(1, "we build on [8] for this stage")],
      pageNum: 1,
      pageCount: 12,
      searchDocumentId: documentId,
    };
  }

  it("merges a citations block into the returned prompt block", async () => {
    forgetBibliography("doc-join");
    const { block } = await resolveSelectionContextAsync(
      "we build on [8]",
      source("doc-join"),
      async (pageNum) => (pageNum >= 10 ? BIB : "body")
    );
    expect(block).toContain("<resolved_citations");
    expect(block).toContain("The cited work");
  });

  it("returns provenance built from the same resolution, not from the block", async () => {
    forgetBibliography("doc-prov");
    const { provenance } = await resolveSelectionContextAsync(
      "we build on [8]",
      source("doc-prov"),
      async (pageNum) => (pageNum >= 10 ? BIB : "body")
    );
    expect(provenance.items.map((i) => i.label)).toContain("[8]");
    expect(provenance.items.find((i) => i.label === "[8]")?.origin).toBe("bibliography");
  });

  it("emits no citations block when nothing resolved, leaving the prompt clean", async () => {
    forgetBibliography("doc-none");
    const { block, provenance } = await resolveSelectionContextAsync(
      "ordinary prose with no citation",
      source("doc-none"),
      async () => BIB
    );
    expect(block).not.toContain("<resolved_citations");
    expect(provenance.items).toEqual([]);
  });

  it("resolves citations from documentKey when there is no search index", async () => {
    // The chat sidebar builds no BM25 index, so it has no searchDocumentId.
    // Keying the bibliography cache on that alone made citation resolution a
    // silent no-op on that entire surface.
    forgetBibliography("hash-abc");
    const { block } = await resolveSelectionContextAsync(
      "we build on [8]",
      {
        windowPages: [page(1, "we build on [8]")],
        pageNum: 1,
        pageCount: 12,
        documentKey: "hash-abc",
      },
      async (pageNum) => (pageNum >= 10 ? BIB : "body")
    );
    expect(block).toContain("<resolved_citations");
  });

  it("skips citations when the caller supplied no document identity", async () => {
    // Without searchDocumentId there is no cache key, so citations are skipped
    // rather than cached under a shared bucket where one document's
    // bibliography would be served for another.
    const fetch = vi.fn(async () => BIB);
    const { block } = await resolveSelectionContextAsync(
      "we build on [8]",
      { windowPages: [page(1, "x")], pageNum: 1, pageCount: 12 },
      fetch
    );
    expect(block).not.toContain("<resolved_citations");
  });

  it("the string wrapper still returns exactly the block", async () => {
    forgetBibliography("doc-wrap");
    const args = [
      "we build on [8]",
      source("doc-wrap"),
      async (pageNum: number) => (pageNum >= 10 ? BIB : "body"),
    ] as const;
    const viaWrapper = await resolveSelectionReferencesBlockAsync(...args);
    forgetBibliography("doc-wrap");
    const { block } = await resolveSelectionContextAsync(...args);
    expect(viaWrapper).toBe(block);
  });
});
