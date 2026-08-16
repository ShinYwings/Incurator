/**
 * Finding the bibliography, and caching it (v0.56.0).
 *
 * `citationResolver` is pure: give it page text, it gives you entries. This
 * module answers the operational question — *which* pages, and how often.
 *
 * Two measurements shape it, both from the motivating paper:
 *
 *  - The References section is at the END. Scanning forward from page 1 would
 *    read the whole paper to find it; scanning backward from the last page
 *    found it in one page.
 *  - It SPANS pages and prints its heading once — p.24 heading + entries 1–28,
 *    then p.25 and p.26 carry 35 and 32 more with no heading. Stopping at the
 *    heading page finds 28 of 110.
 *
 * Caching is not an optimisation here, it is the difference between usable and
 * not: without it every popover question would re-fetch and re-parse several
 * pages before the model sees anything.
 */
import {
  collectBibliography,
  resolveCitations,
  type ResolvedCitation,
} from "./citationResolver";

/** Pages to scan backward from the end looking for the heading. */
const TAIL_SCAN_PAGES = 6;
/** Pages to follow forward once the heading is found. */
const CONTINUATION_PAGES = 5;

interface CacheEntry {
  bibliography: Map<number, string>;
  /** Present but empty means "looked, found nothing" — do not look again. */
  searched: true;
}

const cache = new Map<string, CacheEntry>();

/** Drop a document's cached bibliography. Exported for tests and reloads. */
export function forgetBibliography(documentId: string): void {
  cache.delete(documentId);
}

export interface CitationSource {
  documentId: string;
  pageCount?: number;
  /** Pages already loaded, used before any fetch is attempted. */
  knownPages?: Array<{ pageNum: number; text: string }>;
}

/**
 * Resolve the citations in `selectedText` against the document's bibliography,
 * fetching and caching that bibliography on first use.
 *
 * Returns `[]` for the overwhelmingly common case of a selection with no
 * citations — and does so WITHOUT fetching anything, because the cheap check
 * (does the selection contain a resolvable bracket at all?) runs first.
 */
export async function resolveSelectionCitations(
  selectedText: string,
  source: CitationSource | undefined,
  fetchPageText: (pageNum: number) => Promise<string | undefined>
): Promise<ResolvedCitation[]> {
  if (!selectedText || !source?.documentId) return [];

  // Cheapest possible early-out: if nothing in the selection could ever be a
  // citation, never touch the document. Probing with a sentinel bibliography
  // reuses the real collision rules instead of duplicating them here.
  if (resolveCitations(selectedText, PROBE).length === 0) return [];

  const bibliography = await loadBibliography(source, fetchPageText);
  if (bibliography.size === 0) return [];
  return resolveCitations(selectedText, bibliography);
}

/**
 * A bibliography that "contains" every plausible citation number, used only to
 * ask the extractor whether the selection holds anything worth a fetch.
 */
const PROBE: Map<number, string> = new Map(
  Array.from({ length: 999 }, (_, i) => [i + 1, "probe"])
);

async function loadBibliography(
  source: CitationSource,
  fetchPageText: (pageNum: number) => Promise<string | undefined>
): Promise<Map<number, string>> {
  const hit = cache.get(source.documentId);
  if (hit) return hit.bibliography;

  const texts = new Map<number, string>();
  for (const page of source.knownPages ?? []) texts.set(page.pageNum, page.text);

  const lastPage = source.pageCount ?? Math.max(0, ...texts.keys());
  const bibliography = lastPage > 0
    ? await scanForBibliography(lastPage, texts, fetchPageText)
    : new Map<number, string>();

  cache.set(source.documentId, { bibliography, searched: true });
  return bibliography;
}

async function scanForBibliography(
  lastPage: number,
  texts: Map<number, string>,
  fetchPageText: (pageNum: number) => Promise<string | undefined>
): Promise<Map<number, string>> {
  const textOf = async (pageNum: number): Promise<string> => {
    const known = texts.get(pageNum);
    if (known !== undefined) return known;
    const fetched = await fetchPageText(pageNum).catch(() => undefined);
    const text = fetched ?? "";
    texts.set(pageNum, text);
    return text;
  };

  const firstToScan = Math.max(1, lastPage - TAIL_SCAN_PAGES + 1);
  for (let start = firstToScan; start <= lastPage; start += 1) {
    const window: string[] = [await textOf(start)];
    // Cheap pre-check: only pay for continuation pages once this page alone
    // yields a heading-anchored parse.
    if (collectBibliography(window).size === 0) continue;

    for (let next = start + 1; next <= Math.min(lastPage, start + CONTINUATION_PAGES); next += 1) {
      window.push(await textOf(next));
    }
    return collectBibliography(window);
  }
  return new Map();
}

/** Render resolved citations as a context block for the model. */
export function buildCitationsBlock(citations: ResolvedCitation[]): string {
  if (citations.length === 0) return "";
  const body = citations
    .map((c) => `<citation label="${c.label}">\n${c.entry}\n</citation>`)
    .join("\n");
  return (
    `<resolved_citations note="The selection cites these works; each entry is ` +
    `the bibliography line it resolves to. Explain the cited work when the ` +
    `question is about it.">\n${body}\n</resolved_citations>`
  );
}
