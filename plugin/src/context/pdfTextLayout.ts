import type { PdfTextQuality, PdfTextSource } from "../types";

export interface RawPdfTextItem {
  str?: unknown;
  transform?: unknown;
  width?: unknown;
  height?: unknown;
  hasEOL?: unknown;
}

export interface LayoutTextItem {
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
  fontSize: number;
  hasEOL?: boolean;
}

export interface LayoutTextLine {
  y: number;
  items: LayoutTextItem[];
  text: string;
}

export interface LayoutTextResult {
  text: string;
  lines: LayoutTextLine[];
  items: LayoutTextItem[];
  quality: PdfTextQuality;
}

export interface LayoutTextOptions {
  /**
   * Set `false` to skip column detection. Used internally when recursing into
   * an already-isolated column; callers should leave it unset.
   */
  columns?: false;
  source: PdfTextSource;
  /**
   * pdf.js text transforms use PDF page coordinates (higher y is higher on page);
   * DOM text layers use viewport coordinates (higher y is lower on page).
   */
  yAxis?: "up" | "down";
  yTolerance?: number;
}

const CONTROL_OR_BROKEN_RE = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\ufffd]/g;

export function pdfJsItemsToLayoutItems(items: RawPdfTextItem[]): LayoutTextItem[] {
  const out: LayoutTextItem[] = [];

  for (const item of items) {
    const text = normalizeInlineText(typeof item.str === "string" ? item.str : "");
    if (!text) continue;

    const transform = Array.isArray(item.transform) ? item.transform : [];
    const a = readNumber(transform[0], 1);
    const b = readNumber(transform[1], 0);
    const c = readNumber(transform[2], 0);
    const d = readNumber(transform[3], 1);
    const x = readNumber(transform[4], 0);
    const y = readNumber(transform[5], 0);
    const width = Math.max(0, readNumber(item.width, text.length * Math.max(4, Math.abs(a))));
    const fontSize = Math.max(1, Math.hypot(c, d) || Math.hypot(a, b) || readNumber(item.height, 12));
    const height = Math.max(1, readNumber(item.height, fontSize));

    out.push({
      text,
      x,
      y,
      width,
      height,
      fontSize,
      hasEOL: item.hasEOL === true,
    });
  }

  return out;
}

export function domTextLayerToLayoutItems(textLayer: Element): LayoutTextItem[] {
  const spans = Array.from(textLayer.querySelectorAll<HTMLElement>("span"));
  const source = spans.length > 0 ? spans : [textLayer as HTMLElement];
  const out: LayoutTextItem[] = [];

  for (const el of source) {
    const text = normalizeInlineText(el.textContent || "");
    if (!text) continue;
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    const fontSize = parseFloat(style.fontSize || "") || rect.height || 12;

    out.push({
      text,
      x: rect.left,
      y: rect.top,
      width: Math.max(0, rect.width),
      height: Math.max(1, rect.height || fontSize),
      fontSize,
    });
  }

  return out;
}

/**
 * Split items into columns when the page has a real gutter (v0.56.0).
 *
 * `layoutTextItems` groups by y and sorts by x, which is correct for a
 * single-column page and wrong for every two-column paper: each visual line
 * concatenates the left column and the right column, so entry `[1]` of a
 * bibliography arrives spliced onto entry `[18]` from the other side.
 *
 * Measured on "3D Line Mapping Revisited" p.24 (its References page):
 * `[1] Hichem Abdellali, Robert Frohlich, Viktor Vilagos, and [18] Daniel
 * DeTone, Tomasz Malisi...` — two separate references, one reconstructed line.
 *
 * Detection is deliberately conservative, because the cost of a false positive
 * (reordering a single-column page) is far worse than a false negative
 * (leaving a two-column page interleaved, i.e. today's behaviour):
 *
 *  - the gutter must be a vertical band that essentially NO item crosses;
 *  - both sides must hold a substantial share of the items;
 *  - the band must be wide relative to the page.
 *
 * A single-column page has no such band, so it takes the original path and its
 * output is byte-identical.
 *
 * Returns `null` when the page is not confidently multi-column.
 */
