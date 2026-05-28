import { EditorPosition, MarkdownView, Notice } from "obsidian";
import { StateEffect, StateField, RangeSetBuilder } from "@codemirror/state";
import { Decoration, DecorationSet, EditorView } from "@codemirror/view";
import type ObsidianAIAgent from "../../main";

interface DiffLine {
  type: "unchanged" | "added" | "removed";
  text: string;
}

interface InlineHunk {
  removedEditorLines: number[]; // 1-based absolute editor line numbers
  addedEditorLines: number[];   // 1-based absolute editor line numbers
}

// ── CM6 decoration field (module-level singleton) ─────────────────────────────
const setDiffDecos = StateEffect.define<DecorationSet>();
const clearDiffDecos = StateEffect.define<void>();

const diffDecosField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(decos, tr) {
    decos = decos.map(tr.changes);
    for (const e of tr.effects) {
      if (e.is(setDiffDecos)) decos = e.value;
      else if (e.is(clearDiffDecos)) decos = Decoration.none;
    }
    return decos;
  },
  provide: (f) => EditorView.decorations.from(f),
});

/**
 * Cursor-style inline diff:
 *  - Inserts a combined view (removed lines + added lines) into the editor.
 *  - Colors removed lines red, added lines green via CM6 line decorations.
 *  - Shows a small floating toolbar: ← → navigation + Accept / Reject.
 *  - Accept → strips removed lines (keeps added). Reject → strips added lines (keeps original).
 */
export class DiffViewer {
  private plugin: ObsidianAIAgent;
  private toolbarEl: HTMLElement | null = null;
  private hunkCountEl: HTMLElement | null = null;
  private view: MarkdownView | null = null;
  private originalText = "";
  private selectionStart: EditorPosition | null = null;

  // After inserting the combined view:
  private combinedEnd: EditorPosition | null = null;
  private hunks: InlineHunk[] = [];
  private currentHunk = 0;

  private keyHandler: ((e: KeyboardEvent) => void) | null = null;

  constructor(plugin: ObsidianAIAgent) {
    this.plugin = plugin;
  }

  show(
    view: MarkdownView,
    originalText: string,
    modifiedText: string,
    selectionStart: EditorPosition,
    selectionEnd: EditorPosition
  ): void {
    this.close();

    this.view = view;
    this.originalText = originalText;
    this.selectionStart = selectionStart;

    const editor = view.editor;
    const diffLines = this.computeDiff(originalText, modifiedText);

    // ── 1. Build combined text ──────────────────────────────────────────────
    // Order: for each hunk, show removed lines first then added lines.
    // Unchanged lines pass through as-is.
    const combinedLines: { text: string; type: DiffLine["type"] }[] = [];
    let i = 0;
    while (i < diffLines.length) {
      if (diffLines[i].type === "unchanged") {
        combinedLines.push(diffLines[i]);
        i++;
      } else {
        // collect all removed then all added in this hunk
        while (i < diffLines.length && diffLines[i].type === "removed") {
          combinedLines.push(diffLines[i]);
          i++;
        }
        while (i < diffLines.length && diffLines[i].type === "added") {
          combinedLines.push(diffLines[i]);
          i++;
        }
      }
    }

    const combinedText = combinedLines.map((l) => l.text).join("\n");

    // ── 2. Replace selection with combined text ─────────────────────────────
    editor.replaceRange(combinedText, selectionStart, selectionEnd);

    const combinedSplit = combinedText.split("\n");
    this.combinedEnd = {
      line: selectionStart.line + combinedSplit.length - 1,
      ch:
        combinedSplit.length === 1
          ? selectionStart.ch + combinedText.length
          : combinedSplit[combinedSplit.length - 1].length,
    };

    // ── 3. Compute absolute editor line numbers for each combined line ───────
    const absLine = (relIdx: number) => selectionStart.line + relIdx + 1; // 1-based

    this.hunks = [];
    let hunkRemoved: number[] = [];
    let hunkAdded: number[] = [];
    let inHunk = false;

    for (let ci = 0; ci < combinedLines.length; ci++) {
      const t = combinedLines[ci].type;
      if (t === "removed") {
        inHunk = true;
        hunkRemoved.push(absLine(ci));
      } else if (t === "added") {
        inHunk = true;
        hunkAdded.push(absLine(ci));
      } else {
        if (inHunk) {
          this.hunks.push({ removedEditorLines: hunkRemoved, addedEditorLines: hunkAdded });
          hunkRemoved = [];
          hunkAdded = [];
          inHunk = false;
        }
      }
    }
    if (inHunk) {
      this.hunks.push({ removedEditorLines: hunkRemoved, addedEditorLines: hunkAdded });
    }
    this.currentHunk = 0;

    // ── 4. Apply CM6 decorations ────────────────────────────────────────────
    requestAnimationFrame(() => {
      this.applyDecorations();

      // ── 5. Position and show floating toolbar ────────────────────────────
      const firstChangedLine = selectionStart.line;
      const coords = this.getScreenCoordsAt(view, { line: firstChangedLine, ch: 0 });
      this.buildToolbar(coords);

      editor.scrollIntoView({ from: selectionStart, to: this.combinedEnd! });
    });
  }

