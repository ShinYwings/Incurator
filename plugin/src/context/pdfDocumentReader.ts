import type { ActiveContext, PdfOutlineItem, PdfPageContext, PdfWindowPage } from "../types";

export interface PdfDocumentRequest {
  filePath?: string;
  fileHash?: string;
  zoteroAttachmentKey?: string;
  pageNum: number;
  radius: number;
  maxPages: number;
}

export type PdfContextFetcher = (args: PdfDocumentRequest) => Promise<{
  pages: PdfWindowPage[];
  outline: PdfOutlineItem[];
  totalPages: number;
} | null>;

export interface PdfReaderFallback {
  documentId: string;
  getDocumentId(): string | undefined;
  fetchPage(pageNum: number): Promise<PdfWindowPage | null>;
  pageCount?: number;
}

export interface PdfDocumentReader {
  documentKey: string | undefined;
  prepare(): Promise<PdfPageContext>;
  fetchPage(pageNum: number): Promise<string | undefined>;
}

/** Capture the source before any await; later workspace focus cannot replace it. */
export function createPdfDocumentReader(
  activeContext: ActiveContext,
  getPdfContext: PdfContextFetcher | undefined,
  fallback?: PdfReaderFallback
): PdfDocumentReader | undefined {
  const pdf = activeContext.pdfPage;
  if (!pdf) return undefined;
  const snapshot: PdfPageContext = {
    ...pdf,
    windowPages: pdf.windowPages?.map((page) => ({ ...page })),
    outline: pdf.outline?.map((item) => ({ ...item })),
    pageLabels: pdf.pageLabels?.slice(),
    ragHits: pdf.ragHits?.map((hit) => ({ ...hit })),
    textQuality: pdf.textQuality && { ...pdf.textQuality },
  };
  const identity = {
    ...(pdf.filePath || activeContext.absolutePath || activeContext.filePath
      ? { filePath: pdf.filePath || activeContext.absolutePath || activeContext.filePath }
      : {}),
    ...(pdf.fileHash ? { fileHash: pdf.fileHash } : {}),
    ...(pdf.zoteroAttachmentKey ? { zoteroAttachmentKey: pdf.zoteroAttachmentKey } : {}),
  };
  snapshot.filePath = identity.filePath;
  const documentKey = identity.fileHash || identity.zoteroAttachmentKey ||
    identity.filePath || pdf.documentId || fallback?.documentId;
  const backend = Object.keys(identity).length ? getPdfContext : undefined;
  // Bind the methods as well as identity: callers may later replace their
  // fallback descriptor, and an in-flight reader must keep its original view.
  const viewerId = fallback?.documentId;
  const viewerIdentity = fallback?.getDocumentId.bind(fallback);
  const viewerFetch = fallback?.fetchPage.bind(fallback);
  const viewerPageCount = fallback?.pageCount;
  const hasSameViewer = () => viewerId !== undefined && viewerIdentity?.() === viewerId;
  const readBackend = async (pageNum: number) => {
    try {
      return await backend?.({ ...identity, pageNum, radius: 0, maxPages: 1 });
    } catch {
      // A failed backend read is unavailable, never a successful empty page.
      // The captured viewer remains a valid source for offline PDF reading.
      return undefined;
    }
  };
  let prepared: Promise<PdfPageContext> | undefined;

  return {
    documentKey,
    prepare() {
      prepared ??= (async () => {
        const result = await readBackend(snapshot.pageNum);
        const context = { ...snapshot };
        if (result) {
          if (Number.isInteger(result.totalPages) && result.totalPages > 0) {
            context.pageCount = result.totalPages;
          }
          context.outline = result.outline.map((item) => ({ ...item }));
          context.outlineResolved = true;
          const pages = new Map(snapshot.windowPages?.map((page) => [page.pageNum, page]));
          for (const page of result.pages) pages.set(page.pageNum, { ...page });
          context.windowPages = [...pages.values()].sort((a, b) => a.pageNum - b.pageNum);
        }
        if ((!result || result.totalPages <= 0) && hasSameViewer() && viewerPageCount) {
          context.pageCount = viewerPageCount;
        }
        return context;
      })();
      return prepared;
    },
    async fetchPage(pageNum) {
      if (!Number.isInteger(pageNum) || pageNum < 1) return undefined;
      let backendText: string | undefined;
      if (backend) {
        const result = await readBackend(pageNum);
        backendText = result?.pages.find((page) => page.pageNum === pageNum)?.text;
        if (backendText?.trim()) return backendText;
      }
      if (!viewerFetch || !hasSameViewer()) return backendText;
      try {
        const page = await viewerFetch(pageNum);
        if (!hasSameViewer() || page?.pageNum !== pageNum) return backendText;
        return page.text;
      } catch {
        return backendText;
      }
    },
  };
}
