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
  type ReferenceQuery,
  type ResolveContext,
  type ResolvedReference,
} from "./crossReferenceResolver";
import type { PdfOutlineItem, PdfWindowPage } from "../types";

const EXACT_OUTLINE_RANGE_FETCH_LIMIT = 12;
const CHAPTER_OUTLINE_RANGE_FETCH_LIMIT = 24;
const OUTLINE_RANGE_FETCH_BATCH_SIZE = 6;
const ADJACENT_EQUATION_PAGE_OFFSETS = [1, -1, 2, -2] as const;

export interface PdfReferenceSource {
  outline?: PdfOutlineItem[];
  windowPages?: PdfWindowPage[];
  pageNum?: number;
  pageCount?: number;
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

function parseOutlineNumber(title: string): string | undefined {
  const m = /^\s*(?:appendix\s+)?([A-Z]?\d+(?:\.\d+)*)/i.exec(title);
  return m ? m[1].toUpperCase() : undefined;
}

function outlineRangeForNumber(
  outline: PdfOutlineItem[],
  sectionNumber: string,
  pageCount: number | undefined,
  maxPages: number
): { start: number; end: number } | null {
  const wanted = sectionNumber.toUpperCase();
  const index = outline.findIndex((item) => parseOutlineNumber(item.title) === wanted);
  const item = index >= 0 ? outline[index] : undefined;
  if (!item || typeof item.pageNum !== "number") return null;

  let end = pageCount ?? item.pageNum + maxPages - 1;
  for (const next of outline.slice(index + 1)) {
    if (typeof next.pageNum !== "number" || next.pageNum <= item.pageNum) continue;
    if (next.level <= item.level) {
      end = next.pageNum - 1;
      break;
    }
  }

  end = Math.min(end, item.pageNum + maxPages - 1);
  if (typeof pageCount === "number") end = Math.min(end, pageCount);
  return { start: item.pageNum, end: Math.max(item.pageNum, end) };
}

function pagesFromRange(range: { start: number; end: number }): number[] {
  const pages: number[] = [];
  for (let pageNum = range.start; pageNum <= range.end; pageNum++) pages.push(pageNum);
  return pages;
}

function outlineCandidatePagesForReference(
  ref: ReferenceQuery,
  outline: PdfOutlineItem[],
  pageCount: number | undefined
): number[] {
  const number = ref.objectNumber ?? ref.sectionNumber;
  if (!number) return [];
  const orderedPages: number[] = [];
  const addRange = (sectionNumber: string, maxPages: number): boolean => {
    const range = outlineRangeForNumber(outline, sectionNumber, pageCount, maxPages);
    if (!range) return false;
    orderedPages.push(...pagesFromRange(range));
    return true;
  };

  if (number.includes(".")) {
    if (addRange(number, EXACT_OUTLINE_RANGE_FETCH_LIMIT)) {
      return orderedUniquePages(orderedPages);
    }
    const chapter = number.split(".")[0];
    addRange(chapter, CHAPTER_OUTLINE_RANGE_FETCH_LIMIT);
    return orderedUniquePages(orderedPages);
  }

  addRange(number, EXACT_OUTLINE_RANGE_FETCH_LIMIT);
  return orderedUniquePages(orderedPages);
}

function isWeakCurrentPageHit(
  ref: ResolvedReference,
  currentPage: number | undefined
): boolean {
  return (
    typeof currentPage === "number" &&
    ref.targetPage === currentPage &&
    (ref.method === "bm25-object" || ref.method === "bm25-section")
  );
}

function needsOutlineExpansion(
  ref: ResolvedReference,
  currentPage: number | undefined
): boolean {
  return ref.method === "unresolved" || isWeakCurrentPageHit(ref, currentPage);
}

function needsAdjacentEquationExpansion(ref: ResolvedReference): boolean {
  return (
    ref.query.kind === "equation" &&
    /^\d+$/.test(ref.query.objectNumber ?? "") &&
    ref.method !== "caption-index"
  );
}

function adjacentEquationCandidatePages(
  currentPage: number | undefined,
  pageCount: number | undefined
): number[] {
  if (typeof currentPage !== "number") return [];
  return ADJACENT_EQUATION_PAGE_OFFSETS
    .map((offset) => currentPage + offset)
    .filter(
      (pageNum) =>
        pageNum > 0 &&
        (typeof pageCount !== "number" || pageCount <= 0 || pageNum <= pageCount)
    );
}

function pageHasExactEquationLabel(text: string | undefined, objectNumber: string): boolean {
  if (!text) return false;
  const escapedNumber = objectNumber.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(
    `(?:\\b(?:equations?|eqs?|eqn)\\.?|수식)\\s*\\(?${escapedNumber}\\)?(?![\\d.])`,
    "i"
  ).test(text);
}

function orderedUniquePages(pages: Iterable<number>): number[] {
  return Array.from(new Set(pages));
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
    pageCount: source.pageCount,
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
    pageCount: source.pageCount,
  });

  // Pass 1: sync resolve
  const pass1 = resolveReferences(refs, buildCtx());

  const fetchPages = async (pageNums: number[]): Promise<boolean> => {
    if (pageNums.length === 0) return false;
    const fetched = await Promise.all(
      pageNums.map((pageNum) =>
        fetchPageText(pageNum)
          .then((text) => (text ? { pageNum, text } : null))
          .catch(() => null)
      )
    );

    let changed = false;
    for (const result of fetched) {
      if (!result) continue;
      pageTextMap.set(result.pageNum, result.text);
      const page: PdfWindowPage = { pageNum: result.pageNum, text: result.text };
      index.upsertPage(searchDocId, page, outline);
      changed = true;
    }
    return changed;
  };

  // Direct targets are cheap: fetch exactly the resolved missing page(s).
  const directMissingPages = new Set<number>();
  for (const r of pass1) {
    if (
      r.method !== "unresolved" &&
      !isWeakCurrentPageHit(r, source.pageNum) &&
      r.targetPage !== undefined &&
      !pageTextMap.has(r.targetPage)
    ) {
      directMissingPages.add(r.targetPage);
    }
  }

  let changed = await fetchPages(orderedUniquePages(directMissingPages));
  let latest = changed ? resolveReferences(refs, buildCtx()) : pass1;

  // Globally numbered equations commonly continue on the next physical page
  // without a useful ToC entry. Probe only a small next-first neighborhood,
  // one page at a time, and stop at the first exact displayed-label hit.
  if (latest.some(needsAdjacentEquationExpansion)) {
    for (const pageNum of adjacentEquationCandidatePages(source.pageNum, source.pageCount)) {
      const pageChanged = await fetchPages([pageNum]);
      changed = changed || pageChanged;
      if (!pageChanged) continue;
      latest = resolveReferences(refs, buildCtx());
      if (!latest.some(needsAdjacentEquationExpansion)) return latest;
      const pendingEquations = latest.filter(needsAdjacentEquationExpansion);
      if (
        pendingEquations.every(
          (ref) =>
            ref.targetPage === pageNum &&
            pageHasExactEquationLabel(
              pageTextMap.get(pageNum),
              ref.query.objectNumber ?? ""
            )
        )
      ) {
        return latest;
      }
    }
  }

  // Outline fallback can span many pages. Fetch in small batches and stop as
  // soon as the resolver finds the referenced target.
  const outlinePages: number[] = [];
  for (const r of pass1) {
    if (!needsOutlineExpansion(r, source.pageNum)) continue;
    if (needsAdjacentEquationExpansion(r)) continue;
    for (const pageNum of outlineCandidatePagesForReference(r.query, outline, source.pageCount)) {
      if (!pageTextMap.has(pageNum)) outlinePages.push(pageNum);
    }
  }

  const outlineQueue = orderedUniquePages(outlinePages);
  for (let i = 0; i < outlineQueue.length; i += OUTLINE_RANGE_FETCH_BATCH_SIZE) {
    const batch = outlineQueue.slice(i, i + OUTLINE_RANGE_FETCH_BATCH_SIZE);
    const batchChanged = await fetchPages(batch);
    changed = changed || batchChanged;
    if (!batchChanged) continue;
    latest = resolveReferences(refs, buildCtx());
    if (!latest.some((r) => needsOutlineExpansion(r, source.pageNum))) return latest;
  }

  if (!changed) {
    // No page text was fetched; suppress any refs whose snippet is empty so the
    // LLM doesn't receive a resolved-looking reference with no content.
    return pass1.map((r) =>
      r.method !== "unresolved" && r.targetPage !== undefined && !pageTextMap.has(r.targetPage)
        ? { ...r, method: "unresolved" as const }
        : r
    );
  }

  return latest;
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
