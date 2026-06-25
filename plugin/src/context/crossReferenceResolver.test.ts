import { describe, expect, it } from "vitest";
import {
  extractReferences,
  resolveReferences,
  resolveObjectOwningSection,
  buildCaptionIndex,
  type ResolveContext,
} from "./crossReferenceResolver";
import type { PdfOutlineItem, PdfRagHit } from "../types";

describe("extractReferences", () => {
  it("detects a glued section + page pointer (real report string)", () => {
    // From the report: cmd+shift+L drag of this exact (hyphen-broken) span.
    const refs = extractReferences(
      "see section A4.2(p580) for Jacobi's al-gorithm for this"
    );
    const section = refs.find((r) => r.kind === "section");
    const page = refs.find((r) => r.kind === "page");
    expect(section?.sectionNumber).toBe("A4.2");
    expect(page?.printedPage).toBe(580);
  });

  it("detects spaced section + page pointer", () => {
    const refs = extractReferences(
      "see section A4.2 (p580) for Jacobi's algorithm"
    );
    expect(refs.find((r) => r.kind === "section")?.sectionNumber).toBe("A4.2");
    expect(refs.find((r) => r.kind === "page")?.printedPage).toBe(580);
  });

  it("detects figures, equations, tables, and theorem-likes", () => {
    expect(extractReferences("Figure 19.1")[0]).toMatchObject({
      kind: "figure",
      objectNumber: "19.1",
    });
    expect(extractReferences("Eq. (19.6)")[0]).toMatchObject({
      kind: "equation",
      objectNumber: "19.6",
    });
    expect(extractReferences("see Table 3 for results")[0]).toMatchObject({
      kind: "table",
      objectNumber: "3",
    });
    expect(extractReferences("by Theorem 2")[0]).toMatchObject({
      kind: "theorem",
      objectNumber: "2",
    });
  });

  it("detects bare parenthesized dotted equation references", () => {
    expect(extractReferences("This follows from (19.11).")[0]).toMatchObject({
      kind: "equation",
      objectNumber: "19.11",
      label: "Equation 19.11",
    });
  });

  it("detects §-style and chapter/appendix references", () => {
    expect(extractReferences("as shown in §19.3")[0]).toMatchObject({
      kind: "section",
      sectionNumber: "19.3",
    });
    expect(extractReferences("Chapter 5 covers this")[0]).toMatchObject({
      kind: "chapter",
      sectionNumber: "5",
    });
    expect(extractReferences("Appendix A4 derives it")[0]).toMatchObject({
      kind: "appendix",
      sectionNumber: "A4",
    });
  });

  it("detects page ranges (pp. 580–582)", () => {
    const ref = extractReferences("pp. 580–582")[0];
    expect(ref.printedPage).toBe(580);
    expect(ref.printedPageEnd).toBe(582);
  });

  it("returns nothing for prose without references", () => {
    expect(extractReferences("The fundamental matrix is rank 2.")).toEqual([]);
  });
});

describe("resolveObjectOwningSection", () => {
  const outline: PdfOutlineItem[] = [
    { title: "18 N-View Computational Methods", pageNum: 434, level: 0 },
    { title: "19 Auto-Calibration", pageNum: 458, level: 0 },
    { title: "19.1 Introduction", pageNum: 458, level: 1 },
    { title: "19.3 Calibration using the absolute dual quadric", pageNum: 462, level: 1 },
    { title: "19.3.4 Linear solution", pageNum: 466, level: 2 },
    { title: "19.3.5 Sequential approach", pageNum: 468, level: 2 },
    { title: "20 Duality", pageNum: 480, level: 0 },
  ];

  it("maps Figure 19.1 to its owning chapter section, not the nearest sub-section", () => {
    // The bug: nearest-page match labeled a Figure 19.1 crop as "19.3.4–19.3.5".
    const owning = resolveObjectOwningSection("19.1", outline, 466);
    expect(owning?.title).toContain("19.1");
  });

  it("falls back to the chapter when no exact sub-section number matches", () => {
    const owning = resolveObjectOwningSection("19.7", outline, 470);
    expect(owning?.title).toContain("19");
  });
});

