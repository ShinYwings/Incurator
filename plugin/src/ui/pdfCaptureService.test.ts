import { describe, expect, it } from "vitest";
import { PdfCaptureService } from "./pdfCaptureService";
import type { PdfTextQuality, PdfWindowPage } from "../types";

const goodQuality: PdfTextQuality = {
  score: 1,
  charCount: 10,
  wordCount: 2,
  lineCount: 1,
  brokenCharRatio: 0,
  whitespaceRatio: 0.1,
  isScannedLike: false,
  source: "pdfjs",
};

function fakePagesEl(pageEl: Partial<HTMLElement> | null): HTMLElement {
  return {
    querySelector: () => pageEl,
  } as unknown as HTMLElement;
}

describe("PdfCaptureService", () => {
  it("captures cached page text and RAG hits without an Obsidian ItemView", () => {
    const service = new PdfCaptureService();
    const current: PdfWindowPage = {
      pageNum: 2,
      text: "alpha beta",
      textQuality: goodQuality,
    };

    const out = service.capture({
      captureMode: "text",
      pagesEl: fakePagesEl({ querySelector: () => null }),
      currentPage: 2,
      totalPages: 5,
      pageLabels: ["i", "1"],
      pageTextCache: new Map([[2, current]]),
      outline: [{ title: "Intro", pageNum: 1, level: 0 }],
      documentId: "doc-1",
      documentName: "Paper",
      filePath: "/local/Paper.pdf",
      zoteroAttachmentKey: "ZOTKEY",
      getSelectionText: () => "alpha",
      searchIndex: {
        search: (docId, query, options) => {
          expect(docId).toBe("doc-1");
          expect(query).toBe("alpha");
          expect(options.excludePages).toEqual([2]);
          return [{ pageNum: 4, score: 1.2, snippet: "alpha again" }];
        },
      },
    });

    expect(out?.pageNum).toBe(2);
    expect(out?.documentName).toBe("Paper");
    expect(out?.filePath).toBe("/local/Paper.pdf");
    expect(out?.zoteroAttachmentKey).toBe("ZOTKEY");
    expect(out?.windowPages).toEqual([current]);
    expect(out?.ragHits).toEqual([{ pageNum: 4, score: 1.2, snippet: "alpha again" }]);
    expect(out?.text).toContain("alpha beta");
  });

  it("returns null when the target page element is not available", () => {
    const service = new PdfCaptureService();
    const out = service.capture({
      captureMode: "text",
      pagesEl: fakePagesEl(null),
      currentPage: 1,
      totalPages: 1,
      pageTextCache: new Map(),
      outline: [],
      documentId: "doc-1",
      documentName: "Paper",
      getSelectionText: () => null,
      searchIndex: { search: () => [] },
    });

    expect(out).toBeNull();
  });
});
