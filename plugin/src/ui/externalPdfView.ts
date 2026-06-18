import {
  ItemView,
  Menu,
  WorkspaceLeaf,
  loadPdfJs,
  setIcon,
  Notice,
  type ViewStateResult,
} from "obsidian";
import type { LLMMessage } from "../types";
import { existsSync, readFileSync } from "fs";
import type {
  PdfOutlineItem as ContextPdfOutlineItem,
  PdfPageContext,
  PdfWindowPage,
} from "../types";
import { PdfDocumentIndexService } from "../context/pdfDocumentIndex";
import {
  extractRegionTextFromSpans,
  type RegionTextSpan,
} from "../context/pdfCapture";
import {
  layoutPdfJsTextItems,
  type RawPdfTextItem,
} from "../context/pdfTextLayout";
import { buildZoteroAnnotationBoxStyle } from "./externalPdfAnnotationStyle";
import {
  buildSyncedExternalPdfState,
  resolveExternalPdfPath,
} from "./externalPdfState";
import {
  getExternalPdfDoc,
  getExternalPdfDocName,
  getExternalPdfDocPath,
  putExternalPdfDoc,
  replaceExternalPdfDocPath,
  resolveCachedExternalPdfPath,
  type ExternalPdfDoc,
} from "./externalPdfRegistry";
import { PdfCaptureService } from "./pdfCaptureService";

export const EXTERNAL_PDF_VIEW_TYPE = "ai-agent-external-pdf";
export const EXTERNAL_PDF_CONTEXT_EVENT = "ai-agent-external-pdf-context";

export interface ExternalPdfState extends Record<string, unknown> {
  docId: string;
  name: string;
  path?: string;
  zoom?: number;
  darkMode?: boolean;
  tocOpen?: boolean;
  currentPage?: number;
  zoteroAttachmentKey?: string;
  targetAnnotationKey?: string;
}

interface PdfJsOutlineItem {
  title?: string;
  dest?: string | unknown[];
  items?: PdfJsOutlineItem[];
}

interface TocTreeNode {
  title: string;
  pageNum: number;
  children: TocTreeNode[];
}

function flattenTocTree(nodes: TocTreeNode[], level = 0): ContextPdfOutlineItem[] {
  const out: ContextPdfOutlineItem[] = [];
  for (const node of nodes) {
    out.push({ title: node.title, pageNum: node.pageNum, level });
    out.push(...flattenTocTree(node.children, level + 1));
  }
  return out;
}

interface PdfDocument {
  numPages: number;
  getPage: (pageNum: number) => Promise<PdfPage>;
  getOutline: () => Promise<PdfJsOutlineItem[] | null>;
  getDestination: (dest: string) => Promise<unknown[] | null>;
  getPageIndex: (ref: unknown) => Promise<number>;
  getPageLabels?: () => Promise<string[] | null>;
}

interface PdfPage {
  getViewport: (options: { scale: number }) => { width: number; height: number; convertToViewportPoint(x: number, y: number): [number, number] };
  render: (options: {
    canvasContext: CanvasRenderingContext2D;
    viewport: { width: number; height: number };
  }) => { promise: Promise<void> };
  getTextContent: () => Promise<{ items: RawPdfTextItem[] }>;
}

const RENDER_RADIUS = 5;
export class ExternalPdfView extends ItemView {
  private docId = "";
  private docState: ExternalPdfState | null = null;
  private renderToken = 0;
  private zoom = 1;
  private renderedZoom = 1;
  private referenceBaseWidth = 800;
  private lastClientWidth = 0;
  private lastDpr = 1;

  private get baseFitScale(): number {
    const clientW = this.pagesEl?.clientWidth || this.containerEl?.clientWidth || 800;
    const stableWidth = Math.max(200, clientW - 32);
    return Math.max(0.1, stableWidth / this.referenceBaseWidth);
  }
  private renderedBaseFitScale = 1;
  private darkMode = false;
  private tocOpen = false;
  private currentPage = 1;
  private pageInputEl: HTMLInputElement | null = null;
  private pageCountEl: HTMLElement | null = null;
  private tocPanelEl: HTMLElement | null = null;
  private pagesEl: HTMLElement | null = null;
  private latexKeydownRegistered = false;
  private darkModeBtnEl: HTMLButtonElement | null = null;
  private zoomInputEl: HTMLInputElement | null = null;
  private totalPages = 0;

  // PDF document cache
  private cachedPdf: PdfDocument | null = null;
  private cachedPdfDocId = "";

  // Per-page base dimensions at scale=1 (stored to avoid re-calling getPage on zoom)
  private pageBaseDims: Array<{ width: number; height: number }> = [];
  private documentIndex = new PdfDocumentIndexService();
  private pdfCaptureService = new PdfCaptureService();
  private pageTextCache = new Map<number, PdfWindowPage>();
  private currentOutlineItems: ContextPdfOutlineItem[] = [];
  private pageLabels: string[] | null = null;
  private indexBuildToken = 0;

  // Lazy rendering state
  private renderedPages = new Set<number>();
  private renderingPages = new Set<number>();
  private isLazyRendering = false;
  private lazyRenderDirty = false;

  // Zoom debounce
  private zoomDebounceTimer: ReturnType<typeof setTimeout> | null = null;

  // Zoom lock to prevent scroll-triggered page flipping
  private isZooming = false;

  // Zoom anchor properties
  private zoomAnchorMouseX?: number;
  private zoomAnchorMouseY?: number;
  private zoomAnchorContentX?: number;
  private zoomAnchorContentY?: number;
  private zoomAnchorOldZoom?: number;

  private zoteroAnnotations: any[] = [];
  private styleObserver: MutationObserver | null = null;
  
  constructor(leaf: WorkspaceLeaf, private plugin: any) {
    super(leaf);
  }

  getViewType(): string {
    return EXTERNAL_PDF_VIEW_TYPE;
  }

  getDisplayText(): string {
    return (
      getExternalPdfDocName(this.docId, "") ||
      this.docState?.name ||
      "External PDF"
    );
  }

  getIcon(): string {
    return "file-text";
  }

  async setState(
    state: Partial<ExternalPdfState>,
    result: ViewStateResult
  ): Promise<void> {
    this.docId = state.docId || "";
    // Build docState whenever a docId is present — even if `name` is missing on a
    // restored state — and backfill path/name from the persisted cache. Previously
    // a name-less restore nulled docState, which then made getState() persist a
    // path-less state and permanently lose the document identity.
    const cached = state.docId ? getExternalPdfDoc(state.docId) : undefined;
    this.docState = state.docId
      ? {
          docId: state.docId,
          name: state.name || cached?.name || "External PDF",
          path: resolveExternalPdfPath(state.path, cached?.path),
          zoom: this.readNumberState(state.zoom, 1),
          darkMode: state.darkMode === true,
          tocOpen: state.tocOpen === true,
          currentPage: this.readNumberState(state.currentPage, 1),
          zoteroAttachmentKey: state.zoteroAttachmentKey,
          targetAnnotationKey: state.targetAnnotationKey,
        }
      : null;
    this.zoom = this.docState?.zoom ?? 1;
    this.renderedZoom = this.zoom;
    this.darkMode = this.docState?.darkMode ?? false;
    this.tocOpen = this.docState?.tocOpen ?? false;
    this.currentPage = this.docState?.currentPage ?? 1;
    await super.setState(state, result);
    this.render();
  }

  getState(): ExternalPdfState {
    // Always persist the path (from docState OR the cache) so a restored view is
    // self-sufficient. The previous fallback branch omitted `path`, so once
    // docState was null the path was lost permanently across restarts.
    const cachePath = getExternalPdfDocPath(this.docId);
    if (this.docState) {
      return { ...this.docState, path: resolveExternalPdfPath(this.docState.path, cachePath) };
    }
    return {
      docId: this.docId,
      name: getExternalPdfDocName(this.docId),
      path: cachePath,
      zoom: this.zoom,
      darkMode: this.darkMode,
      tocOpen: this.tocOpen,
      currentPage: this.currentPage,
    };
  }

  async onOpen(): Promise<void> {
    this.setupDropHandler();
    this.setupPdfJsStyleSync();
    this.render();
    this.notifyContextChanged();
  }

