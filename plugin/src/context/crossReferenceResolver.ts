/**
 * Cross-reference resolver for the reading assistant.
 *
 * When the user selects/crops a passage that is itself a *pointer* — e.g.
 * "see section A4.2 (p580) for Jacobi's algorithm" or a cropped "Figure 19.1"
 * caption — the assistant must follow that pointer: detect the reference,
 * resolve it to a target page/section in the document, and fetch the target's
 * text so the model explains the *referenced* content rather than the visible
 * page.
 *
 * Prior art this mirrors (see `.agents/plans/2026-06-06_reading_assistant_crossref_toc.md`):
 *   - AllenAI ScholarPhi (arXiv 2009.14237): position-sensitive resolution —
 *     when a reference is ambiguous, prefer the most recent qualifying target
 *     appearing *before* the usage. We approximate "before the usage" with the
 *     reader's current page.
 *   - Macro PDF / Semantic Reader: resolve a label (Section/Figure/Eq) to a
 *     target location via a structure index, with graceful fallback to search.
 *
 * Everything here is pure and unit-testable. Resolution takes its document
 * knowledge (outline, page search, current page) as an explicit context object
 * so it works for both the in-memory plugin index and (later) a backend index.
 */
import type { PdfOutlineItem, PdfRagHit } from "../types";

export type ReferenceKind =
  | "page"
  | "section"
  | "chapter"
  | "appendix"
  | "figure"
  | "table"
  | "equation"
  | "theorem";

export interface ReferenceQuery {
  kind: ReferenceKind;
  /** Human-readable label, e.g. "Section A4.2", "Figure 19.1", "p.580". */
  label: string;
  /** Exact matched substring of the selection. */
  raw: string;
  /** Character offset of the match within the selection. */
  index: number;
  printedPage?: number;
  printedPageEnd?: number;
  /** For section/chapter/appendix references, e.g. "A4.2", "19.3.4". */
  sectionNumber?: string;
  /** For figure/table/equation/theorem references, e.g. "19.1". */
  objectNumber?: string;
}

export type ResolveMethod =
  | "explicit-page"
  | "outline-section"
  | "caption-index"
  | "bm25-object"
  | "bm25-section"
  | "unresolved";

/** A line-anchored caption/heading that *defines* a numbered object. */
export interface CaptionEntry {
  kind: ReferenceKind;
  number: string;
  pageNum: number;
  line: string;
}

export interface ResolveContext {
  outline: PdfOutlineItem[];
  /** BM25 page search over the in-memory document index. */
  searchPages: (query: string, topK?: number) => PdfRagHit[];
  /** Fetch a page's full text (for the injected snippet). */
  getPageText?: (pageNum: number) => string | undefined;
  /** The reader's current page — used for position-sensitive disambiguation. */
  currentPage: number;
  /**
   * Line-anchored caption/definition index (sioyek-style). When present it is
   * preferred over question/label BM25 for numbered objects because it pins the
   * *caption* page rather than any page that merely mentions the object.
   */
  captionIndex?: CaptionEntry[];
  /** Front-matter offset so that pdfIndex = printedPage + pageOffset. */
  pageOffset?: number;
  /** Explicit printed→pdf page map (from pdf.js pageLabels), preferred over pageOffset. */
  printedToPdf?: (printed: number) => number | undefined;
  /**
   * Scan of already-known page texts: returns the pdf page whose extracted
   * printed header equals `printed`. Direct textual evidence — consulted after
   * printedToPdf/pageOffset but before the unverified identity guess.
   */
  printedHeaderToPdf?: (printed: number) => number | undefined;
  /** Physical page count, used to accept explicit page locators as fetchable pages. */
  pageCount?: number;
}

