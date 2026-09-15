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
  asksAboutBibliography,
  BIBLIOGRAPHY_HEADING,
  collectBibliography,
  resolveCitations,
  type ResolvedCitation,
} from "./citationResolver";

/** Pages to scan backward from the end looking for the heading. */
const TAIL_SCAN_PAGES = 6;
/**
 * How deep to scan back from the end, for a document of `pageCount` pages.
 *
 * Six pages is right for a paper, whose references sit at the very end. A book
 * puts an index — often twenty pages or more — AFTER its bibliography, so a
 * fixed six never reaches the heading and the reader gets nothing, on the
 * document kind where looking a reference up by hand is most tedious.
 *
 * Proportional with a floor and a ceiling: the floor keeps papers cheap, the
 * ceiling keeps a 900-page book from scanning half of itself. Ten percent
 * clears the twenty-to-thirty page index a technical book puts after its
 * references. The scan stops at the first heading-anchored parse, and the result
 * is cached per document, so the ceiling is a worst case paid once — not a cost
 * per question.
 * Scanning stops at the first heading-anchored parse either way, so the depth is
 * a bound, not a cost.
 */
function tailScanDepth(pageCount: number | undefined): number {
  if (!pageCount || pageCount <= 0) return TAIL_SCAN_PAGES;
  return Math.min(40, Math.max(TAIL_SCAN_PAGES, Math.ceil(pageCount * 0.1)));
}
/**
 * Pages to follow forward once the heading is found.
 *
 * Five covers a paper, whose reference list is a page or two. A book's runs for
 * ten or more, so a fixed five found the heading and then stopped inside the
 * A's — the reader asking about entry 90 got nothing, having paid for the scan
 * that located the section. Scaled the same way the tail scan is, and for the
 * same reason.
 */
const CONTINUATION_PAGES = 5;

function continuationDepth(pageCount: number | undefined): number {
  if (!pageCount || pageCount <= 0) return CONTINUATION_PAGES;
  return Math.min(20, Math.max(CONTINUATION_PAGES, Math.ceil(pageCount * 0.03)));
}

interface CacheEntry {
  bibliography: Map<number, string>;
  pages: Array<{ pageNum: number; text: string }>;
  attemptedPages: number[];
  failedPages: number[];
}

const cache = new Map<string, { coverageKey: string; result: CacheEntry }>();

/** Drop a document's cached bibliography. Exported for tests and reloads. */
export function forgetBibliography(documentId: string): void {
  cache.delete(documentId);
}

export interface CitationSource {
  documentId: string;
  pageCount?: number;
  /** Pages already loaded, used before any fetch is attempted. */
  knownPages?: Array<{ pageNum: number; text: string }>;
  outline?: Array<{ title: string; pageNum?: number }>;
}

export interface BibliographyResolution {
  citations: ResolvedCitation[];
  block: string;
  pages: Array<{ pageNum: number; text: string }>;
  attemptedPages: number[];
  failedPages: number[];
}

/**
 * Resolve the citations in `selectedText` against the document's bibliography,
 * fetching and caching that bibliography on first use.
 *
 * Returns `[]` for the overwhelmingly common case of a selection with no
 * citations — and does so WITHOUT fetching anything, because the cheap check
 * (does the selection contain a resolvable bracket at all?) runs first.
 */
/** Entries returned when the question asks for the reference list wholesale. */
const MAX_WHOLE_BIBLIOGRAPHY_ENTRIES = 40;

export async function resolveSelectionCitations(
  selectedText: string,
  source: CitationSource | undefined,
  fetchPageText: (pageNum: number) => Promise<string | undefined>,
  question?: string
): Promise<ResolvedCitation[]> {
  return (await resolveSelectionBibliography(selectedText, source, fetchPageText, question)).citations;
}

