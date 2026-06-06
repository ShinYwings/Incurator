/**
 * Bridges the pure {@link crossReferenceResolver} with the in-memory PDF index.
 *
 * Both quick-query (drag → "Ask AI") and the chat sidebar (crop/selection pins)
 * call this to follow a pointer in the selected passage: it builds an ad-hoc
 * BM25 index + caption index over whatever PDF window/outline is on hand,
 * resolves any cross-references, and returns either the resolved set or the
 * formatted `<resolved_cross_references>` block.
 */
import { PdfDocumentIndexService } from "./pdfDocumentIndex";
import {
  buildCaptionIndex,
  buildResolvedReferencesBlock,
  extractReferences,
  resolveReferences,
  type ResolveContext,
  type ResolvedReference,
} from "./crossReferenceResolver";
import type { PdfOutlineItem, PdfWindowPage } from "../types";

export interface PdfReferenceSource {
  outline?: PdfOutlineItem[];
  windowPages?: PdfWindowPage[];
  pageNum?: number;
  pageLabels?: string[];
}

function mapPrintedPageLabel(pageLabels: string[] | undefined, printed: number): number | undefined {
  if (!pageLabels?.length) return undefined;
  const wanted = String(printed);
  const index = pageLabels.findIndex((label) => String(label).trim() === wanted);
  return index >= 0 ? index + 1 : undefined;
}

export function resolveSelectionReferences(
  selectedText: string,
  source: PdfReferenceSource | undefined
): ResolvedReference[] {
  if (!selectedText || !source) return [];
  const refs = extractReferences(selectedText);
  if (refs.length === 0) return [];

  const pages = source.windowPages ?? [];
  const outline = source.outline ?? [];
  if (pages.length === 0 && outline.length === 0) return [];

  const pageText = new Map<number, string>();
  for (const page of pages) pageText.set(page.pageNum, page.text);

  const index = new PdfDocumentIndexService();
  if (pages.length) index.upsertDocument("selection", pages, outline);

  const ctx: ResolveContext = {
    outline,
    currentPage: source.pageNum ?? 1,
    captionIndex: buildCaptionIndex(
      pages.map((page) => ({ pageNum: page.pageNum, text: page.text }))
    ),
    searchPages: (query, topK) =>
      pages.length ? index.search("selection", query, { topK }) : [],
    getPageText: (pageNum) => pageText.get(pageNum),
    printedToPdf: (printed) => mapPrintedPageLabel(source.pageLabels, printed),
  };
  return resolveReferences(refs, ctx);
}

/** Convenience: resolve and format in one call. Returns "" when nothing resolves. */
export function resolveSelectionReferencesBlock(
  selectedText: string,
  source: PdfReferenceSource | undefined
): string {
  return buildResolvedReferencesBlock(resolveSelectionReferences(selectedText, source));
}