export interface ResolvedReference {
  query: ReferenceQuery;
  label: string;
  targetPage?: number;
  sectionTitle?: string;
  snippet?: string;
  confidence: number;
  method: ResolveMethod;
  /**
   * This page reference RESOLVED, but its page text was folded into a nearby
   * sibling reference, so it must not be rendered a second time on its own.
   *
   * `resolveWithNearbyPageHints` marks such a reference `method: "unresolved"`
   * to suppress that duplicate render. That overloads one value with two
   * meanings — "we found nothing" and "we found it and showed it elsewhere" —
   * which was harmless only while every unresolved entry was silently dropped.
   * Once unresolved references started being NAMED to the model, the overload
   * began asserting that a page whose text is quoted verbatim in
   * `<resolved_cross_references>` is absent from the document. This flag keeps
   * the two apart. The fetch and identity-repair paths in
   * `pdfReferenceContext.ts` still read `method`, whose meaning is unchanged.
   */
  consumedBySibling?: boolean;
}

const SNIPPET_LIMIT = 1800;

// ── Extraction ────────────────────────────────────────────────────

interface PatternSpec {
  kind: ReferenceKind;
  re: RegExp;
  build: (m: RegExpExecArray) => Partial<ReferenceQuery> & { label: string };
}

const RANGE = "(?:\\s*[\\-\\u2013\\u2014]\\s*(\\d{1,4}))?";

const PATTERNS: PatternSpec[] = [
  // Explicit page: p580, p. 580, pp. 580–582
  {
    kind: "page",
    re: new RegExp(`\\b(pp?)\\.?\\s*(\\d{1,4})${RANGE}`, "gi"),
    build: (m) => ({
      label: `p.${m[2]}`,
      printedPage: Number(m[2]),
      printedPageEnd: m[3] ? Number(m[3]) : undefined,
    }),
  },
  // page 580 / pages 580-582
  {
    kind: "page",
    re: new RegExp(`\\bpages?\\s+(\\d{1,4})${RANGE}`, "gi"),
    build: (m) => ({
      label: `p.${m[1]}`,
      printedPage: Number(m[1]),
      printedPageEnd: m[2] ? Number(m[2]) : undefined,
    }),
  },
  // Section A4.2 / Sec. 19.3.4 / §19.3
  {
    kind: "section",
    re: /\b(?:sections?|sec)\.?\s*([A-Z]?\d+(?:\.\d+)*)/gi,
    build: (m) => ({ label: `Section ${m[1]}`, sectionNumber: m[1].toUpperCase() }),
  },
  {
    kind: "section",
    re: /§\s*([A-Z]?\d+(?:\.\d+)*)/g,
    build: (m) => ({ label: `Section ${m[1]}`, sectionNumber: m[1].toUpperCase() }),
  },
  // Appendix A4 / Appendix A4.2
  {
    kind: "appendix",
    re: /\b(?:appendix|appendices)\s*([A-Z]\d*(?:\.\d+)*)/gi,
    build: (m) => ({ label: `Appendix ${m[1]}`, sectionNumber: m[1].toUpperCase() }),
  },
  // Chapter 5
  {
    kind: "chapter",
    re: /\b(?:chapters?|chap)\.?\s*(\d+(?:\.\d+)*)/gi,
    build: (m) => ({ label: `Chapter ${m[1]}`, sectionNumber: m[1] }),
  },
  // Figure 19.1 / Fig. 19.1
  {
    kind: "figure",
    re: /\b(?:figures?|figs?)\.?\s*(\d+(?:\.\d+)*)/gi,
    build: (m) => ({ label: `Figure ${m[1]}`, objectNumber: m[1] }),
  },
  // Table 3
  {
    kind: "table",
    re: /\b(?:tables?|tbls?)\.?\s*(\d+(?:\.\d+)*)/gi,
    build: (m) => ({ label: `Table ${m[1]}`, objectNumber: m[1] }),
  },
  // Eq. (19.6) / Equation 19.4
  {
    kind: "equation",
    re: /(?:\b(?:equations?|eqs?|eqn)\.?|수식)\s*\(?(\d+(?:\.\d+)*)\)?/gi,
    build: (m) => ({ label: `Equation ${m[1]}`, objectNumber: m[1] }),
  },
  // Bare equation label such as "(19.11)" in math prose.
  {
    kind: "equation",
    re: /(^|[\s,;:])\((\d+(?:\.\d+)+)\)/g,
    build: (m) => ({ label: `Equation ${m[2]}`, objectNumber: m[2] }),
  },
  // Theorem 2 / Lemma 5.1 / Corollary 1 / Result 19.4 / Result A4.1
  {
    kind: "theorem",
    re: /\b(?:theorems?|lemmas?|corollar(?:y|ies)|propositions?|prop|definitions?|results?|claims?|conjectures?)\.?\s*([A-Z]?\d+(?:\.\d+)*)/gi,
    build: (m) => ({ label: m[0].trim(), objectNumber: m[1].toUpperCase() }),
  },
];

