import type { MarkdownRenderer as MarkdownRendererType } from "obsidian";
import type ObsidianAIAgent from "../../main";
import type { LLMMessage, StreamChunk } from "../types";
import {
  buildQuickQueryMessages as buildQuickQueryContextMessages,
  buildQuickQueryRetrievalQuery,
  type QuickQueryTurn,
} from "../context/quickQueryContext";
import { formatCuratorContextPack } from "../context/providerContextFormat";
import { resolveWorkspacePath } from "../context/workspaceScope";
import { isEditRequest } from "../context/providerContextPolicy";
import { logger } from "../utils/logger";
import {
  attachLatexCopyHandler,
  normalizeLatexDelimiters,
  selectionToTextWithLatex,
  stampMathSourceData,
} from "../utils/textUtils";
import { resolveSelectionContextAsync } from "../context/pdfReferenceContext";
import { summarizeProvenance, type ProvenanceRecord } from "../context/provenance";
import { POPOVER_PROFILE } from "../context/promptRegistry";

/**
 * In-line Copilot — drag-to-select quick query popover.
 *
 * When the user selects (drags) text anywhere in the workspace, a single small
 * floating button appears next to the selection. Clicking it opens a popover
 * with just a query input and a submit button (no presets). On submit the input
 * row is hidden and only the streamed AI answer is shown — selectable/copyable,
 * scrollable, size-capped, and fully ephemeral: closing the popover discards the
 * exchange without touching the chat sidebar history.
 *
 * This behaves like a lightweight `wiki query` for the selected passage, aimed
 * at quick lookups such as "참조: [섹션 4.2]" or "Eq. (3)에 의해...".
 */

/** Build the temp-query messages for the selected passage + the user question. */
export function buildQuickQueryMessages(
  selectedText: string,
  question: string
): LLMMessage[] {
  return buildQuickQueryContextMessages({ selectedText, question });
}

/**
 * Strip thinking/status scaffolding the CLI providers wrap around the real
 * answer so the popover shows only the clean response text.
 */
export function stripThinkingForDisplay(content: string): string {
  return content
    .replace(/<thinking>[\s\S]*?<\/thinking>/gi, "")
    .replace(/<thinking>[\s\S]*$/i, "")
    .replace(/<think>[\s\S]*?<\/think>/gi, "")
    .replace(/<think>[\s\S]*$/i, "")
    .replace(/<thought>[\s\S]*?<\/thought>/gi, "")
    .trim();
}

export interface FloatingSize {
  width: number;
  height: number;
}

export interface FloatingViewport {
  width: number;
  height: number;
}

export interface FloatingAnchor {
  top: number;
  bottom: number;
  left: number;
}

export interface FloatingPosition {
  top: number;
  left: number;
}

/**
 * Position a floating element next to a selection rect. Defaults below the
 * selection, flips above when it would overflow the viewport bottom (so the
 * answer is never clipped — report item 5), and clamps into the viewport on
 * both axes. Pure so it is unit-tested without a DOM.
 */
export function computeFloatingPosition(
  anchor: FloatingAnchor,
  size: FloatingSize,
  viewport: FloatingViewport,
  gap = 6,
  margin = 8
): FloatingPosition {
  let top = anchor.bottom + gap;
  if (top + size.height > viewport.height - margin) {
    const above = anchor.top - gap - size.height;
    top = above >= margin ? above : Math.max(margin, viewport.height - size.height - margin);
  }
  let left = Math.min(anchor.left, viewport.width - size.width - margin);
  left = Math.max(margin, left);
  top = Math.max(margin, top);
  return { top, left };
}

const MAX_SELECTION_LENGTH = 8000;
const BUTTON_SIZE: FloatingSize = { width: 120, height: 40 };
const POPOVER_SIZE: FloatingSize = { width: 380, height: 320 };

