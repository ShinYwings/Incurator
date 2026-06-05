import { WorkspaceLeaf } from "obsidian";
import type { PdfPageContext, PdfRagHit, PdfWindowPage } from "../types";
import {
  assessPdfTextQuality,
  extractDomTextLayerText,
} from "./pdfTextLayout";

const DEFAULT_PDF_WINDOW_RADIUS = 1;

/**
 * Capture the currently visible PDF page from Obsidian's built-in PDF viewer.
 *
 * Obsidian uses pdf.js internally. The rendered PDF pages are in the DOM as
 * `.pdf-page[data-page-number]` elements, each containing a `<canvas>` for
 * rendering and a `.textLayer` div for selectable text.
 */
export function getPdfContext(
  leaf: WorkspaceLeaf,
  captureMode: "text" | "image" | "both"
): PdfPageContext | null {
  const view = leaf.view as unknown as Record<string, unknown>;

  // Obsidian PDF view has a containerEl with the rendered pages
  const containerEl =
    (view.containerEl as HTMLElement) ||
    (view.contentEl as HTMLElement);

  if (!containerEl) return null;

  // Find the active / most visible page
  const activePage = findActivePageElement(containerEl);
  if (!activePage) return null;

  const pageNum = parseInt(
    activePage.getAttribute("data-page-number") || "1",
    10
  );
  const pageCount = countPdfPages(containerEl);

  let text = "";
  let imageBase64: string | undefined;
  let windowPages: PdfWindowPage[] = [];
  let textQuality = assessPdfTextQuality("", "none", "Text capture was not requested.");

  // ── Text extraction ──
  if (captureMode === "text" || captureMode === "both") {
    const extracted = extractPdfPageTextFromDom(activePage);
    text = extracted.text;
    textQuality = extracted.textQuality;
    windowPages = extractVisibleWindowPages(containerEl, pageNum, DEFAULT_PDF_WINDOW_RADIUS);
    text = composePdfContextText(pageNum, text, windowPages);
  }

  // ── Image capture ──
  if (captureMode === "image" || captureMode === "both") {
    imageBase64 = capturePageCanvas(activePage);
  }

  return {
    pageNum,
    pageCount,
    text,
    imageBase64,
    windowPages,
    textQuality,
    isScannedLike: textQuality.isScannedLike,
  };
}

/**
 * When pdfCaptureMode="text" and pdfVisionFallback=true and the page is
 * scanned-like, augment `ctx` with an imageBase64 from `getImageBase64`.
 * Returns the same (mutated) ctx, or null if ctx was null.
 */
export function withVisionFallback(
  ctx: PdfPageContext | null,
  captureMode: "text" | "image" | "both",
  visionFallback: boolean,
  getImageBase64: () => string | undefined
): PdfPageContext | null {
  if (!ctx || captureMode !== "text" || !visionFallback || !ctx.isScannedLike) return ctx;
  const imageBase64 = getImageBase64();
  if (imageBase64) ctx.imageBase64 = imageBase64;
  return ctx;
}

/**
 * Find the PDF page element that is most visible in the viewport.
 * Obsidian renders each page as a div with `data-page-number`.
 */
function findActivePageElement(container: HTMLElement): HTMLElement | null {
  // Try multiple selectors that Obsidian's PDF viewer might use
  const selectors = [
    ".pdf-page[data-page-number]",
    '[data-page-number]',
    ".page[data-page-number]",
  ];

  let pages: NodeListOf<HTMLElement> | null = null;
  for (const selector of selectors) {
    pages = container.querySelectorAll<HTMLElement>(selector);
    if (pages.length > 0) break;
  }

  if (!pages || pages.length === 0) return null;

  // Find the page with the most visibility in the scroll viewport
  const scrollContainer = findScrollContainer(container);
  if (!scrollContainer) {
    return pages[0]; // Fallback to first page
  }

  const viewportRect = scrollContainer.getBoundingClientRect();
  const viewportTop = viewportRect.top;
  const viewportBottom = viewportRect.bottom;

  let bestPage: HTMLElement | null = null;
  let bestOverlap = -Infinity;

  for (const page of Array.from(pages)) {
    const rect = page.getBoundingClientRect();
    const pageTop = rect.top;
    const pageBottom = rect.bottom;

    // Calculate overlap with viewport
    const overlapTop = Math.max(viewportTop, pageTop);
    const overlapBottom = Math.min(viewportBottom, pageBottom);
    const overlap = Math.max(0, overlapBottom - overlapTop);

    if (overlap > bestOverlap) {
      bestOverlap = overlap;
      bestPage = page;
    }
  }

  return bestPage;
}

/**
 * Find the scrollable parent container for the PDF viewer.
 */
function findScrollContainer(el: HTMLElement): HTMLElement | null {
  let current: HTMLElement | null = el;
  while (current) {
    const style = getComputedStyle(current);
    if (
      style.overflow === "auto" ||
      style.overflow === "scroll" ||
      style.overflowY === "auto" ||
      style.overflowY === "scroll"
    ) {
      return current;
    }
    current = current.parentElement;
  }
  return el; // Fallback to the element itself
}

/**
 * Extract text content from a PDF page's text layer.
 * pdf.js renders text into a `.textLayer` or `.text-layer` div with <span> elements.
 */
