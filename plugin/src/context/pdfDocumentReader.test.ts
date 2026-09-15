import { describe, expect, it, vi } from "vitest";
import type { ActiveContext, PdfWindowPage } from "../types";
import { createPdfDocumentReader } from "./pdfDocumentReader";

function nativeContext(): ActiveContext {
  return {
    viewType: "pdf",
    filePath: "Papers/a.pdf",
    absolutePath: "/vault/Papers/a.pdf",
    pdfPage: {
      pageNum: 7,
      pageCount: 7,
      text: "visible page seven",
      windowPages: [{ pageNum: 7, text: "visible page seven" }],
    },
  };
}

describe("a PDF reader bound to the captured document", () => {
  it("uses native absolute identity and authoritative page count to reach page eleven", async () => {
    const context = nativeContext();
    const backend = vi.fn(async ({ pageNum }: { pageNum: number }) => ({
      pages: [{ pageNum, text: pageNum === 11 ? "References\nAuthor eleven" : "page seven" }],
      outline: [{ title: "References", pageNum: 11, level: 1 }],
      totalPages: 11,
    }));
    const reader = createPdfDocumentReader(context, backend)!;
    const prepared = await reader.prepare();
    expect(prepared.pageCount).toBe(11);
    expect(prepared.outline?.[0].pageNum).toBe(11);
    expect(reader.documentKey).toBe("/vault/Papers/a.pdf");
    expect(await reader.fetchPage(11)).toContain("Author eleven");
    expect(backend.mock.calls).toEqual([
      [{ filePath: "/vault/Papers/a.pdf", pageNum: 7, radius: 0, maxPages: 1 }],
      [{ filePath: "/vault/Papers/a.pdf", pageNum: 11, radius: 0, maxPages: 1 }],
    ]);
    expect(context.pdfPage?.pageCount).toBe(7);
    expect(context.pdfPage?.windowPages?.[0].text).toBe("visible page seven");
  });

  it("does not read a newly selected PDF or mutated page arrays", async () => {
    const context = nativeContext();
    const backend = vi.fn(async () => null);
    const reader = createPdfDocumentReader(context, backend)!;
    context.absolutePath = "/vault/Papers/b.pdf";
    context.pdfPage!.filePath = "/vault/Papers/b.pdf";
    context.pdfPage!.windowPages![0].text = "foreign page";
    const prepared = await reader.prepare();
    await reader.fetchPage(11);
    expect(prepared.windowPages?.[0].text).toBe("visible page seven");
    for (const [args] of backend.mock.calls as unknown as [{ filePath: string }][]) {
      expect(args.filePath).toBe("/vault/Papers/a.pdf");
    }
  });

  it("rejects a viewer replaced while its page fetch is pending", async () => {
    let documentId = "a";
    let finish!: (page: PdfWindowPage) => void;
    const fetchPage = vi.fn(() => new Promise<PdfWindowPage>((resolve) => { finish = resolve; }));
    const reader = createPdfDocumentReader(nativeContext(), undefined, {
      documentId: "a", getDocumentId: () => documentId, fetchPage,
    })!;
    const pending = reader.fetchPage(11);
    documentId = "b";
    finish({ pageNum: 11, text: "foreign page" });
    expect(await pending).toBeUndefined();
    expect(await reader.fetchPage(12)).toBeUndefined();
    expect(fetchPage).toHaveBeenCalledTimes(1);
  });

  it("falls back to the captured viewer when the backend is unavailable", async () => {
    const reader = createPdfDocumentReader(nativeContext(), async () => { throw new Error("offline"); }, {
      documentId: "a", getDocumentId: () => "a", pageCount: 11,
      fetchPage: async (pageNum) => ({ pageNum, text: "References\nOffline author" }),
    })!;
    expect((await reader.prepare()).pageCount).toBe(11);
    expect(await reader.fetchPage(11)).toContain("Offline author");
  });

  it("does not send requests without a backend identity", async () => {
    const backend = vi.fn(async () => null);
    const reader = createPdfDocumentReader({ viewType: "pdf", pdfPage: { pageNum: 7, text: "page" } }, backend)!;
    expect(reader.documentKey).toBeUndefined();
    await reader.prepare();
    expect(await reader.fetchPage(11)).toBeUndefined();
    expect(backend).not.toHaveBeenCalled();
  });

  it("distinguishes a successfully read blank page from an unavailable page", async () => {
    const reader = createPdfDocumentReader(nativeContext(), async ({ pageNum }) => ({
      pages: pageNum === 10 ? [{ pageNum, text: "" }] : [], outline: [], totalPages: 11,
    }))!;
    expect(await reader.fetchPage(10)).toBe("");
    expect(await reader.fetchPage(11)).toBeUndefined();
  });

  it("rejects invalid page numbers without fetching", async () => {
    const backend = vi.fn(async () => null);
    const reader = createPdfDocumentReader(nativeContext(), backend)!;
    for (const pageNum of [0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(await reader.fetchPage(pageNum)).toBeUndefined();
    }
    expect(backend).not.toHaveBeenCalled();
  });
});