/** Detect every cross-reference inside a selected/cropped passage. */
export function extractReferences(selectedText: string): ReferenceQuery[] {
  if (!selectedText) return [];
  const matches: ReferenceQuery[] = [];
  for (const spec of PATTERNS) {
    spec.re.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = spec.re.exec(selectedText)) !== null) {
      const built = spec.build(m);
      matches.push({
        kind: spec.kind,
        index: m.index,
        raw: m[0],
        ...built,
      } as ReferenceQuery);
    }
  }

  // Sort by position, then drop matches whose span overlaps an already-kept,
  // more-specific match (longer raw text wins on a tie).
  matches.sort((a, b) => a.index - b.index || b.raw.length - a.raw.length);
  const kept: ReferenceQuery[] = [];
  for (const ref of matches) {
    const start = ref.index;
    const end = ref.index + ref.raw.length;
    const overlaps = kept.some(
      (k) => start < k.index + k.raw.length && end > k.index
    );
    if (!overlaps) kept.push(ref);
  }
  return kept;
}

// ── Printed page headers / front-matter offset ────────────────────

const HEADER_SCAN_LINES = 3;
const LEADING_PAGE_NUMBER_RE = /^\s*(\d{1,4})(?![\d.])/;
const TRAILING_PAGE_NUMBER_RE = /(?<![\d.])(\d{1,4})\s*$/;

/**
 * Extract candidate printed page numbers from a page's header/footer region
 * (first and last few non-empty lines). Dotted section heads ("9.6 …") are
 * rejected by the lookarounds; a page may yield several candidates (e.g. a
 * chapter-opening number plus a folio) — consumers must apply consensus.
 */
export function printedHeaderCandidates(text: string): number[] {
  if (!text) return [];
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const edges = [
    ...lines.slice(0, HEADER_SCAN_LINES),
    ...lines.slice(Math.max(lines.length - HEADER_SCAN_LINES, HEADER_SCAN_LINES)),
  ];
  const candidates = new Set<number>();
  for (const line of edges) {
    const leading = LEADING_PAGE_NUMBER_RE.exec(line);
    if (leading) candidates.add(Number(leading[1]));
    const trailing = TRAILING_PAGE_NUMBER_RE.exec(line);
    if (trailing) candidates.add(Number(trailing[1]));
  }
  return Array.from(candidates);
}

/**
 * Infer the front-matter offset (pdfIndex = printedPage + offset) from the
 * printed numbers visible in known page texts. Consensus rule (Arena-locked):
 * the modal delta must be supported by ≥ 2 distinct pages AND by a strict
 * majority of the pages that yielded any candidate; ties fail closed.
 */
