import { EditorPosition, MarkdownView, Notice } from "obsidian";
import { StateEffect, StateField, RangeSetBuilder } from "@codemirror/state";
import { Decoration, DecorationSet, EditorView, WidgetType } from "@codemirror/view";
import type ObsidianAIAgent from "../../main";

interface DiffLine {
  type: "unchanged" | "added" | "removed";
  text: string;
}

interface InlineHunk {
  lineNum: number; // 1-based editor line to scroll to (in the new text)
}

class RemovedWidget extends WidgetType {
  constructor(public text: string) {
    super();
  }
  
  eq(other: RemovedWidget) { return this.text === other.text; }
  
  toDOM() {
    const div = document.createElement("div");
    div.className = "ai-agent-diff-inline-removed-block";
    const lines = this.text.split("\n");
    for (const line of lines) {
      const lineDiv = document.createElement("div");
      lineDiv.className = "ai-agent-diff-inline-removed-line ai-agent-inline-diff-line-removed";
      
      const prefix = document.createElement("span");
      prefix.className = "ai-agent-inline-diff-gutter";
      prefix.textContent = "- ";
      lineDiv.appendChild(prefix);
      
      const textSpan = document.createElement("span");
      textSpan.className = "ai-agent-inline-diff-text";
      textSpan.textContent = line;
      lineDiv.appendChild(textSpan);
      
      div.appendChild(lineDiv);
    }
    return div;
  }
  
  ignoreEvent() { return true; }
}

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
 *  - Replaces text buffer with the NEW text.
 *  - Renders old (removed) text as virtual block widgets above the changes.
 *  - Adds line decorations for new (added) text.
 *  - Accept → clears decorations (keeps new text). Reject → reverts buffer.
 */
export class DiffViewer {
  private plugin: ObsidianAIAgent;
  private toolbarEl: HTMLElement | null = null;
  private hunkCountEl: HTMLElement | null = null;
  private view: MarkdownView | null = null;
  private originalText = "";
  private modifiedText = "";
  private selectionStart: EditorPosition | null = null;
  private modifiedEnd: EditorPosition | null = null;
  
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
    this.modifiedText = modifiedText;
    this.selectionStart = selectionStart;

    const editor = view.editor;
    const diffLines = this.computeDiff(originalText, modifiedText);

    // ── 1. Replace selection with NEW text ─────────────────────────────
    editor.replaceRange(modifiedText, selectionStart, selectionEnd);

    const modifiedSplit = modifiedText.split("\n");
    this.modifiedEnd = {
      line: selectionStart.line + modifiedSplit.length - 1,
      ch: modifiedSplit.length === 1
          ? selectionStart.ch + modifiedText.length
          : modifiedSplit[modifiedSplit.length - 1].length,
    };

    // ── 2. Compute Decorations based on Diff ─────────────────────────────
    let currentLineIdx = selectionStart.line + 1; // 1-based CM6 line number
    let currentRemoved: string[] = [];
    
    this.hunks = [];
    const decos: { pos: number, deco: Decoration }[] = [];
    const addedDeco = Decoration.line({ class: "ai-agent-diff-inline-added" });

    for (const diffLine of diffLines) {
      if (diffLine.type === "removed") {
        currentRemoved.push(diffLine.text);
      } else if (diffLine.type === "added") {
        if (currentRemoved.length > 0) {
          decos.push({
            pos: currentLineIdx,
            deco: Decoration.widget({
              widget: new RemovedWidget(currentRemoved.join("\n")),
              block: true,
              side: -1
            })
          });
          this.hunks.push({ lineNum: currentLineIdx });
          currentRemoved = [];
        } else if (this.hunks.length === 0 || this.hunks[this.hunks.length - 1].lineNum !== currentLineIdx) {
          this.hunks.push({ lineNum: currentLineIdx });
        }
        
        decos.push({ pos: currentLineIdx, deco: addedDeco });
        currentLineIdx++;
      } else {
        if (currentRemoved.length > 0) {
          decos.push({
            pos: currentLineIdx,
            deco: Decoration.widget({
              widget: new RemovedWidget(currentRemoved.join("\n")),
              block: true,
              side: -1
            })
          });
          this.hunks.push({ lineNum: currentLineIdx });
          currentRemoved = [];
        }
        currentLineIdx++;
      }
    }
    
