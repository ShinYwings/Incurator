import type { MarkdownRenderer as MarkdownRendererType } from "obsidian";
import type ObsidianAIAgent from "../../main";
import type { LLMMessage, StreamChunk } from "../types";
import {
  buildQuickQueryMessages as buildQuickQueryContextMessages,
  type QuickQueryTurn,
} from "../context/quickQueryContext";
import { normalizeLatexDelimiters } from "../utils/textUtils";

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

export class QuickQueryPopover {
  private plugin: ObsidianAIAgent;
  private buttonEl: HTMLElement | null = null;
  private popoverEl: HTMLElement | null = null;
  private capturedSelection = "";
  private isProcessing = false;
  private turns: QuickQueryTurn[] = [];
  /** Document that owns the current selection (main window or a popout). */
  private activeDoc: Document = document;
  /** Live selection range, kept so the button/popover track PDF scrolling. */
  private anchorRange: Range | null = null;
  private repositionHandler: (() => void) | null = null;

  constructor(plugin: ObsidianAIAgent) {
    this.plugin = plugin;
  }

  private get activeWin(): Window {
    return this.activeDoc.defaultView ?? window;
  }

  /** Hide the trigger button and any open popover, discarding the exchange. */
  close(): void {
    this.removeButton();
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
    // Don't react to selections the user makes inside our own answer popover.
    if (this.popoverEl) return;

    const selection = doc.getSelection();
    const text = selection?.toString().trim() ?? "";
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
    const text = selection?.toString().trim() ?? "";
    if (!text || !selection || selection.rangeCount === 0) {
      new (require("obsidian").Notice)("Quick query: select some text first.");
      return;
    }
    const range = selection.getRangeAt(0);
    this.activeDoc = ownerDoc;
    this.anchorRange = range.cloneRange();
    this.capturedSelection = text.slice(0, MAX_SELECTION_LENGTH);
    this.openPopover(range.getBoundingClientRect());
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
      this.openPopover(rect);
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

  /**
   * Keep the trigger button / popover pinned to the live selection as the PDF
   * (or note) scrolls or the window resizes (report item 5). Detached on close.
   */
  private attachRepositionListeners(): void {
    if (this.repositionHandler) return;
    const handler = () => {
      const rect = this.anchorRange?.getBoundingClientRect();
      if (!rect || (rect.width === 0 && rect.height === 0)) return;
      if (this.buttonEl) this.applyFloatingPosition(this.buttonEl, rect, BUTTON_SIZE);
      if (this.popoverEl) this.applyFloatingPosition(this.popoverEl, rect, POPOVER_SIZE);
    };
    this.repositionHandler = handler;
    this.activeWin.addEventListener("scroll", handler, true);
    this.activeWin.addEventListener("resize", handler);
  }

  private detachRepositionListeners(): void {
    if (!this.repositionHandler) return;
    this.activeWin.removeEventListener("scroll", this.repositionHandler, true);
    this.activeWin.removeEventListener("resize", this.repositionHandler);
    this.repositionHandler = null;
  }

  private removeButton(): void {
    this.buttonEl?.remove();
    this.buttonEl = null;
    if (!this.popoverEl) this.detachRepositionListeners();
  }

  // ── Popover ───────────────────────────────────────────────────

  private openPopover(rect: DOMRect): void {
    this.removeButton();
    this.removePopover();
    this.turns = [];

    const doc = this.activeDoc;
    const popover = doc.createElement("div");
    popover.className = "ai-agent-quick-query-popover";

    this.applyFloatingPosition(popover, rect, POPOVER_SIZE);

    // Header (label + close)
    const header = popover.createDiv("ai-agent-quick-query-header");
    header.createSpan({
      cls: "ai-agent-quick-query-title",
      text: "Quick query",
    });
    const closeBtn = header.createSpan({
      cls: "ai-agent-quick-query-close",
      text: "×",
    });
    closeBtn.addEventListener("click", () => this.removePopover());

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
    this.attachRepositionListeners();
    (this.activeWin.requestAnimationFrame ?? requestAnimationFrame)(() => input.focus());
  }

  private async runQuery(
    question: string,
    answerEl: HTMLElement,
    inputRow: HTMLElement,
    input: HTMLInputElement
  ): Promise<void> {
    this.isProcessing = true;
    answerEl.empty();
    answerEl.createSpan({
      cls: "ai-agent-quick-query-loading",
      text: "⏳ Thinking…",
    });

    const messages = buildQuickQueryContextMessages({
      selectedText: this.capturedSelection,
      question,
      activeContext: this.plugin.refreshActiveContext(),
      previousTurns: this.turns,
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
            answerEl.empty();
            // Plain text during streaming; markdown render once finished.
            answerEl.createEl("div", {
              cls: "ai-agent-quick-query-stream",
              text: display || "⏳ Thinking…",
            });
          }
        );
      } else {
        raw = await this.plugin.llmClient.complete(messages);
      }
    } catch (err: unknown) {
      this.isProcessing = false;
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
    }

    this.isProcessing = false;
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
      const MarkdownRenderer = (
        require("obsidian") as { MarkdownRenderer: typeof MarkdownRendererType }
      ).MarkdownRenderer;
      await MarkdownRenderer.render(
        this.plugin.app,
        finalText,
        answerEl,
        "",
        this.plugin
      );
    } catch {
      answerEl.createEl("div", {
        cls: "ai-agent-quick-query-stream",
        text: finalText,
      });
    }
    this.turns.push({ question, answer: finalText });
    this.turns = this.turns.slice(-3);
    input.value = "";
    input.placeholder = "Ask a follow-up…";
    inputRow.show();
  }

  private removePopover(): void {
    if (this.isProcessing) {
      this.plugin.llmClient.abort();
      this.isProcessing = false;
    }
    this.popoverEl?.remove();
    this.popoverEl = null;
    this.anchorRange = null;
    if (!this.buttonEl) this.detachRepositionListeners();
  }

  /**
   * Dismiss the button/popover when the user clicks outside of them.
   */
  handleDocumentClick(target: EventTarget | null): void {
    const el = target instanceof Element ? target : null;
    if (
      el?.closest(".ai-agent-quick-query-popover, .ai-agent-quick-query-button")
    ) {
      return;
    }
    this.removeButton();
    // Keep an open popover alive while a query is streaming; only the close
    // button or Escape should dismiss it mid-answer.
    if (this.popoverEl && !this.isProcessing) {
      this.removePopover();
    }
  }
}