interface QuickQueryDragState {
  win: Window;
  startX: number;
  startY: number;
  startLeft: number;
  startTop: number;
  move: (e: MouseEvent) => void;
  up: (e: MouseEvent) => void;
}

/** Token budget for the popover's pre-turn vault evidence. Deliberately a
 *  fraction of the sidechat's pack: the popover answers about a selection, and
 *  the evidence is there to point at the reader's own notes, not to replace the
 *  passage in front of them. */
const QUICK_QUERY_VAULT_EVIDENCE_TOKENS = 2500;

/** How long the answer will wait for vault evidence before going without it.
 *
 *  Measured on a live vault, the fetch takes **59-99 s** — an LLM call that
 *  writes search terms, plus a cold embedding and reranker load on every
 *  invocation. This surface is documented as "a lightweight `wiki query` aimed
 *  at quick lookups while reading", so it cannot wait for that.
 *
 *  A `try/catch` was not enough: it catches a throw, not slowness, so a hung
 *  backend meant the popover never answered at all. This bounds the wait; the
 *  evidence is a bonus, never the gate. */
const QUICK_QUERY_VAULT_EVIDENCE_TIMEOUT_MS = 4000;

export class QuickQueryPopover {
  private plugin: ObsidianAIAgent;
  private buttonEl: HTMLElement | null = null;
  private popoverEl: HTMLElement | null = null;
  private capturedSelection = "";

  /** One fetch per popover. `runQuery` is also the follow-up path and the
   *  selection does not change between turns, so the same 59-99 s retrieval
   *  was being re-issued for every follow-up. `""` records a miss, so a
   *  timeout is not retried on the next question either. */
  private vaultEvidenceCache: string | undefined;

  /** The in-flight fetch, so a turn that times out does not discard it. The
   *  result still lands in `vaultEvidenceCache` for the next question. */
  private vaultEvidencePending: Promise<string> | undefined;
  private isProcessing = false;
  private turns: QuickQueryTurn[] = [];
  private titleEl: HTMLElement | null = null;
  private minimizeBtnEl: HTMLElement | null = null;
  private isMinimized = false;
  private popoverKeyHandler: ((e: KeyboardEvent) => void) | null = null;
  private dragState: QuickQueryDragState | null = null;
  /** Document that owns the current selection (main window or a popout). */
  private activeDoc: Document = document;
  /** Live selection range, kept so the trigger button tracks PDF scrolling. */
  private anchorRange: Range | null = null;
  private repositionHandler: (() => void) | null = null;
  /** The window the reposition listeners were ATTACHED to. `activeWin` follows
   *  `activeDoc`, which moves when the user selects in another window, so
   *  detaching against it would target the wrong window and strand a
   *  capture-phase scroll listener on the original one. Mirrors `dragState.win`. */
  private repositionWin: Window | null = null;
  private childPopovers = new Set<QuickQueryPopover>();
  private onPopoverRemoved: ((popover: QuickQueryPopover) => void) | null = null;
  private requestAbortController: AbortController | null = null;
  /** Ticks the elapsed-seconds readout while the provider is working. A
   *  CLI-backed provider round-trip measures 8-12s even for a one-word answer
   *  (the cost is the provider service handshake, not inference), and
   *  `agy --print` cannot stream, so a static "Thinking…" is indistinguishable
   *  from a hang for the whole wait. The sidebar already shows elapsed time;
   *  this gives the popover the same signal. */
  private thinkingTimer: ReturnType<typeof setInterval> | null = null;

  constructor(plugin: ObsidianAIAgent) {
    this.plugin = plugin;
  }

  private get activeWin(): Window {
    return this.activeDoc.defaultView ?? window;
  }

  /** Hide the trigger button and any open popover, discarding the exchange. */
  close(): void {
    this.removeButton();
    for (const popover of Array.from(this.childPopovers)) {
      popover.removePopover();
    }
    this.childPopovers.clear();
    this.removePopover();
  }

  unload(): void {
    this.close();
  }

