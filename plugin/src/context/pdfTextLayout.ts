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