export function extractPdfPageTextFromDom(pageEl: HTMLElement): {
  text: string;
  textQuality: ReturnType<typeof assessPdfTextQuality>;
} {
  const renderedText = pageEl.dataset.text;
  if (renderedText) {
    return {
      text: renderedText.trim(),
      textQuality: assessPdfTextQuality(renderedText, "pdfjs"),
    };
  }

  // Try multiple selectors for the text layer
  const textLayer =
    pageEl.querySelector(".textLayer") ||
    pageEl.querySelector(".text-layer") ||
    pageEl.querySelector('[class*="textLayer"]') ||
    pageEl.querySelector('[class*="text-layer"]');

  if (!textLayer) {
    // Fallback: try to get any text content from the page element
    const text = pageEl.innerText?.trim() || "";
    return {
      text,
      textQuality: assessPdfTextQuality(
        text,
        text ? "dom" : "none",
        text ? undefined : "No PDF text layer was found."
      ),
    };
  }

  try {
    const result = extractDomTextLayerText(textLayer, "obsidian-text-layer");
    const spansCount = textLayer.querySelectorAll("span").length;
    // If layout extraction succeeded and didn't trigger the scanned-like fallback
    // (which happens if words are smashed due to 0-width rects), use it.
    if (result.text && (!result.quality.isScannedLike || spansCount < 10)) {
      return {
        text: result.text,
        textQuality: result.quality,
      };
    }
  } catch (err) {
    console.warn("[AI Agent] Failed to layout PDF text layer:", err);
  }

  // Fallback: If DOM is unrendered (rects are 0), layout extraction mashes text.
  // Instead, try innerText (if partially rendered) or join spans with spaces manually.
  let text = (textLayer as HTMLElement).innerText?.trim();
  if (!text) {
    const spans = Array.from(textLayer.querySelectorAll("span"));
    if (spans.length > 0) {
      text = spans.map((s) => s.textContent?.trim()).filter(Boolean).join(" ");
    } else {
      text = textLayer.textContent?.trim() || "";
    }
  }

  // Final sanity check: if we got substantial text but it's marked as scanned-like
  // (e.g. math heavy or weird whitespace), we still want to prefer the text over a blank/bad image.
  const quality = assessPdfTextQuality(
    text,
    text ? "obsidian-text-layer" : "none",
    text ? undefined : "The PDF text layer did not contain selectable text."
  );

  // If we extracted more than 100 characters of text, forcefully trust it.
  if (text.length > 100) {
    quality.isScannedLike = false;
  }

  return {
    text,
    textQuality: quality,
  };
}

/**
 * Capture the rendered PDF page canvas as a base64-encoded PNG.
 */
function capturePageCanvas(pageEl: HTMLElement): string | undefined {
  const canvas = pageEl.querySelector("canvas");
  if (!canvas) return undefined;

  try {
    // toDataURL returns "data:image/png;base64,..." — we strip the prefix
    const dataUrl = canvas.toDataURL("image/png");
    const base64 = dataUrl.replace(/^data:image\/png;base64,/, "");
    return base64;
  } catch (err) {
    console.warn("[AI Agent] Failed to capture PDF canvas:", err);
    return undefined;
  }
}

/**
 * Get the currently selected text in a PDF view, if any.
 */
export function getPdfSelection(leaf: WorkspaceLeaf): { text: string; imageBase64?: string } | null {
  const view = leaf.view as unknown as Record<string, unknown>;
  const containerEl =
    (view.containerEl as HTMLElement) ||
    (view.contentEl as HTMLElement);

  if (!containerEl) return null;

  const selection = containerEl.ownerDocument.getSelection();
  if (!selection || selection.isCollapsed) return null;

  // Check if the selection is within the PDF container
  const range = selection.getRangeAt(0);
  if (!containerEl.contains(range.commonAncestorContainer)) return null;

  const text = selection.toString().trim();
  if (!text) return null;

  return { text };
}

export function composePdfContextText(
  pageNum: number,
  currentText: string,
  windowPages: PdfWindowPage[] = [],
  ragHits: PdfRagHit[] = []
): string {
  const parts: string[] = [];
  const current = currentText.trim();
  if (current) {
    parts.push(current);
  }

  const nearby = windowPages
    .filter((page) => page.pageNum !== pageNum && page.text.trim())
    .sort((a, b) => a.pageNum - b.pageNum);
  if (nearby.length > 0) {
    parts.push(
      [
        "[Nearby PDF pages]",
        ...nearby.map((page) => `Page ${page.pageNum}:\n${trimText(page.text, 3000)}`),
      ].join("\n\n")
    );
  }

  if (ragHits.length > 0) {
    parts.push(
      [
        "[Related PDF snippets]",
        ...ragHits.map((hit) => {
          const section = hit.sectionTitle ? ` (${hit.sectionTitle})` : "";
          return `Page ${hit.pageNum}${section}: ${hit.snippet}`;
        }),
      ].join("\n")
    );
  }

  return parts.join("\n\n").trim();
}

function extractVisibleWindowPages(
  container: HTMLElement,
  currentPage: number,
  radius: number
): PdfWindowPage[] {
  const pages: PdfWindowPage[] = [];
  for (let pageNum = currentPage - radius; pageNum <= currentPage + radius; pageNum++) {
    if (pageNum < 1) continue;
    const pageEl = container.querySelector<HTMLElement>(
      `.pdf-page[data-page-number="${pageNum}"], [data-page-number="${pageNum}"], .page[data-page-number="${pageNum}"]`
    );
    if (!pageEl) continue;
    const extracted = extractPdfPageTextFromDom(pageEl);
    pages.push({
      pageNum,
      text: extracted.text,
      textQuality: extracted.textQuality,
    });
  }
  return pages;
}

function countPdfPages(container: HTMLElement): number | undefined {
  const pages = Array.from(container.querySelectorAll<HTMLElement>("[data-page-number]"));
  const pageNumbers = pages
    .map((page) => Number(page.getAttribute("data-page-number") || "0"))
    .filter((pageNum) => Number.isFinite(pageNum) && pageNum > 0);
  if (pageNumbers.length === 0) return undefined;
  return Math.max(...pageNumbers);
}

function trimText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}\n[...truncated]`;
}