  // ── Selection trigger ─────────────────────────────────────────

  /**
   * Called on mouseup. Shows or hides the floating trigger button based on the
   * current selection. Ignores selections inside our own popover.
   */
  handleSelectionChange(doc: Document = document): void {
    if (!this.plugin.settings.quickQueryEnabled) {
      this.removeButton();
      return;
    }
    const selection = doc.getSelection();
    const text = selectionToTextWithLatex(selection).trim();
    if (!text || !selection || selection.rangeCount === 0) {
      this.removeButton();
      return;
    }

    if (this.isInsideOwnUi(selection)) {
      return;
    }

    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    if (!rect || (rect.width === 0 && rect.height === 0)) {
      this.removeButton();
      return;
    }

    // Tear the old button (and its listeners) down BEFORE `activeDoc` moves, so
    // a selection made in another window cannot strand listeners on this one.
    if (doc !== this.activeDoc) this.removeButton();
    this.activeDoc = doc;
    this.anchorRange = range.cloneRange();
    this.capturedSelection = text.slice(0, MAX_SELECTION_LENGTH);
    this.showButton(rect);
  }

  /**
   * Open the quick query popover for the current selection, triggered by a
   * command/hotkey instead of the floating button. No-op (with a hint) when
   * there is no active text selection.
   */
  openForCurrentSelection(doc?: Document): void {
    const ownerDoc =
      doc ??
      this.plugin.app.workspace.activeLeaf?.view?.containerEl?.ownerDocument ??
      document;
    const selection = ownerDoc.getSelection();
    const text = selectionToTextWithLatex(selection).trim();
    if (!text || !selection || selection.rangeCount === 0) {
      new (require("obsidian").Notice)("Quick query: select some text first.");
      return;
    }
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    this.removeButton();
    this.activeDoc = ownerDoc;
    this.anchorRange = range.cloneRange();
    this.capturedSelection = text.slice(0, MAX_SELECTION_LENGTH);
    this.openPopover(rect);
  }

  private isInsideOwnUi(selection: Selection): boolean {
    const node = selection.anchorNode;
    const el = node instanceof Element ? node : node?.parentElement ?? null;
    return Boolean(
      el?.closest(".ai-agent-quick-query-popover, .ai-agent-quick-query-button")
    );
  }

  // ── Trigger button ────────────────────────────────────────────

  private showButton(rect: DOMRect): void {
    this.removeButton();

    const doc = this.activeDoc;
    const btn = doc.createElement("div");
    btn.className = "ai-agent-quick-query-button";
    btn.setAttr("aria-label", "Ask AI about selection");
    btn.setText("✨ Ask AI");

    this.applyFloatingPosition(btn, rect, BUTTON_SIZE);

    // Use mousedown to fire before the selection collapses on click.
    btn.addEventListener("mousedown", (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.openPopover(this.anchorRange?.getBoundingClientRect() ?? rect);
    });

    doc.body.appendChild(btn);
    this.buttonEl = btn;
    this.attachRepositionListeners();
  }

  /** Position a floating element using the clamp/flip math against the active window. */
  private applyFloatingPosition(el: HTMLElement, rect: DOMRect, size: FloatingSize): void {
    const win = this.activeWin;
    const pos = computeFloatingPosition(
      { top: rect.top, bottom: rect.bottom, left: rect.left },
      size,
      { width: win.innerWidth, height: win.innerHeight }
    );
    el.style.top = `${pos.top}px`;
    el.style.left = `${pos.left}px`;
  }

  /** Keep the trigger button pinned to the live selection while the document scrolls. */
  private attachRepositionListeners(): void {
    if (this.repositionHandler) return;
    const handler = () => {
      if (!this.buttonEl) {
        this.detachRepositionListeners();
        return;
      }
      const rect = this.anchorRange?.getBoundingClientRect();
      if (!rect || (rect.width === 0 && rect.height === 0)) return;
      this.applyFloatingPosition(this.buttonEl, rect, BUTTON_SIZE);
    };
    this.repositionHandler = handler;
    const win = this.activeWin;
    this.repositionWin = win;
    win.addEventListener("scroll", handler, true);
    win.addEventListener("resize", handler);
  }