function detectColumnSplit(items: LayoutTextItem[]): number | null {
  if (items.length < 40) return null;

  const left = Math.min(...items.map((i) => i.x));
  const right = Math.max(...items.map((i) => i.x + (i.width || 0)));
  const pageWidth = right - left;
  if (pageWidth <= 0) return null;

  // Candidate gutters: scan the middle half of the page. A two-column layout
  // puts its gutter near the centre; scanning the edges only invites splitting
  // a margin off a single-column page.
  //
  // The width floor is measured against the TEXT, not only the page. A page
  // fraction alone is not a discriminator: ordinary inter-word gaps on a wide
  // page clear 3% of page width easily, and an early version of this detector
  // duly split single-column pages into ribbons. A real gutter is several
  // characters wide; a word space is under one. Requiring both floors means a
  // candidate has to be wide in absolute type terms AND a real share of the
  // page before it counts.
  const medianHeight =
    median(items.map((i) => i.height || i.fontSize).filter((n) => n > 0)) || 10;
  const minGutter = Math.max(pageWidth * 0.04, medianHeight * 1.5);
  let best: { at: number; width: number } | null = null;

  const STEPS = 60;
  for (let s = 0; s <= STEPS; s += 1) {
    const at = left + pageWidth * (0.25 + (0.5 * s) / STEPS);
    let straddling = 0;
    let leftCount = 0;
    let rightCount = 0;
    let gapLeft = left;
    let gapRight = right;
    for (const item of items) {
      const a = item.x;
      const b = item.x + (item.width || 0);
      if (a < at && b > at) {
        straddling += 1;
        if (straddling > 1) break;
      } else if (b <= at) {
        leftCount += 1;
        if (b > gapLeft) gapLeft = b;
      } else {
        rightCount += 1;
        if (a < gapRight) gapRight = a;
      }
    }
    // At most one straddling item tolerates a stray full-width rule or a
    // figure caption; more than that means the band is not a gutter.
    if (straddling > 1) continue;
    const share = Math.min(leftCount, rightCount) / items.length;
    if (share < 0.25) continue;
    const width = gapRight - gapLeft;
    if (width < minGutter) continue;
    if (!best || width > best.width) best = { at, width };
  }
  return best ? best.at : null;
}

/** The y-range in which BOTH columns carry text. Anything outside is furniture. */
function sharedColumnBand(
  items: LayoutTextItem[],
  inLeft: (i: LayoutTextItem) => boolean
): { min: number; max: number } | null {
  const ys = { left: [] as number[], right: [] as number[] };
  for (const item of items) (inLeft(item) ? ys.left : ys.right).push(item.y);
  if (!ys.left.length || !ys.right.length) return null;
  const min = Math.max(Math.min(...ys.left), Math.min(...ys.right));
  const max = Math.min(Math.max(...ys.left), Math.max(...ys.right));
  return max > min ? { min, max } : null;
}

/** Is this item outside the shared band, on the given side of the page? */
function beyond(
  item: LayoutTextItem,
  band: { min: number; max: number } | null,
  side: "above" | "below",
  yAxis: "up" | "down" | undefined
): boolean {
  if (!band) return false;
  // With yAxis "up" (pdf.js) a LARGER y is higher on the page.
  const higherIsLarger = yAxis === "up";
  if (side === "above") return higherIsLarger ? item.y > band.max : item.y < band.min;
  return higherIsLarger ? item.y < band.min : item.y > band.max;
}

export function layoutTextItems(
  inputItems: LayoutTextItem[],
  options: LayoutTextOptions
): LayoutTextResult {
  const items = inputItems
    .filter((item) => item.text.trim().length > 0)
    .map((item) => ({ ...item, text: normalizeInlineText(item.text) }));
  const yAxis = options.yAxis || "down";
  const medianHeight = median(items.map((item) => item.height || item.fontSize).filter((n) => n > 0)) || 12;
  const yTolerance = options.yTolerance ?? Math.max(2, medianHeight * 0.45);

  const sorted = [...items].sort((a, b) => {
    const yDelta = yAxis === "up" ? b.y - a.y : a.y - b.y;
    if (Math.abs(yDelta) > yTolerance) return yDelta;
    return a.x - b.x;
  });

  // Two-column pages must be read column by column, not line by line across
  // the gutter. Only a confidently detected gutter triggers this; a
  // single-column page falls straight through to the original path.
  const gutter = options.columns === false ? null : detectColumnSplit(items);
  if (gutter !== null) {
    const opts = { ...options, columns: false as const };
    const inLeft = (i: LayoutTextItem): boolean => i.x + (i.width || 0) <= gutter;

    // Page furniture — the running head and the page-number footer — sits
    // OUTSIDE the vertical band where both columns have text, and must keep its
    // raster position. Bucketing it by x instead put a footer that happens to
    // sit left of the gutter at the end of the LEFT COLUMN, i.e. the middle of
    // the page's text. `printedHeaderCandidates` reads the first and last three
    // lines to infer a printed page number, so that silently broke
    // printed-page cross-references on exactly the two-column papers this
    // change is meant to help.
    const band = sharedColumnBand(items, inLeft);
    const above = items.filter((i) => beyond(i, band, "above", options.yAxis));
    const below = items.filter((i) => beyond(i, band, "below", options.yAxis));
    const furniture = new Set([...above, ...below]);
    const body = items.filter((i) => !furniture.has(i));

    const head = above.length ? layoutTextItems(above, opts) : null;
    const a = layoutTextItems(body.filter(inLeft), opts);
    const b = layoutTextItems(body.filter((i) => !inLeft(i)), opts);
    const foot = below.length ? layoutTextItems(below, opts) : null;

    const parts = [head, a, b, foot].filter((r): r is LayoutTextResult => r !== null);
    const text = parts.map((r) => r.text).filter(Boolean).join("\n");
    return {
      text,
      lines: parts.flatMap((r) => r.lines),
      items,
      quality: assessPdfTextQuality(text, options.source),
    };
  }

  const lines: LayoutTextLine[] = [];
  for (const item of sorted) {
    const last = lines[lines.length - 1];
    if (!last || Math.abs(item.y - last.y) > yTolerance) {
      lines.push({ y: item.y, items: [item], text: "" });
    } else {
      last.items.push(item);
      last.y = (last.y * (last.items.length - 1) + item.y) / last.items.length;
    }
  }

  for (const line of lines) {
    line.items.sort((a, b) => a.x - b.x);
    line.text = joinLineItems(line.items);
  }

  const text = lines
    .map((line) => line.text.trim())
    .filter(Boolean)
    .join("\n")
    .trim();

  return {
    text,
    lines,
    items,
    quality: assessPdfTextQuality(text, options.source),
  };
}