export function inferPrintedPageOffset(
  pages: { pageNum: number; text: string }[]
): number | undefined {
  const support = new Map<number, number>();
  let pagesWithCandidates = 0;
  for (const page of pages) {
    const candidates = printedHeaderCandidates(page.text);
    if (candidates.length === 0) continue;
    pagesWithCandidates++;
    const deltas = new Set(candidates.map((printed) => page.pageNum - printed));
    for (const delta of deltas) support.set(delta, (support.get(delta) ?? 0) + 1);
  }
  let best: number | undefined;
  let bestCount = 0;
  for (const [delta, count] of support) {
    if (count > bestCount) {
      best = delta;
      bestCount = count;
    }
  }
  if (best === undefined || bestCount < 2) return undefined;
  // Strict majority also rules out ties (two deltas cannot both exceed half).
  if (bestCount * 2 <= pagesWithCandidates) return undefined;
  return best;
}

// ── Caption / definition index (sioyek-style) ─────────────────────

const CAPTION_LINE_RE =
  /^\s*(figures?|figs?|tables?|tbls?|equations?|eqs?|eqn|수식|theorems?|lemmas?|sections?|results?|corollar(?:y|ies)|propositions?|prop|definitions?|claims?|conjectures?)\.?\s+([A-Z]?\d+(?:\.\d+)*[a-z]?)\b/i;
const DISPLAY_EQUATION_LABEL_RE = /(^|[\s,;:])\(([A-Z]?\d+(?:\.\d+)*)\)(?=$|[\s,.;:])/gi;
const DISPLAY_EQUATION_MATH_RE = /[=+\-*/^_{}]|\\[A-Za-z]+|[∑∫√≤≥≈≠]/u;

function captionKind(word: string): ReferenceKind {
  const w = word.toLowerCase();
  if (w.startsWith("fig")) return "figure";
  if (w.startsWith("tab") || w.startsWith("tbl")) return "table";
  if (w.startsWith("eq") || w === "수식") return "equation";
  if (w.startsWith("sec")) return "section";
  return "theorem";
}

/**
 * Scan per-page text for line-anchored captions/headings that *define* a
 * numbered object (e.g. a line beginning "Figure 19.1 ..."). Only the
 * definition site starts a line with the label; inline prose mentions do not,
 * so this index pins the true target page.
 */
export function buildCaptionIndex(
  pages: { pageNum: number; text: string }[]
): CaptionEntry[] {
  const entries: CaptionEntry[] = [];
  for (const page of pages) {
    if (!page.text) continue;
    const rawLines = page.text.split(/\r?\n/);
    for (let lineIndex = 0; lineIndex < rawLines.length; lineIndex++) {
      const rawLine = rawLines[lineIndex];
      const line = rawLine.trim();
      const m = CAPTION_LINE_RE.exec(rawLine);
      if (m) {
        entries.push({
          kind: captionKind(m[1]),
          number: m[2].toUpperCase(),
          pageNum: page.pageNum,
          line: line.slice(0, 360),
        });
      }

      DISPLAY_EQUATION_LABEL_RE.lastIndex = 0;
      let eq: RegExpExecArray | null;
      while ((eq = DISPLAY_EQUATION_LABEL_RE.exec(rawLine)) !== null) {
        const beforeLabel = rawLine.slice(0, eq.index + eq[1].length).trim();
        const singleNumber = !eq[2].includes(".");
        const standaloneLabel = line === `(${eq[2]})`;
        const previousLine = rawLines[lineIndex - 1]?.trim() ?? "";
        const looksLikeDisplayedMath =
          DISPLAY_EQUATION_MATH_RE.test(beforeLabel) ||
          (!singleNumber && beforeLabel.length === 0) ||
          (singleNumber && standaloneLabel && DISPLAY_EQUATION_MATH_RE.test(previousLine));
        if (!looksLikeDisplayedMath) continue;
        entries.push({
          kind: "equation",
          number: eq[2].toUpperCase(),
          pageNum: page.pageNum,
          line: line.slice(0, 360),
        });
      }
    }
  }
  return entries;
}

