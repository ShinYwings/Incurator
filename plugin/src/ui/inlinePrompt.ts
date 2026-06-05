import { Editor, EditorPosition, MarkdownView } from "obsidian";
import type ObsidianAIAgent from "../../main";
import type { StreamChunk } from "../types";
import { DiffViewer } from "./diffViewer";

/**
 * Floating inline prompt bar that appears above the cursor when the Inline Edit
 * command runs (no default hotkey; user-assignable in Settings → Hotkeys).
 * Sends the selected text + instruction to the LLM and opens a diff view.
 */
export class InlinePromptWidget {
  private plugin: ObsidianAIAgent;
  private containerEl: HTMLElement | null = null;
  private inputEl: HTMLInputElement | null = null;
  private statusEl: HTMLElement | null = null;
  private editor: Editor | null = null;
  private view: MarkdownView | null = null;
  private originalText: string = "";
  private selectionStart: EditorPosition | null = null;
  private selectionEnd: EditorPosition | null = null;
  private isProcessing = false;

  constructor(plugin: ObsidianAIAgent) {
    this.plugin = plugin;
  }

  /**
   * Open the inline prompt at the current cursor/selection position.
   */
  open(view: MarkdownView): void {
    this.close(); // Close any existing prompt

    this.view = view;
    this.editor = view.editor;

    // Capture selection
    const selection = this.editor.getSelection();
    if (selection) {
      this.originalText = selection;
      this.selectionStart = this.editor.getCursor("from");
      this.selectionEnd = this.editor.getCursor("to");
    } else {
      // If no selection, use the current line
      const cursor = this.editor.getCursor();
      const lineText = this.editor.getLine(cursor.line);
      this.originalText = lineText;
      this.selectionStart = { line: cursor.line, ch: 0 };
      this.selectionEnd = { line: cursor.line, ch: lineText.length };
    }

    // Create floating prompt UI
    this.createPromptUI();
  }

  /**
   * Close the inline prompt.
   */
  close(): void {
    if (this.containerEl) {
      this.containerEl.remove();
      this.containerEl = null;
    }
    this.inputEl = null;
    this.statusEl = null;
    this.isProcessing = false;
    this.plugin.llmClient.abort();
  }

  unload(): void {
    this.close();
  }

  get isOpen(): boolean {
    return this.containerEl !== null;
  }

  // ── UI Creation ─────────────────────────────────────────────

  private createPromptUI(): void {
    if (!this.view) return;

    // Insert at the top of .cm-scroller so position:sticky keeps it visible
    // as the user scrolls. Only present in source/edit mode.
    const scroller = this.view.contentEl.querySelector<HTMLElement>(".cm-scroller");
    if (!scroller) {
      // File is in Reading view — Cmd+K requires Editing mode.
      new (require("obsidian").Notice)("Inline edit requires Editing mode. Switch from Reading view first.");
      return;
    }
    this.containerEl = document.createElement("div");
    this.containerEl.className = "ai-agent-inline-prompt";
    scroller.prepend(this.containerEl);

    // Header with context indicator
    const headerEl = this.containerEl.createDiv(
      "ai-agent-inline-prompt-header"
    );
    const contextLabel = headerEl.createSpan(
      "ai-agent-inline-prompt-context"
    );
    const previewText =
      this.originalText.length > 50
        ? this.originalText.slice(0, 50) + "…"
        : this.originalText;
    contextLabel.setText(`✂️ Editing: "${previewText}"`);

    // Close button
    const closeBtn = headerEl.createSpan({
      cls: "ai-agent-inline-prompt-close",
      text: "×",
    });
    closeBtn.addEventListener("click", () => this.close());

    // Input row
    const inputRow = this.containerEl.createDiv(
      "ai-agent-inline-prompt-input-row"
    );

    this.inputEl = inputRow.createEl("input", {
      cls: "ai-agent-inline-prompt-input",
      attr: {
        type: "text",
        placeholder: "Describe the edit... (e.g. 'translate to English')",
      },
    });

    this.inputEl.addEventListener("keydown", (e: KeyboardEvent) => {
      if (e.key === "Enter" && !this.isProcessing) {
        e.preventDefault();
        this.handleSubmit();
      }
      if (e.key === "Escape") {
        e.preventDefault();
        this.close();
      }
    });

    const submitBtn = inputRow.createEl("button", {
      cls: "ai-agent-inline-prompt-submit",
      text: "Edit",
    });
    submitBtn.addEventListener("click", () => this.handleSubmit());

    // Status area (for loading/streaming)
    this.statusEl = this.containerEl.createDiv(
      "ai-agent-inline-prompt-status"
    );

    // Focus the input
    requestAnimationFrame(() => {
      this.inputEl?.focus();
    });
  }