  private detachRepositionListeners(): void {
    if (!this.repositionHandler) return;
    // Detach from the window we attached to, not from whatever is active now.
    const win = this.repositionWin ?? this.activeWin;
    win.removeEventListener("scroll", this.repositionHandler, true);
    win.removeEventListener("resize", this.repositionHandler);
    this.repositionHandler = null;
    this.repositionWin = null;
  }

  private removeButton(): void {
    this.buttonEl?.remove();
    this.buttonEl = null;
    this.detachRepositionListeners();
  }

  // ── Popover ───────────────────────────────────────────────────

  private openPopover(rect: DOMRect): void {
    this.removeButton();
    const session = new QuickQueryPopover(this.plugin);
    session.activeDoc = this.activeDoc;
    session.anchorRange = this.anchorRange?.cloneRange() ?? null;
    session.capturedSelection = this.capturedSelection;
    session.onPopoverRemoved = (popover) => {
      this.childPopovers.delete(popover);
    };
    this.childPopovers.add(session);
    session.openSinglePopover(rect);
  }

  private openSinglePopover(rect: DOMRect): void {
    this.removeButton();
    this.removePopover();
    this.turns = [];
    this.isMinimized = false;

    const doc = this.activeDoc;
    const popover = doc.createElement("div");
    popover.className = "ai-agent-quick-query-popover";
    this.popoverKeyHandler = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || !this.popoverEl) return;
      const target = e.target instanceof Node ? e.target : null;
      if (!target || !this.popoverEl.contains(target)) return;
      e.preventDefault();
      e.stopPropagation();
      this.removePopover();
    };
    doc.addEventListener("keydown", this.popoverKeyHandler, true);

    this.applyFloatingPosition(popover, rect, POPOVER_SIZE);

    // Header (drag handle + minimize + close)
    const header = popover.createDiv("ai-agent-quick-query-header");
    header.addEventListener("mousedown", (e) => this.startDrag(e));
    this.titleEl = header.createSpan({
      cls: "ai-agent-quick-query-title",
      text: "Quick query",
    });
    const controls = header.createSpan({ cls: "ai-agent-quick-query-controls" });
    this.minimizeBtnEl = controls.createSpan({
      cls: "ai-agent-quick-query-minimize",
      text: "−",
      attr: { role: "button", "aria-label": "Minimize quick query", title: "Minimize" },
    });
    this.minimizeBtnEl.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.toggleMinimized();
    });
    const closeBtn = header.createSpan({
      cls: "ai-agent-quick-query-close",
      text: "×",
      attr: { role: "button", "aria-label": "Close quick query", title: "Close" },
    });
    closeBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.removePopover();
    });

    // Input row (hidden after submit)
    const inputRow = popover.createDiv("ai-agent-quick-query-input-row");
    const input = inputRow.createEl("input", {
      cls: "ai-agent-quick-query-input",
      attr: { type: "text", placeholder: "Ask about the selection…" },
    });
    const submitBtn = inputRow.createEl("button", {
      cls: "ai-agent-quick-query-submit",
      text: "Ask",
    });

    const answerEl = popover.createDiv("ai-agent-quick-query-answer");
    answerEl.hide();

    const submit = () => {
      const question = input.value.trim();
      if (!question || this.isProcessing) return;
      if (this.titleEl) {
        this.titleEl.setText(question);
        this.titleEl.title = question;
      }
      inputRow.hide();
      answerEl.show();
      void this.runQuery(question, answerEl, inputRow, input);
    };

    input.addEventListener("keydown", (e: KeyboardEvent) => {
      if (e.key === "Enter") {
        e.preventDefault();
        submit();
      } else if (e.key === "Escape") {
        e.preventDefault();
        this.removePopover();
      }
    });
    submitBtn.addEventListener("click", submit);

    doc.body.appendChild(popover);
    this.popoverEl = popover;
    (this.activeWin.requestAnimationFrame ?? requestAnimationFrame)(() => input.focus());
  }

  private toggleMinimized(): void {
    if (!this.popoverEl) return;
    this.isMinimized = !this.isMinimized;
    this.popoverEl.classList.toggle("is-minimized", this.isMinimized);
    if (this.minimizeBtnEl) {
      this.minimizeBtnEl.setText(this.isMinimized ? "+" : "−");
      this.minimizeBtnEl.setAttr("aria-label", this.isMinimized ? "Restore quick query" : "Minimize quick query");
      this.minimizeBtnEl.title = this.isMinimized ? "Restore" : "Minimize";
    }
  }

  private startDrag(e: MouseEvent): void {
    if (e.button !== 0 || !this.popoverEl) return;
    const target = e.target instanceof Element ? e.target : null;
    if (target?.closest(".ai-agent-quick-query-minimize, .ai-agent-quick-query-close")) return;

    e.preventDefault();
    const rect = this.popoverEl.getBoundingClientRect();
    const win = this.activeWin;
    this.detachDragListeners();
    const move = (event: MouseEvent) => this.moveDrag(event);
    const up = (_event: MouseEvent) => this.detachDragListeners();
    this.dragState = {
      win,
      startX: e.clientX,
      startY: e.clientY,
      startLeft: rect.left,
      startTop: rect.top,
      move,
      up,
    };
    this.popoverEl.classList.add("is-dragging");
    win.addEventListener("mousemove", move);
    win.addEventListener("mouseup", up);
  }

  private moveDrag(e: MouseEvent): void {
    if (!this.dragState || !this.popoverEl) return;
    const left = this.dragState.startLeft + e.clientX - this.dragState.startX;
    const top = this.dragState.startTop + e.clientY - this.dragState.startY;
    const margin = 8;
    const width = this.popoverEl.offsetWidth || POPOVER_SIZE.width;
    const height = this.popoverEl.offsetHeight || 40;
    const maxLeft = Math.max(margin, this.dragState.win.innerWidth - width - margin);
    const maxTop = Math.max(margin, this.dragState.win.innerHeight - height - margin);
    this.popoverEl.style.left = `${Math.min(Math.max(margin, left), maxLeft)}px`;
    this.popoverEl.style.top = `${Math.min(Math.max(margin, top), maxTop)}px`;
  }

  private detachDragListeners(): void {
    if (!this.dragState) return;
    this.dragState.win.removeEventListener("mousemove", this.dragState.move);
    this.dragState.win.removeEventListener("mouseup", this.dragState.up);
    this.popoverEl?.classList.remove("is-dragging");
    this.dragState = null;
  }

  private async runQuery(
    question: string,
    answerEl: HTMLElement,
    inputRow: HTMLElement,
    input: HTMLInputElement
  ): Promise<void> {
    this.isProcessing = true;
    const requestController = new AbortController();
    this.requestAbortController = requestController;
    answerEl.empty();
    const loadingEl = answerEl.createSpan({
      cls: "ai-agent-quick-query-loading",
      text: "⏳ Thinking…",
    });
    this.startThinkingTimer(loadingEl);

    const activeContext = this.plugin.refreshActiveContext();
    // Async cross-page resolution: fetch any pages not yet in the window before
    // building the LLM messages. Falls back to sync inline resolution when the
    // PDF is not open or the fetch returns nothing.
    let resolvedReferencesBlock: string | undefined;
    // §13.9: provenance is built from the resolution record, here, and shown as
    // UI state. It is never recovered by scanning the model's answer.
    let provenance: ProvenanceRecord | undefined;
    if (activeContext?.pdfPage) {
      // Read the identity ONCE, before the first await, and use the same value
      // for the index we write into and for every page fetch below.
      const pinnedDocumentId = this.plugin.getActivePdfDocumentId();
      try {
        const resolution = await resolveSelectionContextAsync(
          this.capturedSelection,
          {
            ...activeContext.pdfPage,
            searchIndex: this.plugin.getActivePdfDocumentIndex(),
            searchDocumentId: pinnedDocumentId,
            // pinnedDocumentId is undefined whenever the active view is not the
            // custom ExternalPdfView — Obsidian's own PDF viewer populates
            // activeContext.pdfPage but has no docId, so citations were being
            // dropped there with no signal.
            documentKey:
              activeContext.pdfPage?.fileHash ||
              activeContext.pdfPage?.zoteroAttachmentKey ||
              activeContext.pdfPage?.filePath ||
              undefined,
          },
          // Pin the document identity for the whole resolution. This loop issues
          // several sequential backend round-trips, so a tab switch mid-flight
          // would otherwise let later fetches read pages out of the NEWLY active
          // PDF — and `resolveSelectionReferencesAsync` writes whatever it
          // fetches back into `searchDocumentId`'s BM25 index, so foreign text
          // would also contaminate this document's index for later queries.
          // `fetchActivePdfPage`'s identity guard is opt-in (it only fires when
          // an expected id is supplied), exactly as the local PDF tool runner
          // opts in (main.ts). Omitting it here was the bug.
          (pageNum) =>
            this.plugin.fetchActivePdfPage(pageNum, pinnedDocumentId),
          undefined,
          // The typed question, not just the highlight. Asking "reference 12의
          // 제목이 뭐야?" without re-selecting the bracket used to resolve
          // nothing, and the answer was in this document's own last pages.
          question
        );
        resolvedReferencesBlock = resolution.block;
        provenance = resolution.provenance;
      } catch {
        // Cross-page resolution failed; fall back to sync inline resolution via buildQuickQueryContextMessages.
        resolvedReferencesBlock = undefined;
      }
    }

    // Duty 2 — "remind me what I wrote". Resolved BEFORE the turn (§4.2) through
    // the SAME DB-native search the sidechat uses; §2 forbids a second retrieval
    // engine and forbids giving the popover tools, so this is one pre-turn
    // backend call and zero extra tool rounds. Never fatal: a popover that
    // cannot reach the vault still answers about the selection.
    const vaultEvidenceBlock = await this.vaultEvidenceFor(question);

    const messages = buildQuickQueryContextMessages({
      selectedText: this.capturedSelection,
      question,
      activeContext,
      previousTurns: this.turns,
      resolvedReferencesBlock,
      pinnedContextRefs: this.plugin.getPinnedContextRefs(),
      vaultEvidenceBlock,
    });
    let raw = "";

    try {
      if (this.plugin.settings.streamingEnabled) {
        await this.plugin.llmClient.streamChat(
          messages,
          (chunk: StreamChunk) => {
            if (chunk.text) raw += chunk.text;
            if (!this.popoverEl) return;
            const display = stripThinkingForDisplay(raw);
            // Until the first real text arrives keep the ticking readout rather
            // than replacing it with a frozen label — a CLI provider delivers
            // nothing at all until the whole answer is ready.
            if (!display) return;
            this.stopThinkingTimer();
            answerEl.empty();
            // Plain text during streaming; markdown render once finished.
            answerEl.createEl("div", {
              cls: "ai-agent-quick-query-stream",
              text: display,
            });
          },
          // Tool isolation (v0.19.0): the popover is an ephemeral, read-only
          // reading assistant — never inject MCP tools, so it cannot run scripts
          // or traverse the filesystem.
          { toolPolicy: POPOVER_PROFILE.toolPolicy, signal: requestController.signal }
        );
      } else {
        // Ephemeral popover: no tools / OS-sandboxed CLI (v0.23.0).
        raw = await this.plugin.llmClient.complete(messages, {
          toolPolicy: POPOVER_PROFILE.toolPolicy,
          signal: requestController.signal,
        });
      }
    } catch (err: unknown) {
      this.isProcessing = false;
      this.stopThinkingTimer();
      if (!this.popoverEl) return;
      answerEl.empty();
      answerEl.createSpan({
        cls: "ai-agent-quick-query-error",
        text: `❌ ${err instanceof Error ? err.message : String(err)}`,
      });
      input.value = "";
      input.placeholder = "Ask a follow-up…";
      inputRow.show();
      return;
    } finally {
      if (this.requestAbortController === requestController) {
        this.requestAbortController = null;
      }
    }

    this.isProcessing = false;
    this.stopThinkingTimer();
    if (!this.popoverEl) return;

    const finalText = normalizeLatexDelimiters(stripThinkingForDisplay(raw));
    answerEl.empty();
    if (!finalText) {
      answerEl.createSpan({
        cls: "ai-agent-quick-query-error",
        text: "No answer was returned.",
      });
      input.value = "";
      input.placeholder = "Ask a follow-up…";
      inputRow.show();
      return;
    }
    try {
      const { MarkdownRenderer, htmlToMarkdown } = require("obsidian") as {
        MarkdownRenderer: typeof MarkdownRendererType;
        htmlToMarkdown: (input: HTMLElement) => string;
      };
      await MarkdownRenderer.render(
        this.plugin.app,
        finalText,
        answerEl,
        "",
        this.plugin
      );
      stampMathSourceData(answerEl, finalText);
      attachLatexCopyHandler(answerEl, htmlToMarkdown);
    } catch {
      answerEl.createEl("div", {
        cls: "ai-agent-quick-query-stream",
        text: finalText,
      });
    }
    const provenanceLine = provenance ? summarizeProvenance(provenance) : "";
    if (provenanceLine) {
      answerEl.createDiv({
        cls: "ai-agent-quick-query-provenance",
        text: provenanceLine,
      });
    }
    this.turns.push({ question, answer: finalText });
    this.turns = this.turns.slice(-3);
    input.value = "";
    input.placeholder = "Ask a follow-up…";
    inputRow.show();
  }

  /** Vault evidence for this turn, or nothing — never a reason to stall.
   *
   *  Three things the first version got wrong, all found by review:
   *  - **No timeout.** The fetch measures 59-99 s and the `try/catch` only
   *    caught throws, so a hung backend blocked the answer indefinitely.
   *  - **Every follow-up re-paid it.** `runQuery` is also the follow-up path and
   *    the selection does not change, so the same query was re-issued each time.
   *    One popover, one fetch.
   *  - **Edit requests paid too.** "rewrite this" does not use vault evidence;
   *    the sidechat already skips retrieval for those and this did not. */
  private async vaultEvidenceFor(question: string): Promise<string | undefined> {
    if (isEditRequest(question)) return undefined;
    if (this.vaultEvidenceCache !== undefined) return this.vaultEvidenceCache || undefined;

    const client = this.plugin.incuratorClient;
    if (!client?.available) return undefined;

    // The SELECTION carries the topic; the question is usually deictic.
    const retrievalQuery = buildQuickQueryRetrievalQuery(this.capturedSelection, question);

    // Start it ONCE and keep the promise. Losing the race must not throw the
    // work away: the fetch runs to completion in the background and its result
    // lands in the cache, so a follow-up — the common next action — gets the
    // evidence this turn had to answer without. Racing a fresh fetch each turn
    // would instead re-pay 59-99 s and keep missing.
    this.vaultEvidencePending ??= client
      .fetchContext(retrievalQuery, {
        workspacePath: this.vaultWorkspacePath(),
        limitTokens: QUICK_QUERY_VAULT_EVIDENCE_TOKENS,
      })
      .then((pack) => {
        // LABELLED with the question, not the retrieval query: the label says
        // what the evidence was gathered for, and the retrieval query opens with
        // the passage the model is already looking at.
        this.vaultEvidenceCache = pack.ok ? formatCuratorContextPack(pack, question) : "";
        return this.vaultEvidenceCache;
      })
      .catch((e) => {
        // Logged, not silent. A quiet failure here reads as "it stopped finding
        // my notes", which is the defect that took a live run to catch.
        logger.warn("Vault evidence fetch failed; answering from the selection alone:", e);
        this.vaultEvidenceCache = "";
        return "";
      });

    let timer: ReturnType<typeof setTimeout> | undefined;
    const evidence = await Promise.race([
      this.vaultEvidencePending,
      new Promise<null>((resolve) => {
        timer = setTimeout(() => resolve(null), QUICK_QUERY_VAULT_EVIDENCE_TIMEOUT_MS);
      }),
    ]);
    if (timer) clearTimeout(timer);

    if (evidence === null) {
      logger.info(
        `Vault evidence did not arrive within ${QUICK_QUERY_VAULT_EVIDENCE_TIMEOUT_MS} ms; ` +
          "answering from the selection alone and keeping it for the next question."
      );
      return undefined;
    }
    return evidence || undefined;
  }

  /** Same resolution the sidechat uses for its vault query, so both surfaces
   *  bind the same workspace. An empty result is fine: the backend resolves
   *  `workspace_id=default`, which is what a plain vault question wants. */
  private vaultWorkspacePath(): string {
    const vaultBase = (this.plugin.app.vault.adapter as any).getBasePath?.() || "";
    const activeRelpath = this.plugin.app.workspace.getActiveFile()?.path || "";
    return resolveWorkspacePath(vaultBase, activeRelpath) || vaultBase;
  }

  private startThinkingTimer(target: HTMLElement): void {
    this.stopThinkingTimer();
    const startedAt = Date.now();
    const tick = () => {
      if (!this.popoverEl) {
        this.stopThinkingTimer();
        return;
      }
      const elapsed = Math.floor((Date.now() - startedAt) / 1000);
      target.setText(elapsed > 0 ? `⏳ Thinking… (${elapsed}s)` : "⏳ Thinking…");
    };
    tick();
    this.thinkingTimer = setInterval(tick, 1000);
  }

  private stopThinkingTimer(): void {
    if (this.thinkingTimer !== null) {
      clearInterval(this.thinkingTimer);
      this.thinkingTimer = null;
    }
  }

  private removePopover(): void {
    const hadPopover = Boolean(this.popoverEl);
    this.stopThinkingTimer();
    this.detachDragListeners();
    if (this.popoverKeyHandler) {
      this.activeDoc.removeEventListener("keydown", this.popoverKeyHandler, true);
      this.popoverKeyHandler = null;
    }
    if (this.isProcessing) {
      this.requestAbortController?.abort();
      this.requestAbortController = null;
      this.isProcessing = false;
    }
    this.popoverEl?.remove();
    this.popoverEl = null;
    this.titleEl = null;
    this.minimizeBtnEl = null;
    this.isMinimized = false;
    this.anchorRange = null;
    if (!this.buttonEl) this.detachRepositionListeners();
    if (hadPopover) {
      const onRemoved = this.onPopoverRemoved;
      this.onPopoverRemoved = null;
      onRemoved?.(this);
    }
  }

  /**
   * Dismiss the trigger button when the user clicks outside of our UI.
   * Open popovers are persistent and close only via close button or Escape.
   */
  handleDocumentClick(target: EventTarget | null): void {
    const node = target instanceof Node ? target : null;
    const el = node instanceof Element ? node : node?.parentElement ?? null;
    if (
      el?.closest(".ai-agent-quick-query-popover, .ai-agent-quick-query-button")
    ) {
      return;
    }
    this.removeButton();
  }
}