function findCaptionEntry(
  index: CaptionEntry[] | undefined,
  kind: ReferenceKind,
  number: string,
  currentPage: number
): CaptionEntry | undefined {
  if (!index?.length) return undefined;
  const want = number.toUpperCase();
  const matches = index.filter((e) => e.kind === kind && e.number === want);
  if (matches.length === 0) return undefined;
  return matches
    .slice()
    .sort(
      (a, b) =>
        positionalDistance(a.pageNum, currentPage) -
        positionalDistance(b.pageNum, currentPage)
    )[0];
}

// ── Outline / section-number helpers ──────────────────────────────

/** Parse the leading section/appendix number out of an outline title. */
function parseOutlineNumber(title: string): string | undefined {
  const m = /^\s*(?:appendix\s+)?([A-Z]?\d+(?:\.\d+)*)/i.exec(title);
  return m ? m[1].toUpperCase() : undefined;
}

/**
 * All numbers an outline title can answer to. "Appendix 4 …" additionally
 * aliases to "A4" because books label appendix objects "Result A4.1" while
 * the ToC entry keeps the bare digit. The alias is additive: a plain "4"
 * lookup still finds Chapter 4 first in document order.
 */
export function outlineNumberCandidates(title: string): string[] {
  const m = /^\s*(appendix\s+)?([A-Z]?\d+(?:\.\d+)*)/i.exec(title);
  if (!m) return [];
  const num = m[2].toUpperCase();
  return m[1] && /^\d/.test(num) ? [num, `A${num}`] : [num];
}

function sectionComponents(num: string): string[] {
  return num.toUpperCase().split(".");
}

/** Find the outline entry whose section number exactly matches `sectionNumber`. */
function matchOutlineBySectionNumber(
  sectionNumber: string,
  outline: PdfOutlineItem[]
): PdfOutlineItem | undefined {
  const want = sectionNumber.toUpperCase();
  return outline.find((item) => outlineNumberCandidates(item.title).includes(want));
}

/**
 * Resolve the section that *owns* a numbered object (Figure/Table/Eq).
 *
 * Fixes the item-4 bug where a cropped "Figure 19.1" got labeled with the
 * nearest preceding outline entry ("Section 19.3.4–19.3.5"). We instead:
 *   1. prefer an exact outline number match (19.1 -> "19.1 Introduction"),
 *   2. else the nearest preceding entry within the same chapter (≤ nearPage),
 *   3. else the chapter-level entry.
 */
export function resolveObjectOwningSection(
  objectNumber: string,
  outline: PdfOutlineItem[],
  nearPage?: number
): PdfOutlineItem | undefined {
  const exact = matchOutlineBySectionNumber(objectNumber, outline);
  if (exact) return exact;

  const chapter = sectionComponents(objectNumber)[0];
  const candidates = outline.filter((item) =>
    outlineNumberCandidates(item.title).some(
      (num) => sectionComponents(num)[0] === chapter
    )
  );
  if (candidates.length === 0) return undefined;

  if (typeof nearPage === "number") {
    const preceding = candidates
      .filter((item) => typeof item.pageNum === "number" && (item.pageNum as number) <= nearPage)
      .sort((a, b) => (b.pageNum || 0) - (a.pageNum || 0));
    if (preceding.length) return preceding[0];
  }

  // Most general (chapter-level) entry — fewest dotted components.
  return candidates
    .slice()
    .sort(
      (a, b) =>
        sectionComponents(parseOutlineNumber(a.title) || "z").length -
        sectionComponents(parseOutlineNumber(b.title) || "z").length
    )[0];
}

// ── Resolution ─────────────────────────────────────────────────────

function snippetFor(ctx: ResolveContext, pageNum: number, fallback?: string): string | undefined {
  const text = ctx.getPageText?.(pageNum) ?? fallback;
  if (!text) return undefined;
  const trimmed = text.trim();
  return trimmed.length > SNIPPET_LIMIT ? `${trimmed.slice(0, SNIPPET_LIMIT)}…` : trimmed;
}