describe("resolveReferences", () => {
  const outline: PdfOutlineItem[] = [
    { title: "A4 Matrix Properties and Decompositions", pageNum: 600, level: 0 },
    { title: "A4.2 Symmetric and skew-symmetric matrices", pageNum: 604, level: 1 },
    { title: "19 Auto-Calibration", pageNum: 458, level: 0 },
    { title: "19.1 Introduction", pageNum: 458, level: 1 },
  ];

  const pageText: Record<number, string> = {
    458: "Chapter 19 Auto-Calibration. Figure 19.1 shows the calibration pipeline overview.",
    604: "A4.2 Symmetric matrices. Jacobi's algorithm diagonalizes a symmetric matrix.",
  };

  function makeCtx(overrides: Partial<ResolveContext> = {}): ResolveContext {
    const searchPages = (query: string, topK = 5): PdfRagHit[] => {
      const q = query.toLowerCase();
      const hits: PdfRagHit[] = [];
      for (const [num, text] of Object.entries(pageText)) {
        const score = text.toLowerCase().includes(q.replace(/[()]/g, "")) ? 5 : 0;
        if (score > 0) {
          hits.push({ pageNum: Number(num), score, snippet: text });
        }
      }
      return hits.slice(0, topK);
    };
    return {
      outline,
      currentPage: 468,
      searchPages,
      getPageText: (n) => pageText[n],
      ...overrides,
    };
  }

  it("resolves a section number to its outline page and title", () => {
    const refs = extractReferences("see section A4.2 (p580)");
    const resolved = resolveReferences(refs, makeCtx());
    const section = resolved.find((r) => r.query.kind === "section");
    expect(section?.targetPage).toBe(604);
    expect(section?.sectionTitle).toContain("A4.2");
    expect(section?.confidence).toBeGreaterThan(0.5);
  });

  it("resolves a printed page via a known page offset", () => {
    // printed 580 with front-matter offset of 24 -> pdf index 604.
    const refs = extractReferences("see p580");
    const resolved = resolveReferences(refs, makeCtx({ pageOffset: 24 }));
    const page = resolved.find((r) => r.query.kind === "page");
    expect(page?.targetPage).toBe(604);
  });

  it("resolves a figure number to its caption page via search", () => {
    const refs = extractReferences("Figure 19.1");
    const resolved = resolveReferences(refs, makeCtx());
    const figure = resolved.find((r) => r.query.kind === "figure");
    expect(figure?.targetPage).toBe(458);
    expect(figure?.snippet).toContain("Figure 19.1");
  });

  it("resolves a bare parenthesized equation reference via available PDF search hits", () => {
    const refs = extractReferences("This follows from (19.11).");
    const ctx = makeCtx({
      currentPage: 490,
      searchPages: (query: string): PdfRagHit[] => {
        expect(query).toBe("Equation 19.11");
        return [
          {
            pageNum: 462,
            score: 7,
            snippet: "Equation 19.11 defines the Kruppa constraints.",
          },
        ];
      },
      getPageText: (n) =>
        n === 462 ? "Equation 19.11 defines the Kruppa constraints." : undefined,
    });
    const equation = resolveReferences(refs, ctx).find((r) => r.query.kind === "equation");
    expect(equation?.method).toBe("bm25-object");
    expect(equation?.targetPage).toBe(462);
    expect(equation?.snippet).toContain("Kruppa constraints");
  });

  it("prefers the caption-index page over a mere-mention page for objects", () => {
    // p.470 only *mentions* the figure; p.458 has the line-anchored caption.
    const pages = [
      { pageNum: 458, text: "19.1 Introduction\nFigure 19.1: the calibration pipeline overview." },
      { pageNum: 470, text: "As discussed earlier, see Figure 19.1 for the pipeline." },
    ];
    const captionIndex = buildCaptionIndex(pages);
    const ctx = makeCtx({
      captionIndex,
      currentPage: 470,
      // Search would rank the mention page too; caption index must win.
      searchPages: () => [
        { pageNum: 470, score: 9, snippet: "see Figure 19.1" },
        { pageNum: 458, score: 4, snippet: "Figure 19.1: the calibration pipeline" },
      ],
    });
    const resolved = resolveReferences(extractReferences("Figure 19.1"), ctx);
    const figure = resolved.find((r) => r.query.kind === "figure");
    expect(figure?.method).toBe("caption-index");
    expect(figure?.targetPage).toBe(458);
    expect(figure?.sectionTitle).toContain("19.1");
  });

  it("marks references it cannot resolve as unresolved with low confidence", () => {
    const refs = extractReferences("see section Z9.9");
    const resolved = resolveReferences(refs, makeCtx());
    const section = resolved.find((r) => r.query.kind === "section");
    expect(section?.method).toBe("unresolved");
    expect(section?.targetPage).toBeUndefined();
  });
});
