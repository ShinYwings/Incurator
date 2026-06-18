import type {
  PdfOutlineItem,
  PdfPageContext,
  PdfRagHit,
  PdfTextQuality,
  PdfWindowPage,
} from "../types";
import {
  composePdfContextText,
  extractPdfPageTextFromDom,
} from "../context/pdfCapture";
import { assessPdfTextQuality } from "../context/pdfTextLayout";

const CONTEXT_RAG_TOP_K = 4;

export interface PdfCaptureSearchIndex {
  search(
    documentId: string,
    query: string,
    options: { topK?: number; excludePages?: number[] }
  ): PdfRagHit[];
}

export interface PdfCaptureServiceInput {
  captureMode: "text" | "image" | "both";
  pagesEl: HTMLElement | null;
  currentPage: number;
  totalPages: number;
  pageLabels?: string[];
  pageTextCache: ReadonlyMap<number, PdfWindowPage>;
  outline: PdfOutlineItem[];
  documentId: string;
  documentName: string;
  filePath?: string;
  zoteroAttachmentKey?: string;
  getSelectionText: () => string | null;
  searchIndex: PdfCaptureSearchIndex;
}

export class PdfCaptureService {
  capture(input: PdfCaptureServiceInput): PdfPageContext | null {
    if (!input.pagesEl || input.totalPages === 0) return null;
    const pageEl = input.pagesEl.querySelector<HTMLElement>(
      `.pdf-page[data-page-number="${input.currentPage}"]`
    );
    if (!pageEl) return null;

    let text = "";
    let imageBase64: string | undefined;
    let textQuality: PdfTextQuality = assessPdfTextQuality(
      "",
      "none",
      "Text capture was not requested."
    );
    let windowPages: PdfWindowPage[] = [];
    let ragHits: PdfRagHit[] = [];

    if (input.captureMode === "text" || input.captureMode === "both") {
      const cached = input.pageTextCache.get(input.currentPage);
      if (cached) {
        text = cached.text;
        textQuality =
          cached.textQuality || assessPdfTextQuality(cached.text, "pdfjs");
      } else {
        const extracted = extractPdfPageTextFromDom(pageEl);
        text = extracted.text;
        textQuality = extracted.textQuality;
      }

      // Window expansion is done server-side via curator_get_pdf_context.
      // Provide only the current page here as a lightweight fallback for when
      // the backend is unavailable.
      const currentCached = input.pageTextCache.get(input.currentPage);
      windowPages = currentCached ? [currentCached] : [];
      const query = input.getSelectionText() || text;
      ragHits = input.searchIndex.search(input.documentId, query, {
        topK: CONTEXT_RAG_TOP_K,
        excludePages: [input.currentPage],
      });
      text = composePdfContextText(input.currentPage, text, windowPages, ragHits);
    }

    if (input.captureMode === "image" || input.captureMode === "both") {
      const canvas = pageEl.querySelector("canvas");
      if (canvas) {
        try {
          imageBase64 = canvas
            .toDataURL("image/png")
            .replace(/^data:image\/png;base64,/, "");
        } catch {
          // Tainted canvas: skip image capture but keep text context.
        }
      }
    }

    return {
      pageNum: input.currentPage,
      pageCount: input.totalPages,
      pageLabels: input.pageLabels,
      text,
      imageBase64,
      windowPages,
      outline: input.outline,
      textQuality,
      ragHits,
      isScannedLike: textQuality.isScannedLike,
      documentId: input.documentId,
      documentName: input.documentName,
      filePath: input.filePath,
      zoteroAttachmentKey: input.zoteroAttachmentKey,
    };
  }
}