/** Confidence from a BM25 hit's score relative to the best hit in the set. */
function bm25Confidence(hit: PdfRagHit, best: PdfRagHit): number {
  if (best.score <= 0) return 0.4;
  return Math.min(0.85, 0.45 + (hit.score / best.score) * 0.4);
}

/**
 * Position-sensitive hit selection (ScholarPhi heuristic). Among hits, prefer
 * the highest-scoring; break near-ties by proximity to the reader's current
 * page, favouring hits that appear *before* the current position.
 */
function pickHit(hits: PdfRagHit[], currentPage: number): PdfRagHit | undefined {
  if (hits.length === 0) return undefined;
  const best = hits[0];
  const contenders = hits.filter((h) => h.score >= best.score * 0.9);
  if (contenders.length === 1) return best;
  return contenders
    .slice()
    .sort((a, b) => {
      const da = positionalDistance(a.pageNum, currentPage);
      const db = positionalDistance(b.pageNum, currentPage);
      return da - db;
    })[0];
}

function positionalDistance(pageNum: number, currentPage: number): number {
  const delta = pageNum - currentPage;
  // Penalise forward references slightly so back-references win near-ties.
  return delta >= 0 ? delta * 1.15 : -delta;
}

function explicitPageTarget(ref: ReferenceQuery, ctx: ResolveContext): {
  pageNum?: number;
  confidence: number;
} {
  if (typeof ref.printedPage !== "number") return { confidence: 0.2 };
  const labeled = ctx.printedToPdf?.(ref.printedPage);
  if (typeof labeled === "number") return { pageNum: labeled, confidence: 0.9 };
  if (typeof ctx.pageOffset === "number") {
    return { pageNum: ref.printedPage + ctx.pageOffset, confidence: 0.75 };
  }
  // Direct textual evidence: a known page whose printed header matches.
  const scanned = ctx.printedHeaderToPdf?.(ref.printedPage);
  if (typeof scanned === "number") return { pageNum: scanned, confidence: 0.8 };
  // Verified identity guess (printed = physical): kept only while the target
  // page's own text does not contradict it. A page whose extracted header
  // names a different printed number must never be injected as this locator.
  if (ref.printedPage > 0 && (typeof ctx.pageCount !== "number" || ref.printedPage <= ctx.pageCount)) {
    const identityText = ctx.getPageText?.(ref.printedPage);
    if (identityText) {
      const printed = printedHeaderCandidates(identityText);
      if (printed.length > 0 && !printed.includes(ref.printedPage)) {
        return { confidence: 0.2 };
      }
    }
    return { pageNum: ref.printedPage, confidence: 0.65 };
  }
  return { confidence: 0.2 };
}

