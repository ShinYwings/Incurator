import { describe, expect, it } from "vitest";
import {
  extractReferences,
  resolveReferences,
  resolveObjectOwningSection,
  buildCaptionIndex,
  buildResolvedReferencesBlock,
  inferPrintedPageOffset,
  type ResolveContext,
  type ResolvedReference,
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

  it("detects comma-separated section + page pointer", () => {
    const refs = extractReferences("참조 대상(Section 11.1.2, p281)");
    expect(refs.find((r) => r.kind === "section")?.sectionNumber).toBe("11.1.2");
    expect(refs.find((r) => r.kind === "page")?.printedPage).toBe(281);
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

  it("detects letter-prefixed theorem-family numbers (real report string)", () => {
    // v0.40.3 report: cmd+shift+L drag of this exact hyphen-glued span.
    const refs = extractReferences(
      "From Result A4.1-(p581), which gives a block decomposition of a general skew-symmetric matrix"
    );
    const theorem = refs.find((r) => r.kind === "theorem");
    const page = refs.find((r) => r.kind === "page");
    expect(theorem?.objectNumber).toBe("A4.1");
    expect(page?.printedPage).toBe(581);
  });

  it("detects other letter-prefixed theorem-family variants", () => {
    expect(extractReferences("by Corollary B2.3")[0]).toMatchObject({
      kind: "theorem",
      objectNumber: "B2.3",
    });
    expect(extractReferences("Definition 3.1 states")[0]).toMatchObject({
      kind: "theorem",
      objectNumber: "3.1",
    });
  });

  it("still requires a digit after the theorem keyword (no prose capture)", () => {
    expect(extractReferences("Result And then some prose")).toEqual([]);
    expect(extractReferences("the results indicate otherwise")).toEqual([]);
  });
});

describe("inferPrintedPageOffset", () => {
  it("infers a consensus offset from leading and trailing header numbers", () => {
    const offset = inferPrintedPageOffset([
      { pageNum: 274, text: "256 9 Epipolar Geometry and the Fundamental Matrix\nbody text" },
      { pageNum: 275, text: "9.6 Extraction of cameras 257\nbody text" },
      { pageNum: 276, text: "258 9 Epipolar Geometry and the Fundamental Matrix\nProof body" },
    ]);
    expect(offset).toBe(18);
  });

  it("never infers from a single page", () => {
    expect(
      inferPrintedPageOffset([{ pageNum: 276, text: "258 Epipolar Geometry" }])
    ).toBeUndefined();
  });

  it("fails closed on a tied vote", () => {
    expect(
      inferPrintedPageOffset([
        { pageNum: 10, text: "10 identity numbering" },
        { pageNum: 11, text: "11 identity numbering" },
        { pageNum: 30, text: "12 offset numbering" },
        { pageNum: 31, text: "13 offset numbering" },
      ])
    ).toBeUndefined();
  });

  it("outvotes a chapter-opening outlier page", () => {
    const offset = inferPrintedPageOffset([
      { pageNum: 274, text: "256 running header" },
      { pageNum: 275, text: "prose 257" },
      { pageNum: 240, text: "9\nEpipolar Geometry chapter opening" },
    ]);
    expect(offset).toBe(18);
  });

  it("ignores dotted section heads like 9.6 at line start", () => {
    expect(
      inferPrintedPageOffset([
        { pageNum: 100, text: "9.6 Extraction of cameras from E" },
        { pageNum: 101, text: "9.7 More sections here" },
      ])
    ).toBeUndefined();
  });

  it("returns undefined when no page yields a header candidate", () => {
    expect(
      inferPrintedPageOffset([
        { pageNum: 5, text: "pure prose without numbers" },
        { pageNum: 6, text: "more prose" },
      ])
    ).toBeUndefined();
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

  it("maps appendix-style numbers (A4.1) to 'Appendix 4' outline titles", () => {
    const withAppendix: PdfOutlineItem[] = [
      { title: "4 Estimation", pageNum: 130, level: 0 },
      { title: "Appendix 4 Matrix Properties and Decompositions", pageNum: 617, level: 0 },
    ];
    const owning = resolveObjectOwningSection("A4.1", withAppendix);
    expect(owning?.title).toContain("Appendix 4");
  });

  it("keeps plain chapter lookups on the chapter, not the aliased appendix", () => {
    const withAppendix: PdfOutlineItem[] = [
      { title: "4 Estimation", pageNum: 130, level: 0 },
      { title: "Appendix 4 Matrix Properties and Decompositions", pageNum: 617, level: 0 },
    ];
    const owning = resolveObjectOwningSection("4.2", withAppendix);
    expect(owning?.title).toContain("Estimation");
  });
});

describe("buildCaptionIndex theorem family", () => {
  it("indexes Result/Corollary/Definition definition lines", () => {
    const index = buildCaptionIndex([
      {
        pageNum: 599,
        text: "581\nA4.1 Skew-symmetric matrices\nResult A4.1. A general 3 x 3 skew-symmetric matrix S may be written as S = kUZU^T.",
      },
      { pageNum: 130, text: "Corollary 3.2 The estimate is unbiased." },
      { pageNum: 131, text: "Definition 3.3 A homography is an invertible map." },
    ]);
    expect(index).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ kind: "theorem", number: "A4.1", pageNum: 599 }),
        expect.objectContaining({ kind: "theorem", number: "3.2", pageNum: 130 }),
        expect.objectContaining({ kind: "theorem", number: "3.3", pageNum: 131 }),
      ])
    );
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

  it("indexes display equation labels such as (3.5) as equation targets", () => {
    const captionIndex = buildCaptionIndex([
      { pageNum: 112, text: "x'^{T} F x = 0 \\quad (3.5)" },
    ]);
    const ctx = makeCtx({
      captionIndex,
      currentPage: 527,
      getPageText: (n) => (n === 112 ? "x'^{T} F x = 0 \\quad (3.5)" : undefined),
      searchPages: () => [],
    });
    const equation = resolveReferences(extractReferences("(3.5)"), ctx).find(
      (r) => r.query.kind === "equation"
    );
    expect(equation?.method).toBe("caption-index");
    expect(equation?.targetPage).toBe(112);
    expect(equation?.snippet).toContain("(3.5)");
  });

  it("indexes single-number display equations without treating citations as equations", () => {
    const captionIndex = buildCaptionIndex([
      { pageNum: 6, text: "L = -\\sum_i y_i \\log p_i \\quad (10)" },
      { pageNum: 7, text: "(2020) Smith and Jones. References." },
    ]);

    expect(captionIndex).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ kind: "equation", number: "10", pageNum: 6 }),
      ])
    );
    expect(captionIndex).not.toEqual(
      expect.arrayContaining([
        expect.objectContaining({ kind: "equation", number: "2020", pageNum: 7 }),
      ])
    );
  });

  it("marks references it cannot resolve as unresolved with low confidence", () => {
    const refs = extractReferences("see section Z9.9");
    const resolved = resolveReferences(refs, makeCtx());
    const section = resolved.find((r) => r.query.kind === "section");
    expect(section?.method).toBe("unresolved");
    expect(section?.targetPage).toBeUndefined();
  });

  it("rejects an identity page whose printed header contradicts the locator", () => {
    // No labels, no offset: the identity guess (physical 581) is only kept
    // while unverifiable. Its header says printed 563 -> fail closed.
    const refs = extractReferences("see p581");
    const ctx = makeCtx({
      outline: [],
      searchPages: () => [],
      getPageText: (n) =>
        n === 581 ? "563 A1 Tensor notation\nThe tensor apparatus follows." : undefined,
      pageCount: 673,
    });
    const page = resolveReferences(refs, ctx).find((r) => r.query.kind === "page");
    expect(page?.method).toBe("unresolved");
    expect(page?.targetPage).toBeUndefined();
  });

  it("resolves a printed page by scanning known page texts for its header", () => {
    // Physical 599 carries printed header 581 -> direct verified match.
    const refs = extractReferences("see p581");
    const ctx = makeCtx({
      outline: [],
      searchPages: () => [],
      getPageText: (n) =>
        n === 599
          ? "581\nA4.1 Skew-symmetric matrices\nResult A4.1. A general skew-symmetric matrix."
          : undefined,
      printedHeaderToPdf: (printed) => (printed === 581 ? 599 : undefined),
      pageCount: 673,
    });
    const page = resolveReferences(refs, ctx).find((r) => r.query.kind === "page");
    expect(page?.method).toBe("explicit-page");
    expect(page?.targetPage).toBe(599);
    expect(page?.snippet).toContain("Result A4.1");
  });

  it("resolves the full v0.40.3 report case once the target page is known (sync)", () => {
    const pages = [
      {
        pageNum: 276,
        text: "258 9 Epipolar Geometry and the Fundamental Matrix\nFrom Result A4.1-(p581), which gives a block decomposition.",
      },
      {
        pageNum: 599,
        text: "581\nA4.1 Skew-symmetric matrices\nResult A4.1. A general 3 x 3 skew-symmetric matrix S may be written as S = kUZU^T.",
      },
    ];
    const text = new Map(pages.map((p) => [p.pageNum, p.text]));
    const refs = extractReferences(
      "From Result A4.1-(p581), which gives a block decomposition"
    );
    const ctx = makeCtx({
      outline: [],
      currentPage: 276,
      searchPages: () => [],
      captionIndex: buildCaptionIndex(pages),
      getPageText: (n) => text.get(n),
      pageOffset: 18,
      pageCount: 673,
    });
    const resolved = resolveReferences(refs, ctx);
    const theorem = resolved.find((r) => r.query.kind === "theorem");
    expect(theorem?.method).toBe("caption-index");
    expect(theorem?.targetPage).toBe(599);
    expect(theorem?.snippet).toContain("Result A4.1");
    const page = resolved.find((r) => r.query.kind === "page");
    expect(page?.targetPage).toBe(599);
  });

  it("uses a nearby explicit page locator as the target for an otherwise unresolved section", () => {
    const refs = extractReferences("참조 대상(Section 11.1.2, p281)");
    const ctx = makeCtx({
      outline: [],
      currentPage: 527,
      searchPages: () => [],
      getPageText: (n) =>
        n === 281
          ? "Section 11.1.2 Seven point correspondences. Compute the fundamental matrix."
          : undefined,
      pageCount: 700,
    });
    const resolved = resolveReferences(refs, ctx);
    const section = resolved.find((r) => r.query.kind === "section");
    const page = resolved.find((r) => r.query.kind === "page");
    expect(section?.targetPage).toBe(281);
    expect(section?.snippet).toContain("Seven point correspondences");
    expect(page?.method).toBe("unresolved");
  });
});

