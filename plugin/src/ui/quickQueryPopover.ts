import type { MarkdownRenderer as MarkdownRendererType } from "obsidian";
import type ObsidianAIAgent from "../../main";
import type { LLMMessage, StreamChunk } from "../types";

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
  return [
    {
      role: "system",
      content:
        "You are a reading assistant embedded in Obsidian. The user selected a " +
        "passage while reading and asks a quick question about it. Answer " +
        "concisely and directly, in the same language as the question. Resolve " +
        "references, equations, and citations using the selected passage as the " +
        "primary context. Do not add preamble, sign-off, or restate the question.",
    },
    {
      role: "user",
      content:
        `Selected passage:\n"""\n${selectedText}\n"""\n\n` + `Question: ${question}`,
    },
  ];
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

const MAX_SELECTION_LENGTH = 8000;

export class QuickQueryPopover {
  private plugin: ObsidianAIAgent;
  private buttonEl: HTMLElement | null = null;
  private popoverEl: HTMLElement | null = null;
  private capturedSelection = "";
  private isProcessing = false;

  constructor(plugin: ObsidianAIAgent) {
    this.plugin = plugin;
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
  handleSelectionChange(): void {
    if (!this.plugin.settings.quickQueryEnabled) {
      this.removeButton();
      return;
    }
    // Don't react to selections the user makes inside our own answer popover.
    if (this.popoverEl) return;

    const selection = window.getSelection();
    const text = selection?.toString().trim() ?? "";
    if (!text || !selection || selection.rangeCount === 0) {
      this.removeButton();
      return;
    }

    if (this.isInsideOwnUi(selection)) {
      return;
    }

    const rect = selection.getRangeAt(0).getBoundingClientRect();
    if (!rect || (rect.width === 0 && rect.height === 0)) {
      this.removeButton();
      return;
    }

    this.capturedSelection = text.slice(0, MAX_SELECTION_LENGTH);
    this.showButton(rect);
  }

  /**
   * Open the quick query popover for the current selection, triggered by a
   * command/hotkey instead of the floating button. No-op (with a hint) when
   * there is no active text selection.
   */
  openForCurrentSelection(): void {
    const selection = window.getSelection();
    const text = selection?.toString().trim() ?? "";
    if (!text || !selection || selection.rangeCount === 0) {
      new (require("obsidian").Notice)("Quick query: select some text first.");
      return;
    }
    const rect = selection.getRangeAt(0).getBoundingClientRect();
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

    const btn = document.createElement("div");
    btn.className = "ai-agent-quick-query-button";
    btn.setAttr("aria-label", "Ask AI about selection");
    btn.setText("✨ Ask AI");

    // Position just below the end of the selection, clamped to the viewport.
    const top = Math.min(rect.bottom + 6, window.innerHeight - 40);
    const left = Math.min(rect.left, window.innerWidth - 120);
    btn.style.top = `${Math.max(8, top)}px`;
    btn.style.left = `${Math.max(8, left)}px`;

    // Use mousedown to fire before the selection collapses on click.
    btn.addEventListener("mousedown", (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.openPopover(rect);
    });

    document.body.appendChild(btn);
    this.buttonEl = btn;
  }

  private removeButton(): void {
    this.buttonEl?.remove();
    this.buttonEl = null;
  }

  // ── Popover ───────────────────────────────────────────────────

  private openPopover(rect: DOMRect): void {
    this.removeButton();
    this.removePopover();

    const popover = document.createElement("div");
    popover.className = "ai-agent-quick-query-popover";

    const top = Math.min(rect.bottom + 6, window.innerHeight - 80);
    const left = Math.min(rect.left, window.innerWidth - 380);
    popover.style.top = `${Math.max(8, top)}px`;
    popover.style.left = `${Math.max(8, left)}px`;

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
      void this.runQuery(question, answerEl);
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

    document.body.appendChild(popover);
    this.popoverEl = popover;
    requestAnimationFrame(() => input.focus());
  }

  private async runQuery(question: string, answerEl: HTMLElement): Promise<void> {
    this.isProcessing = true;
    answerEl.empty();
    answerEl.createSpan({
      cls: "ai-agent-quick-query-loading",
      text: "⏳ Thinking…",
    });

    const messages = buildQuickQueryMessages(this.capturedSelection, question);
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
      return;
    }

    this.isProcessing = false;
    if (!this.popoverEl) return;

    const finalText = stripThinkingForDisplay(raw);
    answerEl.empty();
    if (!finalText) {
      answerEl.createSpan({
        cls: "ai-agent-quick-query-error",
        text: "No answer was returned.",
      });
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
  }

  private removePopover(): void {
    if (this.isProcessing) {
      this.plugin.llmClient.abort();
      this.isProcessing = false;
    }
    this.popoverEl?.remove();
    this.popoverEl = null;
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