function resolveOne(ref: ReferenceQuery, ctx: ResolveContext): ResolvedReference {
  const base: ResolvedReference = {
    query: ref,
    label: ref.label,
    confidence: 0.2,
    method: "unresolved",
  };

  if (ref.kind === "page" && typeof ref.printedPage === "number") {
    const target = explicitPageTarget(ref, ctx);
    if (typeof target.pageNum === "number") {
      return {
        ...base,
        targetPage: target.pageNum,
        snippet: snippetFor(ctx, target.pageNum),
        confidence: target.confidence,
        method: "explicit-page",
      };
    }
    return base;
  }

  if (ref.kind === "section" || ref.kind === "chapter" || ref.kind === "appendix") {
    if (ref.sectionNumber) {
      const entry = matchOutlineBySectionNumber(ref.sectionNumber, ctx.outline);
      if (entry && typeof entry.pageNum === "number") {
        return {
          ...base,
          targetPage: entry.pageNum,
          sectionTitle: entry.title,
          snippet: snippetFor(ctx, entry.pageNum),
          confidence: 0.9,
          method: "outline-section",
        };
      }
      const hits = ctx.searchPages(`section ${ref.sectionNumber}`, 5);
      const hit = pickHit(hits, ctx.currentPage);
      if (hit) {
        return {
          ...base,
          targetPage: hit.pageNum,
          sectionTitle: hit.sectionTitle,
          snippet: snippetFor(ctx, hit.pageNum, hit.snippet),
          confidence: bm25Confidence(hit, hits[0]),
          method: "bm25-section",
        };
      }
    }
    return base;
  }

  // figure / table / equation / theorem -> resolve via the caption index first
  // (pins the definition page), then fall back to label BM25.
  if (ref.objectNumber) {
    const caption = findCaptionEntry(
      ctx.captionIndex,
      ref.kind,
      ref.objectNumber,
      ctx.currentPage
    );
    if (caption) {
      const owning = resolveObjectOwningSection(ref.objectNumber, ctx.outline, caption.pageNum);
      return {
        ...base,
        targetPage: caption.pageNum,
        sectionTitle: owning?.title,
        snippet: snippetFor(ctx, caption.pageNum, caption.line),
        confidence: 0.88,
        method: "caption-index",
      };
    }
    const hits = ctx.searchPages(ref.label, 5);
    const hit = pickHit(hits, ctx.currentPage);
    if (hit) {
      const owning = resolveObjectOwningSection(ref.objectNumber, ctx.outline, hit.pageNum);
      return {
        ...base,
        targetPage: hit.pageNum,
        sectionTitle: owning?.title ?? hit.sectionTitle,
        snippet: snippetFor(ctx, hit.pageNum, hit.snippet),
        confidence: bm25Confidence(hit, hits[0]),
        method: "bm25-object",
      };
    }
    // No caption hit, but we can still label the owning section from the number.
    const owning = resolveObjectOwningSection(ref.objectNumber, ctx.outline);
    if (owning) {
      return {
        ...base,
        targetPage: owning.pageNum,
        sectionTitle: owning.title,
        confidence: 0.4,
        method: "outline-section",
      };
    }
  }
  return base;
}

function resolveWithNearbyPageHints(
  resolved: ResolvedReference[],
  ctx: ResolveContext
): ResolvedReference[] {
  const out = resolved.map((r) => ({ ...r }));
  const consumedPageIndexes = new Set<number>();

  for (let i = 0; i < out.length; i++) {
    const ref = out[i];
    if (ref.method !== "unresolved" || ref.query.kind === "page") continue;

    let bestIndex = -1;
    let bestDistance = Infinity;
    for (let j = 0; j < out.length; j++) {
      const pageRef = out[j];
      if (
        pageRef.query.kind !== "page" ||
        pageRef.method !== "explicit-page" ||
        typeof pageRef.targetPage !== "number"
      ) {
        continue;
      }
      const distance = Math.abs(pageRef.query.index - ref.query.index);
      if (distance > 64 || distance >= bestDistance) continue;
      bestIndex = j;
      bestDistance = distance;
    }

    if (bestIndex < 0) continue;
    const pageRef = out[bestIndex];
    const pageNum = pageRef.targetPage as number;
    out[i] = {
      ...ref,
      targetPage: pageNum,
      snippet: snippetFor(ctx, pageNum, pageRef.snippet),
      confidence: Math.min(pageRef.confidence, 0.72),
      method: "explicit-page",
    };
    consumedPageIndexes.add(bestIndex);
  }

  for (const index of consumedPageIndexes) {
    // `method` stays "unresolved" so the fetch/repair paths keep behaving
    // exactly as before; `consumedBySibling` records WHY, so serialization can
    // tell a suppressed duplicate from a genuine miss.
    out[index] = { ...out[index], method: "unresolved", consumedBySibling: true };
  }
  return out;
}

