/**
 * Bridges the pure {@link crossReferenceResolver} with the in-memory PDF index.
 *
 * Both quick-query (drag → "Ask AI") and the chat sidebar (crop/selection pins)
 * call this to follow a pointer in the selected passage: it builds an ad-hoc
 * BM25 index + caption index over whatever PDF window/outline is on hand,
 * resolves any cross-references, and returns either the resolved set or the
 * formatted `<resolved_cross_references>` / `<unresolved_cross_references>`
 * blocks.
 */
import { buildCitationsBlock, resolveSelectionCitations } from "./citationContext";
import { buildProvenance, type ProvenanceRecord } from "./provenance";
import { PdfDocumentIndexService } from "./pdfDocumentIndex";
import {
  buildCaptionIndex,
  buildResolvedReferencesBlock,
  extractReferences,
  inferPrintedPageOffset,
  outlineNumberCandidates,
  printedHeaderCandidates,
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
const DIRECT_FETCH_ROUND_LIMIT = 3;
// Bounded so a bad locator hit list cannot turn one question into dozens of
// backend page fetches.
const DOCUMENT_WIDE_EQUATION_PAGE_LIMIT = 3;

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
  /**
   * Stable per-document identity for caches that are NOT the search index.
   *
   * `searchDocumentId` exists only where a BM25 index was built, which is the
   * custom PDF viewer via the popover — so keying the bibliography cache on it
   * alone silently disabled citation resolution for the chat sidebar and for
   * Obsidian's own PDF viewer. Callers that have a durable identity (content
   * hash, Zotero key, path) supply it here; it is never used for the index, so
   * it cannot perturb search behaviour.
   */
  documentKey?: string;
}

function mapPrintedPageLabel(pageLabels: string[] | undefined, printed: number): number | undefined {
  if (!pageLabels?.length) return undefined;
  const wanted = String(printed);
  const index = pageLabels.findIndex((label) => String(label).trim() === wanted);
  return index >= 0 ? index + 1 : undefined;
}

function findPageByPrintedHeader(
  pageText: Map<number, string>,
  printed: number
): number | undefined {
  for (const [pageNum, text] of pageText) {
    if (printedHeaderCandidates(text).includes(printed)) return pageNum;
  }
  return undefined;
}