  /**
   * Force a full reload of the PDF from disk: drop the cached document, rendered
   * pages, text caches, and document index, then re-render. Shared by the toolbar
   * Reload button and the `Cmd+Shift+R` hotkey so both take the same path.
   */
  reloadFromDisk(): void {
    this.cachedPdf = null;
    this.cachedPdfDocId = "";
    this.renderedPages.clear();
    this.renderingPages.clear();
    this.pageTextCache.clear();
    this.documentIndex.removeDocument(this.docId);
    this.indexBuildToken++;
    this.render();
    new Notice("PDF reloaded");
  }

  private setupPdfJsStyleSync(): void {
    // When moved to a new window (popout), pdfjs font styles injected into main document.head 
    // must be synced to the popout window's document.head, otherwise text will render corrupted.
    if (typeof window.MutationObserver !== "undefined") {
      this.styleObserver = new MutationObserver(() => this.syncPdfJsStyles());
      this.styleObserver.observe(document.head, { childList: true });
    }
    this.syncPdfJsStyles();
  }

  private syncPdfJsStyles(): void {
    const mainDoc = document;
    const childDoc = this.containerEl.doc;
    if (mainDoc === childDoc) return;

    const childStyles = Array.from(childDoc.head.querySelectorAll("style"));
    const childStyleContents = new Set(childStyles.map((s) => s.textContent));

    const mainStyles = Array.from(mainDoc.head.querySelectorAll("style"));
    for (const style of mainStyles) {
      const text = style.textContent || "";
      if (text.includes("@font-face")) {
        if (!childStyleContents.has(text)) {
          const clone = childDoc.createElement("style");
          clone.textContent = text;
          clone.dataset.pdfjsSynced = "true";
          childDoc.head.appendChild(clone);
          childStyleContents.add(text);
        }
      }
    }
  }

  onResize(): void {
    super.onResize();
    this.syncPdfJsStyles();
    if (!this.pagesEl || !this.cachedPdf || this.totalPages === 0) return;
    const currentWidth = this.containerEl.clientWidth;
    const currentDpr = (this.containerEl.win || window).devicePixelRatio || 1;
    if (currentWidth === this.lastClientWidth && currentDpr === this.lastDpr) return;
    this.lastClientWidth = currentWidth;
    this.lastDpr = currentDpr;
    this.setZoom(this.zoom);
  }