export function resolveReferences(
  refs: ReferenceQuery[],
  ctx: ResolveContext
): ResolvedReference[] {
  return resolveWithNearbyPageHints(
    refs.map((ref) => resolveOne(ref, ctx)),
    ctx
  );
}

// ── Context-block formatting ───────────────────────────────────────

function escapeAttr(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

/**
 * Instruction carried on the unresolved block.
 *
 * The provider must be told not to go looking. A headless CLI provider cannot
 * prompt for the tool permission it would need to open the file, so an implied
 * "go read it yourself" is answered by the runtime with an auto-denial and the
 * user sees no answer at all.
 *
 * It says "could not be retrieved", never "confirmed absent". How hard the
 * plugin actually looked varies by call site: the quick-query popover passes no
 * `locatePages` at all, so nothing beyond the adjacent-page probe is ever
 * searched, and even where it IS wired the locator returns no pages when the
 * backend is offline. Asserting a verified absence the code did not establish
 * would make the model state a falsehood confidently — the wrong-context
 * failure this block exists to avoid, relocated from the snippet to the note.
 */
const UNRESOLVED_NOTE =
  "The verbatim text behind these references is not in this context (commonly " +
  "a rasterized equation or figure, or a page outside the loaded range). " +
  "A rasterized target is not missing from the paper, only from its text " +
  "layer: if a tool for reading a page as an image is available to you, that " +
  "is what it is for, so call it on the page the reference points to before " +
  "settling for less. Where no such tool is available, describe these targets " +
  "from what the supplied material establishes about them. This note is " +
  "addressed to you, not to the reader: the answer describes the document, " +
  "never the context or what it does or does not contain.";

/**
 * Render cross-references as first-class context blocks.
 *
 * References resolved with usable target text/section are rendered verbatim.
 * References we could NOT deliver content for are *named* rather than dropped:
 * silence made the prompt look as though the user had asked about nothing, and
 * the provider filled the gap with a tool call it was not permitted to make
 * (surfacing as "no output produced ... auto-denied"). Naming the gap keeps the
 * model answering from what it has without injecting misleading content.
 *
 * A reference whose text was folded into a nearby sibling (`consumedBySibling`)
 * appears in NEITHER block. It is not missing — its page text is already quoted
 * under the sibling's entry — so naming it would tell the model that a page it
 * can read right there could not be retrieved.
 */
export function buildResolvedReferencesBlock(resolved: ResolvedReference[]): string {
  if (resolved.length === 0) return "";
  const reportable = resolved.filter((r) => !r.consumedBySibling);
  if (reportable.length === 0) return "";
  const usable = new Set(
    reportable.filter((r) => r.method !== "unresolved" && (r.snippet || r.sectionTitle))
  );

  const resolvedBody = reportable
    .filter((r) => usable.has(r))
    .map((r) => {
      const attrs = [
        `label="${escapeAttr(r.label)}"`,
        typeof r.targetPage === "number" ? `target_page="${r.targetPage}"` : "",
        r.sectionTitle ? `section="${escapeAttr(r.sectionTitle)}"` : "",
        `confidence="${r.confidence.toFixed(2)}"`,
      ]
        .filter(Boolean)
        .join(" ");
      const inner = r.snippet ? `\n${r.snippet}\n` : "\n";
      return `  <reference ${attrs}>${inner}  </reference>`;
    })
    .join("\n");

  const missingBody = reportable
    .filter((r) => !usable.has(r))
    .map((r) => `  <reference label="${escapeAttr(r.label)}" />`)
    .join("\n");

  const blocks: string[] = [];
  if (resolvedBody) {
    blocks.push(`<resolved_cross_references>\n${resolvedBody}\n</resolved_cross_references>`);
  }
  if (missingBody) {
    blocks.push(
      `<unresolved_cross_references note="${escapeAttr(UNRESOLVED_NOTE)}">\n` +
        `${missingBody}\n</unresolved_cross_references>`
    );
  }
  return blocks.join("\n");
}