    if (currentRemoved.length > 0) {
      decos.push({
        pos: currentLineIdx,
        deco: Decoration.widget({
          widget: new RemovedWidget(currentRemoved.join("\n")),
          block: true,
          side: -1
        })
      });
      this.hunks.push({ lineNum: currentLineIdx });
    }
    this.currentHunk = 0;

    // ── 3. Apply CM6 decorations ────────────────────────────────────────────
    requestAnimationFrame(() => {
      this.applyDecorations(decos);

      // ── 4. Position and show floating toolbar ────────────────────────────
      const firstChangedLine = selectionStart.line;
      const coords = this.getScreenCoordsAt(view, { line: firstChangedLine, ch: 0 });
      this.buildToolbar(coords);

      editor.scrollIntoView({ from: selectionStart, to: this.modifiedEnd! });
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

  private applyDecorations(decos: { pos: number, deco: Decoration }[]): void {
    const cmView = this.getCmView();
    if (!cmView) return;
    this.ensureFieldRegistered(cmView);

    const builder = new RangeSetBuilder<Decoration>();
    decos.sort((a, b) => a.pos - b.pos);

    for (let i = 0; i < decos.length; i++) {
      const d = decos[i];
      const lineNum = Math.max(1, Math.min(d.pos, cmView.state.doc.lines));
      const linePos = cmView.state.doc.line(lineNum).from;
      
      // If there are multiple decorations at the exact same linePos, we must add them in one go 
      // or ensure they don't break strict ordering. RangeSetBuilder requires `from` to be >= previous `from`.
      // The sort above ensures `d.pos` is ascending.
      builder.add(linePos, linePos, d.deco);
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
    const hunk = this.hunks[this.currentHunk];
    if (hunk && this.view) {
      const firstLine = hunk.lineNum - 1; // 0-based
      if (firstLine >= 0) {
        this.view.editor.scrollIntoView({ from: { line: firstLine, ch: 0 }, to: { line: firstLine, ch: 0 } });
      }
    }
  }

  // ── Accept / Reject ────────────────────────────────────────────────────────

  private accept(): void {
    if (this.view && this.modifiedEnd) {
      this.view.editor.setCursor(this.modifiedEnd);
    }
    new Notice("Edit accepted");
    this.close();
  }

  private reject(): void {
    if (this.view && this.selectionStart && this.modifiedEnd) {
      this.view.editor.replaceRange(this.originalText, this.selectionStart, this.modifiedEnd);
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

    let start = 0;
    while (start < origLines.length && start < modLines.length && origLines[start] === modLines[start]) {
      start++;
    }

    let endOrig = origLines.length - 1;
    let endMod = modLines.length - 1;
    while (endOrig >= start && endMod >= start && origLines[endOrig] === modLines[endMod]) {
      endOrig--;
      endMod--;
    }

    const midOrig = origLines.slice(start, endOrig + 1);
    const midMod = modLines.slice(start, endMod + 1);
    const lcs = this.lcs(midOrig, midMod);

    const result: DiffLine[] = [];
    
    // 1. Unchanged prefix
    for (let i = 0; i < start; i++) {
      result.push({ type: "unchanged", text: origLines[i] });
    }

    // 2. Middle section (diff)
    let oi = 0;
    let mi = 0;
    for (const [origIdx, modIdx] of lcs) {
      while (oi < origIdx) result.push({ type: "removed", text: midOrig[oi++] });
      while (mi < modIdx) result.push({ type: "added", text: midMod[mi++] });
      result.push({ type: "unchanged", text: midOrig[oi] });
      oi++;
      mi++;
    }
    while (oi < midOrig.length) result.push({ type: "removed", text: midOrig[oi++] });
    while (mi < midMod.length) result.push({ type: "added", text: midMod[mi++] });

    // 3. Unchanged suffix
    for (let i = endOrig + 1; i < origLines.length; i++) {
      result.push({ type: "unchanged", text: origLines[i] });
    }

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
