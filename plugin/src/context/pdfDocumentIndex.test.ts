import { describe, it, expect, beforeEach } from "vitest";
import { PdfDocumentIndexService } from "./pdfDocumentIndex";
import type { PdfWindowPage, PdfOutlineItem } from "../types";

function page(pageNum: number, text: string): PdfWindowPage {
  return { pageNum, text };
}

describe("PdfDocumentIndexService", () => {
  let svc: PdfDocumentIndexService;
  const DOC = "doc-1";

  beforeEach(() => {
    svc = new PdfDocumentIndexService();
  });

  // ── search ────────────────────────────────────────────────────────────────

  it("returns empty hits for unknown document", () => {
    expect(svc.search("nope", "anything")).toEqual([]);
  });

  it("returns empty hits for empty query", () => {
    svc.upsertDocument(DOC, [page(1, "neural scaling laws")]);
    expect(svc.search(DOC, "")).toEqual([]);
    expect(svc.search(DOC, "   ")).toEqual([]);
  });

  it("finds a page containing query terms", () => {
    svc.upsertDocument(DOC, [
      page(1, "Transformer architecture attention mechanism"),
      page(2, "Convolutional neural networks for image classification"),
      page(3, "Reinforcement learning reward signal"),
    ]);
    const hits = svc.search(DOC, "transformer attention");
    expect(hits.length).toBeGreaterThan(0);
    expect(hits[0].pageNum).toBe(1);
  });

  it("returns empty hits when no page matches", () => {
    svc.upsertDocument(DOC, [page(1, "cats and dogs")]);
    expect(svc.search(DOC, "xyzzy_nonexistent")).toEqual([]);
  });

  it("ranks more relevant pages higher", () => {
    svc.upsertDocument(DOC, [
      page(1, "scaling scaling scaling scaling scaling laws performance language model"),
      page(2, "scaling mentioned once here"),
    ]);
    const hits = svc.search(DOC, "scaling laws");
    expect(hits.length).toBe(2);
    expect(hits[0].pageNum).toBe(1);
    expect(hits[0].score).toBeGreaterThanOrEqual(hits[1].score);
  });

  it("respects topK option", () => {
    svc.upsertDocument(DOC, [
      page(1, "machine learning neural network"),
      page(2, "machine translation neural network"),
      page(3, "neural network optimization"),
    ]);
    const hits = svc.search(DOC, "neural network", { topK: 2 });
    expect(hits.length).toBeLessThanOrEqual(2);
  });

  it("excludes specified pages", () => {
    svc.upsertDocument(DOC, [
      page(1, "deep learning architectures"),
      page(2, "deep learning applications"),
    ]);
    const hits = svc.search(DOC, "deep learning", { excludePages: [1] });
    expect(hits.every((h) => h.pageNum !== 1)).toBe(true);
  });

  it("stop words are ignored and do not inflate score", () => {
    // "the", "is", "of", "in", "to" are stop words; they should be stripped
    svc.upsertDocument(DOC, [
      page(1, "the quick brown fox"),
      page(2, "attention is all you need"),
    ]);
    // Searching only stop words should return no hits
    const hits = svc.search(DOC, "the is of");
    expect(hits).toEqual([]);
  });

  // ── getWindowPages ─────────────────────────────────────────────────────────

  it("returns the requested window of pages", () => {
    svc.upsertDocument(DOC, [
      page(1, "page one"),
      page(2, "page two"),
      page(3, "page three"),
      page(4, "page four"),
      page(5, "page five"),
    ]);
    const win = svc.getWindowPages(DOC, 3, 1);
    expect(win.map((p) => p.pageNum)).toEqual([2, 3, 4]);
  });

  it("clamps window at document boundaries", () => {
    svc.upsertDocument(DOC, [page(1, "first"), page(2, "second")]);
    const win = svc.getWindowPages(DOC, 1, 2);
    // Can't go below page 1
    expect(win.map((p) => p.pageNum)).toEqual([1, 2, 3].filter((n) => n <= 2));
  });

  it("returns empty array for unknown document", () => {
    expect(svc.getWindowPages("unknown", 1, 1)).toEqual([]);
  });

  // ── upsertPage ─────────────────────────────────────────────────────────────

  it("adds a new page to an existing index", () => {
    svc.upsertDocument(DOC, [page(1, "first page")]);
    svc.upsertPage(DOC, page(2, "second page"));
    expect(svc.getPage(DOC, 2)?.text).toBe("second page");
  });

  it("replaces an existing page by page number", () => {
    svc.upsertDocument(DOC, [page(1, "old text on page one")]);
    svc.upsertPage(DOC, page(1, "new text on page one"));
    expect(svc.getPage(DOC, 1)?.text).toBe("new text on page one");
  });

  // ── sectionTitle from outline ──────────────────────────────────────────────

  it("assigns section title from outline to hits", () => {
    const outline: PdfOutlineItem[] = [
      { title: "Introduction", pageNum: 1, level: 0 },
      { title: "Methods", pageNum: 3, level: 0 },
    ];
    svc.upsertDocument(
      DOC,
      [page(3, "methods section optimization gradient descent")],
      outline
    );
    const hits = svc.search(DOC, "gradient descent");
    expect(hits[0].sectionTitle).toBe("Methods");
  });
});