describe("buildResolvedReferencesBlock — unresolved references fail open", () => {
  /**
   * Regression: a paper whose displayed equations are rasterized images stores
   * no `(26)` anywhere, so "수식 26 설명좀" extracts a reference that cannot
   * resolve. The block used to return "" — the prompt then said nothing about
   * the missing equation, and the provider tried to read the PDF with its own
   * shell tool. A headless CLI cannot prompt for that permission, so it was
   * auto-denied and the user saw only:
   *   "jetski: no output produced — a tool required the 'command' permission
   *    that headless mode cannot prompt for, so it was auto-denied"
   * Naming the failure keeps the model answering from what it has.
   */
  const unresolved = (label: string, objectNumber: string): ResolvedReference => ({
    query: { kind: "equation", label, raw: label, index: 0, objectNumber },
    label,
    confidence: 0,
    method: "unresolved",
  });

  it("declares unresolved references instead of returning an empty block", () => {
    const block = buildResolvedReferencesBlock([unresolved("Equation (26)", "26")]);
    expect(block).not.toBe("");
    expect(block).toContain("<unresolved_cross_references");
    expect(block).toContain('label="Equation (26)"');
  });

  it("still returns nothing when no references were extracted at all", () => {
    expect(buildResolvedReferencesBlock([])).toBe("");
  });

  it("reports both resolved and unresolved references together", () => {
    const resolved: ResolvedReference = {
      query: { kind: "equation", label: "Equation (2)", raw: "Equation (2)", index: 0, objectNumber: "2" },
      label: "Equation (2)",
      targetPage: 3,
      snippet: "the reprojection residual",
      confidence: 0.9,
      method: "caption-index",
    };
    const block = buildResolvedReferencesBlock([resolved, unresolved("Equation (26)", "26")]);
    expect(block).toContain("<resolved_cross_references>");
    expect(block).toContain("the reprojection residual");
    expect(block).toContain("<unresolved_cross_references");
    expect(block).toContain('label="Equation (26)"');
  });
  it("never names a page whose text was folded into a nearby sibling", () => {
    // Regression: `resolveWithNearbyPageHints` marks a RESOLVED page ref
    // "unresolved" only to suppress a duplicate render. Naming it told the
    // model that page 281 — quoted verbatim right above — was absent.
    const pages = [
      {
        pageNum: 281,
        text: "Section 11.1.2 Seven point correspondences. Compute the fundamental matrix.",
      },
    ];
    const map = new Map(pages.map((pg) => [pg.pageNum, pg.text]));
    const ctx: ResolveContext = {
      outline: [],
      currentPage: 281,
      captionIndex: buildCaptionIndex(pages),
      searchPages: () => [],
      getPageText: (n) => map.get(n),
      printedToPdf: () => undefined,
      printedHeaderToPdf: () => undefined,
      pageOffset: 0,
      pageCount: 400,
    };
    const resolved = resolveReferences(
      extractReferences("참조 대상(Section 11.1.2, p281)"),
      ctx
    );
    const pageRef = resolved.find((r) => r.query.kind === "page");
    expect(pageRef?.consumedBySibling).toBe(true);

    const block = buildResolvedReferencesBlock(resolved);
    expect(block).toContain("Seven point correspondences");
    expect(block).not.toContain("<unresolved_cross_references");
    expect(block).not.toContain('label="p.281"');
  });

  it("does not claim a verified absence it never established", () => {
    const block = buildResolvedReferencesBlock([unresolved("Equation (26)", "26")]);
    // The quick-query path passes no `locatePages`, so nothing beyond the
    // adjacent probe is searched. Asserting "confirmed absent" would make the
    // model state a falsehood confidently.
    expect(block).not.toContain("confirmed");
    expect(block).not.toContain("absent from the extracted document");
    // The note scopes the gap to THIS CONTEXT, never to the document — the
    // distinction the surrounding assertions exist to protect.
    expect(block).toContain("not in this context");
    // v0.53.3: and it must not tell the model to relay the gap to the reader.
    expect(block).not.toContain("say plainly");
    expect(block).toContain("addressed to you, not");
  });
});
