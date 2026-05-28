import type {
  PdfOutlineItem,
  PdfRagHit,
  PdfTextQuality,
  PdfWindowPage,
} from "../types";

export interface PdfIndexPage {
  pageNum: number;
  text: string;
  textQuality?: PdfTextQuality;
  sectionTitle?: string;
}

export interface PdfSearchOptions {
  topK?: number;
  excludePages?: number[];
}

interface IndexedPage extends PdfIndexPage {
  tokens: string[];
  termFrequency: Map<string, number>;
  length: number;
}

interface PdfIndex {
  documentId: string;
  pages: Map<number, IndexedPage>;
  documentFrequency: Map<string, number>;
  avgPageLength: number;
}

const STOP_WORDS = new Set([
  "a",
  "an",
  "and",
  "are",
  "as",
  "at",
  "be",
  "but",
  "by",
  "for",
  "from",
  "has",
  "have",
  "in",
  "into",
  "is",
  "it",
  "its",
  "of",
  "on",
  "or",
  "that",
  "the",
  "their",
  "this",
  "to",
  "was",
  "were",
  "with",
]);

export class PdfDocumentIndexService {
  private indexes = new Map<string, PdfIndex>();

  upsertDocument(
    documentId: string,
    pages: PdfWindowPage[],
    outline: PdfOutlineItem[] = []
  ): void {
    const indexPages: PdfIndexPage[] = pages.map((page) => ({
      pageNum: page.pageNum,
      text: page.text,
      textQuality: page.textQuality,
      sectionTitle: findSectionTitle(outline, page.pageNum),
    }));
    this.indexes.set(documentId, buildIndex(documentId, indexPages));
  }

  upsertPage(
    documentId: string,
    page: PdfWindowPage,
    outline: PdfOutlineItem[] = []
  ): void {
    const existing = this.indexes.get(documentId);
    const pages = existing ? Array.from(existing.pages.values()) : [];
    const nextPages = pages
      .filter((existingPage) => existingPage.pageNum !== page.pageNum)
      .map((existingPage) => ({
        pageNum: existingPage.pageNum,
        text: existingPage.text,
        textQuality: existingPage.textQuality,
        sectionTitle: existingPage.sectionTitle,
      }));
    nextPages.push({
      pageNum: page.pageNum,
      text: page.text,
      textQuality: page.textQuality,
      sectionTitle: findSectionTitle(outline, page.pageNum),
    });
    nextPages.sort((a, b) => a.pageNum - b.pageNum);
    this.indexes.set(documentId, buildIndex(documentId, nextPages));
  }

  removeDocument(documentId: string): void {
    this.indexes.delete(documentId);
  }

  getPage(documentId: string, pageNum: number): PdfWindowPage | null {
    const page = this.indexes.get(documentId)?.pages.get(pageNum);
    if (!page) return null;
    return {
      pageNum: page.pageNum,
      text: page.text,
      textQuality: page.textQuality,
    };
  }

  getWindowPages(
    documentId: string,
    currentPage: number,
    radius: number
  ): PdfWindowPage[] {
    const index = this.indexes.get(documentId);
    if (!index) return [];
    const from = Math.max(1, currentPage - Math.max(0, radius));
    const to = currentPage + Math.max(0, radius);
    const pages: PdfWindowPage[] = [];

    for (let pageNum = from; pageNum <= to; pageNum++) {
      const page = index.pages.get(pageNum);
      if (!page) continue;
      pages.push({
        pageNum,
        text: page.text,
        textQuality: page.textQuality,
      });
    }

    return pages;
  }

  search(
    documentId: string,
    query: string,
    options: PdfSearchOptions = {}
  ): PdfRagHit[] {
    const index = this.indexes.get(documentId);
    if (!index) return [];

    const queryTokens = tokenize(query);
    if (queryTokens.length === 0) return [];

    const exclude = new Set(options.excludePages || []);
    const topK = Math.max(1, options.topK ?? 5);
    const queryTerms = Array.from(new Set(queryTokens));
    const hits: PdfRagHit[] = [];

    for (const page of index.pages.values()) {
      if (exclude.has(page.pageNum) || page.length === 0) continue;
      let score = 0;
      for (const term of queryTerms) {
        const tf = page.termFrequency.get(term) || 0;
        if (tf === 0) continue;
        const df = index.documentFrequency.get(term) || 0;
        const idf = Math.log(1 + (index.pages.size - df + 0.5) / (df + 0.5));
        const k1 = 1.2;
        const b = 0.75;
        const denom =
          tf + k1 * (1 - b + b * (page.length / Math.max(1, index.avgPageLength)));
        score += idf * ((tf * (k1 + 1)) / denom);
      }

      if (score <= 0) continue;
      const qualityBoost = page.textQuality ? 0.6 + page.textQuality.score * 0.4 : 1;
      hits.push({
        pageNum: page.pageNum,
        score: Number((score * qualityBoost).toFixed(4)),
        snippet: makeSnippet(page.text, queryTerms),
        sectionTitle: page.sectionTitle,
      });
    }

    return hits.sort((a, b) => b.score - a.score).slice(0, topK);
  }
}

function buildIndex(documentId: string, pages: PdfIndexPage[]): PdfIndex {
  const indexedPages = new Map<number, IndexedPage>();
  const documentFrequency = new Map<string, number>();
  let totalLength = 0;

  for (const page of pages) {
    const tokens = tokenize(page.text);
    const termFrequency = new Map<string, number>();
    for (const token of tokens) {
      termFrequency.set(token, (termFrequency.get(token) || 0) + 1);
    }
    for (const token of new Set(tokens)) {
      documentFrequency.set(token, (documentFrequency.get(token) || 0) + 1);
    }
    totalLength += tokens.length;
    indexedPages.set(page.pageNum, {
      ...page,
      tokens,
      termFrequency,
      length: tokens.length,
    });
  }

  return {
    documentId,
    pages: indexedPages,
    documentFrequency,
    avgPageLength: indexedPages.size > 0 ? totalLength / indexedPages.size : 0,
  };
}

function tokenize(text: string): string[] {
  return text
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[\u0300-\u036f]/g, "")
    .match(/[\p{L}\p{N}]{2,}/gu)
    ?.filter((token) => !STOP_WORDS.has(token)) || [];
}

function makeSnippet(text: string, queryTerms: string[]): string {
  const lines = text
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) return "";

  let bestLine = lines[0];
  let bestScore = -1;
  for (const line of lines) {
    const lineTokens = new Set(tokenize(line));
    const score = queryTerms.reduce((sum, term) => sum + (lineTokens.has(term) ? 1 : 0), 0);
    if (score > bestScore) {
      bestScore = score;
      bestLine = line;
    }
  }

  return bestLine.length > 360 ? `${bestLine.slice(0, 357)}...` : bestLine;
}

function findSectionTitle(outline: PdfOutlineItem[], pageNum: number): string | undefined {
  let best: PdfOutlineItem | undefined;
  for (const item of outline) {
    if (typeof item.pageNum !== "number" || item.pageNum > pageNum) continue;
    if (!best || item.pageNum >= (best.pageNum || 0)) best = item;
  }
  return best?.title;
}