export async function resolveSelectionBibliography(
  selectedText: string,
  source: CitationSource | undefined,
  fetchPageText: (pageNum: number) => Promise<string | undefined>,
  question?: string
): Promise<BibliographyResolution> {
  const empty: BibliographyResolution = { citations: [], block: "", pages: [], attemptedPages: [], failedPages: [] };
  if (!source?.documentId) return empty;

  // The question counts, not just the selection.
  //
  // Until v0.77.0 only `selectedText` was read here, so someone who typed
  // "reference 12의 제목이 뭐야?" without re-selecting the bracket resolved
  // nothing — and the answer was in the paper's own last pages. The chat sidebar
  // had always passed its typed message; the popover passed only the highlight.
  const asksForList = asksAboutBibliography(question ?? "");
  const searchText = [selectedText || "", question || ""].filter(Boolean).join("\n");
  if (!searchText && !asksForList) return empty;

  // Cheapest possible early-out: if nothing here could ever be a citation, never
  // touch the document. Probing with a sentinel bibliography reuses the real
  // collision rules instead of duplicating them. Skipped when the question asks
  // for the list itself, which names no bracket by definition.
  if (!asksForList && resolveCitations(searchText, PROBE).length === 0) return empty;

  const loaded = await loadBibliography(source, fetchPageText);
  const bibliography = loaded.bibliography;

  // Explicit prose numbers identify the requested entry before the general-list
  // cap. Ordinary bracket/code collision handling remains in resolveCitations.
  const named = Array.from((question ?? "").matchAll(
    /(?:\b(?:references?|citations?|ref)\s*\.?\s*(?:no\.?\s*)?|참\s*고\s*문\s*헌\s*|参考文献\s*の?\s*)\[?(\d{1,3})(?!\d)/gi
  ), match => `[${match[1]}]`).join(" ");
  const matched = resolveCitations([searchText, named].join("\n"), bibliography);

  // Asked about the reference list, named no bracket. Hand over the list itself
  // rather than nothing: "what is reference 12" is answerable from it, and so is
  // every other phrasing of the same request. Bounded, because a bibliography can
  // run to hundreds of entries and this rides in a popover prompt.
  const citations = matched.length || !asksForList ? matched : Array.from(bibliography.entries())
    .sort((a, b) => a[0] - b[0])
    .slice(0, MAX_WHOLE_BIBLIOGRAPHY_ENTRIES)
    .map(([num, entry]) => ({ num, label: `[${num}]`, entry }));
  const raw = asksForList ? buildBibliographyPagesBlock(loaded) : "";
  return { citations, block: [buildCitationsBlock(citations), raw].filter(Boolean).join("\n"),
    pages: loaded.pages, attemptedPages: loaded.attemptedPages, failedPages: loaded.failedPages };
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
): Promise<CacheEntry> {
  const texts = new Map<number, string>();
  for (const page of source.knownPages ?? []) texts.set(page.pageNum, page.text);

  const lastPage = source.pageCount ?? Math.max(0, ...texts.keys());
  // Document identity alone cannot validate scan coverage: native DOM metadata
  // can grow from page7 to the authoritative eleven pages, and a late outline
  // can reveal a References heading outside the previous tail window. Invalidate
  // positive as well as negative results when either search boundary changes.
  const coverageKey = JSON.stringify([lastPage, source.pageCount !== undefined,
    (source.outline ?? []).filter(item => BIBLIOGRAPHY_HEADING.test(item.title))
      .map(item => [item.title, item.pageNum])]);
  const hit = cache.get(source.documentId);
  if (hit?.coverageKey === coverageKey) return hit.result;
  const result = lastPage > 0
    ? await scanForBibliography(lastPage, texts, fetchPageText, source.outline)
    : { bibliography: new Map<number, string>(), pages: [], attemptedPages: [], failedPages: [] };

  // An unavailable page is not an empty page. In particular a good heading
  // followed by a failed continuation must remain retryable on the next turn.
  if (lastPage > 0 && result.failedPages.length === 0) cache.set(source.documentId, { coverageKey, result });
  return result;
}

async function scanForBibliography(
  lastPage: number,
  texts: Map<number, string>,
  fetchPageText: (pageNum: number) => Promise<string | undefined>,
  outline: CitationSource["outline"]
): Promise<CacheEntry> {
  const attemptedPages: number[] = [];
  const failedPages: number[] = [];
  const textOf = async (pageNum: number): Promise<string> => {
    if (!attemptedPages.includes(pageNum)) attemptedPages.push(pageNum);
    const known = texts.get(pageNum);
    if (known !== undefined) return known;
    const fetched = await fetchPageText(pageNum).catch(() => undefined);
    if (fetched === undefined) failedPages.push(pageNum);
    const text = fetched ?? "";
    texts.set(pageNum, text);
    return text;
  };

  const firstToScan = Math.max(1, lastPage - tailScanDepth(lastPage) + 1);
  const outlinePages = (outline ?? []).filter(item => BIBLIOGRAPHY_HEADING.test(item.title))
    .map(item => item.pageNum).filter((n): n is number => Number.isInteger(n) && n! > 0 && n! <= lastPage);
  const candidates = new Set([...outlinePages,
    ...Array.from({ length: lastPage - firstToScan + 1 }, (_, i) => firstToScan + i)]);
  for (const start of candidates) {
    const first = await textOf(start);
    const heading = BIBLIOGRAPHY_HEADING.exec(first);
    if (!heading) continue;
    const pages: CacheEntry["pages"] = [];
    const window: string[] = [];
    // Preserve exact heading-anchored source text independently of numbered
    // parsing, so author-year lists remain answerable without invented entries.
    for (let next = start; next <= Math.min(lastPage, start + continuationDepth(lastPage)); next += 1) {
      const text = next === start ? first.slice(heading.index) : await textOf(next);
      const section = /^\s*(?:appendix\b|supplementary\s+(?:material|information)\b)/im.exec(text);
      const excerpt = section ? text.slice(0, section.index) : text;
      window.push(excerpt);
      if (excerpt.trim()) pages.push({ pageNum: next, text: excerpt });
      if (section || (text === "" && !failedPages.includes(next))) break;
    }
    return { bibliography: collectBibliography(window), pages, attemptedPages, failedPages };
  }
  return { bibliography: new Map(), pages: [], attemptedPages, failedPages };
}

function buildBibliographyPagesBlock(result: CacheEntry): string {
  const pages = result.pages.map(page => {
    const clipped = page.text.length > 6000;
    const text = clipped ? `${page.text.slice(0, 6000)}\n[bibliography page ${page.pageNum} excerpt clipped]` : page.text;
    return `<bibliography_page page="${page.pageNum}" clipped="${clipped}">\n${text}\n</bibliography_page>`;
  }).join("\n");
  return `<bibliography_lookup read_pages="${result.attemptedPages.filter(n => !result.failedPages.includes(n)).join(",")}" failed_pages="${result.failedPages.join(",")}" coverage="bounded search; not whole document">\n` +
    pages + "\n</bibliography_lookup>";
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
