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
  /** Full document BM25 index — all pages seen so far ("fog of war"). When
   *  provided, the resolver uses it instead of building a fresh index from
   *  windowPages only, enabling cross-page lookups into already-seen pages. */
  searchIndex?: PdfDocumentIndexService;
  /** Document ID used when the pages were upserted into searchIndex.
   *  Must be provided alongside searchIndex; defaults to "selection". */
  searchDocumentId?: string;
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

  // Prefer the full document index if available; otherwise build from window only.
  const searchDocId = source.searchDocumentId ?? "selection";
  const index = source.searchIndex ?? new PdfDocumentIndexService();
  if (!source.searchIndex && pages.length) index.upsertDocument("selection", pages, outline);

  const ctx: ResolveContext = {
    outline,
    currentPage: source.pageNum ?? 1,
    captionIndex: buildCaptionIndex(
      pages.map((page) => ({ pageNum: page.pageNum, text: page.text }))
    ),
    searchPages: (query, topK) =>
      index.search(searchDocId, query, { topK }),
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

/**
 * Async variant: same as {@link resolveSelectionReferences} but when a
 * resolved reference points to a page whose text is not yet in the window,
 * it fetches that page via {@link fetchPageText}, upserts it into the index,
 * and re-resolves so the LLM gets the actual equation/section content.
 *
 * Two-pass approach keeps all resolvers synchronous; only the outer wrapper is async.
 */
export async function resolveSelectionReferencesAsync(
  selectedText: string,
  source: PdfReferenceSource | undefined,
  fetchPageText: (pageNum: number) => Promise<string | undefined>
): Promise<ResolvedReference[]> {
  if (!selectedText || !source) return [];
  const refs = extractReferences(selectedText);
  if (refs.length === 0) return [];

  const pages = source.windowPages ?? [];
  const outline = source.outline ?? [];

  const pageTextMap = new Map<number, string>();
  for (const page of pages) pageTextMap.set(page.pageNum, page.text);

  const searchDocId = source.searchDocumentId ?? "selection";
  const index = source.searchIndex ?? new PdfDocumentIndexService();
  if (!source.searchIndex && pages.length) index.upsertDocument("selection", pages, outline);

  const buildCtx = (): ResolveContext => ({
    outline,
    currentPage: source.pageNum ?? 1,
    captionIndex: buildCaptionIndex(
      Array.from(pageTextMap.entries()).map(([pageNum, text]) => ({ pageNum, text }))
    ),
    searchPages: (query, topK) => index.search(searchDocId, query, { topK }),
    getPageText: (pageNum) => pageTextMap.get(pageNum),
    printedToPdf: (printed) => mapPrintedPageLabel(source.pageLabels, printed),
  });

  // Pass 1: sync resolve
  const pass1 = resolveReferences(refs, buildCtx());

  // Collect resolved references whose target page text is missing
  const missingPages = new Set<number>();
  for (const r of pass1) {
    if (r.method !== "unresolved" && r.targetPage !== undefined && !pageTextMap.has(r.targetPage)) {
      missingPages.add(r.targetPage);
    }
  }

  if (missingPages.size === 0) return pass1;

  // Fetch missing pages in parallel
  const fetched = await Promise.all(
    Array.from(missingPages).map(async (pageNum) => {
      const text = await fetchPageText(pageNum);
      return text ? { pageNum, text } : null;
    })
  );

  let changed = false;
  for (const result of fetched) {
    if (!result) continue;
    pageTextMap.set(result.pageNum, result.text);
    const page: PdfWindowPage = { pageNum: result.pageNum, text: result.text };
    index.upsertPage(searchDocId, page, outline);
    changed = true;
  }

  if (!changed) return pass1;

  // Pass 2: re-resolve with enriched index + page text
  return resolveReferences(refs, buildCtx());
}

/** Async convenience wrapper: resolve, fetch missing pages, format. Returns "" when nothing resolves. */
export async function resolveSelectionReferencesBlockAsync(
  selectedText: string,
  source: PdfReferenceSource | undefined,
  fetchPageText: (pageNum: number) => Promise<string | undefined>
): Promise<string> {
  const resolved = await resolveSelectionReferencesAsync(selectedText, source, fetchPageText);
  return buildResolvedReferencesBlock(resolved);
}
