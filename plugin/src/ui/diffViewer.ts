import { EditorPosition, EventRef, MarkdownView, Notice } from "obsidian";
import { StateEffect, StateField, RangeSetBuilder } from "@codemirror/state";
import { Decoration, DecorationSet, EditorView, WidgetType } from "@codemirror/view";
import type ObsidianAIAgent from "../../main";

interface DiffLine {
  type: "unchanged" | "added" | "removed";
  text: string;
}

interface DiffChunk {
  type: "unchanged" | "change";
  lines: DiffLine[];
}

interface InlineHunk {
  chunkIndex: number;
  lineNum: number; // 1-based CM6 line number in the original buffer
}

// Renders removed text as a visual widget (kept for CSS class compatibility)
class RemovedWidget extends WidgetType {
  constructor(public text: string) {
    super();
  }

  eq(other: RemovedWidget) { return this.text === other.text; }

  toDOM() {
    const div = document.createElement("div");
    div.className = "ai-agent-diff-inline-removed-block";
    for (const line of this.text.split("\n")) {
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

// Bug 13: Projects added lines as virtual block widgets (Inverted Model)
class AddedWidget extends WidgetType {
  constructor(public text: string) {
    super();
  }

  eq(other: AddedWidget) { return this.text === other.text; }

  toDOM() {
    const div = document.createElement("div");
    div.className = "ai-agent-diff-inline-added-block";
    for (const line of this.text.split("\n")) {
      const lineDiv = document.createElement("div");
      lineDiv.className = "ai-agent-diff-inline-added-line ai-agent-inline-diff-line-added";
      const prefix = document.createElement("span");
      prefix.className = "ai-agent-inline-diff-gutter";
      prefix.textContent = "+ ";
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
 * Inverted Pure-Decoration inline diff:
 *  - Keeps originalText in the buffer. NEVER writes modifiedText on open (Bug 4).
 *  - Highlights removed lines in-buffer with a CSS line decoration.
 *  - Projects added lines as virtual AddedWidget block widgets (Bug 13).
 *  - Supports accepting/rejecting changes hunk-by-hunk.
 *  - Singleton pattern prevents DOM/listener leaks (Bug 16).
 */
export class DiffViewer {
  // Bug 16: Strict Singleton — prevents multiple DOM/listener instances
  private static instance: DiffViewer | null = null;

  public static getInstance(plugin: ObsidianAIAgent): DiffViewer {
    if (!DiffViewer.instance) {
      DiffViewer.instance = new DiffViewer(plugin);
    }
    return DiffViewer.instance;
  }

  private plugin: ObsidianAIAgent;
  private toolbarEl: HTMLElement | null = null;
  private hunkCountEl: HTMLElement | null = null;
  private view: MarkdownView | null = null;
  private originalText = "";
  private modifiedText = "";
  private selectionStart: EditorPosition | null = null;
  // Bug 19: Tracks end of the *original* text range, not modified
  private originalEndPos: EditorPosition | null = null;

  private chunks: DiffChunk[] = [];
  private hunks: InlineHunk[] = [];
  private currentHunk = 0;
  private keyHandler: ((e: KeyboardEvent) => void) | null = null;
  // Bug 23, 31: Typed event refs for proper cleanup via offref()
  private layoutChangeRef: EventRef | null = null;
  private changeRef: EventRef | null = null;

  constructor(plugin: ObsidianAIAgent) {
    this.plugin = plugin;
  }

  show(
    view: MarkdownView,
    originalText: string,
    modifiedText: string,
    selectionStart: EditorPosition,
    _selectionEnd: EditorPosition,  // Bug 21: kept for API compatibility, unused in Inverted Model
    preserveHunkIndex?: number
  ): void {
    this.close(); // Clean up any previous UI and all event listeners

    this.view = view;
    this.originalText = originalText;
    this.modifiedText = modifiedText;
    this.selectionStart = selectionStart;

    // Bug 19: Calculate originalEndPos from the original text, not modified
    const originalSplit = originalText.split("\n");
    this.originalEndPos = {
      line: selectionStart.line + originalSplit.length - 1,
      ch: originalSplit.length === 1
        ? selectionStart.ch + originalText.length
        : originalSplit[originalSplit.length - 1].length,
    };

    const diffLines = this.computeDiff(originalText, modifiedText);
    this.chunks = this.groupIntoChunks(diffLines);

    // Bug 10: If there are no changes, return silently without touching the buffer
    if (this.chunks.filter(c => c.type === "change").length === 0) {
      return;
    }

    const cmView = this.getCmView();
    if (!cmView) return;

    // Bug 20: Use relativeLine counter (not absolute lines) to place decorations
    this.hunks = [];
    const decos: { pos: number; deco: Decoration }[] = [];

    let relativeLine = 0;
    for (let chunkIdx = 0; chunkIdx < this.chunks.length; chunkIdx++) {
      const chunk = this.chunks[chunkIdx];
      if (chunk.type === "unchanged") {
        relativeLine += chunk.lines.length;
      } else {
        const removedLines = chunk.lines.filter(l => l.type === "removed").map(l => l.text);
        const addedLines = chunk.lines.filter(l => l.type === "added").map(l => l.text);

        const startLineNum = selectionStart.line + 1 + relativeLine; // 1-based CM6
        this.hunks.push({ chunkIndex: chunkIdx, lineNum: startLineNum });

        if (removedLines.length > 0) {
          const endLineNum = startLineNum + removedLines.length - 1;
          // Removed lines exist in the buffer — highlight with CSS line decoration
          for (let i = startLineNum; i <= endLineNum; i++) {
            const safeLineNum = Math.min(i, cmView.state.doc.lines);
            decos.push({ pos: cmView.state.doc.line(safeLineNum).from, deco: Decoration.line({ class: "ai-agent-diff-inline-removed" }) });
          }
          if (addedLines.length > 0) {
            // Project added lines as a virtual widget after the last removed line
            const safeEnd = Math.min(endLineNum, cmView.state.doc.lines);
            const insertPos = cmView.state.doc.line(safeEnd).to;
            decos.push({ pos: insertPos, deco: Decoration.widget({ widget: new AddedWidget(addedLines.join("\n")), block: true, side: 1 }) });
          }
          relativeLine += removedLines.length;
        } else if (addedLines.length > 0) {
          // Pure insertion: insert widget before the next unchanged line
          const targetLine = selectionStart.line + 1 + relativeLine;
          let insertPos: number;
          let side: number;
          if (targetLine <= cmView.state.doc.lines) {
            insertPos = cmView.state.doc.line(targetLine).from;
            side = -1;
          } else {
            insertPos = cmView.state.doc.line(targetLine - 1).to;
            side = 1;
          }
          decos.push({ pos: insertPos, deco: Decoration.widget({ widget: new AddedWidget(addedLines.join("\n")), block: true, side }) });
        }
      }
    }

    // Bug 3: Preserve the user's current hunk index across re-renders
    this.currentHunk = preserveHunkIndex !== undefined
      ? Math.min(preserveHunkIndex, Math.max(0, this.hunks.length - 1))
      : 0;

    // Bug 31: layout-change listener — closes if the hosting tab is destroyed
    this.layoutChangeRef = this.plugin.app.workspace.on("layout-change", () => {
      if (this.view && !this.view.contentEl.isConnected) {
        this.close();
      }
    });

    // Bugs 24, 29: editor-change listener — exact sub-range match, not full doc
    this.changeRef = this.plugin.app.workspace.on("editor-change", (editor, info) => {
      if (
        info.file?.path === this.view?.file?.path &&
        this.selectionStart &&
        this.originalEndPos
      ) {
        // Bug 33: guard against accessing a destroyed view
        if (!this.view?.contentEl.isConnected) { this.close(); return; }
        const currentRange = editor.getRange(this.selectionStart, this.originalEndPos);
        if (currentRange !== this.originalText) {
          new Notice("Diff review aborted due to manual document edit.");
          this.close();
        }
      }
    });

    requestAnimationFrame(() => {
      this.applyDecorations(decos);

      const firstChangedLine = this.hunks[0]?.lineNum ? this.hunks[0].lineNum - 1 : selectionStart.line;
      const coords = this.getScreenCoordsAt(view, { line: firstChangedLine, ch: 0 });
      this.buildToolbar(coords);

      this.refreshHunkUI();
    });
  }

  close(): void {
    if (this.keyHandler) {
      document.removeEventListener("keydown", this.keyHandler);
      this.keyHandler = null;
    }
    // Bug 23, 31: offref both workspace listeners to prevent leaks
    if (this.layoutChangeRef) {
      this.plugin.app.workspace.offref(this.layoutChangeRef);
      this.layoutChangeRef = null;
    }
    if (this.changeRef) {
      this.plugin.app.workspace.offref(this.changeRef);
      this.changeRef = null;
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

  private applyDecorations(decos: { pos: number; deco: Decoration }[]): void {
    const cmView = this.getCmView();
    if (!cmView) return;
    this.ensureFieldRegistered(cmView);

    const builder = new RangeSetBuilder<Decoration>();
    decos.sort((a, b) => a.pos - b.pos);

    for (const d of decos) {
      builder.add(d.pos, d.pos, d.deco);
    }

    cmView.dispatch({ effects: setDiffDecos.of(builder.finish()) });
  }

  // Bug 33: Safe clearDecorations — guards against dispatching to a destroyed view
  private clearDecorations(): void {
    try {
      if (this.view && this.view.contentEl?.isConnected && (this.view.editor as any)?.cm) {
        const cmView = this.getCmView();
        if (cmView) {
          cmView.state.field(diffDecosField);
          cmView.dispatch({ effects: clearDiffDecos.of() });
        }
      }
    } catch {
      // Field not registered or view destroyed — nothing to clear
    }
  }

  // ── Floating toolbar ───────────────────────────────────────────────────────

  private buildToolbar(coords: { top: number; left: number }): void {
    // Bug 14: Clamp top with minimum bound so off-screen hunks don't lock the keyboard
    const top = Math.max(20, Math.min(coords.top - 68, window.innerHeight - 80));
    const left = Math.max(8, Math.min(coords.left, window.innerWidth - 320));

    this.toolbarEl = document.createElement("div");
    this.toolbarEl.className = "ai-agent-diff-toolbar";
    this.toolbarEl.style.position = "fixed";
    this.toolbarEl.style.top = `${top}px`;
    this.toolbarEl.style.left = `${left}px`;
    this.toolbarEl.style.display = "flex";
    this.toolbarEl.style.flexDirection = "column";
    this.toolbarEl.style.gap = "4px";
    this.toolbarEl.style.zIndex = "1000";
    document.body.appendChild(this.toolbarEl);

    // Top row: Navigation + Hunk actions
    const hunkRow = this.toolbarEl.createDiv("ai-agent-diff-toolbar-row");
    hunkRow.style.display = "flex";
    hunkRow.style.gap = "8px";
    hunkRow.style.justifyContent = "center";

    const navGroup = hunkRow.createDiv("ai-agent-diff-toolbar-group");
    const multiHunk = this.hunks.length > 1;
    if (multiHunk) {
      navGroup
        .createEl("button", { cls: "ai-agent-diff-toolbar-btn", text: "↑", attr: { title: "Prev change (Shift+Tab)" } })
        .addEventListener("click", () => this.goHunk(-1));
    }
    this.hunkCountEl = navGroup.createSpan({ cls: "ai-agent-diff-toolbar-count" });
    if (multiHunk) {
      navGroup
        .createEl("button", { cls: "ai-agent-diff-toolbar-btn", text: "↓", attr: { title: "Next change (Tab)" } })
        .addEventListener("click", () => this.goHunk(1));
    }

    const actionGroup = hunkRow.createDiv("ai-agent-diff-toolbar-group");
    actionGroup
      .createEl("button", { cls: "ai-agent-diff-toolbar-accept", text: "✓ Accept", attr: { title: "Accept this hunk (Y)" } })
      .addEventListener("click", () => this.acceptCurrentHunk());
    actionGroup
      .createEl("button", { cls: "ai-agent-diff-toolbar-reject", text: "✗ Reject", attr: { title: "Reject this hunk (N)" } })
      .addEventListener("click", () => this.rejectCurrentHunk());

    // Bottom row: Global actions
    const globalRow = this.toolbarEl.createDiv("ai-agent-diff-toolbar-row");
    globalRow.style.display = "flex";
    globalRow.style.gap = "8px";
    globalRow.style.justifyContent = "center";
    globalRow.style.width = "100%";
    globalRow.style.borderTop = "1px solid var(--background-modifier-border)";
    globalRow.style.paddingTop = "4px";

    const globalGroup = globalRow.createDiv("ai-agent-diff-toolbar-group");
    globalGroup
      .createEl("button", { cls: "ai-agent-diff-toolbar-accept-all", text: "✓ Accept All", attr: { title: "Accept all remaining changes (Enter)" } })
      .addEventListener("click", () => this.acceptAll());
    globalGroup
      .createEl("button", { cls: "ai-agent-diff-toolbar-reject-all", text: "✗ Reject All", attr: { title: "Reject all remaining changes (Escape)" } })
      .addEventListener("click", () => this.rejectAll());

    this.refreshHunkUI();

    this.keyHandler = (e: KeyboardEvent) => {
      if (e.key === "Enter") { e.preventDefault(); this.acceptAll(); }
      else if (e.key === "Escape") { e.preventDefault(); this.rejectAll(); }
      else if (e.key === "Tab" && !e.shiftKey) { e.preventDefault(); this.goHunk(1); }
      else if (e.key === "Tab" && e.shiftKey) { e.preventDefault(); this.goHunk(-1); }
      else if (e.key.toLowerCase() === "y") { e.preventDefault(); this.acceptCurrentHunk(); }
      else if (e.key.toLowerCase() === "n") { e.preventDefault(); this.rejectCurrentHunk(); }
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

  // Bug 1: Use CM6 EditorView.scrollIntoView dispatch instead of zero-length range no-op
  private refreshHunkUI(): void {
    if (this.hunkCountEl && this.hunks.length >= 1) {
      this.hunkCountEl.setText(`${this.currentHunk + 1}/${this.hunks.length}`);
    }
    const hunk = this.hunks[this.currentHunk];
    if (hunk && this.view) {
      const cmView = this.getCmView();
      if (cmView) {
        const lineNum = Math.max(1, Math.min(hunk.lineNum, cmView.state.doc.lines));
        const pos = cmView.state.doc.line(lineNum).from;
        cmView.dispatch({ effects: EditorView.scrollIntoView(pos, { y: "center" }) });
      }
    }
  }

  // ── Accept / Reject Logic ──────────────────────────────────────────────────

  // Bug 17: Use helpers to reconstruct both texts; pass to show() for re-render
  private acceptCurrentHunk(): void {
    if (!this.view || !this.originalEndPos || this.hunks.length === 0) return;

    const hunk = this.hunks[this.currentHunk];
    // Bug 3: Preserve position — advance index if not at last hunk, else go back
    const preserveIdx = this.currentHunk < this.hunks.length - 1
      ? this.currentHunk
      : Math.max(0, this.currentHunk - 1);

    // New baseline: original with hunk N's added lines merged in
    const newOriginalText = this.applyChunkToText(this.originalText, hunk);
    // Write accepted state to buffer before calling show()
    this.view.editor.replaceRange(newOriginalText, this.selectionStart!, this.originalEndPos);

    // modifiedText is unchanged — computeDiff will drop the resolved hunk naturally
    this.show(this.view, newOriginalText, this.modifiedText, this.selectionStart!, this.originalEndPos, preserveIdx);
  }

  // Bug 25: Dedicated state-builder for reject — only removes rejected hunk from proposal
  private rejectCurrentHunk(): void {
    if (!this.view || !this.originalEndPos || this.hunks.length === 0) return;

    const hunk = this.hunks[this.currentHunk];
    const preserveIdx = this.currentHunk < this.hunks.length - 1
      ? this.currentHunk
      : Math.max(0, this.currentHunk - 1);

    // New modifiedText: drop hunk N's additions, keep all others
    const newModifiedText = this.applyChunkToModifiedText(hunk);
    // Buffer keeps originalText (no replaceRange needed in Inverted Model)
    this.show(this.view, this.originalText, newModifiedText, this.selectionStart!, this.originalEndPos, preserveIdx);
  }

  // Bug 18: acceptAll must actively write modifiedText (in Inverted Model buffer = originalText)
  private acceptAll(): void {
    if (this.view && this.selectionStart && this.originalEndPos) {
      this.view.editor.replaceRange(this.modifiedText, this.selectionStart, this.originalEndPos);
      const modifiedSplit = this.modifiedText.split("\n");
      const finalEndPos = {
        line: this.selectionStart.line + modifiedSplit.length - 1,
        ch: modifiedSplit.length === 1
          ? this.selectionStart.ch + this.modifiedText.length
          : modifiedSplit[modifiedSplit.length - 1].length,
      };
      this.view.editor.setCursor(finalEndPos);
    }
    new Notice("All remaining edits accepted");
    this.close();
  }

  // Bug 9: rejectAll requires no replaceRange — buffer already holds originalText
  private rejectAll(): void {
    if (this.view && this.selectionStart) {
      this.view.editor.setCursor(this.selectionStart);
    }
    new Notice("All remaining edits rejected");
    this.close();
  }

  // ── Hunk state-builder helpers ─────────────────────────────────────────────

  // For acceptCurrentHunk: emit added lines for the target chunk, removed for others
  private applyChunkToText(baseText: string, targetHunk: InlineHunk): string {
    void baseText; // unused — chunks already hold the line state
    const lines: string[] = [];
    for (let i = 0; i < this.chunks.length; i++) {
      const chunk = this.chunks[i];
      if (chunk.type === "unchanged") {
        lines.push(...chunk.lines.map(l => l.text));
      } else {
        if (i === targetHunk.chunkIndex) {
          // Accept this hunk: take the added lines
          lines.push(...chunk.lines.filter(l => l.type === "added").map(l => l.text));
        } else {
          // Other hunks: keep original (removed) lines as baseline
          lines.push(...chunk.lines.filter(l => l.type === "removed").map(l => l.text));
        }
      }
    }
    return lines.join("\n");
  }

  // For rejectCurrentHunk: emit removed lines for target (revert), added for others (keep)
  private applyChunkToModifiedText(targetHunk: InlineHunk): string {
    const lines: string[] = [];
    for (let i = 0; i < this.chunks.length; i++) {
      const chunk = this.chunks[i];
      if (chunk.type === "unchanged") {
        lines.push(...chunk.lines.map(l => l.text));
      } else {
        if (i === targetHunk.chunkIndex) {
          // Reject this hunk: revert to original (removed) lines
          lines.push(...chunk.lines.filter(l => l.type === "removed").map(l => l.text));
        } else {
          // Other hunks: keep the added lines in the proposal
          lines.push(...chunk.lines.filter(l => l.type === "added").map(l => l.text));
        }
      }
    }
    return lines.join("\n");
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

  // ── Diff algorithm (LCS with OOM guard) ───────────────────────────────────

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

    // Bug 8: OOM guard — if the LCS matrix would exceed 500k cells, fallback to a single chunk
    let lcs: Array<[number, number]>;
    if (midOrig.length * midMod.length > 500_000) {
      lcs = []; // Treat as pure delete + add for the entire middle section
    } else {
      lcs = this.lcs(midOrig, midMod);
    }

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

  private groupIntoChunks(diffLines: DiffLine[]): DiffChunk[] {
    const chunks: DiffChunk[] = [];
    let currentChunk: DiffLine[] = [];
    let currentType: "unchanged" | "change" | null = null;

    for (const line of diffLines) {
      const type = line.type === "unchanged" ? "unchanged" : "change";
      if (currentType === null) {
        currentType = type;
        currentChunk.push(line);
      } else if (currentType === type) {
        currentChunk.push(line);
      } else {
        chunks.push({ type: currentType, lines: currentChunk });
        currentType = type;
        currentChunk = [line];
      }
    }
    if (currentChunk.length > 0 && currentType) {
      chunks.push({ type: currentType, lines: currentChunk });
    }
    return chunks;
  }
}