export function layoutPdfJsTextItems(
  items: RawPdfTextItem[],
  source: PdfTextSource = "pdfjs"
): LayoutTextResult {
  return layoutTextItems(pdfJsItemsToLayoutItems(items), { source, yAxis: "up" });
}

export function extractDomTextLayerText(
  textLayer: Element,
  source: PdfTextSource = "obsidian-text-layer"
): LayoutTextResult {
  return layoutTextItems(domTextLayerToLayoutItems(textLayer), { source, yAxis: "down" });
}

export function assessPdfTextQuality(
  text: string,
  source: PdfTextSource,
  reason?: string
): PdfTextQuality {
  const normalized = text || "";
  const charCount = normalized.replace(/\s/g, "").length;
  const words = normalized.match(/[\p{L}\p{N}][\p{L}\p{N}'-]*/gu) || [];
  const wordCount = words.length;
  const lineCount = normalized.trim() ? normalized.split(/\n+/).filter((line) => line.trim()).length : 0;
  const brokenCount = (normalized.match(CONTROL_OR_BROKEN_RE) || []).length;
  const brokenCharRatio = normalized.length > 0 ? brokenCount / normalized.length : 1;
  const whitespaceRatio = normalized.length > 0 ? (normalized.match(/\s/g) || []).length / normalized.length : 1;
  const alphaNumCount = (normalized.match(/[\p{L}\p{N}]/gu) || []).length;
  const alphaNumRatio = normalized.length > 0 ? alphaNumCount / normalized.length : 0;
  const avgWordLength =
    wordCount > 0 ? words.reduce((sum, word) => sum + word.length, 0) / wordCount : 0;

  let score = 0;
  score += Math.min(0.25, charCount / 1200);
  score += Math.min(0.3, wordCount / 240);
  score += Math.min(0.15, lineCount / 30);
  score += Math.min(0.2, alphaNumRatio * 0.25);
  score += Math.min(0.1, avgWordLength / 60);
  score -= Math.min(0.35, brokenCharRatio * 3);
  if (whitespaceRatio > 0.45) score -= Math.min(0.2, (whitespaceRatio - 0.45) * 0.8);
  if (wordCount > 0 && avgWordLength < 2.2) score -= 0.15;
  score = clamp(score, 0, 1);

  const isScannedLike =
    source === "none" ||
    charCount < 20 ||
    wordCount < 4 ||
    alphaNumRatio < 0.10 ||
    brokenCharRatio > 0.35 ||
    score < 0.10;

  return {
    score,
    charCount,
    wordCount,
    lineCount,
    brokenCharRatio,
    whitespaceRatio,
    isScannedLike,
    source,
    reason,
  };
}

function joinLineItems(items: LayoutTextItem[]): string {
  let line = "";
  let previous: LayoutTextItem | null = null;

  for (const item of items) {
    const text = item.text;
    if (!previous) {
      line = text;
      previous = item;
      continue;
    }

    const previousRight = previous.x + previous.width;
    const gap = item.x - previousRight;
    const previousCharWidth = estimateCharWidth(previous);
    const shouldInsertSpace =
      gap > Math.max(1.5, previousCharWidth * 0.45) &&
      !/\s$/.test(line) &&
      !/^[,.;:!?%)]/.test(text);

    line += shouldInsertSpace ? ` ${text}` : text;
    previous = item;
  }

  return line.replace(/[ \t]+\n/g, "\n").replace(/[ \t]{2,}/g, " ");
}

function normalizeInlineText(text: string): string {
  return text.replace(/\u00a0/g, " ").replace(/[\r\n\t]+/g, " ");
}

function estimateCharWidth(item: LayoutTextItem): number {
  const visibleLength = Math.max(1, item.text.trim().length);
  if (item.width > 0) return item.width / visibleLength;
  return Math.max(3, item.fontSize * 0.45);
}

function readNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}