function outlineRangeForNumber(
  outline: PdfOutlineItem[],
  sectionNumber: string,
  pageCount: number | undefined,
  maxPages: number
): { start: number; end: number } | null {
  const wanted = sectionNumber.toUpperCase();
  const index = outline.findIndex((item) =>
    outlineNumberCandidates(item.title).includes(wanted)
  );
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

function failClosedUnresolvedAdjacentEquations(
  resolved: ResolvedReference[]
): ResolvedReference[] {
  return resolved.map((ref) =>
    needsAdjacentEquationExpansion(ref)
      ? {
          query: ref.query,
          label: ref.label,
          confidence: 0,
          method: "unresolved" as const,
        }
      : ref
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
    printedHeaderToPdf: (printed) => findPageByPrintedHeader(pageText, printed),
    pageOffset: inferPrintedPageOffset(pages),
    pageCount: source.pageCount,
  };
  return resolveReferences(refs, ctx);
}

/**
 * Convenience: resolve and format in one call.
 *
 * Returns "" only when the selection contained no reference to resolve. When
 * references were found but none could be delivered, the result is a non-empty
 * `<unresolved_cross_references>` block naming them — an empty string is NOT
 * the "nothing to show" signal it used to be.
 */
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
 * Bounded multi-pass approach (direct-fetch rounds are capped) that keeps all
 * resolvers synchronous; only the outer wrapper is async.
 */
export async function resolveSelectionReferencesAsync(
  selectedText: string,
  source: PdfReferenceSource | undefined,
  fetchPageText: (pageNum: number) => Promise<string | undefined>,
  /**
   * Locate a label anywhere in the document, not just near the current page.
   *
   * The adjacent probe below only looks at currentPage +/-2. Ask about
   * equation (24) while reading page 1 of a 30-page paper and it is never
   * probed, the reference fails closed, and the provider is left to find the
   * page with its own tool call — which a headless CLI provider cannot do,
   * surfacing as "no output produced ... auto-denied".
   *
   * Optional: callers without a backend simply keep the old behaviour.
   */
  locatePages?: (label: string) => Promise<number[]>
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

  const buildCtx = (): ResolveContext => {
    const knownPages = Array.from(pageTextMap.entries()).map(
      ([pageNum, text]) => ({ pageNum, text })
    );
    return {
      outline,
      currentPage: source.pageNum ?? 1,
      captionIndex: buildCaptionIndex(knownPages),
      searchPages: (query, topK) => index.search(searchDocId, query, { topK }),
      getPageText: (pageNum) => pageTextMap.get(pageNum),
      printedToPdf: (printed) => mapPrintedPageLabel(source.pageLabels, printed),
      printedHeaderToPdf: (printed) => findPageByPrintedHeader(pageTextMap, printed),
      pageOffset: inferPrintedPageOffset(knownPages),
      pageCount: source.pageCount,
    };
  };

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
  // Bounded round loop because one fetch can *relocate* a target: a fetched
  // identity-guess page whose printed header contradicts the locator flips to
  // unresolved and contributes header-derived repair candidates
  // (printed + observed delta), which the next round fetches and verifies via
  // the printed-header scan. Headers on fetched pages also feed offset
  // inference, so re-resolution converges instead of looping.
  const withinDocument = (pageNum: number): boolean =>
    pageNum > 0 &&
    (typeof source.pageCount !== "number" ||
      source.pageCount <= 0 ||
      pageNum <= source.pageCount);

  let changed = false;
  let latest = pass1;
  for (let round = 0; round < DIRECT_FETCH_ROUND_LIMIT; round++) {
    const wanted = new Set<number>();
    for (const r of latest) {
      if (
        r.method !== "unresolved" &&
        !isWeakCurrentPageHit(r, source.pageNum) &&
        r.targetPage !== undefined &&
        !pageTextMap.has(r.targetPage)
      ) {
        wanted.add(r.targetPage);
      }
      if (
        r.query.kind === "page" &&
        r.method === "unresolved" &&
        typeof r.query.printedPage === "number"
      ) {
        const printed = r.query.printedPage;
        const identityText = pageTextMap.get(printed);
        if (!identityText) continue;
        const headers = printedHeaderCandidates(identityText);
        // Repair only a *contradicted* identity guess. Hint transfer also
        // marks consumed-but-valid page refs "unresolved"; a page whose own
        // header confirms the locator must not spawn repairs from incidental
        // digits on that page.
        if (headers.length === 0 || headers.includes(printed)) continue;
        for (const header of headers) {
          const repair = printed + (printed - header);
          if (repair !== printed && withinDocument(repair) && !pageTextMap.has(repair)) {
            wanted.add(repair);
          }
        }
      }
    }
    if (wanted.size === 0) break;
    const roundChanged = await fetchPages(orderedUniquePages(wanted));
    changed = changed || roundChanged;
    if (!roundChanged) break;
    latest = resolveReferences(refs, buildCtx());
  }

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

  // The adjacent probe is bounded to +/-2 pages, so a reference to a distant
  // equation is still unresolved here. Ask the backend where that label lives
  // in the whole document and fetch exactly those pages. Without this the
  // reference fails closed and the provider must find the page itself, which a
  // headless CLI provider cannot do.
  if (locatePages && latest.some(needsAdjacentEquationExpansion)) {
    const pending = latest.filter(needsAdjacentEquationExpansion);
    for (const ref of pending) {
      const objectNumber = ref.query.objectNumber ?? "";
      if (!objectNumber) continue;
      let located: number[] = [];
      try {
        located = await locatePages(ref.label || objectNumber);
      } catch {
        located = [];
      }
      const fresh = orderedUniquePages(located).filter(
        (pageNum) => withinDocument(pageNum) && !pageTextMap.has(pageNum)
      );
      if (fresh.length === 0) continue;
      const locatedChanged = await fetchPages(
        fresh.slice(0, DOCUMENT_WIDE_EQUATION_PAGE_LIMIT)
      );
      changed = changed || locatedChanged;
      if (!locatedChanged) continue;
      latest = resolveReferences(refs, buildCtx());
      if (!latest.some(needsAdjacentEquationExpansion)) return latest;
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
    return failClosedUnresolvedAdjacentEquations(
      pass1.map((r) =>
        r.method !== "unresolved" && r.targetPage !== undefined && !pageTextMap.has(r.targetPage)
          ? { ...r, method: "unresolved" as const }
          : r
      )
    );
  }

  return failClosedUnresolvedAdjacentEquations(latest);
}

/**
 * Async convenience wrapper: resolve, fetch missing pages, format.
 *
 * Returns "" only when the selection contained neither a reference nor a
 * resolvable citation — see {@link resolveSelectionReferencesBlock} on why ""
 * no longer means "nothing resolved". A selection whose only hit is a citation
 * still returns a non-empty block, so a caller MUST NOT read "" as "no
 * cross-reference was found".
 */
export async function resolveSelectionReferencesBlockAsync(
  selectedText: string,
  source: PdfReferenceSource | undefined,
  fetchPageText: (pageNum: number) => Promise<string | undefined>,
  locatePages?: (label: string) => Promise<number[]>,
  /**
   * The question the reader typed. Forwarded, because omitting it here is how the
   * popover got the "ask about the bibliography with no bracket" fallback and the
   * chat sidebar did not — the same feature working on one surface and silently
   * absent on the other, which is the shape this whole release keeps finding.
   */
  question?: string
): Promise<string> {
  return (
    await resolveSelectionContextAsync(
      selectedText,
      source,
      fetchPageText,
      locatePages,
      question
    )
  ).block;
}

/**
 * Resolve once, return BOTH the prompt block and the provenance record.
 *
 * `resolveSelectionReferencesBlockAsync` above returns only the block, which is
 * all the prompt needs. But §13.9 requires provenance to be built from the
 * resolution record rather than recovered from model output, and that record
 * exists only here — discarding it and reconstructing it later is precisely the
 * output-scanning design §13.9 rejects. So the record is returned alongside.
 */
export async function resolveSelectionContextAsync(
  selectedText: string,
  source: PdfReferenceSource | undefined,
  fetchPageText: (pageNum: number) => Promise<string | undefined>,
  locatePages?: (label: string) => Promise<number[]>,
  /**
   * The question the reader typed, when there is one.
   *
   * Citation resolution reads it alongside the selection. The popover used to
   * pass only the highlight, so a typed "reference 12의 제목이 뭐야?" resolved
   * nothing and the paper's own bibliography never reached the model.
   */
  question?: string
): Promise<{ block: string; provenance: ProvenanceRecord }> {
  // Citations resolve alongside the cross-references, in the same pre-turn
  // pass and on the same fetcher, so the model gets both in one prompt and
  // spends no tool rounds chasing either (plan §4.2).
  //
  // Both surfaces funnel through here, but funnelling is not enough on its own:
  // the bibliography cache needs a per-document key, and the first version keyed
  // it on `searchDocumentId`, which only the custom viewer's popover path sets.
  // Citations were therefore skipped in silence for the chat sidebar and for
  // Obsidian's native PDF viewer. `documentKey` is the fallback identity.
  const [resolved, citations] = await Promise.all([
    // The question counts here too, not just the selection. Asking "Fig. 4가
    // 뭐야?" without highlighting the pointer resolved nothing, while the same
    // words highlighted resolved fine. The citation path had exactly this gap and
    // it was the reported bug; this is the same gap in the sibling resolver.
    resolveSelectionReferencesAsync(
      [selectedText || "", question || ""].filter(Boolean).join("\n"),
      source,
      fetchPageText,
      locatePages
    ),
    resolveSelectionCitations(
      selectedText,
      source?.searchDocumentId || source?.documentKey
        ? {
            documentId: source.searchDocumentId ?? source.documentKey ?? "",
            pageCount: source.pageCount,
            knownPages: source.windowPages?.map((page) => ({
              pageNum: page.pageNum,
              text: page.text,
            })),
          }
        : undefined,
      fetchPageText,
      question
    ),
  ]);
  const block = [buildResolvedReferencesBlock(resolved), buildCitationsBlock(citations)]
    .filter(Boolean)
    .join("\n");
  return { block, provenance: buildProvenance(resolved, citations) };
}