  private setupDropHandler(): void {
    const el = this.contentEl;

    this.registerDomEvent(el, "dragover", (e: DragEvent) => {
      if (!e.dataTransfer) return;
      const types = Array.from(e.dataTransfer.types);
      const hasFiles =
        types.includes("Files") ||
        types.includes("text/uri-list") ||
        types.includes("text/plain");
      if (hasFiles) {
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = "copy";
      }
    });

    this.registerDomEvent(el, "drop", async (e: DragEvent) => {
      if (!e.dataTransfer) return;

      let file: File | undefined = undefined;
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        file = e.dataTransfer.files[0];
      }

      e.preventDefault();
      e.stopPropagation();

      let path: string | undefined = undefined;
      let name = "External PDF";

      // 1. Try to get absolute path from e.dataTransfer text/uri-list or text/plain
      try {
        const uriList =
          e.dataTransfer.getData("text/uri-list") ||
          e.dataTransfer.getData("text/plain");
        if (uriList) {
          const lines = uriList
            .split(/[\r\n]+/)
            .map((line) => line.trim())
            .filter(Boolean);
          if (lines.length > 0) {
            const firstUri = lines[0];
            if (firstUri.startsWith("file://")) {
              const url = new URL(firstUri);
              let decoded = decodeURIComponent(url.pathname);
              if (
                typeof process !== "undefined" &&
                (process.platform === "win32" ||
                  navigator.platform.startsWith("Win"))
              ) {
                if (decoded.startsWith("/")) {
                  decoded = decoded.substring(1);
                }
              }
              path = decoded;
            } else if (firstUri.startsWith("/")) {
              path = firstUri;
            }
          }
        }
      } catch (err) {
        console.warn("Failed to extract path from dataTransfer URIs:", err);
      }

      // 2. Fall back to standard file.path if we didn't get path or if it's a standard drop
      if (file) {
        const rawPath = (file as unknown as { path?: string }).path;
        if (!path && typeof rawPath === "string" && rawPath.length > 0) {
          path = rawPath;
        }
        name = file.name;
      } else if (path) {
        // Resolve name from path
        name = path.split(/[/\\]/).pop() || "External PDF";
      } else {
        new Notice("No file or valid path dropped!");
        return;
      }

      const ext = name.split(".").pop()?.toLowerCase();
      if (ext !== "pdf") {
        new Notice("Only PDF files are supported!");
        return;
      }

      if (!this.docId) {
        this.docId = `${Date.now().toString(36)}${Math.random()
          .toString(36)
          .slice(2, 8)}`;
      }

      putExternalPdfDoc({
        id: this.docId,
        name,
        path,
        file,
      });

      if (path) {
        new Notice(`Opened PDF: ${name}\nPath: ${path}`);
      } else {
        new Notice(`Opened PDF: ${name}\nWarning: No absolute path captured!`);
      }

      this.docState = {
        docId: this.docId,
        name,
        path,
        zoom: this.zoom,
        darkMode: this.darkMode,
        tocOpen: this.tocOpen,
        currentPage: this.currentPage,
      };
      this.syncState();
      this.render();
    });
  }

  async onClose(): Promise<void> {
    this.clearTimers();
    if (this.styleObserver) {
      this.styleObserver.disconnect();
      this.styleObserver = null;
    }
    this.cachedPdf = null;
    this.pageLabels = null;
    this.indexBuildToken++;
    this.documentIndex.removeDocument(this.docId);
  }

  /** Called by main plugin to capture current page for LLM context. */
  getActivePdfContext(
    captureMode: "text" | "image" | "both"
  ): PdfPageContext | null {
    return this.pdfCaptureService.capture({
      captureMode,
      pagesEl: this.pagesEl,
      currentPage: this.currentPage,
      totalPages: this.totalPages,
      pageLabels: this.pageLabels ?? undefined,
      pageTextCache: this.pageTextCache,
      outline: this.currentOutlineItems,
      documentId: this.docId,
      documentName: this.getDisplayText(),
      filePath: resolveCachedExternalPdfPath(this.docId, this.docState?.path),
      zoteroAttachmentKey: this.docState?.zoteroAttachmentKey,
      getSelectionText: () => this.getSelectionTextWithinView(),
      searchIndex: this.documentIndex,
    });
  }

  // ── Snipping Mode ─────────────────────────────────────────────

  public cancelSnippingMode(): void {
    if (!this.pagesEl) return;
    const overlays = this.pagesEl.querySelectorAll(".ai-agent-snipping-overlay");
    overlays.forEach(el => el.remove());
  }

  public startSnippingMode(
    onSnip: (base64: string, pageNum: number, regionText: string) => void
  ): void {
    if (!this.pagesEl) return;
    this.cancelSnippingMode();

    const pageNum = this.currentPage;
    const pageEl = this.pagesEl.querySelector<HTMLElement>(`.pdf-page[data-page-number="${pageNum}"]`);
    if (!pageEl) {
      new Notice("Please wait for the current page to render before snipping.");
      return;
    }

    const overlay = pageEl.createDiv("ai-agent-snipping-overlay");
    const box = overlay.createDiv("ai-agent-snipping-box");
    box.style.display = "none";

    let isDrawing = false;
    let startX = 0;
    let startY = 0;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        this.cancelSnippingMode();
        document.removeEventListener("keydown", handleKeyDown);
      }
    };
    document.addEventListener("keydown", handleKeyDown);

    overlay.addEventListener("mousedown", (e: MouseEvent) => {
      e.stopPropagation();
      e.preventDefault();
      isDrawing = true;
      const rect = overlay.getBoundingClientRect();
      startX = e.clientX - rect.left;
      startY = e.clientY - rect.top;

      box.style.display = "block";
      box.style.left = `${startX}px`;
      box.style.top = `${startY}px`;
      box.style.width = "0px";
      box.style.height = "0px";
    });

    overlay.addEventListener("mousemove", (e: MouseEvent) => {
      if (!isDrawing) return;
      e.stopPropagation();
      e.preventDefault();
      const rect = overlay.getBoundingClientRect();
      const currentX = e.clientX - rect.left;
      const currentY = e.clientY - rect.top;

      const left = Math.min(startX, currentX);
      const top = Math.min(startY, currentY);
      const width = Math.abs(currentX - startX);
      const height = Math.abs(currentY - startY);

      box.style.left = `${left}px`;
      box.style.top = `${top}px`;
      box.style.width = `${width}px`;
      box.style.height = `${height}px`;
    });

    overlay.addEventListener("mouseup", (e: MouseEvent) => {
      if (!isDrawing) return;
      isDrawing = false;
      e.stopPropagation();
      e.preventDefault();

      const rect = overlay.getBoundingClientRect();
      const endX = e.clientX - rect.left;
      const endY = e.clientY - rect.top;

      const left = Math.min(startX, endX);
      const top = Math.min(startY, endY);
      const width = Math.abs(endX - startX);
      const height = Math.abs(endY - startY);

      document.removeEventListener("keydown", handleKeyDown);

      if (width > 5 && height > 5) {
        // Extract the text lines WITHIN the cropped rectangle (region-scoped),
        // not the whole page, before tearing down the overlay. The overlay rect
        // shares the page's client-coordinate space, so the crop box maps
        // directly onto the text-layer spans' bounding rects.
        const regionText = this.extractRegionText(pageEl, {
          left: rect.left + left,
          top: rect.top + top,
          right: rect.left + left + width,
          bottom: rect.top + top + height,
        });
        this.cancelSnippingMode();
        this.extractCanvasRegion(pageEl, left, top, width, height, (base64) =>
          onSnip(base64, pageNum, regionText)
        );
      } else {
        this.cancelSnippingMode();
      }
    });
  }

  /**
   * Collect the text-layer spans whose bounding boxes fall inside a crop
   * rectangle (in client coordinates) and reconstruct their text in reading
   * order. Returns "" when the region has no selectable text (scanned page),
   * letting the caller fall back to an image-only crop reference.
   */
  private extractRegionText(
    pageEl: HTMLElement,
    crop: { left: number; top: number; right: number; bottom: number }
  ): string {
    const spans: RegionTextSpan[] = Array.from(
      pageEl.querySelectorAll<HTMLElement>(".ai-agent-pdf-text-span")
    ).map((el) => {
      const r = el.getBoundingClientRect();
      return {
        left: r.left,
        top: r.top,
        right: r.right,
        bottom: r.bottom,
        text: el.textContent ?? "",
      };
    });
    return extractRegionTextFromSpans(spans, crop);
  }

  private extractCanvasRegion(pageEl: HTMLElement, left: number, top: number, width: number, height: number, onSnip: (base64: string) => void): void {
    const canvas = pageEl.querySelector("canvas");
    if (!canvas) return;

    const scaleX = canvas.width / pageEl.clientWidth;
    const scaleY = canvas.height / pageEl.clientHeight;

    const cropX = left * scaleX;
    const cropY = top * scaleY;
    const cropW = width * scaleX;
    const cropH = height * scaleY;

    const tempCanvas = document.createElement("canvas");
    tempCanvas.width = cropW;
    tempCanvas.height = cropH;
    const ctx = tempCanvas.getContext("2d");
    if (!ctx) return;

    ctx.drawImage(
      canvas,
      cropX, cropY, cropW, cropH,
      0, 0, cropW, cropH
    );

    try {
      const base64 = tempCanvas.toDataURL("image/png").replace(/^data:image\/png;base64,/, "");
      onSnip(base64);
    } catch {
      new Notice("Could not crop image (canvas tainted).");
    }
  }

  // ── Render entry point ────────────────────────────────────────

  private render(): void {
    const container = this.containerEl.children[1] as HTMLElement;
    container.empty();
    container.addClass("ai-agent-external-pdf-view");
    container.toggleClass("ai-agent-external-pdf-dark", this.darkMode);

    const doc = this.resolveDoc();
    if (!doc) {
      this.renderReopenPrompt(container);
      return;
    }

    container.createDiv({ cls: "ai-agent-external-pdf-loading", text: "Loading PDF..." });
    this.renderToolbar(container);
    this.renderPdf(container, doc);
  }

  private renderReopenPrompt(container: HTMLElement): void {
    const wrap = container.createDiv("ai-agent-external-pdf-empty");
    wrap.createDiv({
      cls: "ai-agent-external-pdf-reopen-msg",
      text: "This PDF could not be reopened automatically because Obsidian's security sandbox prevents saving absolute file paths.\n\nPlease use the button below to re-select the file, or drag & drop it here.",
    });
    const btn = wrap.createEl("button", {
      cls: "ai-agent-pdf-reopen-btn",
      text: "Choose file…",
    });
    btn.addEventListener("click", () => {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = ".pdf,application/pdf";
      input.style.display = "none";
      input.addEventListener("change", () => {
        const file = input.files?.[0];
        input.remove();
        if (!file) return;
        const rawPath = (file as unknown as { path?: string }).path;
        const path = typeof rawPath === "string" && rawPath.length > 0 ? rawPath : undefined;

        putExternalPdfDoc({
          id: this.docId,
          name: file.name,
          path,
          file,
        });

        this.docState = {
          docId: this.docId,
          name: file.name,
          path,
          zoom: this.zoom,
          darkMode: this.darkMode,
          tocOpen: this.tocOpen,
          currentPage: this.currentPage,
        };
        this.syncState();
        this.render();
      });
      document.body.appendChild(input);
      input.click();
    });
  }

  private resolveDoc(): ExternalPdfDoc | null {
    let cached = getExternalPdfDoc(this.docId);
    const resolvedStatePath = resolveExternalPdfPath(this.docState?.path, cached?.path);
    if (cached && resolvedStatePath && cached.path !== resolvedStatePath) {
      cached = replaceExternalPdfDocPath(this.docId, resolvedStatePath) || cached;
    }
    if (cached) {
      if (cached.path && !this.docState?.path) {
        this.docState = {
          ...this.docState,
          docId: this.docId,
          name: cached.name,
          path: cached.path,
        };
      }
      return cached;
    }
    if (!this.docState?.path) {
      console.warn("[AI Agent] resolveDoc failed: no path in docState or cache for ID", this.docId);
      return null;
    }
    if (!existsSync(this.docState.path)) {
      console.warn("[AI Agent] resolveDoc failed: file does not exist at path", this.docState.path);
      return null;
    }
    const doc: ExternalPdfDoc = {
      id: this.docState.docId,
      name: this.docState.name,
      path: this.docState.path,
    };
    putExternalPdfDoc(doc);
    return doc;
  }

  // ── PDF loading + lazy rendering ──────────────────────────────

  private async renderPdf(
    container: HTMLElement,
    doc: ExternalPdfDoc
  ): Promise<void> {
    const token = ++this.renderToken;
    this.renderedPages.clear();
    this.renderingPages.clear();
    this.pageBaseDims = [];
    this.pageTextCache.clear();
    this.currentOutlineItems = [];
    this.documentIndex.removeDocument(this.docId);
    this.renderedZoom = this.zoom;

    try {
      // 1. Load (or reuse cached) PDF document
      let pdf: PdfDocument;
      if (this.cachedPdfDocId === this.docId && this.cachedPdf) {
        pdf = this.cachedPdf;
      } else {
        const data = await this.loadPdfData(doc);
        if (token !== this.renderToken) return;
        const pdfjsLib = await loadPdfJs();
        pdf = (await pdfjsLib.getDocument({ data, disableFontFace: true }).promise) as PdfDocument;
        if (token !== this.renderToken) return;
        this.cachedPdf = pdf;
        this.cachedPdfDocId = this.docId;
      }

      // 2. Set up container
      container.empty();
      this.renderToolbar(container);
      const pagesEl = container.createDiv("ai-agent-external-pdf-pages");
      this.pagesEl = pagesEl;
      this.attachPdfSelectionHandlers(pagesEl);

      // Determine a stable reference width by checking the first few pages and the current page,
      // because the cover page (Page 1) is often narrower than the rest of the document.
      let maxW = 0;
      const pagesToCheck = new Set([1, 2, 3, this.currentPage]);
      for (const pNum of pagesToCheck) {
        if (pNum > 0 && pNum <= pdf.numPages) {
          const p = await pdf.getPage(pNum);
          const vp = p.getViewport({ scale: 1 });
          if (vp.width > maxW) maxW = vp.width;
        }
      }
      this.referenceBaseWidth = maxW || 800;

      this.renderedZoom = this.zoom;
      this.renderedBaseFitScale = this.baseFitScale;
      this.totalPages = pdf.numPages;
      this.pageLabels = await this.loadPageLabels(pdf);
      this.updatePageCount();
      await this.renderToc(pdf);
      // Removed startDocumentTextIndex: Frontend should not perform full-document indexing. L1 extraction is handled by backend.
      container.onwheel = (e: WheelEvent) => this.handleWheelZoom(e);


        // Fetch Zotero annotations if we have an attachment key
        if (this.docState?.zoteroAttachmentKey && this.plugin?.getZoteroAnnotations) {
          try {
            this.zoteroAnnotations = await this.plugin.getZoteroAnnotations(this.docState.zoteroAttachmentKey);
          } catch (e) {
            console.warn("Failed to fetch Zotero annotations", e);
          }
        }

        let savedPage = this.currentPage;

        // Overwrite savedPage with the exact pageIndex from the target annotation
        if (this.docState?.targetAnnotationKey && this.zoteroAnnotations.length > 0) {
          const targetAnn = this.zoteroAnnotations.find(a => a.key === this.docState!.targetAnnotationKey);
          if (targetAnn && targetAnn.position && typeof targetAnn.position.pageIndex === 'number') {
            savedPage = targetAnn.position.pageIndex + 1;
            this.currentPage = savedPage;
          }
        }

        // 3. Create placeholder divs for ALL pages (dimensions only, no canvas yet).
      //    This reserves correct scroll space without rendering every page.
      for (let i = 1; i <= pdf.numPages; i++) {
        if (token !== this.renderToken) return;
        const page = await pdf.getPage(i);
        const baseVp = page.getViewport({ scale: 1 });
        this.pageBaseDims[i - 1] = { width: baseVp.width, height: baseVp.height };
        const scale = this.baseFitScale * this.zoom;
        const vp = page.getViewport({ scale });
        const pageEl = pagesEl.createDiv("pdf-page ai-agent-external-pdf-page");
        pageEl.setAttribute("data-page-number", String(i));
        pageEl.style.width = `${Math.floor(vp.width)}px`;
        pageEl.style.height = `${Math.floor(vp.height)}px`;
      }

      // 4. Render current page first for immediate display, then neighbors in background

      await this.renderPagesInRange(token, savedPage, savedPage);
      if (token !== this.renderToken) return;
      this.notifyContextChanged();
      // Background-render surrounding pages without blocking scroll setup
      this.renderPagesInRange(token, savedPage - RENDER_RADIUS, savedPage + RENDER_RADIUS);

      // 5. Scroll to saved page, then enable scroll-driven lazy rendering
      setTimeout(() => {
        if (token !== this.renderToken) return;
        this.goToPage(savedPage, "auto");

        // Scroll to specific annotation if requested
        if (this.docState?.targetAnnotationKey && this.pagesEl) {
          const annEl = this.pagesEl.querySelector<HTMLElement>(`[data-annotation-key="${this.docState.targetAnnotationKey}"]`);
          const scrollContainer = this.containerEl.children[1] as HTMLElement;
          if (annEl && scrollContainer) {
            const scrollToAnnotation = () => {
              if (scrollContainer.clientHeight === 0) {
                setTimeout(scrollToAnnotation, 50);
                return;
              }
              annEl.scrollIntoView({ block: "center", behavior: "instant" });

              // Flash effect to highlight it
              annEl.style.transition = "outline-color 0.5s ease, box-shadow 0.5s ease";
              const originalOutline = annEl.style.outline;
              const originalBoxShadow = annEl.style.boxShadow;
              annEl.style.outline = "3px solid rgba(255, 100, 100, 0.95)";
              annEl.style.boxShadow = "0 0 0 4px rgba(255, 100, 100, 0.25)";
              setTimeout(() => {
                annEl.style.outline = originalOutline;
                annEl.style.boxShadow = originalBoxShadow;
              }, 1000);
            };
            scrollToAnnotation();
          }
        }

        // Start lazy rendering on scroll

        setTimeout(() => {
          if (token !== this.renderToken) return;
          container.onscroll = () => {
            if (this.isZooming) return;
            this.updateCurrentPage();
            this.onScrollLazyRender(token);
          };
        }, 200);
      }, 300);
    } catch (err: unknown) {
      if (token !== this.renderToken) return;
      container.empty();
      container.createDiv({
        cls: "ai-agent-external-pdf-empty",
        text: `Could not render PDF: ${err instanceof Error ? err.message : String(err)}`,
      });
    }
  }

  /** Renders canvas content for pages [start, end] that haven't been rendered yet. */
  private async renderPagesInRange(
    token: number,
    start: number,
    end: number
  ): Promise<void> {
    if (!this.pagesEl || !this.cachedPdf) return;
    const from = Math.max(1, start);
    const to = Math.min(this.totalPages, end);
    for (let i = from; i <= to; i++) {
      if (token !== this.renderToken) return;
      if (this.renderedPages.has(i) || this.renderingPages.has(i)) continue;
      const pageEl = this.pagesEl.querySelector<HTMLElement>(
        `.pdf-page[data-page-number="${i}"]`
      );
      if (!pageEl) continue;

      this.renderingPages.add(i);
      try {
        const page = await this.cachedPdf.getPage(i);
        if (token !== this.renderToken) { this.renderingPages.delete(i); return; }
        await this.renderPageCanvas(pageEl, page, i);
        if (token !== this.renderToken) { this.renderingPages.delete(i); return; }
        this.renderedPages.add(i);
      } catch (err) {
        console.error(`[AI Agent] Failed to render PDF page ${i}:`, err);
        this.renderedPages.add(i);
      } finally {
        this.renderingPages.delete(i);
      }
    }
  }

  /** Renders (or re-renders) a single page's canvas inside an existing placeholder div. */
  private async renderPageCanvas(
    pageEl: HTMLElement,
    page: PdfPage,
    pageNum: number
  ): Promise<void> {
    if (!this.pagesEl) return;
    const scale = this.baseFitScale * this.zoom;
    // Use a hi-res viewport scaled by DPR so canvas is crisp on retina displays
    const dpr = (this.containerEl.win || window).devicePixelRatio || 1;
    const viewport = page.getViewport({ scale });
    const hiResViewport = page.getViewport({ scale: scale * dpr });
    const w = Math.floor(viewport.width);
    const h = Math.floor(viewport.height);

    // Update placeholder size (CSS/logical pixels)
    pageEl.style.width = `${w}px`;
    pageEl.style.height = `${h}px`;

    // Reuse existing canvas if present, otherwise create
    let canvas = pageEl.querySelector("canvas");
    if (!canvas) {
      canvas = pageEl.createEl("canvas");
    }
    // Physical canvas dimensions at device resolution
    canvas.width = Math.floor(hiResViewport.width);
    canvas.height = Math.floor(hiResViewport.height);
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    canvas.style.transform = "none";

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    // Reset any leftover transform from previous render (prevents flipped pages on reuse)
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    await page.render({ canvasContext: ctx, viewport: hiResViewport }).promise;

    // Text extraction and precise HTML text layer positioning. pdf.js text is
    // the source of truth; the DOM text layer is only a capture fallback.
    this.extractPageTextFromPdfJs(page, pageNum).then(({ pageContext, items }) => {
      pageEl.dataset.text = pageContext.text;
      pageEl.dataset.textSource = pageContext.textQuality?.source || "pdfjs";
      pageEl.dataset.textQualityScore = String(pageContext.textQuality?.score ?? 0);

      // 2. Re-create text layer with absolutely positioned spans matching the canvas
      let textLayer = pageEl.querySelector<HTMLElement>(".ai-agent-external-text-layer");
      if (!textLayer) {
        textLayer = pageEl.createDiv("textLayer ai-agent-external-text-layer");
      } else {
        textLayer.empty();
      }
      textLayer.style.transform = "none";

      // Create spans for each text item
      for (const item of items) {
        const str = typeof item.str === "string" ? item.str : "";
        if (!str.trim()) continue;

        const transform = Array.isArray(item.transform) ? item.transform : [];
        const tx = typeof transform[4] === "number" ? transform[4] : 0;
        const ty = typeof transform[5] === "number" ? transform[5] : 0;

        // Convert PDF coordinates to viewport coordinates
        const [vx, vy] = viewport.convertToViewportPoint(tx, ty);

        // Calculate font size (using transform[3] which is scaleY)
        const scaleY = typeof transform[3] === "number" ? Math.abs(transform[3]) : 12;
        const fontSize = scaleY * scale;

        const span = textLayer.createEl("span", {
          text: str,
          cls: "ai-agent-pdf-text-span"
        });

        span.style.left = `${vx}px`;
        // Since vy is the baseline, subtract the font height to align the span top
        span.style.top = `${vy - fontSize}px`;
        span.style.fontSize = `${fontSize}px`;
        span.style.height = `${fontSize}px`;

        // Scale width and stretch font mathematically if width is provided in the PDF
        const itemWidth = typeof item.width === "number" ? item.width : 0;
        if (itemWidth > 0) {
          const targetWidth = itemWidth * scale;
          span.style.width = `${targetWidth}px`;

          const measuredWidth = span.offsetWidth;
          if (measuredWidth > 0 && Math.abs(measuredWidth - targetWidth) > 0.5) {
            const scaleX = targetWidth / measuredWidth;
            span.style.transform = `scaleX(${scaleX})`;
          }
        }
      }

      // 3. Render Zotero Annotations for this page
      const pageZoteroAnnotations = this.zoteroAnnotations.filter(
        (a) => a.position && a.position.pageIndex === pageNum - 1
      );
      if (pageZoteroAnnotations.length > 0) {
        let annotLayer = pageEl.querySelector<HTMLElement>(".zotero-annotation-layer");
        if (!annotLayer) {
          annotLayer = pageEl.createDiv("zotero-annotation-layer");
          annotLayer.style.position = "absolute";
          annotLayer.style.top = "0";
          annotLayer.style.left = "0";
          annotLayer.style.width = "100%";
          annotLayer.style.height = "100%";
          annotLayer.style.pointerEvents = "none";
          annotLayer.style.zIndex = "1";
        } else {
          annotLayer.empty();
        }

        for (const ann of pageZoteroAnnotations) {
          if (!ann.position.rects || !Array.isArray(ann.position.rects)) continue;

          for (const rect of ann.position.rects) {
            // Zotero rect format: [x1, y1, x2, y2]
            const [x1, y1, x2, y2] = rect;
            // Need to convert bottom-left PDF coordinates to viewport coordinates
            const [vx1, vy1] = viewport.convertToViewportPoint(x1, y1);
            const [vx2, vy2] = viewport.convertToViewportPoint(x2, y2);

            const minX = Math.min(vx1, vx2);
            const minY = Math.min(vy1, vy2);
            const w = Math.abs(vx1 - vx2);
            const h = Math.abs(vy1 - vy2);

            const div = annotLayer.createDiv("zotero-highlight");
            div.setAttribute("data-annotation-key", ann.key);
            div.style.position = "absolute";
            div.style.left = `${minX}px`;
            div.style.top = `${minY}px`;
            div.style.width = `${w}px`;
            div.style.height = `${h}px`;

            const boxStyle = buildZoteroAnnotationBoxStyle(ann.type, ann.color);
            div.style.border = boxStyle.border;
            if (boxStyle.borderBottom) div.style.borderBottom = boxStyle.borderBottom;
            div.style.backgroundColor = boxStyle.backgroundColor;
            if (boxStyle.boxShadow) div.style.boxShadow = boxStyle.boxShadow;
            if (boxStyle.opacity) div.style.opacity = boxStyle.opacity;
            if (boxStyle.mixBlendMode) div.style.mixBlendMode = boxStyle.mixBlendMode;
            div.style.boxSizing = "border-box";
          }
        }
      }
    }).catch((err) => {
      console.warn("[AI Agent] Text content extraction failed:", err);
    });
  }

  /**
   * In-place zoom re-render: updates canvas resolution for already-rendered pages
   * and adjusts placeholder sizes for the rest — no DOM clear, no page jump.
   */
  private async rerenderInPlace(oldZoom?: number): Promise<void> {
    if (!this.pagesEl || !this.cachedPdf) return;
    const token = this.renderToken;
    const scrollContainer = this.pagesEl.parentElement;

    // Clear any CSS transform so offsetTop reads are layout-accurate
    this.pagesEl.style.transform = "";

    // Save scroll anchor: we want the anchor page to stay at the same visual offset
    // after all page sizes change. Record its offsetTop and its distance from scrollTop.
    const anchorEl = this.pagesEl.querySelector<HTMLElement>(
      `.pdf-page[data-page-number="${this.currentPage}"]`
    );
    const anchorTopBefore = anchorEl?.offsetTop ?? 0;
    const scrollTopBefore = scrollContainer?.scrollTop ?? 0;
    const offsetWithinPage = scrollTopBefore - anchorTopBefore;
    const anchorFromScrollTop = anchorTopBefore - scrollTopBefore;

    // Only re-render visible pages to keep zoom buttery-smooth and responsive
    const startPage = Math.max(1, this.currentPage - 1);
    const endPage = Math.min(this.totalPages, this.currentPage + 1);

    // Remove non-visible pages from renderedPages so they are lazily re-rendered on scroll
    for (const pageNum of Array.from(this.renderedPages)) {
      if (pageNum < startPage || pageNum > endPage) {
        this.renderedPages.delete(pageNum);
      }
    }

    // Re-render visible pages at new zoom in-place
    for (let pageNum = startPage; pageNum <= endPage; pageNum++) {
      if (token !== this.renderToken) return;
      const pageEl = this.pagesEl.querySelector<HTMLElement>(
        `.pdf-page[data-page-number="${pageNum}"]`
      );
      if (!pageEl) continue;
      const page = await this.cachedPdf.getPage(pageNum);
      if (token !== this.renderToken) return;
      await this.renderPageCanvas(pageEl, page, pageNum);
      this.renderedPages.add(pageNum);
    }

    // Resize placeholder divs for non-rendered pages using cached base dimensions and reset their transforms
    for (let i = 1; i <= this.totalPages; i++) {
      if (this.renderedPages.has(i)) continue;
      const pageEl = this.pagesEl.querySelector<HTMLElement>(
        `.pdf-page[data-page-number="${i}"]`
      );
      if (!pageEl || !this.pageBaseDims[i - 1]) continue;
      const { width: bw, height: bh } = this.pageBaseDims[i - 1];
      if (bw > 0 && bh > 0) {
        const scale = this.baseFitScale * this.zoom;
        pageEl.style.width = `${Math.floor(bw * scale)}px`;
        pageEl.style.height = `${Math.floor(bh * scale)}px`;
      }

      const canvas = pageEl.querySelector("canvas");
      if (canvas) {
        canvas.style.transform = "none";
      }
      const textLayer = pageEl.querySelector<HTMLElement>(".ai-agent-external-text-layer");
      if (textLayer) {
        textLayer.style.transform = "none";
      }
    }

    if (token !== this.renderToken) return;

    // Restore scroll: just to handle minor layout shifts from canvas replacing placeholders
    if (scrollContainer) {
      if (anchorEl) {
        scrollContainer.scrollTop = anchorEl.offsetTop - anchorFromScrollTop;
      }
    }

    if (this.zoomInputEl && document.activeElement !== this.zoomInputEl) {
      this.zoomInputEl.value = `${Math.round(this.zoom * 100)}%`;
    }
  }

  /** Triggered on scroll: renders pages entering the ±RENDER_RADIUS window immediately.
   *  If a render is in progress, marks dirty so a follow-up render fires automatically. */
  private async onScrollLazyRender(token: number): Promise<void> {
    if (this.isLazyRendering) {
      this.lazyRenderDirty = true;
      return;
    }
    this.isLazyRendering = true;
    this.lazyRenderDirty = false;

    try {
      await this.renderPagesInRange(
        token,
        this.currentPage - RENDER_RADIUS,
        this.currentPage + RENDER_RADIUS
      );
    } catch (err) {
      console.error("[AI Agent] Lazy render batch failed:", err);
    } finally {
      this.isLazyRendering = false;
      if (this.lazyRenderDirty && token === this.renderToken) {
        this.lazyRenderDirty = false;
        this.onScrollLazyRender(token);
      }
    }
  }

  private async loadPdfData(doc: ExternalPdfDoc): Promise<Uint8Array> {
    if (doc.file) return new Uint8Array(await doc.file.arrayBuffer());
    if (doc.path && existsSync(doc.path)) return new Uint8Array(readFileSync(doc.path));
    throw new Error("The PDF file is not available.");
  }

  private async extractPageTextFromPdfJs(
    page: PdfPage,
    pageNum: number
  ): Promise<{ pageContext: PdfWindowPage; items: RawPdfTextItem[] }> {
    const textContent = await page.getTextContent();
    const items = textContent.items;
    const layout = layoutPdfJsTextItems(items, "pdfjs");
    const pageContext: PdfWindowPage = {
      pageNum,
      text: layout.text,
      textQuality: layout.quality,
    };

    this.pageTextCache.set(pageNum, pageContext);
    this.documentIndex.upsertPage(this.docId, pageContext, this.currentOutlineItems);
    if (pageNum === this.currentPage) this.notifyContextChanged();

    return { pageContext, items };
  }

  private getSelectionTextWithinView(): string | null {
    if (!this.pagesEl) return null;
    const selection = this.pagesEl.ownerDocument.getSelection();
    if (!selection || selection.isCollapsed) return null;
    const range = selection.getRangeAt(0);
    if (!this.pagesEl.contains(range.commonAncestorContainer)) return null;
    return selection.toString().trim() || null;
  }

  private attachPdfSelectionHandlers(pagesEl: HTMLElement): void {
    pagesEl.addEventListener("contextmenu", (e: MouseEvent) => {
      const text = this.getSelectionTextWithinView();
      if (!text) return;
      const menu = new Menu();
      menu.addItem((item) =>
        item
          .setIcon("sigma")
          .setTitle("Convert to LaTeX (Copy)")
          .onClick(() => this.convertSelectionToLatex(text))
      );
      menu.showAtMouseEvent(e);
    });

    if (!this.latexKeydownRegistered) {
      this.latexKeydownRegistered = true;
      this.registerDomEvent(
        this.containerEl.ownerDocument,
        "keydown",
        (e: KeyboardEvent) => {
          if (e.key === "c" && e.shiftKey && (e.metaKey || e.ctrlKey)) {
            const text = this.getSelectionTextWithinView();
            if (!text) return;
            e.preventDefault();
            this.convertSelectionToLatex(text);
          }
        }
      );
    }
  }

  private async convertSelectionToLatex(rawText: string): Promise<void> {
    if (!this.plugin?.llmClient) {
      new Notice("LLM client not available.");
      return;
    }
    new Notice("Converting to LaTeX…");
    const messages: LLMMessage[] = [
      {
        role: "system",
        content:
          "You are a LaTeX transcription assistant. The user will give you raw text extracted from a PDF, which may contain garbled or missing math. Convert it to clean Markdown with proper LaTeX delimiters: inline math as $...$, display math as $$...$$. Output only the converted text — no explanations, no code fences.",
      },
      {
        role: "user",
        content: rawText,
      },
    ];
    try {
      const result = await this.plugin.llmClient.complete(messages);
      await navigator.clipboard.writeText(result.trim());
      new Notice("LaTeX copied to clipboard.");
    } catch (err) {
      console.error("LaTeX conversion failed:", err);
      new Notice("Conversion failed. Check the console for details.");
    }
  }

  private createToolbarIcon(
    toolbar: HTMLElement,
    label: string,
    icon: string,
    onClick: () => void
  ): HTMLElement {
    const btn = toolbar.createDiv({
      cls: "clickable-icon ai-agent-pdf-tool-btn",
      attr: { "aria-label": label },
    });
    setIcon(btn, icon);
    btn.addEventListener("click", onClick);
    return btn;
  }

  private renderToolbar(container: HTMLElement): void {
    const titleContainer = this.containerEl.querySelector(".view-header-title-container") as HTMLElement;
    const titleEl = this.containerEl.querySelector(".view-header-title") as HTMLElement;

    if (titleEl) {
      titleEl.style.display = "none";
    }

    if (titleContainer) {
      titleContainer.querySelector(".ai-agent-external-pdf-toolbar")?.remove();

      const toolbar = titleContainer.createDiv("ai-agent-external-pdf-toolbar");
      toolbar.setAttribute("aria-label", "PDF controls");

      this.createToolbarIcon(toolbar, "Table of contents", "list", () => this.toggleToc());
      this.createToolbarIcon(toolbar, "Zoom out", "zoom-out", () => this.setZoom(this.zoom - 0.15));

      this.zoomInputEl = toolbar.createEl("input", {
        cls: "ai-agent-pdf-zoom-label ai-agent-pdf-zoom-input",
        attr: {
          type: "text",
          value: `${Math.round(this.zoom * 100)}%`,
          "aria-label": "Zoom level",
        },
      });
      this.zoomInputEl.addEventListener("focus", () => {
        if (this.zoomInputEl) {
          // Strip the % sign when editing
          this.zoomInputEl.value = String(Math.round(this.zoom * 100));
          this.zoomInputEl.select();
        }
      });
      this.zoomInputEl.addEventListener("blur", () => {
        this.applyZoomInput();
      });
      this.zoomInputEl.addEventListener("keydown", (e: KeyboardEvent) => {
        if (e.key === "Enter") {
          e.preventDefault();
          this.zoomInputEl?.blur();
        } else if (e.key === "Escape") {
          if (this.zoomInputEl) {
            this.zoomInputEl.value = `${Math.round(this.zoom * 100)}%`;
            this.zoomInputEl.blur();
          }
        }
      });

      this.createToolbarIcon(toolbar, "Zoom in", "zoom-in", () => this.setZoom(this.zoom + 0.15));
      this.createToolbarIcon(toolbar, "Fit to width", "maximize", () => this.setZoom(1));
      this.createToolbarIcon(toolbar, "Snip Region to Chat", "scissors", () => {
        (this.app as any).commands.executeCommandById("incurator-obsidian-agent:snip-pdf-to-chat");
      });
      this.createToolbarIcon(toolbar, "Reload PDF from disk", "refresh-cw", () => this.reloadFromDisk());

      const pageGroup = toolbar.createDiv("ai-agent-pdf-page-jump");
      this.pageInputEl = pageGroup.createEl("input", {
        cls: "ai-agent-pdf-page-input",
        attr: { type: "number", min: "1", value: "1", "aria-label": "Page number" },
      });
      this.pageInputEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter") this.goToPage(Number(this.pageInputEl?.value || "1"));
      });
      this.pageInputEl.addEventListener("change", () => {
        this.goToPage(Number(this.pageInputEl?.value || "1"));
      });
      this.pageCountEl = pageGroup.createSpan({
        cls: "ai-agent-pdf-page-count",
        text: "/ -",
      });

      const darkBtn = this.createToolbarIcon(toolbar, "Toggle dark mode", "moon", () => this.toggleDarkMode());
      this.darkModeBtnEl = darkBtn as unknown as HTMLButtonElement; // Keep type compatibility
      darkBtn.toggleClass("is-active", this.darkMode);
    }

    const tocWrapper = container.createDiv("ai-agent-external-pdf-toc-wrapper");
    this.tocPanelEl = tocWrapper.createDiv("ai-agent-external-pdf-toc");
    this.tocPanelEl.toggleClass("is-open", this.tocOpen);
  }

  // ── TOC ───────────────────────────────────────────────────────

  private async renderToc(pdf: PdfDocument): Promise<void> {
    if (!this.tocPanelEl) return;
    this.tocPanelEl.empty();
    const outline = await pdf.getOutline();
    if (!outline || outline.length === 0) {
      this.currentOutlineItems = [];
      this.tocPanelEl.createDiv({ cls: "ai-agent-pdf-toc-empty", text: "No table of contents" });
      return;
    }
    const tree = await this.buildTocTree(pdf, outline);
    this.currentOutlineItems = flattenTocTree(tree);
    for (const node of tree) {
      this.renderTocNode(this.tocPanelEl, node, 0);
    }
  }

  private async loadPageLabels(pdf: PdfDocument): Promise<string[] | null> {
    if (typeof pdf.getPageLabels !== "function") return null;
    try {
      const labels = await pdf.getPageLabels();
      return Array.isArray(labels) ? labels : null;
    } catch {
      return null;
    }
  }

  private renderTocNode(container: HTMLElement, node: TocTreeNode, level: number): void {
    const wrap = container.createDiv("ai-agent-pdf-toc-node");
    const row = wrap.createDiv("ai-agent-pdf-toc-row");
    row.style.paddingLeft = `${level * 16 + 6}px`;

    if (node.children.length > 0) {
      const toggleBtn = row.createSpan({ cls: "ai-agent-pdf-toc-toggle" });
      setIcon(toggleBtn, "chevron-right");
      const childrenEl = wrap.createDiv("ai-agent-pdf-toc-children");
      // Top-level nodes start expanded
      if (level === 0) {
        childrenEl.addClass("is-open");
        toggleBtn.addClass("is-open");
      }
      toggleBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const open = childrenEl.hasClass("is-open");
        childrenEl.toggleClass("is-open", !open);
        toggleBtn.toggleClass("is-open", !open);
      });
      const label = row.createEl("span", {
        cls: "ai-agent-pdf-toc-label",
        text: node.title,
        attr: { "data-page-num": String(node.pageNum) },
      });
      label.addEventListener("click", () => this.selectTocPage(node.pageNum));
      for (const child of node.children) {
        this.renderTocNode(childrenEl, child, level + 1);
      }
    } else {
      row.createSpan({ cls: "ai-agent-pdf-toc-toggle-spacer" });
      const label = row.createEl("span", {
        cls: "ai-agent-pdf-toc-label",
        text: node.title,
        attr: { "data-page-num": String(node.pageNum) },
      });
      label.addEventListener("click", () => this.selectTocPage(node.pageNum));
    }
  }

  private selectTocPage(pageNum: number): void {
    this.goToPage(pageNum);
    this.tocOpen = false;
    this.tocPanelEl?.removeClass("is-open");
    this.syncState();
  }

  /** Highlights the TOC entry for the current page and scrolls it into view. */
  private updateTocActive(): void {
    if (!this.tocPanelEl) return;
    const labels = Array.from(
      this.tocPanelEl.querySelectorAll<HTMLElement>(".ai-agent-pdf-toc-label[data-page-num]")
    );
    if (labels.length === 0) return;

    let activeLabel: HTMLElement | null = null;
    for (const label of labels) {
      if (Number(label.dataset.pageNum) <= this.currentPage) activeLabel = label;
    }

    labels.forEach((l) => l.removeClass("is-active"));
    if (activeLabel) {
      activeLabel.addClass("is-active");
      // Expand any collapsed ancestor so the active item is visible
      let el: HTMLElement | null = activeLabel.parentElement;
      while (el && el !== this.tocPanelEl) {
        if (el.hasClass("ai-agent-pdf-toc-children") && !el.hasClass("is-open")) {
          el.addClass("is-open");
          const prevRow = el.previousElementSibling as HTMLElement | null;
          prevRow?.querySelector<HTMLElement>(".ai-agent-pdf-toc-toggle")?.addClass("is-open");
        }
        el = el.parentElement;
      }
      const panel = this.tocPanelEl;
      const labelRect = activeLabel.getBoundingClientRect();
      const panelRect = panel.getBoundingClientRect();

      if (labelRect.top < panelRect.top || labelRect.bottom > panelRect.bottom) {
        panel.scrollTo({
          top: panel.scrollTop + (labelRect.top - panelRect.top) - panel.clientHeight / 2 + labelRect.height / 2,
          behavior: "smooth"
        });
      }
    }
  }

  private async buildTocTree(
    pdf: PdfDocument,
    outline: PdfJsOutlineItem[]
  ): Promise<TocTreeNode[]> {
    const nodes: TocTreeNode[] = [];
    for (const entry of outline) {
      const pageNum = await this.resolveOutlinePage(pdf, entry.dest);
      if (entry.title && pageNum !== null) {
        nodes.push({
          title: entry.title,
          pageNum,
          children: entry.items?.length
            ? await this.buildTocTree(pdf, entry.items)
            : [],
        });
      }
    }
    return nodes;
  }

  private async resolveOutlinePage(
    pdf: PdfDocument,
    dest: string | unknown[] | undefined
  ): Promise<number | null> {
    if (!dest) return null;
    const destination = typeof dest === "string" ? await pdf.getDestination(dest) : dest;
    const ref = destination?.[0];
    if (!ref) return null;
    try {
      return (await pdf.getPageIndex(ref)) + 1;
    } catch {
      return null;
    }
  }

  // ── Zoom ──────────────────────────────────────────────────────

  private applyVisualZoom(oldZoom: number): void {
    if (!this.pagesEl) return;

    const currentLogicalScale = this.baseFitScale * this.zoom;
    const renderedLogicalScale = this.renderedBaseFitScale * this.renderedZoom;
    const factor = currentLogicalScale / renderedLogicalScale;

    for (let i = 1; i <= this.totalPages; i++) {
      const pageEl = this.pagesEl.querySelector<HTMLElement>(
        `.pdf-page[data-page-number="${i}"]`
      );
      if (!pageEl || !this.pageBaseDims[i - 1]) continue;

      const { width: bw, height: bh } = this.pageBaseDims[i - 1];

      // Calculate new logical dimensions for the placeholder div
      const scale = this.baseFitScale * this.zoom;
      const newW = Math.floor(bw * scale);
      const newH = Math.floor(bh * scale);

      pageEl.style.width = `${newW}px`;
      pageEl.style.height = `${newH}px`;

      // Scale the canvas visually using GPU transforms
      const canvas = pageEl.querySelector("canvas");
      if (canvas) {
        canvas.style.transform = `scale(${factor})`;
        canvas.style.transformOrigin = "left top";
      }

      // Scale the text layer visually
      const textLayer = pageEl.querySelector<HTMLElement>(".ai-agent-external-text-layer");
      if (textLayer) {
        textLayer.style.transform = `scale(${factor})`;
        textLayer.style.transformOrigin = "left top";
      }
    }
  }

  private applyZoomInput(): void {
    if (!this.zoomInputEl) return;
    const raw = this.zoomInputEl.value.trim().replace(/%$/, "");
    const parsed = parseFloat(raw);
    if (!isNaN(parsed) && parsed >= 10 && parsed <= 500) {
      this.setZoom(parsed / 100);
    }
    // Always restore the display value with %
    this.zoomInputEl.value = `${Math.round(this.zoom * 100)}%`;
  }

  public setZoom(newZoom: number): void {
    if (!this.pagesEl || !this.cachedPdf || this.totalPages === 0) return;

    const oldZoom = this.zoom;
    this.zoom = Math.max(0.1, Math.min(newZoom, 5.0));

    // Update zoom input (only if not currently being edited)
    if (this.zoomInputEl && document.activeElement !== this.zoomInputEl) {
      this.zoomInputEl.value = `${Math.round(this.zoom * 100)}%`;
    }

    if (this.zoomDebounceTimer !== null) {
      clearTimeout(this.zoomDebounceTimer);
      this.zoomDebounceTimer = null;
    }

    const scrollContainer = this.pagesEl?.parentElement;
    let anchorTopBefore = 0;
    let offsetWithinPage = 0;
    let anchorEl: HTMLElement | null = null;

    if (scrollContainer && this.pagesEl) {
      anchorEl = this.pagesEl.querySelector<HTMLElement>(
        `.pdf-page[data-page-number="${this.currentPage}"]`
      );
      if (anchorEl) {
        anchorTopBefore = anchorEl.offsetTop;
        const scrollTopBefore = scrollContainer.scrollTop;
        offsetWithinPage = scrollTopBefore - anchorTopBefore;
      }
    }

    // Apply visual scale instantly
    this.applyVisualZoom(oldZoom);

    // Adjust scroll position synchronously to avoid page jumping
    if (scrollContainer) {
      // Force layout reflow so scroll bounds update synchronously
      const _forceReflow = scrollContainer.scrollHeight;

      if (
        this.zoomAnchorOldZoom !== undefined &&
        this.zoomAnchorMouseX !== undefined &&
        this.zoomAnchorMouseY !== undefined &&
        this.zoomAnchorContentX !== undefined &&
        this.zoomAnchorContentY !== undefined
      ) {
        const factor = this.zoom / this.zoomAnchorOldZoom;
        scrollContainer.scrollLeft = this.zoomAnchorContentX * factor - this.zoomAnchorMouseX;
        scrollContainer.scrollTop = this.zoomAnchorContentY * factor - this.zoomAnchorMouseY;

        // Reset anchor info
        this.zoomAnchorOldZoom = undefined;
        this.zoomAnchorMouseX = undefined;
        this.zoomAnchorMouseY = undefined;
        this.zoomAnchorContentX = undefined;
        this.zoomAnchorContentY = undefined;
      } else if (anchorEl) {
        const ratio = this.zoom / oldZoom;
        scrollContainer.scrollTop = anchorEl.offsetTop + (offsetWithinPage * ratio);
      }
    }

    this.syncState();

    // Debounce high-res render to allow quick successive clicks
    this.zoomDebounceTimer = setTimeout(() => {
      this.zoomDebounceTimer = null;
      this.renderedZoom = this.zoom;
      this.renderedBaseFitScale = this.baseFitScale;

      this.rerenderInPlace().then(() => {
        setTimeout(() => {
          this.isZooming = false;
        }, 200);
      });
    }, 150);
  }

  private handleWheelZoom(event: WheelEvent): void {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    event.stopPropagation();

    const pagesEl = this.pagesEl;
    const scrollContainer = pagesEl?.parentElement;
    if (!pagesEl || !scrollContainer) return;

    const rect = scrollContainer.getBoundingClientRect();
    const contentRect = pagesEl.getBoundingClientRect();

    const mouseX = event.clientX - rect.left;
    const mouseY = event.clientY - rect.top;

    const oldZoom = this.zoom;
    const step = event.deltaY < 0 ? 0.1 : -0.1;
    const newZoom = Math.min(3, Math.max(0.5, Number((oldZoom + step).toFixed(2))));

    if (newZoom === oldZoom) return;

    this.isZooming = true;
    this.zoom = newZoom;

    // Apply visual scale instantly (buttery smooth CSS transition/rendering)
    this.applyVisualZoom(oldZoom);

    // Force synchronous layout reflow so scrollContainer's scrollWidth/scrollHeight update immediately
    const _forceReflow = scrollContainer.scrollHeight;

    // Adjust scroll container scroll position to keep mouse point anchored perfectly
    const factor = newZoom / oldZoom;
    const mouseInContentX = event.clientX - contentRect.left;
    const mouseInContentY = event.clientY - contentRect.top;

    scrollContainer.scrollLeft = mouseInContentX * factor - mouseX;
    scrollContainer.scrollTop = mouseInContentY * factor - mouseY;

    // Update label immediately for responsiveness
    if (this.zoomInputEl && document.activeElement !== this.zoomInputEl) {
      this.zoomInputEl.value = `${Math.round(this.zoom * 100)}%`;
    }

    // Debounce actual high-res PDF.js rendering once zooming gesture settles (250ms)
    if (this.zoomDebounceTimer !== null) clearTimeout(this.zoomDebounceTimer);
    this.zoomDebounceTimer = setTimeout(() => {
      this.zoomDebounceTimer = null;
      this.syncState();

      this.renderedZoom = this.zoom;

      this.rerenderInPlace().then(() => {
        setTimeout(() => {
          this.isZooming = false;
        }, 200);
      });
    }, 250);
  }

  // ── Navigation ────────────────────────────────────────────────

  public jumpToPage(pageNum: number, behavior: ScrollBehavior = "smooth"): void {
    this.goToPage(pageNum, behavior);
  }

  public resolvePrintedPageLabel(printedPage: number): number | undefined {
    const wanted = String(printedPage);
    const index = this.pageLabels?.findIndex((label) => String(label).trim() === wanted) ?? -1;
    return index >= 0 ? index + 1 : undefined;
  }

  private goToPage(pageNum: number, behavior: ScrollBehavior = "auto"): void {
    if (!this.pagesEl || !Number.isFinite(pageNum)) return;
    const bounded = Math.min(this.totalPages, Math.max(1, Math.floor(pageNum)));
    const pageEl = this.pagesEl.querySelector<HTMLElement>(
      `.pdf-page[data-page-number="${bounded}"]`
    );

    if (pageEl) {
      const scrollContainer = this.containerEl.children[1] as HTMLElement;
      if (scrollContainer) {
        // If container is not yet visible (e.g. tab is switching), retry shortly
        if (scrollContainer.clientHeight === 0) {
          setTimeout(() => this.goToPage(pageNum, behavior), 50);
          return;
        }
        // Exactly snap to the page using offsetTop (most reliable)
        scrollContainer.scrollTop = pageEl.offsetTop - 16;
      } else {
        pageEl.scrollIntoView({ block: "start", behavior: "instant" });
      }
    }
    if (this.pageInputEl) this.pageInputEl.value = String(bounded);
    this.currentPage = bounded;
    this.syncState();
    this.notifyContextChanged();
  }

  private updateCurrentPage(): void {
    if (!this.pagesEl || !this.pageInputEl) return;
    const pages = Array.from(
      this.pagesEl.querySelectorAll<HTMLElement>(".pdf-page[data-page-number]")
    );
    const viewport = this.pagesEl.parentElement?.getBoundingClientRect();
    if (!viewport) return;

    let bestPage = 1;
    let bestOverlap = -Infinity;
    for (const page of pages) {
      const rect = page.getBoundingClientRect();
      const overlap = Math.max(
        0,
        Math.min(rect.bottom, viewport.bottom) - Math.max(rect.top, viewport.top)
      );
      if (overlap > bestOverlap) {
        bestOverlap = overlap;
        bestPage = Number(page.dataset.pageNumber || "1");
      }
    }
    this.pageInputEl.value = String(bestPage);
    if (bestPage !== this.currentPage) {
      this.currentPage = bestPage;
      this.syncState();
      this.notifyContextChanged();
    }
  }

  private notifyContextChanged(): void {
    window.dispatchEvent(
      new CustomEvent(EXTERNAL_PDF_CONTEXT_EVENT, {
        detail: { viewType: EXTERNAL_PDF_VIEW_TYPE, docId: this.docId },
      })
    );
  }

  // ── Dark mode / TOC ───────────────────────────────────────────

  private toggleDarkMode(): void {
    this.darkMode = !this.darkMode;
    this.syncState();
    const container = this.containerEl.children[1] as HTMLElement;
    container.toggleClass("ai-agent-external-pdf-dark", this.darkMode);
    this.darkModeBtnEl?.toggleClass("is-active", this.darkMode);
  }

  private toggleToc(): void {
    this.tocOpen = !this.tocOpen;
    this.tocPanelEl?.toggleClass("is-open", this.tocOpen);
    if (this.tocOpen) this.updateTocActive();
    this.syncState();
  }

  // ── Utilities ─────────────────────────────────────────────────

  private updatePageCount(): void {
    if (this.pageCountEl) this.pageCountEl.setText(`/ ${this.totalPages || "-"}`);
  }

  private syncState(): void {
    this.docState = buildSyncedExternalPdfState({
      docId: this.docId,
      name: this.docState?.name,
      fallbackName: getExternalPdfDocName(this.docId),
      path: this.docState?.path,
      zoom: this.zoom,
      darkMode: this.darkMode,
      tocOpen: this.tocOpen,
      currentPage: this.currentPage,
      zoteroAttachmentKey: this.docState?.zoteroAttachmentKey,
      targetAnnotationKey: this.docState?.targetAnnotationKey,
    });
    this.app.workspace.requestSaveLayout();
  }

  private clearTimers(): void {
    if (this.zoomDebounceTimer !== null) {
      clearTimeout(this.zoomDebounceTimer);
      this.zoomDebounceTimer = null;
    }
  }

  private readNumberState(value: unknown, fallback: number): number {
    return typeof value === "number" && Number.isFinite(value) ? value : fallback;
  }
}