  close(): void {
    if (this.keyHandler) {
      document.removeEventListener("keydown", this.keyHandler);
      this.keyHandler = null;
    }
    this.toolbarEl?.remove();
    this.toolbarEl = null;
    this.clearDecorations();
    this.hunks = [];
  }

  // ── CM6 decoration helpers ─────────────────────────────────────────────────

  private getCmView(): EditorView | null {
    const cmView = (this.view?.editor as any)?.cm;
    return cmView instanceof EditorView ? cmView : null;
  }

  private ensureFieldRegistered(cmView: EditorView): void {
    try {
      cmView.state.field(diffDecosField);
    } catch {
      cmView.dispatch({ effects: StateEffect.appendConfig.of(diffDecosField) });
    }
  }

  private applyDecorations(): void {
    const cmView = this.getCmView();
    if (!cmView) return;
    this.ensureFieldRegistered(cmView);

    const builder = new RangeSetBuilder<Decoration>();
    const removedDeco = Decoration.line({ class: "ai-agent-diff-inline-removed" });
    const addedDeco = Decoration.line({ class: "ai-agent-diff-inline-added" });

    // Collect all decorated lines and sort by line number (builder requires sorted order)
    const lines: { n: number; deco: Decoration }[] = [];
    for (const hunk of this.hunks) {
      for (const n of hunk.removedEditorLines) lines.push({ n, deco: removedDeco });
      for (const n of hunk.addedEditorLines) lines.push({ n, deco: addedDeco });
    }
    lines.sort((a, b) => a.n - b.n);

    for (const { n, deco } of lines) {
      if (n < 1 || n > cmView.state.doc.lines) continue;
      const line = cmView.state.doc.line(n);
      builder.add(line.from, line.from, deco);
    }

    cmView.dispatch({ effects: setDiffDecos.of(builder.finish()) });
  }

  private clearDecorations(): void {
    const cmView = this.getCmView();
    if (!cmView) return;
    try {
      cmView.state.field(diffDecosField);
      cmView.dispatch({ effects: clearDiffDecos.of() });
    } catch {
      // field not registered yet, nothing to clear
    }
  }

  // ── Floating toolbar ───────────────────────────────────────────────────────

  private buildToolbar(coords: { top: number; left: number }): void {
    const top = Math.min(coords.top - 38, window.innerHeight - 50);
    const left = Math.max(8, Math.min(coords.left, window.innerWidth - 320));

    this.toolbarEl = document.createElement("div");
    this.toolbarEl.className = "ai-agent-diff-toolbar";
    this.toolbarEl.style.position = "fixed";
    this.toolbarEl.style.top = `${top}px`;
    this.toolbarEl.style.left = `${left}px`;
    document.body.appendChild(this.toolbarEl);

    // Hunk navigation (only if multiple hunks)
    if (this.hunks.length > 1) {
      const navGroup = this.toolbarEl.createDiv("ai-agent-diff-toolbar-group");
      navGroup
        .createEl("button", { cls: "ai-agent-diff-toolbar-btn", text: "↑", attr: { title: "Prev change (Shift+Tab)" } })
        .addEventListener("click", () => this.goHunk(-1));
      this.hunkCountEl = navGroup.createSpan({ cls: "ai-agent-diff-toolbar-count" });
      navGroup
        .createEl("button", { cls: "ai-agent-diff-toolbar-btn", text: "↓", attr: { title: "Next change (Tab)" } })
        .addEventListener("click", () => this.goHunk(1));
    } else {
      this.hunkCountEl = null;
    }

    const actionGroup = this.toolbarEl.createDiv("ai-agent-diff-toolbar-group");
    actionGroup
      .createEl("button", { cls: "ai-agent-diff-toolbar-accept", text: "✓ Accept" })
      .addEventListener("click", () => this.accept());
    actionGroup
      .createEl("button", { cls: "ai-agent-diff-toolbar-reject", text: "✗ Reject" })
      .addEventListener("click", () => this.reject());

    this.refreshHunkUI();

    this.keyHandler = (e: KeyboardEvent) => {
      if (e.key === "Enter") { e.preventDefault(); this.accept(); }
      else if (e.key === "Escape") { e.preventDefault(); this.reject(); }
      else if (e.key === "Tab" && !e.shiftKey) { e.preventDefault(); this.goHunk(1); }
      else if (e.key === "Tab" && e.shiftKey) { e.preventDefault(); this.goHunk(-1); }
    };
    document.addEventListener("keydown", this.keyHandler);
  }