  // ── Submit Logic ────────────────────────────────────────────

  private async handleSubmit(): Promise<void> {
    if (!this.inputEl || !this.editor || !this.view) return;
    const instruction = this.inputEl.value.trim();
    if (!instruction || this.isProcessing) return;

    this.isProcessing = true;
    this.inputEl.disabled = true;
    if (this.statusEl) {
      this.statusEl.empty();
      this.statusEl.createSpan({
        cls: "ai-agent-inline-prompt-loading",
        text: "⏳ Generating edit...",
      });
    }

    try {
      let modifiedText = "";

      if (this.plugin.settings.streamingEnabled) {
        // Track streaming phase to show meaningful progress.
        let inThinking = false;
        let lastToolLabel = "";
        let answerLen = 0;

        modifiedText = await this.plugin.llmClient.editText(
          this.originalText,
          instruction,
          (chunk: StreamChunk) => {
            if (chunk.done || !this.statusEl) return;

            const t = chunk.text;
            if (t.includes("<thinking>")) inThinking = true;
            if (t.includes("</thinking>")) { inThinking = false; lastToolLabel = ""; }

            // Pick up tool call lines emitted by the CLI parser
            const toolMatch = t.match(/\*\*([^*]+)\*\*/);
            if (t.includes("> Tool:") && toolMatch) {
              lastToolLabel = toolMatch[1];
            }

            // Measure non-thinking output length to detect real answer text
            if (!inThinking && !t.includes("<thinking>") && !t.includes("> Tool:")) {
              answerLen += t.length;
            }

            // Compose status line
            let statusText: string;
            if (inThinking) {
              statusText = "🧠 Thinking...";
            } else if (lastToolLabel) {
              statusText = `🔧 ${lastToolLabel}`;
            } else if (answerLen > 0) {
              statusText = "✍️ Writing edit...";
            } else {
              statusText = "⏳ Generating...";
            }

            this.statusEl.empty();
            this.statusEl.createSpan({
              cls: "ai-agent-inline-prompt-loading",
              text: statusText,
            });
          }
        );
      } else {
        modifiedText = await this.plugin.llmClient.editText(
          this.originalText,
          instruction
        );
      }

      // Strip markdown code fences if the LLM wraps the output
      modifiedText = this.stripCodeFences(modifiedText);

      // Close prompt and show diff
      this.close();

      if (
        this.editor &&
        this.view &&
        this.selectionStart &&
        this.selectionEnd
      ) {
        const diffViewer = new DiffViewer(this.plugin);
        diffViewer.show(
          this.view,
          this.originalText,
          modifiedText,
          this.selectionStart,
          this.selectionEnd
        );
      }
    } catch (err: unknown) {
      if (this.statusEl) {
        this.statusEl.empty();
        this.statusEl.createSpan({
          cls: "ai-agent-inline-prompt-error",
          text: `❌ ${err instanceof Error ? err.message : String(err)}`,
        });
      }
      this.isProcessing = false;
      if (this.inputEl) this.inputEl.disabled = false;
    }
  }

  /**
   * Strip markdown code fences that LLMs sometimes wrap around edited text.
   */
  private stripCodeFences(text: string): string {
    const trimmed = text.trim();
    // Match ```...``` or ```lang\n...\n```
    const fenceMatch = trimmed.match(
      /^```(?:\w*\n)?([\s\S]*?)```$/
    );
    if (fenceMatch) {
      return fenceMatch[1].trim();
    }
    return trimmed;
  }
}