  // ── Hunk navigation ────────────────────────────────────────────────────────

  private goHunk(delta: number): void {
    const next = this.currentHunk + delta;
    if (next < 0 || next >= this.hunks.length) return;
    this.currentHunk = next;
    this.refreshHunkUI();
  }

  private refreshHunkUI(): void {
    if (this.hunkCountEl && this.hunks.length > 1) {
      this.hunkCountEl.setText(`${this.currentHunk + 1}/${this.hunks.length}`);
    }
    // Scroll editor to first line of current hunk
    const hunk = this.hunks[this.currentHunk];
    if (hunk && this.view) {
      const firstLine = (hunk.removedEditorLines[0] ?? hunk.addedEditorLines[0]) - 1; // 0-based
      if (firstLine >= 0) {
        this.view.editor.scrollIntoView({ from: { line: firstLine, ch: 0 }, to: { line: firstLine, ch: 0 } });
      }
    }
  }

  // ── Accept / Reject ────────────────────────────────────────────────────────

  private accept(): void {
    // Remove all removed lines, keep added lines
    if (this.view && this.selectionStart && this.combinedEnd) {
      const editor = this.view.editor;
      const combined = editor.getRange(this.selectionStart, this.combinedEnd);
      const combinedLineTexts = combined.split("\n");

      // Build a set of relative line indices that are "removed"
      const removedRelative = new Set<number>();
      for (const hunk of this.hunks) {
        for (const absLine of hunk.removedEditorLines) {
          removedRelative.add(absLine - 1 - this.selectionStart.line); // convert to 0-based relative
        }
      }

      const kept = combinedLineTexts.filter((_, idx) => !removedRelative.has(idx));
      editor.replaceRange(kept.join("\n"), this.selectionStart, this.combinedEnd);
      const keptEnd: EditorPosition = {
        line: this.selectionStart.line + kept.length - 1,
        ch: kept.length === 1
          ? this.selectionStart.ch + kept[0].length
          : kept[kept.length - 1].length,
      };
      editor.setCursor(keptEnd);
    }
    new Notice("Edit accepted");
    this.close();
  }

  private reject(): void {
    // Revert: replace entire combined range back to original text
    if (this.view && this.selectionStart && this.combinedEnd) {
      this.view.editor.replaceRange(this.originalText, this.selectionStart, this.combinedEnd);
      this.view.editor.setCursor(this.selectionStart);
    }
    new Notice("Edit rejected");
    this.close();
  }

  // ── Screen coordinate helper ───────────────────────────────────────────────

  private getScreenCoordsAt(
    view: MarkdownView,
    pos: EditorPosition
  ): { top: number; left: number } {
    try {
      const cmView = (view.editor as any).cm;
      if (cmView?.state && cmView?.coordsAtPos) {
        const lineInfo = cmView.state.doc.line(pos.line + 1);
        const offset = Math.min(lineInfo.from + pos.ch, cmView.state.doc.length);
        const coords = cmView.coordsAtPos(offset);
        if (coords) return { top: coords.top, left: coords.left };
      }
    } catch {
      // fall through
    }
    const rect = view.contentEl.getBoundingClientRect();
    return { top: rect.top + 80, left: rect.left + 40 };
  }

  // ── Diff algorithm (LCS) ───────────────────────────────────────────────────

  private computeDiff(original: string, modified: string): DiffLine[] {
    const origLines = original.split("\n");
    const modLines = modified.split("\n");
    const lcs = this.lcs(origLines, modLines);

    const result: DiffLine[] = [];
    let oi = 0;
    let mi = 0;
    for (const [origIdx, modIdx] of lcs) {
      while (oi < origIdx) result.push({ type: "removed", text: origLines[oi++] });
      while (mi < modIdx) result.push({ type: "added", text: modLines[mi++] });
      result.push({ type: "unchanged", text: origLines[oi] });
      oi++;
      mi++;
    }
    while (oi < origLines.length) result.push({ type: "removed", text: origLines[oi++] });
    while (mi < modLines.length) result.push({ type: "added", text: modLines[mi++] });
    return result;
  }

  private lcs(a: string[], b: string[]): Array<[number, number]> {
    const m = a.length;
    const n = b.length;
    const dp: number[][] = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
    for (let i = 1; i <= m; i++) {
      for (let j = 1; j <= n; j++) {
        dp[i][j] =
          a[i - 1] === b[j - 1]
            ? dp[i - 1][j - 1] + 1
            : Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
    const result: Array<[number, number]> = [];
    let i = m;
    let j = n;
    while (i > 0 && j > 0) {
      if (a[i - 1] === b[j - 1]) {
        result.unshift([i - 1, j - 1]);
        i--;
        j--;
      } else if (dp[i - 1][j] > dp[i][j - 1]) {
        i--;
      } else {
        j--;
      }
    }
    return result;
  }
}
