import {
  ItemView,
  WorkspaceLeaf,
  MarkdownRenderer,
  htmlToMarkdown,
  setIcon,
  TFile,
  Notice,
  Menu,
  App,
  MarkdownView,
} from "obsidian";
import { existsSync, readdirSync, readFileSync, statSync } from "fs";
import { join } from "path";
import type ObsidianAIAgent from "../../main";
import { IncuratorClient } from "../agent/incuratorClient";
import {
  EXTERNAL_PDF_CONTEXT_EVENT,
  EXTERNAL_PDF_VIEW_TYPE,
  ExternalPdfView,
  registerExternalPdf,
} from "./externalPdfView";
import { IngestDestinationModal } from "./ingestDestinationModal";
import { getPdfContext, withVisionFallback } from "../context/pdfCapture";
import { attachLatexCopyHandler, collapseStreamingEditBlocks, normalizeLatexDelimiters, stampMathSourceData, stripDanglingEditMarkers, truncateToLength } from "../utils/textUtils";
import { inferIngestDestination } from "../utils/pathUtils";
import { hashFileSha256 } from "../utils/fileHash";
import { findSearchBlock } from "../utils/editMatch";
import { DiffViewer } from "./diffViewer";
import { renderCuratorQueryTrace } from "./incuratorQueryTrace";
import {
  escapeAttribute,
  formatCuratorQueryResult,
  formatIncuratorHits,
  formatOutline,
  formatPdfWindow,
  formatRagHits,
} from "../context/providerContextFormat";
import { buildBaseSystemPrompt, editableSelectionInstruction, wrapLatestUserMessageForLanguageBridge } from "../context/systemPrompt";
import { detectLanguage, inferQueryLanguageMetadata } from "../context/languageBridge";
import {
  deriveChatSessionTitle,
  formatRelativeSessionTime,
} from "../context/chatSessionSummary";
import {
  contextPriorityInstruction,
  contextPromptLabel,
  hasPrimaryUserContext,
  includedContextRefs,
  isPrimaryUserContext,
  shouldIncludeContext,
} from "../context/chatContextPriority";
import { buildMarkdownOutline } from "../context/quickQueryContext";
import { parseAnswerLinkTarget, type AnswerLinkTarget } from "../context/answerLinkNavigation";
import { resolveSelectionReferencesBlock } from "../context/pdfReferenceContext";
import {
  shouldRunCuratorDomainQuery,
  shouldUseBackendPdfContext,
} from "../context/providerContextPolicy";
import {
  detectGitSidechatCommand,
  type GitSidechatCommand,
} from "./gitSidechatCommands";
import {
  type ChatMessage,
  type ChatMode,
  type ChatSession,
  type CodexReasoningEffort,
  type ContextRef,
  type CuratorQueryResult,
  type IncuratorSourceStatus,
  type LLMMessage,
  type LLMContentPart,
  type PdfPageContext,
  type LLMProvider,
  type StreamChunk,
  getDefaultModel,
  getModelOption,
  modelSupportsVision,
} from "../types";

export interface MultiEditProposal {
  filepath: string;
  search: string;
  replace: string;
  originalBlock: string;
}

export const CHAT_VIEW_TYPE = "ai-agent-chat";

function leafContainerEl(leaf: WorkspaceLeaf): HTMLElement {
  return (leaf as unknown as { containerEl: HTMLElement }).containerEl;
}

const IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"];
const CUSTOM_MODEL_VALUE = "__custom__";
const RULES_CONTEXT_LIMIT = 12000;
const CONTINUITY_MESSAGE_LIMIT = 6;

/** Built sources show an inert "Added" badge (PLUGIN_SCHEMA §4.1.1). */
function isAddedState(state: string): boolean {
  return state === "l1_ready" || state === "l2_ready" || state === "l3_ready" || state === "l4_ready";
}

export class ChatSidebarView extends ItemView {
  private plugin: ObsidianAIAgent;
  private messages: ChatMessage[] = [];
  private messagesContainer!: HTMLElement;
  private inputEl!: HTMLTextAreaElement;
  private sendBtn!: HTMLButtonElement;
  private contextChipsContainer!: HTMLElement;
  private modelSelectEl!: HTMLSelectElement;
  private sessionBtn!: HTMLButtonElement;
  private activeSessionTitleEl!: HTMLElement;
  private sessionDrawerEl!: HTMLElement;
  private sessionSearchEl!: HTMLInputElement;
  private modeSelectEl!: HTMLSelectElement;
  private reasoningSelectEl!: HTMLSelectElement;
  private customModelInputEl!: HTMLInputElement;
  private inputAreaEl!: HTMLElement;
  private dropOverlayEl!: HTMLElement;
  private pendingContextRefs: ContextRef[] = [];
  private cachedAutoContextRefs: ContextRef[] = [];
  private activeContextExcludedKeys: Set<string> = new Set();
  private isGenerating = false;
  private thinkingTimer: ReturnType<typeof setInterval> | null = null;
  private thinkingStartTime = 0;
  private splitDropOverlay: HTMLElement | null = null;
  private splitDropSide: "left" | "right" | "top" | "bottom" | "center" = "center";
  private splitDropTarget: WorkspaceLeaf | null = null;
  private incuratorClient: IncuratorClient | null = null;
  private incuratorStatusByPath = new Map<string, IncuratorSourceStatus>();
  private incuratorStatusInFlight = new Set<string>();
  private fileHashByPath = new Map<string, string>();
  private prepareStatusText = "";
  private lastQueryTrace: CuratorQueryResult | null = null;
  private sessionDrawerVisible = false;
  private sessionQuery = "";
  private statusBarEl!: HTMLElement;
  private statusPollInterval: any = null;

  constructor(leaf: WorkspaceLeaf, plugin: ObsidianAIAgent) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType(): string {
    return CHAT_VIEW_TYPE;
  }

  getDisplayText(): string {
    return "AI Agent";
  }

  getIcon(): string {
    return "bot";
  }

  async onOpen(): Promise<void> {
    const container = this.containerEl.children[1] as HTMLElement;
    container.empty();
    container.addClass("ai-agent-chat-container");

    // ── Codex-style sidebar header ──
    const header = container.createDiv("ai-agent-chat-header");
    const titleBlock = header.createDiv("ai-agent-chat-header-title");
    titleBlock.createEl("div", { cls: "ai-agent-chat-header-kicker", text: "Incurator" });
    this.activeSessionTitleEl = titleBlock.createEl("div", {
      cls: "ai-agent-chat-header-session",
      text: "New chat",
    });

    const headerActions = header.createDiv("ai-agent-chat-header-actions");
    
    // Status bar container
    this.statusBarEl = headerActions.createDiv("ai-agent-chat-status-bar");
    this.statusBarEl.style.display = "flex";
    this.statusBarEl.style.alignItems = "center";
    this.statusBarEl.style.marginRight = "8px";
    this.statusBarEl.style.fontSize = "11px";
    this.statusBarEl.style.color = "var(--text-muted)";
    this.statusBarEl.style.gap = "8px";

    const newChatBtn = headerActions.createEl("button", {
      cls: "ai-agent-icon-btn ai-agent-new-chat-btn",
      attr: { "aria-label": "New conversation", title: "New chat" },
    });
    setIcon(newChatBtn, "square-pen");
    newChatBtn.addEventListener("click", async () => {
      await this.createNewChatSession();
      this.hideSessionDrawer();
      this.restoreInputFocus();
    });

    this.sessionBtn = headerActions.createEl("button", {
      cls: "ai-agent-icon-btn ai-agent-session-toggle-btn",
      attr: { "aria-label": "Conversations", title: "Conversations" },
    });
    setIcon(this.sessionBtn, "history");
    this.sessionBtn.addEventListener("click", () => this.toggleSessionDrawer());

    this.sessionDrawerEl = container.createDiv("ai-agent-session-drawer");
    this.sessionDrawerEl.hide();
    const sessionSearch = this.sessionDrawerEl.createDiv("ai-agent-session-drawer-search");
    setIcon(sessionSearch.createSpan("ai-agent-session-drawer-search-icon"), "search");
    this.sessionSearchEl = sessionSearch.createEl("input", {
      attr: {
        type: "search",
        placeholder: "Search conversations",
        "aria-label": "Search conversations",
      },
    });
    this.sessionSearchEl.addEventListener("input", () => {
      this.sessionQuery = this.sessionSearchEl.value.trim().toLowerCase();
      this.renderSessionDrawer();
    });
    this.sessionDrawerEl.createDiv("ai-agent-session-drawer-list");

    // Start status polling
    this.statusPollInterval = setInterval(() => this.updateStatusBar(), 2000) as any;
    this.updateStatusBar();

    // ── Messages area ──
    this.messagesContainer = container.createDiv("ai-agent-chat-messages");
    await this.loadActiveSession();
    this.renderMessages();

    // ── Input area (bottom dock) ──
    this.inputAreaEl = container.createDiv("ai-agent-chat-input-area");

    // Refresh context chips whenever the active leaf changes.
    // NOTE: Do NOT clear activeContextExcludedKeys here — the user's eye-off
    // state must persist across tab switches. Keys become stale naturally when
    // the file they refer to is no longer open (renderContextChips will not
    // render chips for those keys, so they are harmlessly ignored).
    this.registerEvent(
      this.app.workspace.on("active-leaf-change", () => {
        setTimeout(() => {
          this.renderContextChips();
        }, 0);
      })
    );
    this.registerDomEvent(
      window,
      EXTERNAL_PDF_CONTEXT_EVENT as keyof WindowEventMap,
      () => {
      this.renderContextChips();
      }
    );

    // Drop overlay (hidden by default)
    this.dropOverlayEl = this.inputAreaEl.createDiv("ai-agent-drop-overlay");
    this.dropOverlayEl.createDiv({
      cls: "ai-agent-drop-overlay-content",
      text: "📎 Drop files here",
    });

    const composer = this.inputAreaEl.createDiv("ai-agent-composer");

    // Context chips
    this.contextChipsContainer = composer.createDiv(
      "ai-agent-context-chips"
    );
    this.setupChipsDrop();
    this.renderContextChips();

    const inputRow = composer.createDiv("ai-agent-chat-input-row");
    this.inputEl = inputRow.createEl("textarea", {
      cls: "ai-agent-chat-input",
      attr: {
        placeholder: "Ask anything... (Shift+Enter for newline)",
        rows: "1",
      },
    });

    this.inputEl.addEventListener("keydown", (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "l") {
        e.preventDefault();

        // Defer execution so that any current focus/selection states are preserved,
        // then execute the global command which handles both MD and PDF extraction robustly.
        window.setTimeout(() => {
          // @ts-ignore (Obsidian internal API)
          this.app.commands.executeCommandById("incurator-obsidian-agent:line-reference");
        }, 0);
        return;
      }

      if (e.key === "Enter" && !e.shiftKey) {
        if (e.isComposing) return;
        e.preventDefault();
        this.handleSend();
      }
    });

    this.inputEl.addEventListener("input", () => {
      this.inputEl.style.height = "auto";
      this.inputEl.style.height =
        Math.min(this.inputEl.scrollHeight, 150) + "px";
    });

    // ── Composer footer: session, mode, model, send ──
    const toolbar = composer.createDiv("ai-agent-bottom-toolbar");
    const leftControls = toolbar.createDiv("ai-agent-toolbar-left");
    const rightControls = toolbar.createDiv("ai-agent-toolbar-right");

    const attachBtn = leftControls.createEl("button", {
      cls: "ai-agent-icon-btn ai-agent-attach-btn",
      attr: { "aria-label": "Attach file or image", title: "Attach file" },
    });
    setIcon(attachBtn, "paperclip");
    attachBtn.addEventListener("click", () => this.openFilePicker());

    this.modeSelectEl = leftControls.createEl("select", {
      cls: "ai-agent-mode-select",
      attr: { "aria-label": "Chat mode", title: "Chat mode" },
    });
    [
      { value: "chat", label: "Chat" },
      { value: "plan", label: "Plan" },
    ].forEach((mode) => {
      this.modeSelectEl.createEl("option", {
        value: mode.value,
        text: mode.label,
      });
    });
    this.modeSelectEl.value = this.plugin.settings.chatMode;
    this.modeSelectEl.addEventListener("change", () => {
      this.onModeChange(this.modeSelectEl.value as ChatMode);
      this.restoreInputFocus();
    });

    this.modelSelectEl = rightControls.createEl("select", {
      cls: "ai-agent-model-select",
      attr: { "aria-label": "Provider and model", title: "Provider and model" },
    });
    this.modelSelectEl.addEventListener("change", () => {
      this.onModelSelectChange(this.modelSelectEl.value);
    });

    this.customModelInputEl = rightControls.createEl("input", {
      cls: "ai-agent-custom-model-input",
      attr: {
        type: "text",
        placeholder: "custom model id",
        spellcheck: "false",
        "aria-label": "Custom model id",
      },
    });
    this.customModelInputEl.addEventListener("change", () => {
      this.onCustomModelChange(this.customModelInputEl.value.trim());
    });

    this.reasoningSelectEl = rightControls.createEl("select", {
      cls: "ai-agent-reasoning-select",
    });
    this.reasoningSelectEl.addEventListener("change", () => {
      this.onReasoningChange(this.reasoningSelectEl.value);
      this.restoreInputFocus();
    });

    this.sendBtn = rightControls.createEl("button", {
      cls: "ai-agent-send-btn",
      attr: { "aria-label": "Send message", title: "Send" },
    });
    setIcon(this.sendBtn, "send");
    this.sendBtn.addEventListener("click", () => this.handleSend());

    this.syncModelControls();
    this.syncSessionControls();

    // ── Drag & Drop ──
    this.setupDragAndDrop(container);
    this.setupGlobalPdfDrop();

    // ── Paste handler (paste images) ──
    this.inputEl.addEventListener("paste", (e: ClipboardEvent) => {
      this.handlePaste(e);
    });
  }

  async onClose(): Promise<void> {
    if (this.statusPollInterval) {
      clearInterval(this.statusPollInterval);
      this.statusPollInterval = null;
    }
    this.stopThinkingTimer();
    this.splitDropOverlay?.remove();
    this.splitDropOverlay = null;
  }

  private updateStatusBar(): void {
    if (!this.statusBarEl) return;
    try {
      const vaultRoot = (this.plugin.app.vault.adapter as any).getBasePath?.() || "";
      if (!vaultRoot) return;
      const jobsPath = join(vaultRoot, ".curator", "runtime", "jobs.json");
      const statusPath = join(vaultRoot, ".curator", "runtime", "status.json");
      
      this.statusBarEl.empty();

      if (existsSync(jobsPath)) {
        const raw = readFileSync(jobsPath, "utf8");
        const data = JSON.parse(raw);
        if (data.running && data.running.length > 0) {
          const spinner = this.statusBarEl.createSpan({ cls: "ai-agent-spin" });
          setIcon(spinner, "loader");
          this.statusBarEl.createSpan({ text: ` ${data.running.length} running` });
        } else if (data.queued && data.queued.length > 0) {
          const spinner = this.statusBarEl.createSpan({ cls: "ai-agent-spin" });
          setIcon(spinner, "loader");
          this.statusBarEl.createSpan({ text: ` ${data.queued.length} queued` });
        }
      }
    } catch (e) {
      // fail silently
    }
  }

  // ── Public API ──────────────────────────────────────────────

  addContextRef(ref: ContextRef): void {
    const existing = this.pendingContextRefs.find(
      (r) =>
        r.type === ref.type &&
        r.label === ref.label &&
        r.content === ref.content &&
        // Two refs with identical labels but different images are distinct
        // (e.g. successive crops of the same PDF page).
        r.imageBase64 === ref.imageBase64
    );
    if (!existing) {
      this.pendingContextRefs.push(ref);
      this.renderContextChips();
    }
  }

  focusInput(): void {
    this.inputEl?.focus();
  }

  // ── File / Media attachment ─────────────────────────────────

  private openFilePicker(): void {
    // Use a native file input to pick any file (images, text, etc. - PDF included as fallback)
    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.multiple = true;
    fileInput.accept = "image/*,.md,.txt,.pdf,.json,.csv,.ts,.js,.py";
    fileInput.style.display = "none";
    fileInput.addEventListener("change", async () => {
      if (fileInput.files) {
        for (const file of Array.from(fileInput.files)) {
          await this.attachNativeFile(file);
        }
      }
      fileInput.remove();
    });
    document.body.appendChild(fileInput);
    fileInput.click();
  }

  private async attachNativeFile(
    file: File,
    explicitPath?: string
  ): Promise<void> {
    const ext = file.name.split(".").pop()?.toLowerCase() || "";
    const isImage = IMAGE_EXTENSIONS.includes(ext) || file.type.startsWith("image/");

    if (ext === "pdf" || file.type === "application/pdf") {
      await this.openExternalPdf(file, explicitPath);
      return;
    }

    if (isImage) {
      // Read as base64
      const base64 = await this.fileToBase64(file);
      const ref: ContextRef = {
        type: "file",
        label: `🖼️ ${file.name}`,
        content: "",
        imageBase64: base64,
      };
      this.addContextRef(ref);
      new Notice(`Attached image: ${file.name}`);
    } else {
      // Read as text
      try {
        const text = await file.text();
        const ref: ContextRef = {
          type: "file",
          label: `📄 ${file.name}`,
          content: text.slice(0, 50000), // Cap at 50K chars
        };
        this.addContextRef(ref);
        new Notice(`Attached file: ${file.name}`);
      } catch {
        new Notice(`Could not read file: ${file.name}`);
      }
    }
  }

  private async attachVaultFile(file: TFile): Promise<void> {
    const ext = file.extension.toLowerCase();
    const isImage = IMAGE_EXTENSIONS.includes(ext);

    if (ext === "pdf") {
      await this.openPdfFile(file);
      return;
    }

    if (isImage) {
      // Read binary from vault and convert to base64
      const arrayBuf = await this.app.vault.readBinary(file);
      const base64 = this.arrayBufferToBase64(arrayBuf);
      const ref: ContextRef = {
        type: "file",
        label: `🖼️ ${file.name}`,
        content: "",
        imageBase64: base64,
        filePath: file.path,
      };
      this.addContextRef(ref);
      new Notice(`Attached image: ${file.name}`);
    } else {
      // Read text from vault
      try {
        const text = await this.app.vault.read(file);
        const ref: ContextRef = {
          type: "file",
          label: `📄 ${file.name}`,
          content: text.slice(0, 50000),
          filePath: file.path,
        };
        this.addContextRef(ref);
        new Notice(`Attached file: ${file.name}`);
      } catch {
        new Notice(`Could not read file: ${file.name}`);
      }
    }
  }

  private async openExternalPdf(
    file: File,
    explicitPath?: string
  ): Promise<void> {
    try {
      const pdfState = registerExternalPdf(file, explicitPath);
      const leaf = this.getMainWorkspaceLeaf();
      await leaf.setViewState({
        type: EXTERNAL_PDF_VIEW_TYPE,
        active: true,
        state: pdfState,
      });
      this.app.workspace.revealLeaf(leaf);
      window.dispatchEvent(new CustomEvent(EXTERNAL_PDF_CONTEXT_EVENT));
      setTimeout(() => this.renderContextChips(), 0);
      setTimeout(() => this.renderContextChips(), 250);
      new Notice(`Opened external PDF: ${file.name}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      new Notice(`Could not open external PDF: ${msg}`);
    }
  }

  /** Returns a leaf in the main editor area (never the sidebar). */
  private getMainWorkspaceLeaf(): WorkspaceLeaf {
    // getMostRecentLeaf(rootSplit) finds the last-used leaf in the main content area
    const rootSplit = this.app.workspace.rootSplit;
    const recent = this.app.workspace.getMostRecentLeaf(rootSplit);
    if (recent) {
      this.app.workspace.setActiveLeaf(recent, { focus: false });
    }
    return this.app.workspace.getLeaf("tab");
  }

  private async openPdfFile(file: TFile): Promise<void> {
    const leaf = this.app.workspace.getLeaf("tab");
    await leaf.openFile(file, { active: true });
    this.app.workspace.revealLeaf(leaf);
  }

  // ── Drag & Drop ─────────────────────────────────────────────

  private setupDragAndDrop(el: HTMLElement): void {
    let dragCounter = 0;

    this.registerDomEvent(el, "dragenter", (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter++;
      this.dropOverlayEl.addClass("ai-agent-drop-active");
    });

    this.registerDomEvent(el, "dragleave", (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter--;
      if (dragCounter <= 0) {
        dragCounter = 0;
        this.dropOverlayEl.removeClass("ai-agent-drop-active");
      }
    });

    this.registerDomEvent(el, "dragover", (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.dataTransfer) {
        e.dataTransfer.dropEffect = "copy";
      }
    });

    this.registerDomEvent(el, "drop", async (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter = 0;
      this.dropOverlayEl.removeClass("ai-agent-drop-active");

      await this.handleDataTransferDrop(e.dataTransfer, false);
    });
  }

  private setupGlobalPdfDrop(): void {
    this.registerDomEvent(
      document,
      "dragover",
      (e: DragEvent) => {
        if (!e.dataTransfer || !this.hasPdfDrag(e.dataTransfer)) return;
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = "copy";
        this.updateSplitDropGuideline(e);
      },
      { capture: true }
    );

    this.registerDomEvent(
      document,
      "dragleave",
      (e: DragEvent) => {
        if (!e.relatedTarget) this.hideSplitDropGuideline();
      },
      { capture: true }
    );

    this.registerDomEvent(
      document,
      "dragend",
      () => this.hideSplitDropGuideline(),
      { capture: true }
    );

    this.registerDomEvent(
      document,
      "drop",
      async (e: DragEvent) => {
        if (!e.dataTransfer || !this.hasPdfDrop(e.dataTransfer)) return;
        e.preventDefault();
        e.stopPropagation();
        const side = this.splitDropSide;
        const target = this.splitDropTarget;
        this.hideSplitDropGuideline();
        // Drop on the chat sidebar itself → attach to chat context
        if (target === this.leaf) {
          await this.handleDataTransferDrop(e.dataTransfer, true);
        } else {
          await this.handleSplitDrop(e.dataTransfer, target, side);
        }
      },
      { capture: true }
    );
  }

  private updateSplitDropGuideline(e: DragEvent): void {
    // Lazy-create fixed overlay
    if (!this.splitDropOverlay) {
      this.splitDropOverlay = document.body.createDiv("ai-agent-split-drop-overlay");
    }

    const leaf = this.getLeafAtPoint(e.clientX, e.clientY);

    // Over the chat sidebar — use the existing drop overlay instead
    if (leaf === this.leaf) {
      this.splitDropOverlay.style.display = "none";
      this.dropOverlayEl?.addClass("ai-agent-drop-active");
      this.splitDropTarget = this.leaf;
      this.splitDropSide = "center";
      return;
    }
    this.dropOverlayEl?.removeClass("ai-agent-drop-active");

    if (!leaf) {
      this.splitDropOverlay.style.display = "none";
      this.splitDropTarget = null;
      return;
    }

    this.splitDropTarget = leaf;
    const rect = leafContainerEl(leaf).getBoundingClientRect();
    const relX = (e.clientX - rect.left) / rect.width;
    const relY = (e.clientY - rect.top) / rect.height;
    const edge = 0.28;

    let side: typeof this.splitDropSide;
    let ox = rect.left, oy = rect.top, ow = rect.width, oh = rect.height;

    if (relX < edge) {
      side = "left"; ow = rect.width / 2;
    } else if (relX > 1 - edge) {
      side = "right"; ox = rect.left + rect.width / 2; ow = rect.width / 2;
    } else if (relY < edge) {
      side = "top"; oh = rect.height / 2;
    } else if (relY > 1 - edge) {
      side = "bottom"; oy = rect.top + rect.height / 2; oh = rect.height / 2;
    } else {
      side = "center";
    }

    this.splitDropSide = side;

    const overlay = this.splitDropOverlay;
    overlay.style.display = "flex";
    overlay.style.left = `${ox}px`;
    overlay.style.top = `${oy}px`;
    overlay.style.width = `${ow}px`;
    overlay.style.height = `${oh}px`;

    overlay.empty();
    const labels: Record<typeof side, string> = {
      left: "⬛ Split left",
      right: "Split right ⬛",
      top: "Split top",
      bottom: "Split bottom",
      center: "Open in tab",
    };
    overlay.createDiv({ cls: "ai-agent-split-drop-label", text: labels[side] });
  }

  private hideSplitDropGuideline(): void {
    if (this.splitDropOverlay) this.splitDropOverlay.style.display = "none";
    this.dropOverlayEl?.removeClass("ai-agent-drop-active");
    this.splitDropTarget = null;
  }

  private getLeafAtPoint(x: number, y: number): WorkspaceLeaf | null {
    const el = document.elementFromPoint(x, y);
    if (!el) return null;
    let found: WorkspaceLeaf | null = null;
    this.app.workspace.iterateAllLeaves((leaf) => {
      if (found) return;
      if (leafContainerEl(leaf).contains(el)) found = leaf;
    });
    return found;
  }

  private async handleSplitDrop(
    dataTransfer: DataTransfer,
    targetLeaf: WorkspaceLeaf | null,
    side: typeof this.splitDropSide
  ): Promise<void> {
    // Vault PDF (Obsidian internal drag)
    const obsidianPath = dataTransfer.getData("text/plain");
    if (obsidianPath) {
      const vaultFile = this.app.vault.getAbstractFileByPath(obsidianPath);
      if (vaultFile instanceof TFile && vaultFile.extension === "pdf") {
        const leaf = this.resolveDropLeaf(targetLeaf, side);
        await leaf.openFile(vaultFile, { active: true });
        this.app.workspace.revealLeaf(leaf);
        return;
      }
    }

    // OS file drag
    const pathHints = this.getExternalFilePathHints(dataTransfer);
    const files = dataTransfer.files?.length
      ? Array.from(dataTransfer.files)
      : Array.from(dataTransfer.items ?? [])
          .filter((i) => i.kind === "file")
          .map((i) => i.getAsFile())
          .filter((f): f is File => f !== null);

    for (const [idx, file] of files.entries()) {
      if (!this.isPdfFile(file)) continue;
      try {
        const pdfState = registerExternalPdf(file, pathHints[idx]);
        const leaf = this.resolveDropLeaf(targetLeaf, side);
        await leaf.setViewState({
          type: EXTERNAL_PDF_VIEW_TYPE,
          active: true,
          state: pdfState,
        });
        this.app.workspace.revealLeaf(leaf);
        new Notice(`Opened PDF: ${file.name}`);
      } catch (err: unknown) {
        new Notice(`Could not open PDF: ${err instanceof Error ? err.message : String(err)}`);
      }
      break; // one PDF per drop
    }
  }

  private resolveDropLeaf(
    targetLeaf: WorkspaceLeaf | null,
    side: typeof this.splitDropSide
  ): WorkspaceLeaf {
    if (side === "center" || !targetLeaf) {
      return this.getMainWorkspaceLeaf();
    }
    const direction: "vertical" | "horizontal" =
      side === "left" || side === "right" ? "vertical" : "horizontal";
    this.app.workspace.setActiveLeaf(targetLeaf, { focus: false });
    return this.app.workspace.getLeaf("split", direction);
  }

  private async handleDataTransferDrop(
    dataTransfer: DataTransfer | null,
    pdfOnly: boolean
  ): Promise<void> {
    if (!dataTransfer) return;

    // 1. Obsidian internal file drag or pure text drag: vault path or text in text/plain.
    const textData = dataTransfer.getData("text/plain");
    if (textData) {
      const file = this.app.vault.getAbstractFileByPath(textData);
      if (file instanceof TFile && (!pdfOnly || file.extension === "pdf")) {
        await this.attachVaultFile(file);
        return;
      } else if (!pdfOnly && !file) {
        // Not a file path, treat as a dragged text snippet
        const trimmed = textData.trim();
        if (trimmed) {
          this.addContextRef({
            type: "text",
            label: "Dragged Text",
            content: trimmed,
          });
          return;
        }
      }
    }

    // 2. OS files.
    if (dataTransfer.files && dataTransfer.files.length > 0) {
      const pathHints = this.getExternalFilePathHints(dataTransfer);
      for (const [index, file] of Array.from(dataTransfer.files).entries()) {
        if (!pdfOnly || this.isPdfFile(file)) {
          await this.attachNativeFile(file, pathHints[index]);
        }
      }
      return;
    }

    // 3. DataTransfer items.
    if (dataTransfer.items) {
      for (const item of Array.from(dataTransfer.items)) {
        if (item.kind === "file") {
          const file = item.getAsFile();
          if (file && (!pdfOnly || this.isPdfFile(file))) {
            await this.attachNativeFile(file);
          }
        }
      }
    }
  }

  private hasPdfDrag(dataTransfer: DataTransfer): boolean {
    if (dataTransfer.items && dataTransfer.items.length > 0) {
      return Array.from(dataTransfer.items).some(
        (item) => item.kind === "file" && item.type === "application/pdf"
      );
    }
    return Array.from(dataTransfer.types).includes("Files");
  }

  private hasPdfDrop(dataTransfer: DataTransfer): boolean {
    const obsidianPath = dataTransfer.getData("text/plain");
    if (obsidianPath) {
      const file = this.app.vault.getAbstractFileByPath(obsidianPath);
      if (file instanceof TFile && file.extension === "pdf") return true;
    }

    if (dataTransfer.files && dataTransfer.files.length > 0) {
      return Array.from(dataTransfer.files).some((file) => this.isPdfFile(file));
    }

    if (dataTransfer.items && dataTransfer.items.length > 0) {
      return Array.from(dataTransfer.items).some(
        (item) => item.kind === "file" && item.type === "application/pdf"
      );
    }

    return false;
  }

  private isPdfFile(file: File): boolean {
    const ext = file.name.split(".").pop()?.toLowerCase();
    return ext === "pdf" || file.type === "application/pdf";
  }

  private getExternalFilePathHints(dataTransfer: DataTransfer): string[] {
    const raw =
      dataTransfer.getData("text/uri-list") ||
      dataTransfer.getData("text/plain") ||
      "";

    return raw
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line.startsWith("file://"))
      .map((line) => {
        try {
          return decodeURIComponent(new URL(line).pathname);
        } catch {
          return "";
        }
      })
      .filter(Boolean);
  }

  // ── Paste handler ───────────────────────────────────────────

  private async handlePaste(e: ClipboardEvent): Promise<void> {
    if (!e.clipboardData) return;

    const items = Array.from(e.clipboardData.items);
    for (const item of items) {
      if (item.type.startsWith("image/")) {
        e.preventDefault();
        const blob = item.getAsFile();
        if (blob) {
          const base64 = await this.fileToBase64(blob);
          const ref: ContextRef = {
            type: "file",
            label: "🖼️ Pasted image",
            content: "",
            imageBase64: base64,
          };
          this.addContextRef(ref);
          new Notice("Pasted image attached");
        }
      }
    }
  }

  // ── Message Handling ────────────────────────────────────────

  private async handleSend(): Promise<void> {
    if (this.isGenerating) {
      this.stopThinkingTimer();
      this.plugin.llmClient.abort();
      return;
    }
    const content = this.inputEl.value.trim();
    if (!content) return;

    // Guard: Ollama requires a model name before sending
    if (this.plugin.settings.provider === "ollama" && !this.plugin.settings.model.trim()) {
      new Notice("Ollama: no model selected. Go to Settings → AI Provider and enter a model name (e.g. qwen2.5:7b).");
      return;
    }

    this.lastQueryTrace = null;
    const capturedActiveCtx = this.plugin.refreshActiveContext();
    const contextRefs = [
      ...this.buildAutoContextRefs(capturedActiveCtx),
      ...(await this.materializeContextRefs(this.pendingContextRefs)),
    ].filter(shouldIncludeContext);
    const userMsg: ChatMessage = {
      id: this.generateId(),
      role: "user",
      content,
      timestamp: Date.now(),
      contextRefs: contextRefs.length > 0 ? contextRefs : undefined,
    };
    this.messages.push(userMsg);
    this.pendingContextRefs = this.pendingContextRefs.filter((ref) => ref.isPinned);
    // Do NOT reset activeContextExcludedKey or pinned includeInPrompt here — user's
    // eye-off state should persist across sends (bug fix: preserve eye-off after send).
    this.renderContextChips();
    await this.persistCurrentSession();

    this.inputEl.value = "";
    this.inputEl.style.height = "auto";

    const assistantMsg: ChatMessage = {
      id: this.generateId(),
      role: "assistant",
      content: "",
      timestamp: Date.now(),
      isStreaming: true,
    };
    this.messages.push(assistantMsg);
    this.renderMessages();
    await this.persistCurrentSession();

    const gitCommand = detectGitSidechatCommand(
      content,
      userMsg.contextRefs || [],
      capturedActiveCtx
        ? {
            viewType: capturedActiveCtx.viewType,
            filePath: capturedActiveCtx.filePath,
            absolutePath: capturedActiveCtx.absolutePath,
          }
        : null
    );
    if (gitCommand) {
      assistantMsg.content = "Running Git command...";
      this.renderAssistantMessage(assistantMsg);
      try {
        assistantMsg.content = await this.runGitSidechatCommand(gitCommand);
      } catch (err) {
        assistantMsg.content = `❌ Git command failed: ${err instanceof Error ? err.message : String(err)}`;
      } finally {
        assistantMsg.isStreaming = false;
        this.renderAssistantMessage(assistantMsg);
        await this.persistCurrentSession();
      }
      return;
    }

    this.setPrepareStatus("Preparing context...");
    const llmMessages = await this.buildLLMMessages(capturedActiveCtx);
    this.prepareStatusText = "";

    this.isGenerating = true;
    setIcon(this.sendBtn, "square");
    this.sendBtn.setAttribute("aria-label", "Stop generating");

    try {
      await this.plugin.llmClient.streamChat(
        llmMessages,
        (chunk: StreamChunk) => {
          assistantMsg.content += chunk.text;
          if (chunk.done) {
            assistantMsg.isStreaming = false;
          }
          this.renderAssistantMessage(assistantMsg);
        }
      );
    } catch (err: unknown) {
      assistantMsg.isStreaming = false;
      const errMsg = err instanceof Error ? err.message : String(err);
      if (errMsg.includes("CLI authentication required")) {
        // Overwrite to remove confusing CLI stdout links/prompts that streamed before rejection
        assistantMsg.content = `\n\n❌ **Authentication Required**\n\n${errMsg}`;
      } else {
        assistantMsg.content += `\n\n❌ Error: ${errMsg}`;
      }
      this.renderAssistantMessage(assistantMsg);
    } finally {
      this.stopThinkingTimer();
      this.isGenerating = false;
      setIcon(this.sendBtn, "send");
      this.sendBtn.setAttribute("aria-label", "Send message");
      // Do not yank the view to the bottom when generation finishes; keep the
      // reader where they are unless they were already following along.
      this.renderMessages(false);
      // Immediately surface the diff for a just-completed edit (safe-gated: only
      // when the target is the active note or no note is focused). Runs once per
      // message here, NOT on history re-render, so old sessions never auto-open.
      await this.maybeAutoOpenDiff(assistantMsg);
      await this.persistCurrentSession();
    }

  }

  private async runGitSidechatCommand(command: GitSidechatCommand): Promise<string> {
    const client = this.getIncuratorClient();
    if (command.kind === "status") {
      const status = await client.getGitStatus();
      if (!status.ok) {
        return `❌ Git status unavailable: ${status.message || status.error || "unknown error"}`;
      }
      const repo = status.repo || {};
      const tree = status.working_tree || {};
      const warnings = status.warnings?.length
        ? `\n\nWarnings:\n${status.warnings.map((w) => `- ${w}`).join("\n")}`
        : "";
      return [
        "Git status",
        "",
        `- Branch: ${repo.branch || "unknown"}`,
        `- Upstream: ${repo.upstream || "none"}`,
        `- Ahead/behind: ${repo.ahead ?? 0}/${repo.behind ?? 0}`,
        `- Remote: ${repo.remote_url || "none"}`,
        `- Working tree: ${tree.clean ? "clean" : "dirty"}`,
        `- Staged/unstaged/untracked/conflicted: ${tree.staged ?? 0}/${tree.unstaged ?? 0}/${tree.untracked ?? 0}/${tree.conflicted ?? 0}`,
        warnings,
      ].filter(Boolean).join("\n");
    }

    if (command.kind === "push") {
      const result = await client.pushGitChanges();
      if (!result.ok) {
        return `❌ Git push blocked: ${result.message || result.error || "unknown error"}`;
      }
      const details = [result.stdout, result.stderr].filter((v) => v && v.trim()).join("\n").trim();
      return `✅ Pushed ${result.branch || "current branch"}${result.upstream ? ` to ${result.upstream}` : ""}.${details ? `\n\n${details}` : ""}`;
    }

    const history = await client.getGitHistory(command.filePath, command.queryText, 10);
    if (!history.ok) {
      return `❌ Git history unavailable: ${history.message || history.error || "unknown error"}`;
    }
    const commits = history.commits || [];
    if (commits.length === 0) {
      return `No Git history found for ${history.file_path || command.filePath}.`;
    }
    const mode = history.query_excerpt
      ? history.exact_match
        ? `matching "${history.query_excerpt}"`
        : `recent file history (no exact match for "${history.query_excerpt}")`
      : "recent file history";
    const lines = [`Git history for ${history.file_path || command.filePath} — ${mode}:`, ""];
    for (const commit of commits.slice(0, 5)) {
      lines.push(`- ${commit.hash.slice(0, 8)} ${commit.subject}${commit.date ? ` (${commit.date})` : ""}`);
      const patch = (commit.patch || "").trim();
      if (patch) {
        lines.push("```diff");
        lines.push(patch.slice(0, 1200));
        lines.push("```");
      }
    }
    return lines.join("\n");
  }

  private async buildLLMMessages(
    activeCtx: ReturnType<ObsidianAIAgent["refreshActiveContext"]>
  ): Promise<LLMMessage[]> {
    const llmMessages: LLMMessage[] = [];
    const lastUserMessage = [...this.messages]
      .reverse()
      .find((msg) => msg.role === "user");
    const hasExternalIncuratorMcp = this.plugin.settings.mcpServers.some(
      (s) => s.enabled && s.name.toLowerCase().includes("incurator")
    );
    let systemText = buildBaseSystemPrompt({
      hasExternalIncuratorMcp,
      planMode: this.plugin.settings.chatMode === "plan",
    });

    const rulesContext = this.loadCursorStyleRules();
    if (rulesContext) {
      systemText += `\n\n<cursor_style_rules>\n${rulesContext}\n</cursor_style_rules>`;
    }

    const continuity = this.buildProviderSharedContext(activeCtx);
    if (continuity) {
      systemText += `\n\n<provider_shared_context>\n${continuity}\n</provider_shared_context>`;
    }

    const lastUserHasPrimaryContext = hasPrimaryUserContext(lastUserMessage?.contextRefs);
    systemText += `\n\n<context_priority>\n${contextPriorityInstruction(lastUserHasPrimaryContext)}\n</context_priority>`;
    const editableRefs = includedContextRefs(lastUserMessage?.contextRefs).filter(
      (ref) =>
        ref.type === "line-range" &&
        Boolean(ref.filePath) &&
        typeof ref.lineStart === "number" &&
        typeof ref.lineEnd === "number"
    );
    const latestIsMarkdownEditRequest = this.isMarkdownEditRequest(lastUserMessage?.content || "");
    const openMarkdownEditTargets = latestIsMarkdownEditRequest
      ? this.buildOpenMarkdownEditTargetContext(activeCtx)
      : "";
    const editInstruction = editableSelectionInstruction(
      editableRefs.length > 0,
      Boolean(openMarkdownEditTargets)
    );
    if (editInstruction) {
      systemText += `\n\n<editable_selection>\n${editInstruction}\n</editable_selection>`;
    }
    if (openMarkdownEditTargets) {
      systemText += `\n\n<open_markdown_edit_targets>\n${openMarkdownEditTargets}\n</open_markdown_edit_targets>`;
    }

    const incuratorContext = await this.buildIncuratorProviderContext(
      activeCtx,
      lastUserMessage?.content || "",
      lastUserMessage?.contextRefs
    );
    if (incuratorContext) {
      systemText += `\n\n<obsidian_incurator_context>\n${incuratorContext}\n</obsidian_incurator_context>`;
    }

    if (activeCtx?.openTabs && activeCtx.openTabs.length > 0) {
      const tabLines = activeCtx.openTabs
        .map((tab) => {
          const marker = tab.isActive ? "*" : "-";
          const path = tab.filePath ? ` (${tab.filePath})` : "";
          return `${marker} ${tab.label} [${tab.viewType}]${path}`;
        })
        .join("\n");
      systemText += `\n\nOpen Obsidian tabs (* = active):\n${tabLines}`;

      const nonActiveMdTabs = activeCtx.openTabs.filter(
        (tab) => !tab.isActive && tab.viewType === "markdown" && tab.content
      );
      if (nonActiveMdTabs.length > 0) {
        const TAB_CONTENT_LIMIT = 8000;
        const tabContents = nonActiveMdTabs
          .map((tab) => {
            const truncated =
              tab.content!.length > TAB_CONTENT_LIMIT
                ? tab.content!.slice(0, TAB_CONTENT_LIMIT) +
                  `\n[...truncated at ${TAB_CONTENT_LIMIT} chars]`
                : tab.content!;
            return `### ${tab.label} (${tab.filePath})\n${truncated}`;
          })
          .join("\n\n---\n\n");
        systemText += `\n\n<open_tabs_content>\n${tabContents}\n</open_tabs_content>`;
      }

      const markdownOutlines = activeCtx.openTabs
        .filter((tab) => tab.viewType === "markdown" && tab.content)
        .map((tab) => {
          const outline = buildMarkdownOutline(tab.content || "");
          if (!outline) return "";
          const path = tab.filePath ? ` path="${escapeAttribute(tab.filePath)}"` : "";
          return `<markdown_outline document="${escapeAttribute(tab.label)}"${path}${tab.isActive ? ' active="true"' : ""}>\n${outline}\n</markdown_outline>`;
        })
        .filter(Boolean)
        .join("\n\n");
      if (markdownOutlines) {
        systemText += `\n\n<markdown_outlines>\n${markdownOutlines}\n</markdown_outlines>`;
      }
    }

    if (activeCtx?.filePath) {
      const displayPath = activeCtx.absolutePath || activeCtx.filePath;
      systemText += `\n\nCurrently active file: ${displayPath}`;
    }
    if (activeCtx?.viewType === "pdf" && activeCtx.pdfPage) {
      systemText += `\n\nThe user is viewing a PDF. Current page: ${activeCtx.pdfPage.pageNum}`;
    }

    llmMessages.push({ role: "system", content: this.truncateContext(systemText) });

    const activeContextParts = this.buildActiveContextParts(activeCtx);

    for (const msg of this.messages) {
      if (msg.role === "system") continue;

      const contentParts: LLMContentPart[] = [];
      const canSendImages = modelSupportsVision(
        this.plugin.getAvailableModels(),
        this.plugin.settings.provider,
        this.plugin.settings.model
      );

      if (msg === lastUserMessage) {
        contentParts.push(...activeContextParts);
      }

      if (msg.contextRefs && msg.contextRefs.length > 0) {
        for (const ref of includedContextRefs(msg.contextRefs)) {
          if (ref.sourceViewType === "auto") continue;
          if (ref.content || ref.imageBase64) {
            let textToPush = `[${contextPromptLabel(ref)}]\n`;
            if (ref.content) {
              if (isPrimaryUserContext(ref)) {
                textToPush += `<primary_focus_selection>\n${ref.content}\n</primary_focus_selection>`;
                // Follow any cross-reference (crop caption or dragged "see §X")
                // to the target page/section so the model explains the referent,
                // not the visible page. (report items 3/4/6/7)
                const resolvedBlock = resolveSelectionReferencesBlock(ref.content, {
                  outline: ref.outline,
                  windowPages: ref.windowPages,
                  pageNum: ref.pageNum,
                  pageLabels: ref.pageLabels,
                });
                if (resolvedBlock) textToPush += `\n${resolvedBlock}`;
              } else {
                textToPush += ref.content;
              }
            } else if (ref.imageBase64 && isPrimaryUserContext(ref)) {
              // Image-only primary focus (e.g. a scanned-PDF crop with no
              // selectable text, or a dragged image): mark it explicitly so the
              // model treats the attached image as the core subject instead of
              // burying it under background page text.
              textToPush +=
                "<primary_focus_selection>\nThe user cropped/attached the image shown below as the primary focus of this request. Base your answer on the visual content of that image, not the surrounding background context.\n</primary_focus_selection>";
            } else {
              textToPush += "(Image context attached below.)";
            }
            contentParts.push({
              type: "text",
              text: textToPush,
            });
          }
          if (ref.imageBase64 && canSendImages) {
            contentParts.push({
              type: "image",
              mimeType: "image/png",
              data: ref.imageBase64,
            });
          } else if (ref.imageBase64 && !canSendImages) {
            contentParts.push({
              type: "text",
              text: `[Image context unavailable]\n${ref.label} is an attached image/crop, but the selected model does not support vision. Tell the user to switch to a vision-capable model or attach textual context if image details are required.`,
            });
          }
        }
      }

      const textContent =
        msg === lastUserMessage
          ? wrapLatestUserMessageForLanguageBridge(msg.content, detectLanguage(msg.content))
          : msg.content;
      contentParts.push({ type: "text", text: textContent });

      llmMessages.push({
        role: msg.role as "user" | "assistant",
        content: contentParts.length === 1 ? textContent : contentParts,
      });
    }

    return llmMessages;
  }

  private buildActiveContextParts(
    activeCtx: ReturnType<ObsidianAIAgent["refreshActiveContext"]>
  ): LLMContentPart[] {
    const parts: LLMContentPart[] = [];
    const canSendImages = modelSupportsVision(
      this.plugin.getAvailableModels(),
      this.plugin.settings.provider,
      this.plugin.settings.model
    );

    for (const ref of this.buildAutoContextRefs(activeCtx)) {
      if (!shouldIncludeContext(ref)) continue;
      if (ref.content) {
        parts.push({
          type: "text",
          text: `[${contextPromptLabel(ref)}]\n${ref.content}`,
        });
      }
      if (ref.imageBase64 && canSendImages) {
        parts.push({ type: "image", mimeType: "image/png", data: ref.imageBase64 });
      }
    }

    return parts;
  }

  private isMarkdownEditRequest(content: string): boolean {
    const text = content.toLowerCase();
    const editIntent =
      /바꿔|고쳐|수정|변경|치환|교체|통일|링크|경로|유사|비슷|전체|모든|replace|change|edit|fix|rewrite|rename|relink|path|link|all|similar|every/.test(text);
    const markdownTarget =
      /md|markdown|마크다운|파일|note|노트|html|img|image|이미지|링크|경로|path|link/.test(text);
    return editIntent && markdownTarget;
  }

  private buildOpenMarkdownEditTargetContext(
    activeCtx: ReturnType<ObsidianAIAgent["refreshActiveContext"]>
  ): string {
    const tabs = activeCtx?.openTabs ?? [];
    const markdownTabs = tabs.filter((tab) => tab.viewType === "markdown" && tab.filePath && tab.content);
    if (markdownTabs.length === 0) return "";

    const TARGET_LIMIT = 50000;
    let remaining = TARGET_LIMIT;
    const sections: string[] = [];
    for (const tab of markdownTabs) {
      if (remaining <= 0) break;
      const content = tab.content || "";
      const selected = tab.selectedText?.trim()
        ? `\nSelected clue in this file:\n${tab.selectedText.trim()}\n`
        : "";
      const header =
        `### ${tab.label} (${tab.filePath})${tab.isActive ? " [active]" : ""}\n` +
        "Use this full file content to find every similar occurrence before proposing ai-agent-edit blocks.\n" +
        selected +
        "Full Markdown file content:\n";
      const sliceLimit = Math.max(0, remaining - header.length - 32);
      const body =
        content.length > sliceLimit
          ? content.slice(0, sliceLimit) + `\n[...truncated at ${sliceLimit} chars]`
          : content;
      const section = `${header}${body}`;
      sections.push(section);
      remaining -= section.length;
    }
    return sections.join("\n\n---\n\n");
  }

  private buildProviderSharedContext(
    activeCtx: ReturnType<ObsidianAIAgent["refreshActiveContext"]>
  ): string {
    const lines: string[] = [
      "This chat session is provider-independent. If the user switches between Antigravity, Claude, Codex, Ollama, and DeepSeek, preserve the same task state, conversation decisions, pinned context, open tabs, and edit-review workflow.",
      `Current provider/model: ${this.plugin.settings.provider} / ${this.plugin.settings.model}`,
    ];

    const activeSession = this.plugin.sessionData.chatSessions.find(
      (session) => session.id === this.plugin.sessionData.activeChatSessionId
    );
    if (activeSession) {
      lines.push(`Active chat: ${activeSession.title}`);
    }

    const pinnedRefs = this.pendingContextRefs.filter((ref) => ref.isPinned && shouldIncludeContext(ref));
    if (pinnedRefs.length > 0) {
      lines.push(`Pinned context: ${pinnedRefs.map((ref) => ref.label).join(", ")}`);
    }

    const autoRefs = includedContextRefs(this.buildAutoContextRefs(activeCtx));
    if (autoRefs.length > 0) {
      lines.push(`Visible context: ${autoRefs.map((ref) => ref.label).join(", ")}`);
    } else if (this.cachedAutoContextRefs.length > 0) {
      lines.push(
        `Recently visible context: ${includedContextRefs(this.cachedAutoContextRefs)
          .map((ref) => ref.label)
          .join(", ")}`
      );
    }

    const recentMessages = this.messages
      .filter((msg) => msg.role === "user" || msg.role === "assistant")
      .slice(-CONTINUITY_MESSAGE_LIMIT);
    if (recentMessages.length > 0) {
      lines.push("Recent session flow:");
      for (const msg of recentMessages) {
        const text = this.stripThinkingBlocks(msg.content)
          .replace(/\s+/g, " ")
          .trim()
          .slice(0, 700);
        if (text) {
          lines.push(`- ${msg.role}: ${text}`);
        }
      }
    }

    return lines.join("\n");
  }

  private async buildIncuratorProviderContext(
    activeCtx: ReturnType<ObsidianAIAgent["refreshActiveContext"]>,
    query: string,
    userContextRefs: ContextRef[] | undefined = undefined
  ): Promise<string> {
    if (this.plugin.settings.incuratorEnabled === false) return "";

    const sections: string[] = [];
    const client = this.getIncuratorClient();
    const pdfSourceStatuses: IncuratorSourceStatus[] = [];
    const pdfTabs = (activeCtx?.openTabs ?? []).filter(
      (tab) =>
        (tab.viewType === "pdf" || tab.viewType === EXTERNAL_PDF_VIEW_TYPE) &&
        tab.pdfPage
    );

    for (const tab of pdfTabs.slice(0, 3)) {
      const pdf = tab.pdfPage;
      if (!pdf) continue;
      const hasLocalViewerContext =
        Boolean(pdf.text?.trim()) ||
        Boolean(pdf.windowPages?.some((page) => page.text.trim())) ||
        Boolean(pdf.imageBase64);
      const useBackendPdfContext = shouldUseBackendPdfContext({
        query,
        userContextRefs,
        hasLocalViewerContext,
      });

      const sourcePath =
        this.toAbsolutePath(pdf.filePath) ||
        this.toAbsolutePath(tab.filePath) ||
        (tab.isActive ? activeCtx.absolutePath : undefined);

      const docLabel = tab.label.replace(/ p\.\d+$/, "");
      const statusRef: ContextRef = {
        type: "pdf-page",
        label: tab.label,
        content: pdf.text || "",
        filePath: pdf.filePath || tab.filePath,
        fileHash: pdf.fileHash,
        pageNum: pdf.pageNum,
        zoteroAttachmentKey: pdf.zoteroAttachmentKey,
      };
      let sourceStatus = sourcePath ? this.incuratorStatusByPath.get(sourcePath) : undefined;
      if (useBackendPdfContext && client.available && (sourcePath || pdf.fileHash || pdf.zoteroAttachmentKey)) {
        sourceStatus = await this.ensureIncuratorStatusForRef(statusRef);
      }
      if (sourceStatus) {
        if (tab.isActive) pdfSourceStatuses.push(sourceStatus);
        sections.push(
          `<incurator_source_status document="${escapeAttribute(tab.label)}" state="${sourceStatus.state}" l1="${sourceStatus.l1Complete === true}" l3="${sourceStatus.l3Complete === true}">\n${escapeAttribute(sourceStatus.message || "")}\n</incurator_source_status>`
        );
      }

      this.setPrepareStatus(
        useBackendPdfContext
          ? `Assembling PDF context — ${docLabel}...`
          : `Using local PDF viewer context — ${docLabel}...`
      );

      // Single backend call: replaces getPdfWindow + getDocumentOutline (both of
      // which silently returned [] because the tools never existed in the backend).
      // Works for tracked and untracked PDFs. Falls back to PDF.js cached data
      // when the backend is unavailable.
      let backendCtx: Awaited<ReturnType<typeof client.getPdfContext>> = null;
      if (useBackendPdfContext && client.available && (sourcePath || pdf.fileHash || pdf.zoteroAttachmentKey)) {
        const startedAt = performance.now();
        backendCtx = await client.getPdfContext({
          filePath: sourcePath,
          sourceId: sourceStatus?.sourceId,
          fileHash: pdf.fileHash,
          zoteroAttachmentKey: pdf.zoteroAttachmentKey,
          query: query.trim() || undefined,
          pageNum: pdf.pageNum,
          radius: this.plugin.settings.pdfWindowRadius,
          maxPages: this.plugin.settings.pdfRagTopK || 8,
        });
        this.logContextTiming("backend_pdf_context", startedAt, docLabel);
      }

      const windowPages = useBackendPdfContext
        ? backendCtx?.pages ?? pdf.windowPages ?? []
        : pdf.windowPages ?? [];
      if (windowPages.length > 0) {
        const contextSource = useBackendPdfContext
          ? backendCtx?.contextSource ?? "ephemeral_parse"
          : "local_viewer";
        const degradedReason = useBackendPdfContext ? backendCtx?.degradedReason : undefined;
        sections.push(
          `<pdf_window document="${escapeAttribute(tab.label)}" current_page="${pdf.pageNum}" context_source="${contextSource}"${degradedReason ? ` degraded_reason="${escapeAttribute(degradedReason)}"` : ""}>\n${formatPdfWindow(windowPages)}\n</pdf_window>`
        );
      }

      if (this.plugin.settings.pdfOutlineEnabled) {
        let outline = backendCtx?.outline ?? pdf.outline ?? [];
        if (outline.length > 0) {
          sections.push(
            `<document_outline document="${escapeAttribute(tab.label)}">\n${formatOutline(outline)}\n</document_outline>`
          );
        }
      }

      // RAG hits use the semantic search index — only meaningful for tracked sources.
      if (useBackendPdfContext && this.plugin.settings.pdfRagEnabled && query.trim()) {
        const canRag = backendCtx?.sourceTracked ?? false;
        if (canRag) {
          this.setPrepareStatus(`Searching PDF pages — ${docLabel}...`);
          const ragHits =
            pdf.ragHits ||
            (client.available
              ? await this.timedContextCall(
                  "backend_pdf_rag",
                  docLabel,
                  () => client.getPdfRagHits({
                    query,
                    sourcePath,
                    documentId: pdf.documentId,
                    topK: this.plugin.settings.pdfRagTopK,
                  })
                )
              : []);
          if (ragHits.length > 0) {
            sections.push(
              `<pdf_rag_hits document="${escapeAttribute(tab.label)}" query="${escapeAttribute(query.slice(0, 120))}">\n${formatRagHits(ragHits, this.plugin.settings.pdfRagTopK)}\n</pdf_rag_hits>`
            );
          }
        } else if (!client.available && pdf.ragHits?.length) {
          // Offline fallback: use pre-fetched hits if available
          sections.push(
            `<pdf_rag_hits document="${escapeAttribute(tab.label)}" query="${escapeAttribute(query.slice(0, 120))}">\n${formatRagHits(pdf.ragHits, this.plugin.settings.pdfRagTopK)}\n</pdf_rag_hits>`
          );
        }
      }

      if (backendCtx?.isEmptyPdf) {
        sections.push(
          `<pdf_text_quality document="${escapeAttribute(tab.label)}" page="${pdf.pageNum}">\nscore=0; scanned_like=true; source=backend; reason=image-only PDF, no text extracted\n</pdf_text_quality>`
        );
      } else if (pdf.textQuality) {
        const qualitySource = backendCtx ? "backend" : pdf.textQuality.source;
        sections.push(
          `<pdf_text_quality document="${escapeAttribute(tab.label)}" page="${pdf.pageNum}">\nscore=${pdf.textQuality.score}; scanned_like=${pdf.textQuality.isScannedLike}; source=${qualitySource}${pdf.textQuality.reason ? `; reason=${pdf.textQuality.reason}` : ""}\n</pdf_text_quality>`
        );
      }
    }

    if (client.available && query.trim()) {
      const wsPath = (this.app.vault.adapter as any).getBasePath();

      if (wsPath) {
        sections.push(
          `<incurator_workspace path="${escapeAttribute(wsPath)}">\n` +
          `This is the active vault path for Incurator backend commands and external-agent MCP tools.\n` +
          `</incurator_workspace>`
        );
      }

      // Run the knowledge-graph query for both in-workspace and plain vault
      // chat. When wsPath is empty the backend resolves workspace_id=default,
      // so a conversational chat never binds an unrelated workspace.
      const pdfFocused = pdfTabs.some((tab) => tab.isActive);
      if (shouldRunCuratorDomainQuery({ query, userContextRefs, pdfFocused, pdfSourceStatuses })) {
        this.setPrepareStatus("Querying Incurator knowledge graph...");
        const language = inferQueryLanguageMetadata(query);
        const queryResult = await this.timedContextCall(
          "curator_query",
          wsPath || "default",
          () => client.curatorQuery(query, {
            workspacePath: wsPath,
            inputLanguage: language.inputLanguage,
            englishQuery: language.englishQuery,
            finalOutputLanguage: language.finalOutputLanguage,
          })
        );
        if (queryResult.ok) {
          sections.push(formatCuratorQueryResult(queryResult, query));
          if (queryResult.trace || queryResult.trace_id) {
            this.lastQueryTrace = queryResult;
          }
        }
      }
    }

    return sections.join("\n\n");
  }

  private async timedContextCall<T>(
    label: string,
    subject: string,
    fn: () => Promise<T>
  ): Promise<T> {
    const startedAt = performance.now();
    const result = await fn();
    this.logContextTiming(label, startedAt, subject);
    return result;
  }

  private logContextTiming(label: string, startedAt: number, subject: string): void {
    const elapsedMs = Math.round(performance.now() - startedAt);
    // eslint-disable-next-line no-console
    console.debug(`[Incurator] ${label} ${elapsedMs}ms`, subject);
  }

  private loadCursorStyleRules(): string {
    const basePath = (this.app.vault.adapter as unknown as { getBasePath?: () => string })
      .getBasePath?.();
    if (!basePath) return "";

    const ruleFiles: string[] = [];
    const legacyRules = join(basePath, ".cursorrules");
    if (existsSync(legacyRules)) {
      ruleFiles.push(legacyRules);
    }

    const rulesDir = join(basePath, ".cursor", "rules");
    if (existsSync(rulesDir)) {
      for (const entry of readdirSync(rulesDir)) {
        const fullPath = join(rulesDir, entry);
        if (!statSync(fullPath).isFile()) continue;
        if (!/\.(mdc|md|txt)$/i.test(entry)) continue;
        ruleFiles.push(fullPath);
      }
    }

    const sections: string[] = [];
    let remaining = RULES_CONTEXT_LIMIT;
    for (const filePath of ruleFiles) {
      if (remaining <= 0) break;
      try {
        const content = readFileSync(filePath, "utf-8").trim();
        if (!content) continue;
        const relative = filePath.startsWith(basePath)
          ? filePath.slice(basePath.length + 1)
          : filePath;
        const section = `### ${relative}\n${content.slice(0, remaining)}`;
        sections.push(section);
        remaining -= section.length;
      } catch {
        // Ignore unreadable rule files; chat should still work.
      }
    }

    return sections.join("\n\n---\n\n");
  }

  private stripThinkingBlocks(content: string): string {
    return content
      .replace(/<thinking>[\s\S]*?<\/thinking>/gi, "")
      .replace(/<thought>[\s\S]*?<\/thought>/gi, "")
      .replace(/<details class="ai-agent-thought-block"[\s\S]*?<\/details>/gi, "");
  }

  private truncateContext(content: string): string {
    const modelOption = getModelOption(
      this.plugin.getAvailableModels(),
      this.plugin.settings.provider,
      this.plugin.settings.model
    );
    const limit = modelOption?.contextWindow ?? this.plugin.settings.maxContextLength;
    return truncateToLength(content, limit);
  }

  private getAutoContextKey(ref: ContextRef): string {
    return `${ref.type}:${ref.filePath || ref.label.replace(/ p\.\d+$/, "")}`;
  }

  private buildAutoContextRefs(
    activeCtx: ReturnType<ObsidianAIAgent["refreshActiveContext"]>
  ): ContextRef[] {
    if (!activeCtx?.openTabs) return [];

    const refs: ContextRef[] = [];
    const seen = new Set<string>();

    for (const tab of activeCtx.openTabs) {
      let ref: ContextRef | null = null;
      if (tab.viewType === "markdown" && tab.filePath) {
        let finalContent = tab.content ? this.truncateContext(tab.content) : "";
        if (tab.selectedText && tab.selectedText.trim()) {
          const sel = tab.selectedText;
          if (finalContent.includes(sel)) {
            finalContent = finalContent.replace(sel, `\n<primary_focus_selection>\n${sel}\n</primary_focus_selection>\n`);
            finalContent = `<background_reference_only>\n${finalContent}\n</background_reference_only>`;
          } else {
            finalContent = `\n<primary_focus_selection>\n${sel}\n</primary_focus_selection>\n\n<background_reference_only>\n${finalContent}\n</background_reference_only>`;
          }
        } else {
          finalContent = `<background_reference_only>\n${finalContent}\n</background_reference_only>`;
        }
        ref = {
          type: "file",
          label: tab.filePath.split("/").pop() || tab.label,
          content: this.truncateContext(finalContent),
          filePath: tab.filePath,
          sourceViewType: "auto",
        };
      } else if ((tab.viewType === "pdf" || tab.viewType === EXTERNAL_PDF_VIEW_TYPE) && tab.pdfPage) {
        let finalContent = tab.pdfPage.text
          ? this.truncateContext(tab.pdfPage.text)
          : "(No extractable text on this page. If you need visual information, please attach the image manually.)";
        
        const hasTextSelection = tab.selectedText && tab.selectedText.trim();
        const hasImageSelection = Boolean(tab.pdfPage.selectedImageBase64 || (tab.pdfPage.isScannedLike && tab.pdfPage.imageBase64));

        if (hasTextSelection) {
          const sel = tab.selectedText || "";
          if (finalContent.includes(sel)) {
            finalContent = finalContent.replace(sel, `\n<primary_focus_selection>\n${sel}\n</primary_focus_selection>\n`);
            finalContent = `<background_reference_only>\n${finalContent}\n</background_reference_only>`;
          } else {
            finalContent = `\n<primary_focus_selection>\n${sel}\n</primary_focus_selection>\n\n<background_reference_only>\n${finalContent}\n</background_reference_only>`;
          }
        } else if (hasImageSelection) {
          finalContent = `<background_reference_only>\n${finalContent}\n</background_reference_only>`;
        } else {
          // Even without any selection, if this is an auto-injected background tab,
          // wrap it to ensure it doesn't overpower explicit user queries or explicit pinned images.
          finalContent = `<background_reference_only>\n${finalContent}\n</background_reference_only>`;
        }
        
        ref = {
          type: "pdf-page",
          label: `${tab.label} p.${tab.pdfPage.pageNum}`,
          content: finalContent,
          filePath: tab.filePath,
          fileHash: tab.pdfPage.fileHash,
          pageNum: tab.pdfPage.pageNum,
          pageLabels: tab.pdfPage.pageLabels,
          zoteroAttachmentKey: tab.pdfPage.zoteroAttachmentKey,
          windowPages: tab.pdfPage.windowPages,
          outline: tab.pdfPage.outline,
          ragHits: tab.pdfPage.ragHits,
          textQuality: tab.pdfPage.textQuality,
          isScannedLike: tab.pdfPage.isScannedLike,
          sourceViewType: "auto",
          // Only send the full page image if the PDF is scanned (vision fallback).
          // Otherwise, only send an explicitly cropped image (if any).
          imageBase64: tab.pdfPage.selectedImageBase64 || (tab.pdfPage.isScannedLike ? tab.pdfPage.imageBase64 : undefined),
        };
      }

      if (!ref) continue;
      const key = this.getAutoContextKey(ref);
      if (seen.has(key)) continue;
      if (this.activeContextExcludedKeys.has(key)) ref.includeInPrompt = false;
      seen.add(key);
      refs.push(ref);
    }

    return refs;
  }

  private async createPinnedFileRef(
    file: TFile,
    viewType: string
  ): Promise<ContextRef> {
    const content = await this.readCurrentVaultFileContent(file);
    return {
      type: "file",
      label: file.name,
      content: this.truncateContext(content),
      filePath: file.path,
      isPinned: true,
      sourceViewType: viewType,
    };
  }

  private createPinnedPdfRef(tab: {
    label: string;
    viewType: string;
    filePath?: string;
  }): ContextRef | null {
    let pdfCtx: PdfPageContext | null = null;

    if (tab.viewType === EXTERNAL_PDF_VIEW_TYPE) {
      for (const leaf of this.app.workspace.getLeavesOfType(EXTERNAL_PDF_VIEW_TYPE)) {
        const view = leaf.view as ExternalPdfView;
        if (view.getDisplayText() === tab.label) {
          pdfCtx = withVisionFallback(
            view.getActivePdfContext(this.plugin.settings.pdfCaptureMode),
            this.plugin.settings.pdfCaptureMode,
            this.plugin.settings.pdfVisionFallback,
            () => view.getActivePdfContext("image")?.imageBase64
          );
          break;
        }
      }
    } else if (tab.filePath) {
      for (const leaf of this.app.workspace.getLeavesOfType("pdf")) {
        const view = leaf.view as unknown as { file?: TFile };
        if (view.file?.path === tab.filePath) {
          pdfCtx = withVisionFallback(
            getPdfContext(leaf, this.plugin.settings.pdfCaptureMode),
            this.plugin.settings.pdfCaptureMode,
            this.plugin.settings.pdfVisionFallback,
            () => getPdfContext(leaf, "image")?.imageBase64
          );
          break;
        }
      }
    }

    if (!pdfCtx) return null;
    return {
      type: "pdf-page",
      label: `${tab.label} p.${pdfCtx.pageNum}`,
      content: pdfCtx.text,
      imageBase64: pdfCtx.imageBase64,
      filePath: tab.filePath,
      pageNum: pdfCtx.pageNum,
      pageLabels: pdfCtx.pageLabels,
      isPinned: true,
      sourceViewType: tab.viewType,
    };
  }

  private async materializeContextRefs(refs: ContextRef[]): Promise<ContextRef[]> {
    const materialized: ContextRef[] = [];
    for (const ref of refs) {
      materialized.push(ref.isPinned ? await this.refreshPinnedContextRef(ref) : { ...ref });
    }
    return materialized;
  }

  private async refreshPinnedContextRef(ref: ContextRef): Promise<ContextRef> {
    if (ref.type === "file" && ref.filePath) {
      const vaultFile = this.app.vault.getAbstractFileByPath(ref.filePath);
      if (vaultFile instanceof TFile) {
        return {
          ...ref,
          content: this.truncateContext(await this.readCurrentVaultFileContent(vaultFile)),
        };
      }
    }

    if (ref.type === "pdf-page") {
      const pdfCtx = this.capturePinnedPdfContext(ref);
      if (pdfCtx) {
        return {
          ...ref,
          label: ref.label.replace(/ p\.\d+$/, ` p.${pdfCtx.pageNum}`),
          content: pdfCtx.text,
          imageBase64: pdfCtx.imageBase64,
          pageNum: pdfCtx.pageNum,
          pageLabels: pdfCtx.pageLabels,
        };
      }
    }

    return { ...ref };
  }

  private async readCurrentVaultFileContent(file: TFile): Promise<string> {
    for (const leaf of this.app.workspace.getLeavesOfType("markdown")) {
      const view = leaf.view as unknown as {
        file?: TFile;
        editor?: { getValue(): string };
      };
      if (view.file?.path === file.path && view.editor) {
        return view.editor.getValue();
      }
    }
    return await this.app.vault.cachedRead(file);
  }

  private capturePinnedPdfContext(ref: ContextRef): PdfPageContext | null {
    const baseLabel = ref.label.replace(/ p\.\d+$/, "");

    for (const leaf of this.app.workspace.getLeavesOfType(EXTERNAL_PDF_VIEW_TYPE)) {
      const view = leaf.view as ExternalPdfView;
      if (view.getDisplayText() === baseLabel) {
        return withVisionFallback(
          view.getActivePdfContext(this.plugin.settings.pdfCaptureMode),
          this.plugin.settings.pdfCaptureMode,
          this.plugin.settings.pdfVisionFallback,
          () => view.getActivePdfContext("image")?.imageBase64
        );
      }
    }

    if (ref.filePath) {
      for (const leaf of this.app.workspace.getLeavesOfType("pdf")) {
        const view = leaf.view as unknown as { file?: TFile };
        if (view.file?.path === ref.filePath) {
          return withVisionFallback(
            getPdfContext(leaf, this.plugin.settings.pdfCaptureMode),
            this.plugin.settings.pdfCaptureMode,
            this.plugin.settings.pdfVisionFallback,
            () => getPdfContext(leaf, "image")?.imageBase64
          );
        }
      }
    }

    return null;
  }

  private getIncuratorClient(): IncuratorClient {
    if (!this.incuratorClient) {
      this.incuratorClient = new IncuratorClient(
        this.plugin.settings,
        this.plugin.manifest.version,
        this.plugin.runBackendJsonCommand.bind(this.plugin)
      );
      // Run version check asynchronously
      this.incuratorClient.checkBackendVersion();
    }
    return this.incuratorClient;
  }

  private toAbsolutePath(vaultRelPath: string | undefined): string | undefined {
    if (!vaultRelPath) return undefined;
    if (vaultRelPath.startsWith("/")) return vaultRelPath;
    const adapter = this.app.vault.adapter as unknown as {
      getFullPath?: (p: string) => string;
      basePath?: string;
      getBasePath?: () => string;
    };
    if (typeof adapter.getFullPath === "function") {
      return adapter.getFullPath(vaultRelPath);
    }
    const basePath = adapter.basePath || adapter.getBasePath?.();
    if (basePath) return `${basePath}/${vaultRelPath}`;
    return vaultRelPath;
  }

  private getPdfRefSourcePath(ref: ContextRef): string | undefined {
    return ref.backendStatus?.sourcePath || this.toAbsolutePath(ref.filePath);
  }

  private async resolvePdfRefSourcePath(ref: ContextRef, status?: IncuratorSourceStatus): Promise<string | undefined> {
    const direct = this.getPdfRefSourcePath(ref) || status?.sourcePath || status?.currentPath;
    if (direct) return direct;
    if (!ref.zoteroAttachmentKey) return undefined;
    const resolved = await this.getIncuratorClient().resolveZoteroPdf(ref.zoteroAttachmentKey);
    if (resolved.ok && resolved.path) return resolved.path;
    this.plugin.openZoteroRepairModal({ attachmentKey: ref.zoteroAttachmentKey, resolution: resolved });
    new Notice(`Zotero PDF unavailable: ${resolved.error || resolved.state || "backend could not resolve attachment"}`);
    return undefined;
  }

  private async getPdfRefFileHash(ref: ContextRef): Promise<string | undefined> {
    if (ref.fileHash) return ref.fileHash;
    const sourcePath = this.getPdfRefSourcePath(ref);
    if (!sourcePath) return undefined;
    const cached = this.fileHashByPath.get(sourcePath);
    if (cached) return cached;
    try {
      const hash = await hashFileSha256(sourcePath);
      this.fileHashByPath.set(sourcePath, hash);
      ref.fileHash = hash;
      return hash;
    } catch {
      return undefined;
    }
  }

  private async ensureIncuratorStatusForRef(ref: ContextRef): Promise<IncuratorSourceStatus> {
    const sourcePath = this.getPdfRefSourcePath(ref);
    const fileHash = await this.getPdfRefFileHash(ref);
    if (!sourcePath && !fileHash && ref.zoteroAttachmentKey) {
      const status: IncuratorSourceStatus = {
        state: "untracked",
        message: "Zotero PDF is available by attachment key; add it to Incurator to register this device's resolved path.",
        updatedAt: Date.now(),
      };
      ref.backendStatus = status;
      return status;
    }
    const status = await this.getIncuratorClient().getSourceStatus({ sourcePath, fileHash });
    if (sourcePath) this.incuratorStatusByPath.set(sourcePath, status);
    ref.backendStatus = status;
    return status;
  }

  private renderIncuratorStatusBadge(
    chip: HTMLElement,
    ref: ContextRef
  ): void {
    if (ref.type !== "pdf-page" || this.plugin.settings.incuratorEnabled === false) return;

    const sourcePath = this.getPdfRefSourcePath(ref);
    const cached = sourcePath ? this.incuratorStatusByPath.get(sourcePath) : ref.backendStatus;
    const badge = chip.createSpan("ai-agent-context-chip-status");
    this.updateIncuratorStatusBadge(badge, cached || { state: sourcePath ? "unknown" : "untracked" });

    badge.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const fallback: IncuratorSourceStatus = { state: "unknown", sourcePath };
      const latest =
        (sourcePath ? this.incuratorStatusByPath.get(sourcePath) : undefined) ||
        ref.backendStatus ||
        cached ||
        fallback;
      this.onIncuratorStatusClick(ref, latest);
    });

    if (sourcePath) {
      this.refreshIncuratorStatus(ref, badge);
    }
  }

  private updateIncuratorStatusBadge(
    badge: HTMLElement,
    status: IncuratorSourceStatus
  ): void {
    badge.empty();
    badge.setText(this.getIncuratorStatusLabel(status));
    badge.dataset.state = status.state;
    badge.toggleClass("is-added", isAddedState(status.state));
    badge.setAttribute("title", status.message || `Incurator: ${status.state}`);
  }

  private getIncuratorStatusLabel(status: IncuratorSourceStatus): string {
    switch (status.state) {
      case "l4_ready":
      case "l3_ready":
      case "l2_ready":
      case "l1_ready":
        return "Added";
      case "queued":
        return "Queued";
      case "running":
        return "Building...";
      case "stale":
        return "stale";
      case "missing":
        return "missing";
      case "moved":
        return "moved";
      case "hash_drift":
        return "changed";
      case "moved_and_hash_drift":
        return "moved+changed";
      case "error":
        return "Error";
      case "untracked":
        return "Add source";
      default:
        return "Check source";
    }
  }

  private async refreshIncuratorStatus(
    ref: ContextRef,
    badge?: HTMLElement
  ): Promise<void> {
    const sourcePath = this.getPdfRefSourcePath(ref);
    if (!sourcePath || this.incuratorStatusInFlight.has(sourcePath)) return;

    this.incuratorStatusInFlight.add(sourcePath);
    try {
      const status = await this.ensureIncuratorStatusForRef(ref);
      this.incuratorStatusByPath.set(sourcePath, status);
      ref.backendStatus = status;
      if (badge?.isConnected) {
        this.updateIncuratorStatusBadge(badge, status);
      }
      if (
        this.plugin.settings.incuratorStatusPolling &&
        (status.state === "queued" || status.state === "running")
      ) {
        window.setTimeout(() => {
          if (badge?.isConnected) this.refreshIncuratorStatus(ref, badge);
        }, 5000);
      }
    } finally {
      this.incuratorStatusInFlight.delete(sourcePath);
    }
  }

  private async onIncuratorStatusClick(
    ref: ContextRef,
    status: IncuratorSourceStatus
  ): Promise<void> {
    // A built source's "Added" badge is inert — never fall through to
    // re-ingest (PLUGIN_SCHEMA §4.1.1).
    if (isAddedState(status.state)) return;
    const sourcePath = this.getPdfRefSourcePath(ref) || status.sourcePath || status.currentPath;
    const statusKey = sourcePath || (ref.zoteroAttachmentKey ? `zotero:${ref.zoteroAttachmentKey}` : "");
    if (!sourcePath && !ref.zoteroAttachmentKey) {
      new Notice("This PDF does not expose a filesystem path and backend resolution did not find one.");
      return;
    }

    if (status.state === "queued" || status.state === "running") {
      new Notice("Incurator build is queued or running. Open Dashboard > Jobs to run or monitor it.");
      return;
    }

    if (status.requiresRebind || status.state === "moved" || status.state === "missing") {
      const rebindSourcePath = sourcePath || await this.resolvePdfRefSourcePath(ref, status);
      if (!rebindSourcePath) return;
      if (!status.candidatePath) {
        new Notice("Source is missing. No candidate path was found in configured external roots.");
        return;
      }
      const approved = window.confirm(
        `Rebind this Incurator source?\n\nFrom:\n${status.currentPath || rebindSourcePath}\n\nTo:\n${status.candidatePath}`
      );
      if (!approved) return;
      new Notice("Rebinding moved Incurator source...");
      const nextStatus = await this.getIncuratorClient().rebindSource({
        sourceId: status.sourceId,
        sourcePath: rebindSourcePath,
        newPath: status.candidatePath,
        apply: true,
      });
      this.incuratorStatusByPath.set(statusKey || rebindSourcePath, nextStatus);
      ref.backendStatus = nextStatus;
      this.renderContextChips();
      if (nextStatus.state === "error" || nextStatus.state === "unknown") {
        new Notice(`Zotero reference registration failed: ${nextStatus.message || "backend did not return a usable source status"}`);
      } else {
        new Notice("Zotero PDF registered as an external reference.");
      }
      return;
    }

    // Zotero-managed PDFs: skip modal, auto-register as reference
    const isZoteroPdf = ref.zoteroAttachmentKey ||
      this.app.workspace.getLeavesOfType("ai-agent-external-pdf")
        .some(leaf => (leaf.view.getState() as any)?.zoteroAttachmentKey &&
                      (leaf.view.getState() as any)?.path === sourcePath);
    if (isZoteroPdf) {
      const pendingStatus: IncuratorSourceStatus = {
        state: "running",
        sourcePath,
        message: "Adding Zotero PDF as an Incurator reference source...",
      };
      if (statusKey) this.incuratorStatusByPath.set(statusKey, pendingStatus);
      ref.backendStatus = pendingStatus;
      this.renderContextChips();
      new Notice("Adding Zotero PDF as an Incurator reference source...");
      const nextStatus = await this.getIncuratorClient().ingestPdf({
        sourcePath,
        zoteroAttachmentKey: ref.zoteroAttachmentKey,
        displayName: ref.label.replace(/ p\.\d+$/, ""),
        destinationRelpath: "",
        importMode: "reference",
      });
      if (statusKey) this.incuratorStatusByPath.set(statusKey, nextStatus);
      ref.backendStatus = nextStatus;
      this.renderContextChips();
      if (nextStatus.state === "error" || nextStatus.state === "unknown") {
        new Notice(`Could not add source: ${nextStatus.message || "backend did not return a usable source status"}`);
      }
      return;
    }

    // Non-Zotero PDFs: show modal with Copy as default
    const nonZoteroSourcePath = sourcePath;
    if (!nonZoteroSourcePath) {
      new Notice("This PDF does not expose a filesystem path.");
      return;
    }
    new IngestDestinationModal(
      this.app,
      ref.label.replace(/ p\.\d+$/, ""),
      status.destinationRelpath || this.inferPdfIngestDestination(),
      this.plugin.settings.incuratorDefaultImportMode,
      async ({ destinationRelpath, importMode }) => {
        const pendingStatus: IncuratorSourceStatus = {
          state: "running",
          sourcePath: nonZoteroSourcePath,
          message: importMode === "copy" ? "Copying and adding PDF source..." : "Adding PDF as a reference source...",
        };
        this.incuratorStatusByPath.set(nonZoteroSourcePath, pendingStatus);
        ref.backendStatus = pendingStatus;
        this.renderContextChips();
        const nextStatus = await this.getIncuratorClient().ingestPdf({
          sourcePath: nonZoteroSourcePath,
          displayName: ref.label.replace(/ p\.\d+$/, ""),
          destinationRelpath,
          importMode,
        });
        this.incuratorStatusByPath.set(nonZoteroSourcePath, nextStatus);
        ref.backendStatus = nextStatus;
        this.renderContextChips();
        if (nextStatus.state === "error" || nextStatus.state === "unknown") {
          throw new Error(nextStatus.message || "Backend did not return a usable source status");
        }
      }
    ).open();
  }

  private inferPdfIngestDestination(): string {
    const configured = this.plugin.settings.incuratorDefaultDestination || "04_Resources";
    const activeCtx = this.plugin.getActiveContext();
    const mdPath =
      activeCtx.viewType === "markdown" && activeCtx.filePath
        ? activeCtx.filePath
        : activeCtx.openTabs?.find((tab) => tab.viewType === "markdown" && tab.filePath)
            ?.filePath;
    return inferIngestDestination(mdPath, configured);
  }

  // ── Rendering ───────────────────────────────────────────────

  private renderMessages(forceScroll: boolean = true): void {
    // Capture the user's scroll position before the DOM is torn down so a
    // re-render triggered by generation completion does not yank the view to
    // the bottom. We only follow to the bottom when the user was already there.
    const prevScrollTop = this.messagesContainer.scrollTop;
    const wasNearBottom = this.isNearBottom();
    this.messagesContainer.empty();

    const updateClient = this.getIncuratorClient();
    // Show the update banner only when an update is needed AND we have a repo to
    // update from (explicit override or backend-reported path). Non-editable
    // installs report no repo path → no dead update button.
    if (updateClient.needsUpdate && this.plugin.resolveRepoPath()) {
      const banner = this.messagesContainer.createDiv("ai-agent-update-banner");
      banner.style.padding = "10px";
      banner.style.marginBottom = "10px";
      banner.style.backgroundColor = "var(--interactive-accent)";
      banner.style.color = "var(--text-on-accent)";
      banner.style.borderRadius = "4px";
      banner.style.display = "flex";
      banner.style.justifyContent = "space-between";
      banner.style.alignItems = "center";
      
      const text = banner.createSpan();
      text.setText(updateClient.updateMessage || "Incurator setup needs to be refreshed on this device.");
      
      const btn = banner.createEl("button", { text: updateClient.updateActionLabel || "Run Setup" });
      btn.style.backgroundColor = "transparent";
      btn.style.border = "1px solid var(--text-on-accent)";
      btn.style.color = "var(--text-on-accent)";
      btn.style.cursor = "pointer";
      btn.style.padding = "4px 8px";
      btn.style.borderRadius = "4px";
      
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        btn.setText("Running setup...");
        await this.plugin.updateIncuratorBackend();
        btn.setText("Restart Required");
      });
    }

    if (this.messages.length === 0) {
      const empty = this.messagesContainer.createDiv("ai-agent-chat-empty");
      const emptyIcon = empty.createEl("div", {
        cls: "ai-agent-chat-empty-icon",
      });
      setIcon(emptyIcon, "sparkles");
      empty.createEl("div", {
        cls: "ai-agent-chat-empty-text",
        text: "Ask from your notes",
      });
      empty.createEl("div", {
        cls: "ai-agent-chat-empty-hint",
        text: "Drop files, paste images, or type a question",
      });
      return;
    }

    for (const msg of this.messages) {
      this.renderMessage(msg);
    }
    if (forceScroll || wasNearBottom) {
      this.scrollToBottom(true);
    } else {
      // Preserve the reader's position; the full rebuild reset scrollTop to 0.
      requestAnimationFrame(() => {
        if (this.messagesContainer) {
          this.messagesContainer.scrollTop = prevScrollTop;
        }
      });
    }
  }

  private renderMessage(msg: ChatMessage): void {
    const msgEl = this.messagesContainer.createDiv(
      `ai-agent-chat-msg ai-agent-chat-msg-${msg.role}`
    );

    const roleEl = msgEl.createDiv("ai-agent-chat-msg-role");
    roleEl.setText(msg.role === "user" ? "You" : "AI Agent");
    this.renderAssistantMessageActions(roleEl, msg);

    if (msg.contextRefs && msg.contextRefs.length > 0) {
      const refsEl = msgEl.createDiv("ai-agent-chat-msg-refs");
      for (const ref of msg.contextRefs) {
        const chip = refsEl.createDiv("ai-agent-context-chip");
        const label = ref.label.length > 24 ? ref.label.slice(0, 22) + "…" : ref.label;
        if (ref.imageBase64) {
          chip.createEl("img", {
            cls: "ai-agent-chip-inline-thumb",
            attr: { src: `data:image/png;base64,${ref.imageBase64}` },
          });
        }
        chip.createSpan({ text: label });
      }
    }

    const contentEl = msgEl.createDiv("ai-agent-chat-msg-content");
    if (msg.role === "assistant" && msg.content) {
      this.renderAssistantMessageContent(msg, contentEl);
    } else {
      contentEl.setText(msg.content);
    }

    if (msg.isStreaming && !msg.content) {
      contentEl.createSpan({ cls: "ai-agent-thinking", text: "Thinking..." });
    }

  }

  /**
   * Render assistant markdown into `wrapper`, then stamp each rendered formula's
   * LaTeX source onto it as `data-tex` (reading-view CHTML keeps no source in the
   * DOM, so selecting + copying a formula would otherwise drop it). `source` is the
   * exact string rendered, so the Nth formula maps to the Nth `.math` element; the
   * stamp only applies on an exact count match (never a wrong source).
   */
  private renderAssistantMarkdown(source: string, wrapper: HTMLElement): void {
    void MarkdownRenderer.render(this.app, source, wrapper, "", this).then(() =>
      stampMathSourceData(wrapper, source)
    );
  }

  private renderAssistantMessageContent(msg: ChatMessage, contentEl: HTMLElement): void {
    contentEl.empty();
    if (!msg.content) return;

    // During streaming, skip MarkdownRenderer entirely to avoid CPU explosion from
    // repeated full DOM reconstruction. Show raw text in a <pre>-like element;
    // the final render (isStreaming=false) will do one proper MarkdownRenderer pass.
    if (msg.isStreaming) {
      const streamEl = contentEl.createDiv("ai-agent-streaming-text");
      // Hide ALL code-edit blocks while streaming, not just the last one, so the
      // chat never floods with raw SEARCH/REPLACE code. The final render swaps
      // the blocks for compact diff-review pills.
      streamEl.textContent = collapseStreamingEditBlocks(msg.content);
      return;
    }

    // --- Streaming is done: full render path ---
    const editRef = this.getEditTargetContextForMessage(msg);
    const multiProposals = this.extractMultiEditProposals(msg.content, editRef?.filePath);
    let remainingContent = msg.content;

    if (multiProposals.length > 0) {
      for (const prop of multiProposals) {
        const escaped = prop.originalBlock.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const withTicks = new RegExp(`\`\`\`(?:\\w+)?\\n?${escaped}\\n?\`\`\``, "g");
        if (withTicks.test(remainingContent)) {
          remainingContent = remainingContent.replace(withTicks, "");
        } else {
          remainingContent = remainingContent.replace(prop.originalBlock, "");
        }
      }
      remainingContent = remainingContent.trim();
      
      const mdWrapper = contentEl.createDiv("ai-agent-markdown-wrapper");
      if (remainingContent) {
        const processedContent = this.processMarkdownForThoughts(remainingContent, false);
        this.renderAssistantMarkdown(processedContent, mdWrapper);
      }
      
      for (const prop of multiProposals) {
        this.renderInlineMultiDiff(contentEl, prop, msg);
      }
    } else {
      const editProposal = this.extractEditProposal(msg.content);
      const legacyRef = editProposal ? this.getEditableContextForMessage(msg) : null;

      if (editProposal && legacyRef) {
        const beforeEdit = msg.content.replace(/```ai-agent-edit[\s\S]*?```/i, "").trim();
        const mdWrapper = contentEl.createDiv("ai-agent-markdown-wrapper");
        if (beforeEdit) {
          const processedBefore = this.processMarkdownForThoughts(beforeEdit, false);
          this.renderAssistantMarkdown(processedBefore, mdWrapper);
        }
        this.renderInlineDiff(contentEl, legacyRef, editProposal, msg);
      } else {
        const mdWrapper = contentEl.createDiv("ai-agent-markdown-wrapper");
        const processedContent = this.processMarkdownForThoughts(msg.content, false);
        this.renderAssistantMarkdown(processedContent, mdWrapper);
      }
    }

    const toolMatch = msg.content.match(/✅ \*\*mcp_[^*]*curator_query\*\* result:\n```(?:json)?\n([\s\S]*?)\n```/);
    if (toolMatch && !this.lastQueryTrace) {
      try {
        const parsed = JSON.parse(toolMatch[1]);
        if (parsed.trace || parsed.trace_id) {
          this.lastQueryTrace = parsed;
        }
      } catch { }
    }
    const traceToRender = this.lastQueryTrace;
    if (traceToRender) {
      const thoughtBlock = contentEl.querySelector("details.ai-agent-thought-block");
      if (thoughtBlock) {
        renderCuratorQueryTrace(thoughtBlock as HTMLElement, traceToRender as any, this.app);
      } else {
        renderCuratorQueryTrace(contentEl, traceToRender as any, this.app);
      }
    }
    window.setTimeout(() => this.attachAssistantAnswerLinkNavigation(contentEl), 0);
    attachLatexCopyHandler(contentEl, htmlToMarkdown);
  }

  private attachAssistantAnswerLinkNavigation(container: HTMLElement): void {
    const links = Array.from(container.querySelectorAll<HTMLAnchorElement>("a"));
    for (const link of links) {
      const target = parseAnswerLinkTarget(link.getAttribute("href"), link.textContent || "");
      if (!target) continue;
      link.addClass("ai-agent-answer-target-link");
      link.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        this.navigateAssistantAnswerTarget(target);
      });
    }
  }

  private navigateAssistantAnswerTarget(target: AnswerLinkTarget): void {
    const view = this.findNavigablePdfView();
    if (!view) {
      new Notice("Open the PDF in Incurator's PDF view to jump to answer links.");
      return;
    }

    const pageNum =
      target.kind === "page"
        ? target.pageKind === "printed"
          ? view.resolvePrintedPageLabel(target.pageNum) ?? target.pageNum
          : target.pageNum
        : this.resolveAssistantSectionPage(target.sectionNumber);
    if (!pageNum) {
      new Notice(
        target.kind === "section"
          ? `Could not find Section ${target.sectionNumber} in the active PDF outline.`
          : "Could not resolve the PDF page link."
      );
      return;
    }
    view.jumpToPage(pageNum, "smooth");
  }

  private resolveAssistantSectionPage(sectionNumber: string): number | undefined {
    const outline = this.plugin.refreshActiveContext()?.pdfPage?.outline ?? [];
    const want = sectionNumber.toUpperCase();
    const match = outline.find((item) => this.parseAssistantOutlineNumber(item.title) === want);
    return match?.pageNum;
  }

  private parseAssistantOutlineNumber(title: string): string | undefined {
    const match = /^\s*(?:appendix\s+)?([A-Z]?\d+(?:\.\d+)*)/i.exec(title);
    return match?.[1]?.toUpperCase();
  }

  private findNavigablePdfView(): ExternalPdfView | null {
    const activeView = this.app.workspace.activeLeaf?.view;
    if (activeView instanceof ExternalPdfView) return activeView;
    const leaves = this.app.workspace.getLeavesOfType(EXTERNAL_PDF_VIEW_TYPE);
    const first = leaves[0]?.view;
    return first instanceof ExternalPdfView ? first : null;
  }

  private renderInlineDiff(
    container: HTMLElement,
    ref: ContextRef,
    modifiedText: string,
    msg: ChatMessage
  ): void {
    // Compute original text from the file
    const file = this.app.vault.getAbstractFileByPath(ref.filePath!);
    if (!(file instanceof TFile)) return;

    const lineStart = ref.lineStart!;
    const lineEnd = ref.lineEnd!;

    // Read original from open editor or vault
    let originalText = ref.content || "";

    const wrapper = container.createDiv("ai-agent-inline-diff");

    // Header
    const header = wrapper.createDiv("ai-agent-inline-diff-header");
    header.createSpan({ cls: "ai-agent-inline-diff-filename", text: `${file.name}  L${lineStart}${lineStart !== lineEnd ? `–${lineEnd}` : ""}` });
    const btnGroup = header.createDiv("ai-agent-inline-diff-actions");
    const acceptBtn = btnGroup.createEl("button", {
      cls: "ai-agent-inline-diff-accept",
      text: "✓ Accept",
      attr: { title: "Apply this edit (Enter)" },
    });
    const rejectBtn = btnGroup.createEl("button", {
      cls: "ai-agent-inline-diff-reject",
      text: "✗ Reject",
      attr: { title: "Discard this edit (Escape)" },
    });

    // Diff lines
    const diffLines = this.computeSimpleDiff(originalText, modifiedText);
    const codeEl = wrapper.createEl("pre", { cls: "ai-agent-inline-diff-code" });
    for (const line of diffLines) {
      const lineEl = codeEl.createDiv({
        cls: `ai-agent-inline-diff-line ai-agent-inline-diff-line-${line.type}`,
      });
      const prefix = line.type === "removed" ? "- " : line.type === "added" ? "+ " : "  ";
      lineEl.createSpan({ cls: "ai-agent-inline-diff-gutter", text: prefix });
      lineEl.createSpan({ cls: "ai-agent-inline-diff-text", text: line.text });
    }

    const applyEdit = async () => {
      await this.applyInlineEdit(ref, modifiedText);
      wrapper.addClass("ai-agent-inline-diff-accepted");
      acceptBtn.disabled = true;
      rejectBtn.disabled = true;
      acceptBtn.setText("✓ Accepted");
    };

    const rejectEdit = () => {
      wrapper.addClass("ai-agent-inline-diff-rejected");
      acceptBtn.disabled = true;
      rejectBtn.disabled = true;
      rejectBtn.setText("✗ Rejected");
    };

    acceptBtn.addEventListener("click", (e) => { e.stopPropagation(); applyEdit(); });
    rejectBtn.addEventListener("click", (e) => { e.stopPropagation(); rejectEdit(); });
  }

  private renderInlineMultiDiff(
    container: HTMLElement,
    prop: MultiEditProposal,
    msg: ChatMessage
  ): void {
    const file = this.app.vault.getAbstractFileByPath(prop.filepath);
    const wrapper = container.createDiv("ai-agent-applied-change");

    let isNewFile = false;
    if (!(file instanceof TFile)) {
      if (prop.search.includes("<<< NEW FILE >>>") || prop.search.trim() === "") {
        isNewFile = true;
      } else {
        const errEl = wrapper.createSpan({ cls: "ai-agent-applied-change-error" });
        errEl.setText(`⚠ File not found: ${prop.filepath}`);
        return;
      }
    }

    const header = wrapper.createDiv("ai-agent-applied-change-header");

    const icon = header.createSpan({ cls: "ai-agent-applied-change-icon", text: isNewFile ? "📄" : "✏️" });
    const nameEl = header.createSpan({ cls: "ai-agent-applied-change-name" });
    nameEl.setText(prop.filepath);
    nameEl.title = "Review edit in editor";
    
    // Instead of auto-applying or showing diffs in chat, we just provide a button
    // (or click the filename) to open the DiffViewer in the editor.
    const reviewInEditor = async () => {
      await this.reviewAssistantEdit(msg);
      // Since DiffViewer doesn't have a callback to update this pill, we just 
      // let the user know they are reviewing it.
      statusBtn.setText("🔍 Opened Diff");
      statusBtn.style.color = "var(--text-accent)";
      statusBtn.style.borderColor = "var(--text-accent)";
      statusBtn.style.background = "transparent";
    };

    wrapper.style.cursor = "pointer";
    wrapper.addEventListener("click", async (e) => {
      e.stopPropagation();
      await reviewInEditor();
    });

    const statusBtn = header.createEl("button", {
      cls: "ai-agent-applied-status",
      text: "🔍 Review Diff",
      attr: { title: "Click to open Diff Viewer" },
    });
    // Style as pending
    statusBtn.style.color = "var(--text-muted)";
    statusBtn.style.borderColor = "var(--background-modifier-border)";
    statusBtn.style.background = "transparent";
    statusBtn.style.cursor = "pointer";
  }

  private async autoApplyProposals(msg: ChatMessage, proposals: MultiEditProposal[]): Promise<void> {
    if (msg.appliedEdits) return;
    msg.appliedEdits = true;
    msg.revertData = [];

    const changelogLines: string[] = [
      `## AI Changes — ${new Date().toLocaleString()}`,
      "",
    ];

    for (const prop of proposals) {
      const file = this.app.vault.getAbstractFileByPath(prop.filepath);
      let isNewFile = false;
      if (!(file instanceof TFile)) {
        if (prop.search.includes("<<< NEW FILE >>>") || prop.search.trim() === "") {
          isNewFile = true;
        } else {
          continue;
        }
      }

      if (isNewFile) {
        msg.revertData.push({ filepath: prop.filepath, originalContent: null });
        await this.createNewFile(prop.filepath, prop.replace);
        changelogLines.push(`### ✓ Created: \`${prop.filepath}\``);
        changelogLines.push("");
        changelogLines.push("```");
        changelogLines.push(prop.replace.slice(0, 2000) + (prop.replace.length > 2000 ? "\n...[truncated]" : ""));
        changelogLines.push("```");
        changelogLines.push("");
      } else if (file instanceof TFile) {
        const originalContent = await this.app.vault.read(file);
        msg.revertData.push({ filepath: prop.filepath, originalContent });
        await this.applyInlineMultiEdit(prop, file);
        changelogLines.push(`### ✓ Modified: \`${prop.filepath}\``);
        changelogLines.push("");
        changelogLines.push("**Removed:**");
        changelogLines.push("```");
        changelogLines.push(prop.search.slice(0, 1000) + (prop.search.length > 1000 ? "\n...[truncated]" : ""));
        changelogLines.push("```");
        changelogLines.push("");
        changelogLines.push("**Added:**");
        changelogLines.push("```");
        changelogLines.push(prop.replace.slice(0, 1000) + (prop.replace.length > 1000 ? "\n...[truncated]" : ""));
        changelogLines.push("```");
        changelogLines.push("");
      }
    }

    // Append changelog to .ai-agent-changes.md in vault root
    try {
      const logPath = ".ai-agent-changes.md";
      const logFile = this.app.vault.getAbstractFileByPath(logPath);
      const entry = changelogLines.join("\n") + "\n---\n\n";
      if (logFile instanceof TFile) {
        const existing = await this.app.vault.read(logFile);
        await this.app.vault.modify(logFile, entry + existing);
      } else {
        await this.app.vault.create(logPath, entry);
      }
    } catch {
      // fail silently — changelog is optional
    }
  }

  private computeSimpleDiff(
    original: string,
    modified: string
  ): { type: "unchanged" | "added" | "removed"; text: string }[] {
    const origLines = original.split("\n");
    const modLines = modified.split("\n");

    // LCS-based diff
    const m = origLines.length;
    const n = modLines.length;
    const dp: number[][] = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
    for (let i = 1; i <= m; i++)
      for (let j = 1; j <= n; j++)
        dp[i][j] = origLines[i-1] === modLines[j-1]
          ? dp[i-1][j-1] + 1
          : Math.max(dp[i-1][j], dp[i][j-1]);

    const lcs: [number, number][] = [];
    let i = m, j = n;
    while (i > 0 && j > 0) {
      if (origLines[i-1] === modLines[j-1]) { lcs.unshift([i-1, j-1]); i--; j--; }
      else if (dp[i-1][j] > dp[i][j-1]) i--;
      else j--;
    }

    const result: { type: "unchanged" | "added" | "removed"; text: string }[] = [];
    let oi = 0, mi = 0;
    for (const [origIdx, modIdx] of lcs) {
      while (oi < origIdx) result.push({ type: "removed", text: origLines[oi++] });
      while (mi < modIdx) result.push({ type: "added", text: modLines[mi++] });
      result.push({ type: "unchanged", text: origLines[oi] });
      oi++; mi++;
    }
    while (oi < origLines.length) result.push({ type: "removed", text: origLines[oi++] });
    while (mi < modLines.length) result.push({ type: "added", text: modLines[mi++] });
    return result;
  }

  private async applyInlineEdit(ref: ContextRef, modifiedText: string): Promise<void> {
    const file = this.app.vault.getAbstractFileByPath(ref.filePath!);
    if (!(file instanceof TFile)) { new Notice(`Could not find ${ref.filePath}`); return; }

    const lineStart = ref.lineStart!;
    const lineEnd = ref.lineEnd!;

    // Find open source-mode leaf for this file
    let leaf: WorkspaceLeaf | null = null;
    this.app.workspace.iterateAllLeaves((l) => {
      if (leaf || l === this.leaf) return;
      const v = l.view;
      const vs = l.getViewState();
      if (v instanceof MarkdownView && v.file?.path === ref.filePath && vs.state?.mode === "source") {
        leaf = l;
      }
    });

    if (!leaf) {
      leaf = this.app.workspace.getLeaf("tab");
      await (leaf as WorkspaceLeaf).openFile(file, { active: true });
      const newVs = (leaf as WorkspaceLeaf).getViewState();
      await (leaf as WorkspaceLeaf).setViewState({ ...newVs, state: { ...newVs.state, mode: "source" } });
      await new Promise<void>((resolve) => requestAnimationFrame(() => { requestAnimationFrame(() => resolve()); }));
    } else {
      this.app.workspace.setActiveLeaf(leaf as WorkspaceLeaf, { focus: false });
      this.app.workspace.revealLeaf(leaf as WorkspaceLeaf);
    }

    const targetLeaf = leaf as WorkspaceLeaf;
    if (!(targetLeaf.view instanceof MarkdownView)) { new Notice("Cannot apply edit: file not open in Markdown view."); return; }

    const editor = targetLeaf.view.editor;
    const start = { line: Math.max(0, lineStart - 1), ch: 0 };
    const endLine = Math.max(0, lineEnd - 1);
    const lineText = editor.getLine(endLine);
    const end = { line: endLine, ch: lineText?.length ?? 0 };
    editor.replaceRange(modifiedText, start, end);
    editor.setCursor({ line: start.line + modifiedText.split("\n").length - 1, ch: 0 });
  }

  private async createNewFile(filepath: string, content: string): Promise<void> {
    const folders = filepath.split('/');
    folders.pop(); // remove filename
    let currentPath = '';
    for (const folder of folders) {
      currentPath += (currentPath === '' ? '' : '/') + folder;
      const folderObj = this.app.vault.getAbstractFileByPath(currentPath);
      if (!folderObj) {
        await this.app.vault.createFolder(currentPath);
      }
    }
    const file = this.app.vault.getAbstractFileByPath(filepath);
    if (file instanceof TFile) {
      await this.app.vault.modify(file, content);
    } else {
      await this.app.vault.create(filepath, content);
    }
    new Notice(`Created ${filepath}`);
  }

  private async applyInlineMultiEdit(prop: MultiEditProposal, file: TFile): Promise<void> {
    // 1. Try modifying in an active editor if the file is open
    let leaf: WorkspaceLeaf | null = null;
    this.app.workspace.iterateAllLeaves((l) => {
      if (leaf || l === this.leaf) return;
      const v = l.view;
      const vs = l.getViewState();
      if (v instanceof MarkdownView && v.file?.path === file.path && vs.state?.mode === "source") {
        leaf = l;
      }
    });

    if (leaf) {
      const view = (leaf as WorkspaceLeaf).view as MarkdownView;
      const editor = view.editor;
      const content = editor.getValue();

      const match = findSearchBlock(content, prop.search);
      if (match) {
        this.warnIfLargeReplacement(match.matchedText, prop.replace, file.basename);
        editor.replaceRange(
          prop.replace,
          editor.offsetToPos(match.start),
          editor.offsetToPos(match.end)
        );
        new Notice(`Applied edit to ${file.basename}`);
      } else {
        new Notice(`Could not find the SEARCH block in ${file.basename}`);
      }
    } else {
      // 2. Modify via vault API if file is closed
      const content = await this.app.vault.read(file);
      const match = findSearchBlock(content, prop.search);
      if (match) {
        this.warnIfLargeReplacement(match.matchedText, prop.replace, file.basename);
        const newContent =
          content.slice(0, match.start) + prop.replace + content.slice(match.end);
        await this.app.vault.modify(file, newContent);
        new Notice(`Applied edit to ${file.basename}`);
      } else {
        new Notice(`Could not find the SEARCH block in ${file.basename}`);
      }
    }
  }

  /**
   * Non-blocking heads-up when a single edit rewrites a very large region — a
   * model-independent safety net for the scope bug where a weak model pastes an
   * entire chat answer as one REPLACE instead of the referenced section.
   */
  private warnIfLargeReplacement(matched: string, replace: string, basename: string): void {
    const matchedLines = matched.split("\n").length;
    const replaceLines = replace.split("\n").length;
    if (replaceLines >= 40 && replaceLines > matchedLines * 4) {
      new Notice(
        `Large edit in ${basename}: replacing ${matchedLines} line(s) with ${replaceLines}. Review the diff carefully.`,
        8000
      );
    }
  }

  private processMarkdownForThoughts(content: string, isStreaming: boolean): string {
    // Drop any orphan ai-agent-edit markers left by a failed parse so they never
    // render as note text. Operates on the display string only — stored
    // msg.content is untouched, keeping "Copy as Markdown" faithful.
    let processed = stripDanglingEditMarkers(this.normalizeLatexDelimiters(content));
    const openTag = isStreaming 
        ? `<details class="ai-agent-thought-block" open><summary>🧠 Thinking Process...</summary>\n\n`
        : `<details class="ai-agent-thought-block"><summary>🧠 Thinking Process</summary>\n\n`;
    
    processed = processed.replace(/<(thought|thinking|think)>/gi, openTag);
    processed = processed.replace(/<\/(thought|thinking|think)>/gi, "\n\n</details>");

    const openCount = (processed.match(/<details class="ai-agent-thought-block"/g) || []).length;
    const closeCount = (processed.match(/<\/details>/g) || []).length;
    if (openCount > closeCount) {
      processed += "\n\n</details>";
    }
    return processed;
  }

  private renderAssistantMessageActions(roleEl: Element, msg: ChatMessage): void {
    if (msg.role !== "assistant" || !msg.content) return;
    roleEl.querySelectorAll(".ai-agent-message-action").forEach((el) => el.remove());

    const copyBtn = (roleEl as HTMLElement).createEl("button", {
      cls: "ai-agent-message-action ai-agent-message-copy-btn",
      attr: {
        "aria-label": "Copy assistant message as Markdown",
        title: "Copy Markdown",
      },
    });
    setIcon(copyBtn, "copy");
    copyBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      await this.copyAssistantMarkdown(msg.content);
    });

    if (
      !msg.isStreaming &&
      this.getEditTargetContextForMessage(msg) &&
      (
        (this.getEditableContextForMessage(msg) && this.extractEditProposal(msg.content)) ||
        this.extractMultiEditProposals(
          msg.content,
          this.getEditTargetContextForMessage(msg)?.filePath
        ).length > 0
      )
    ) {
      const reviewBtn = (roleEl as HTMLElement).createEl("button", {
        cls: "ai-agent-message-action ai-agent-message-review-btn",
        text: "Review edit",
        attr: {
          "aria-label": "Review proposed edit",
          title: "Review proposed edit",
        },
      });
      reviewBtn.addEventListener("click", async (e) => {
        e.preventDefault();
        e.stopPropagation();
        await this.reviewAssistantEdit(msg);
      });
    }
  }

  private async copyAssistantMarkdown(content: string): Promise<void> {
    const markdown = this.normalizeLatexDelimiters(content);
    try {
      await navigator.clipboard.writeText(markdown);
      new Notice("Copied Markdown with LaTeX");
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = markdown;
      textarea.style.position = "fixed";
      textarea.style.left = "-9999px";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
      new Notice("Copied Markdown with LaTeX");
    }
  }

  private getEditableContextForMessage(msg: ChatMessage): ContextRef | null {
    const msgIndex = this.messages.findIndex((item) => item.id === msg.id);
    if (msgIndex <= 0) return null;

    for (let i = msgIndex - 1; i >= 0; i--) {
      const candidate = this.messages[i];
      if (candidate.role !== "user") continue;
      const refs = candidate.contextRefs ?? [];
      const editable = refs.find(
        (ref) =>
          ref.filePath &&
          ref.type === "line-range" &&
          typeof ref.lineStart === "number" &&
          typeof ref.lineEnd === "number"
      );
      if (editable) return editable;
    }

    return null;
  }

  private getEditTargetContextForMessage(msg: ChatMessage): ContextRef | null {
    const msgIndex = this.messages.findIndex((item) => item.id === msg.id);
    if (msgIndex <= 0) return null;

    for (let i = msgIndex - 1; i >= 0; i--) {
      const candidate = this.messages[i];
      if (candidate.role !== "user") continue;
      const refs = candidate.contextRefs ?? [];
      const editable = refs.find(
        (ref) =>
          ref.filePath &&
          ref.type === "line-range" &&
          typeof ref.lineStart === "number" &&
          typeof ref.lineEnd === "number"
      );
      if (editable) return editable;
      const fileTarget = refs.find(
        (ref) =>
          ref.filePath &&
          ref.type === "file" &&
          ref.filePath.toLowerCase().endsWith(".md")
      );
      if (fileTarget) return fileTarget;
    }

    return null;
  }

  private async reviewAssistantEdit(msg: ChatMessage): Promise<void> {
    const ref = this.getEditTargetContextForMessage(msg);
    if (!ref?.filePath) {
      new Notice("No referenced Markdown file found for this edit.");
      return;
    }

    const modifiedText = this.extractEditProposal(msg.content);
    const multiProposals = this.extractMultiEditProposals(msg.content, ref.filePath)
      .filter((prop) => prop.filepath === ref.filePath);
    if (
      modifiedText &&
      multiProposals.length === 0 &&
      (typeof ref.lineStart !== "number" || typeof ref.lineEnd !== "number")
    ) {
      new Notice("A full replacement edit needs a selected Markdown line range.");
      return;
    }

    if (!modifiedText && multiProposals.length === 0) {
      new Notice("No ai-agent-edit proposal found in this answer.");
      return;
    }

    const file = this.app.vault.getAbstractFileByPath(ref.filePath);
    if (!(file instanceof TFile)) {
      new Notice(`Could not find ${ref.filePath}`);
      return;
    }

    // Look for an existing leaf that already has the file open IN SOURCE mode.
    // Do NOT reuse reading-mode leaves — switching them to source mode destroys
    // rendered figures and the user's view state.
    let leaf: WorkspaceLeaf | null = null;
    this.app.workspace.iterateAllLeaves((l) => {
      if (leaf || l === this.leaf) return;
      const v = l.view;
      const vs = l.getViewState();
      if (
        v instanceof MarkdownView &&
        v.file?.path === ref.filePath &&
        vs.state?.mode === "source"
      ) {
        leaf = l;
      }
    });

    if (!leaf) {
      // Open a brand-new tab in source mode — existing reading-mode leaves are untouched.
      leaf = this.app.workspace.getLeaf("tab");
      await (leaf as WorkspaceLeaf).openFile(file, { active: true });
      const newVs = (leaf as WorkspaceLeaf).getViewState();
      await (leaf as WorkspaceLeaf).setViewState({
        ...newVs,
        state: { ...newVs.state, mode: "source" },
      });
      // Wait two frames for Obsidian to apply the view state and for CM6 to mount.
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => { requestAnimationFrame(() => resolve()); })
      );
    } else {
      this.app.workspace.setActiveLeaf(leaf as WorkspaceLeaf, { focus: false });
      this.app.workspace.revealLeaf(leaf as WorkspaceLeaf);
    }

    const targetLeaf = leaf as WorkspaceLeaf;

    if (!(targetLeaf.view instanceof MarkdownView)) {
      new Notice("Open the target file as Markdown to review this edit.");
      return;
    }

    const editor = targetLeaf.view.editor;
    let start = { line: Math.max(0, (ref.lineStart ?? 1) - 1), ch: 0 };
    let endLine = Math.max(0, (ref.lineEnd ?? ref.lineStart ?? 1) - 1);
    let lineText = editor.getLine(endLine);
    let end = { line: endLine, ch: lineText?.length ?? 0 };
    let originalText = editor.getRange(start, end);
    let replacementText = modifiedText || "";

    if (multiProposals.length > 0) {
      const originalFullText = editor.getValue();
      let modifiedFullText = originalFullText;
      let replacementCount = 0;

      for (const proposal of multiProposals) {
        if (!proposal.search) continue;
        // Use the same matcher as apply so the previewed diff equals what would
        // actually be written. Splice one (the matcher's) span per proposal; if
        // the agent emitted N blocks for N identical occurrences, each block
        // resolves against the progressively-mutated text and hits a fresh one.
        const match = findSearchBlock(modifiedFullText, proposal.search);
        if (!match) continue;
        replacementCount += 1;
        modifiedFullText =
          modifiedFullText.slice(0, match.start) +
          proposal.replace +
          modifiedFullText.slice(match.end);
      }

      if (replacementCount === 0 || modifiedFullText === originalFullText) {
        new Notice("Could not find SEARCH text in the target Markdown file.");
        return;
      }

      const lastLine = Math.max(0, editor.lineCount() - 1);
      const lastLineText = editor.getLine(lastLine);
      const diffViewer = new DiffViewer(this.plugin);
      diffViewer.show(
        targetLeaf.view,
        originalFullText,
        modifiedFullText,
        { line: 0, ch: 0 },
        { line: lastLine, ch: lastLineText?.length ?? 0 }
      );
      new Notice(`Reviewing ${replacementCount} proposed change${replacementCount === 1 ? "" : "s"} in ${file.basename}`);
      return;
    }

    const diffViewer = new DiffViewer(this.plugin);
    diffViewer.show(targetLeaf.view, originalText, replacementText, start, end);
  }

  private readEditBlockFilepath(infoText: string, fallbackFilepath = ""): string {
    const doubleQuoted = infoText.match(/filepath="([^"]+)"/i);
    if (doubleQuoted) return doubleQuoted[1].trim();
    const singleQuoted = infoText.match(/filepath='([^']+)'/i);
    if (singleQuoted) return singleQuoted[1].trim();
    const bare = infoText.match(/filepath=([^\s]+)/i);
    return bare ? bare[1].trim() : fallbackFilepath;
  }

  /**
   * Immediately open the in-editor diff for a just-completed edit, but only
   * under a safe gate so it never steals the user's editor:
   *   - exactly one target file (multi-file edits keep the clickable pill);
   *   - the target is the already-active Markdown note, OR no Markdown note is
   *     focused (a different focused note → keep the pill).
   * Runs once per message from the stream-completion path, never on history
   * re-render, so loading an old session does not pop diffs open.
   */
  private async maybeAutoOpenDiff(msg: ChatMessage): Promise<void> {
    if (msg.diffAutoOpened) return;

    const editRef = this.getEditTargetContextForMessage(msg);
    const proposals = this.extractMultiEditProposals(msg.content, editRef?.filePath);
    if (proposals.length === 0) return;

    const files = new Set(proposals.map((p) => p.filepath));
    if (files.size !== 1) return;
    const target = proposals[0].filepath;
    if (!(this.app.vault.getAbstractFileByPath(target) instanceof TFile)) return;

    const active = this.app.workspace.getActiveViewOfType(MarkdownView);
    if (active && active.file?.path !== target) return; // different note focused → keep pill

    msg.diffAutoOpened = true;
    await this.reviewAssistantEdit(msg);
  }

  private extractMultiEditProposals(content: string, fallbackFilepath = ""): MultiEditProposal[] {
    const proposals: MultiEditProposal[] = [];
    const blockRegex = /```ai-agent-edit([^\n]*)\n([\s\S]*?)```/gi;
    let match;
    while ((match = blockRegex.exec(content)) !== null) {
      const originalBlock = match[0];
      const filepath = this.readEditBlockFilepath(match[1], fallbackFilepath);
      const innerContent = match[2];

      // Tolerate marker variants: 3+ angle/equals chars, optional spacing, and a
      // REPLACE body that ends at `>>>>` OR at the end of the block (a missing
      // closer should still parse rather than leak markers into the render).
      const searchMatch = innerContent.match(/<{3,}\s*SEARCH\s*\n([\s\S]*?)={3,}\s*REPLACE/i);
      const replaceMatch = innerContent.match(/={3,}\s*REPLACE\s*\n([\s\S]*?)(?:>{3,}|$)/i);

      if (filepath && searchMatch && replaceMatch) {
        let search = searchMatch[1];
        if (search.endsWith("\n")) search = search.slice(0, -1);
        
        let replace = replaceMatch[1];
        if (replace.endsWith("\n")) replace = replace.slice(0, -1);

        proposals.push({
          filepath,
          search,
          replace,
          originalBlock
        });
      }
    }
    if (proposals.length > 0) return proposals;

    const bareBlockRegex = /<{3,}\s*SEARCH\s*\n([\s\S]*?)={3,}\s*REPLACE\s*\n([\s\S]*?)>{3,}/gi;
    while ((match = bareBlockRegex.exec(content)) !== null) {
      if (!fallbackFilepath) continue;
      let search = match[1];
      if (search.endsWith("\n")) search = search.slice(0, -1);
      let replace = match[2];
      if (replace.endsWith("\n")) replace = replace.slice(0, -1);
      proposals.push({
        filepath: fallbackFilepath,
        search,
        replace,
        originalBlock: match[0],
      });
    }
    return proposals;
  }

  private extractEditProposal(content: string): string | null {
    const editBlock = content.match(/```ai-agent-edit\s*\n([\s\S]*?)```/i);
    if (editBlock) return editBlock[1].trim();

    const codeBlock = content.match(/```(?:markdown|md)?\s*\n([\s\S]*?)```/i);
    if (codeBlock) return codeBlock[1].trim();

    return null;
  }

  private normalizeLatexDelimiters(content: string): string {
    return normalizeLatexDelimiters(content);
  }

  private renderAssistantMessage(msg: ChatMessage): void {
    const allMsgEls = this.messagesContainer.querySelectorAll(
      ".ai-agent-chat-msg-assistant"
    );
    const lastEl = allMsgEls[allMsgEls.length - 1];

    if (lastEl) {
      const roleEl = lastEl.querySelector(".ai-agent-chat-msg-role");
      if (roleEl) {
        this.renderAssistantMessageActions(roleEl, msg);
      }
      const contentEl = lastEl.querySelector(".ai-agent-chat-msg-content");
      if (contentEl) {
        this.stopThinkingTimer();
        if (msg.content) {
          this.renderAssistantMessageContent(msg, contentEl as HTMLElement);
        } else if (msg.isStreaming) {
          contentEl.empty();
          const thinkingSpan = (contentEl as HTMLElement).createSpan({
            cls: "ai-agent-thinking",
          });
          if (this.prepareStatusText) {
            thinkingSpan.setText(this.prepareStatusText);
          } else {
            if (!this.thinkingTimer) {
              this.thinkingStartTime = Date.now();
            }
            const updateThinkingText = () => {
              const elapsed = Math.floor((Date.now() - this.thinkingStartTime) / 1000);
              thinkingSpan.setText(`Thinking... (${elapsed}s)`);
            };
            updateThinkingText();
            if (!this.thinkingTimer) {
              this.thinkingTimer = setInterval(updateThinkingText, 1000);
            }
          }
        }
      }
    }
    this.scrollToBottom(false);
  }

  private stopThinkingTimer(): void {
    if (this.thinkingTimer !== null) {
      clearInterval(this.thinkingTimer);
      this.thinkingTimer = null;
    }
  }

  private setPrepareStatus(text: string): void {
    this.prepareStatusText = text;
    const allMsgEls = this.messagesContainer?.querySelectorAll(".ai-agent-chat-msg-assistant");
    if (!allMsgEls || allMsgEls.length === 0) return;
    const lastEl = allMsgEls[allMsgEls.length - 1];
    const span = lastEl?.querySelector<HTMLElement>(".ai-agent-thinking");
    if (span) span.setText(text);
  }

  private renderContextChips(): void {
    if (!this.contextChipsContainer) return;
    this.contextChipsContainer.empty();

    const activeCtx = this.plugin.refreshActiveContext();
    const freshAutoRefs = this.buildAutoContextRefs(activeCtx);
    if (freshAutoRefs.length > 0) {
      this.cachedAutoContextRefs = this.mergeAutoContextRefs(
        this.cachedAutoContextRefs,
        freshAutoRefs
      );
    }

    // When fresh context lacks PDF data (pdfPage not yet captured), restore cached PDF refs
    // for tabs that are still open so the chip doesn't flicker away on leaf-change.
    const openPdfTabKeys = new Set<string>();
    this.plugin.app.workspace.iterateAllLeaves((leaf) => {
      const viewType = leaf.view.getViewType();
      if (viewType === "pdf" || viewType === EXTERNAL_PDF_VIEW_TYPE) {
        if (viewType === EXTERNAL_PDF_VIEW_TYPE) {
          const state = leaf.view.getState() as { path?: unknown };
          if (typeof state.path === "string") openPdfTabKeys.add(state.path);
          openPdfTabKeys.add(leaf.view.getDisplayText());
        } else {
          // Internal PDF view
          const file = (leaf.view as any).file;
          if (file && file.path) openPdfTabKeys.add(file.path);
          openPdfTabKeys.add(leaf.view.getDisplayText());
        }
      }
    });
    
    const cachedPdfsStillOpen = this.cachedAutoContextRefs.filter((r) => {
      if (r.type !== "pdf-page") return false;
      return openPdfTabKeys.has(r.filePath || r.label.replace(/ p\.\d+$/, ""));
    });
    let autoRefs: ContextRef[];
    if (freshAutoRefs.length > 0) {
      const freshHasPdf = freshAutoRefs.some((r) => r.type === "pdf-page");
      autoRefs = (!freshHasPdf && cachedPdfsStillOpen.length > 0)
        ? this.mergeAutoContextRefs(cachedPdfsStillOpen, freshAutoRefs)
        : freshAutoRefs;
    } else {
      autoRefs = this.cachedAutoContextRefs;
    }

    // Auto context chips show every visible markdown/PDF split.
    for (const ref of autoRefs) {
      let isSuppressed = false;
      for (const pinned of this.pendingContextRefs) {
        // Text/line-range/selections never suppress the full file auto chip
        if (pinned.type === "line-range" || pinned.type === "text" || pinned.type === "selection") continue;
        
        // Explicit PDF crops/selections never suppress the full PDF page auto chip
        if (pinned.type === "pdf-page" && pinned.label && (pinned.label.includes("(Crop)") || pinned.label.includes("(Selection)"))) continue;

        // If it's a full file or full PDF page pin, check if it matches this auto chip
        if (ref.filePath && pinned.filePath === ref.filePath) {
          isSuppressed = true;
          break;
        }
        if (!ref.filePath && pinned.label.replace(/ p\.\d+$/, "") === ref.label.replace(/ p\.\d+$/, "")) {
          isSuppressed = true;
          break;
        }
      }
      if (isSuppressed) {
        continue;
      }

      const activeKey = this.getAutoContextKey(ref);
      const chip = this.contextChipsContainer.createDiv(
        "ai-agent-context-chip ai-agent-context-chip-auto"
      );
      if (!shouldIncludeContext(ref)) chip.addClass("is-excluded");
      const icon = ref.type === "pdf-page" ? "file-text" : "file";
      const iconEl = chip.createSpan({ cls: "ai-agent-context-chip-icon" });
      setIcon(iconEl, icon);
      chip.createSpan({ cls: "ai-agent-context-chip-label", text: ref.label });
      this.renderIncuratorStatusBadge(chip, ref);
      const visibilityBtn = chip.createSpan({
        cls: "ai-agent-context-chip-visibility",
        attr: {
          "aria-label": shouldIncludeContext(ref) ? "Exclude context from prompt" : "Include context in prompt",
          title: shouldIncludeContext(ref) ? "Exclude from prompt" : "Include in prompt",
        },
      });
      setIcon(visibilityBtn, shouldIncludeContext(ref) ? "eye" : "eye-off");
      visibilityBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (shouldIncludeContext(ref)) {
          this.activeContextExcludedKeys.add(activeKey);
        } else {
          this.activeContextExcludedKeys.delete(activeKey);
        }
        this.renderContextChips();
      });
      const removeBtn = chip.createSpan({ cls: "ai-agent-context-chip-remove", text: "×" });
      removeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        this.activeContextExcludedKeys.add(activeKey);
        this.renderContextChips();
      });
    }

    // Pending refs
    for (let i = 0; i < this.pendingContextRefs.length; i++) {
      const ref = this.pendingContextRefs[i];
      const chip = this.contextChipsContainer.createDiv("ai-agent-context-chip");
      if (!shouldIncludeContext(ref)) chip.addClass("is-excluded");

      if (ref.imageBase64) {
        chip.createEl("img", {
          cls: "ai-agent-chip-thumb",
          attr: { src: `data:image/png;base64,${ref.imageBase64}` },
        });
      } else if (ref.type === "line-range") {
        const iconEl = chip.createSpan({ cls: "ai-agent-context-chip-icon" });
        setIcon(iconEl, "brackets");
      }

      chip.createSpan({
        cls: "ai-agent-context-chip-label",
        text: `${ref.isPinned ? "📌 " : ""}${ref.label}`,
      });
      this.renderIncuratorStatusBadge(chip, ref);

      const visibilityBtn = chip.createSpan({
        cls: "ai-agent-context-chip-visibility",
        attr: {
          "aria-label": shouldIncludeContext(ref) ? "Exclude context from prompt" : "Include context in prompt",
          title: shouldIncludeContext(ref) ? "Exclude from prompt" : "Include in prompt",
        },
      });
      setIcon(visibilityBtn, shouldIncludeContext(ref) ? "eye" : "eye-off");
      visibilityBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        ref.includeInPrompt = shouldIncludeContext(ref) ? false : true;
        this.renderContextChips();
      });

      const removeBtn = chip.createSpan({ cls: "ai-agent-context-chip-remove", text: "×" });
      removeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        this.pendingContextRefs.splice(i, 1);
        this.renderContextChips();
      });
    }

    // "+" button — opens a menu to pick any open tab as context
    const addBtn = this.contextChipsContainer.createEl("button", {
      cls: "ai-agent-context-chip ai-agent-context-chip-add",
      attr: { "aria-label": "Add context from open tabs" },
    });
    setIcon(addBtn, "plus");
    addBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      this.showAddContextMenu(e);
    });
  }

  private mergeAutoContextRefs(
    cachedRefs: ContextRef[],
    freshRefs: ContextRef[]
  ): ContextRef[] {
    const merged = new Map<string, ContextRef>();
    for (const ref of cachedRefs) {
      merged.set(this.getAutoContextKey(ref), ref);
    }
    for (const ref of freshRefs) {
      merged.set(this.getAutoContextKey(ref), ref);
    }
    return Array.from(merged.values());
  }

  private showAddContextMenu(e: MouseEvent): void {
    const openTabs = this.plugin.refreshActiveContext()?.openTabs ?? [];
    const addableTabs = openTabs.filter((t) => {
      if (t.viewType === EXTERNAL_PDF_VIEW_TYPE || t.viewType === "pdf") {
        return !this.pendingContextRefs.some((r) => r.label.startsWith(t.label));
      }
      return (
        t.filePath &&
        !this.pendingContextRefs.some((r) => r.filePath === t.filePath)
      );
    });

    const menu = new Menu();

    if (addableTabs.length === 0) {
      menu.addItem((item) => item.setTitle("No other open files").setDisabled(true));
    } else {
      for (const tab of addableTabs) {
        menu.addItem((item) => {
          const isPdf = tab.viewType === "pdf" || tab.viewType === EXTERNAL_PDF_VIEW_TYPE;
          item.setIcon(isPdf ? "file-text" : "document");
          item.setTitle(tab.label);
          item.onClick(async () => {
            if (isPdf) {
              const ref = this.createPinnedPdfRef(tab);
              if (ref) this.addContextRef(ref);
            } else if (tab.filePath) {
              const vaultFile = this.app.vault.getAbstractFileByPath(tab.filePath);
              if (vaultFile instanceof TFile) {
                const ref = await this.createPinnedFileRef(vaultFile, tab.viewType);
                this.addContextRef(ref);
              }
            }
          });
        });
      }
    }

    menu.showAtMouseEvent(e);
  }

  private setupChipsDrop(): void {
    const el = this.contextChipsContainer;
    let counter = 0;

    // This is registered once in onOpen — not per renderContextChips call.
    el.addEventListener("dragenter", (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      counter++;
      el.addClass("drag-over");
    });

    el.addEventListener("dragleave", (e: DragEvent) => {
      e.stopPropagation();
      counter--;
      if (counter <= 0) { counter = 0; el.removeClass("drag-over"); }
    });

    el.addEventListener("dragover", (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
    });

    el.addEventListener("drop", async (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      counter = 0;
      el.removeClass("drag-over");
      if (!e.dataTransfer) return;

      const initialRefs = this.pendingContextRefs.length;

      // Fallback 1: Obsidian internal dragManager for tabs (leaves)
      // Obsidian stores the currently dragged leaf in the app's dragManager
      const dragManager = (this.app as any).dragManager;
      const dragLeaf = dragManager?.dragLeaf || dragManager?.draggable?.leaf;
      if (dragLeaf && dragLeaf.view) {
        const view = dragLeaf.view;
        if (view.getViewType() === EXTERNAL_PDF_VIEW_TYPE) {
          const pdfCtx = (view as ExternalPdfView).getActivePdfContext(this.plugin.settings.pdfCaptureMode);
          if (pdfCtx) {
            this.addContextRef({
              type: "pdf-page",
              label: `${view.getDisplayText()} p.${pdfCtx.pageNum}`,
              content: pdfCtx.text,
              imageBase64: pdfCtx.imageBase64,
              pageNum: pdfCtx.pageNum,
              pageLabels: pdfCtx.pageLabels,
            });
            return;
          }
        } else if (view.file instanceof TFile) {
          await this.attachVaultFile(view.file);
          return;
        }
      }

      // Fallback 2: Obsidian internal file drag: vault-relative path in text/plain
      const vaultPath = e.dataTransfer.getData("text/plain");
      if (vaultPath) {
        const vaultFile = this.app.vault.getAbstractFileByPath(vaultPath);
        if (vaultFile instanceof TFile) {
          await this.attachVaultFile(vaultFile);
          return;
        }
      }

      // Fallback 3: OS file drop (or external PDF uri-list)
      await this.handleDataTransferDrop(e.dataTransfer, false);

      // If nothing was added, show the + menu as a helpful fallback
      if (this.pendingContextRefs.length === initialRefs) {
        this.showAddContextMenu(e);
      }
    });
  }

  // ── Chat history / mode ─────────────────────────────────────

  private async loadActiveSession(): Promise<void> {
    const sessions = this.plugin.sessionData.chatSessions ?? [];
    let session =
      sessions.find((s) => s.id === this.plugin.sessionData.activeChatSessionId) ??
      sessions[0];

    if (!session) {
      session = this.createSession();
      this.plugin.sessionData.chatSessions = [session];
      this.plugin.sessionData.activeChatSessionId = session.id;
      await this.plugin.saveSessionData();
    }

    this.plugin.sessionData.activeChatSessionId = session.id;
    this.messages = this.cloneMessages(session.messages);
  }

  private async createNewChatSession(): Promise<void> {
    await this.persistCurrentSession();

    const session = this.createSession();
    this.plugin.sessionData.chatSessions = [
      session,
      ...(this.plugin.sessionData.chatSessions ?? []),
    ].slice(0, 30);
    this.plugin.sessionData.activeChatSessionId = session.id;
    this.messages = [];
    this.pendingContextRefs = [];
    this.plugin.llmClient.abort();
    this.isGenerating = false;
    await this.plugin.saveSessionData();

    this.renderMessages();
    this.renderContextChips();
    this.syncSessionControls();
  }

  private async onSessionChange(sessionId: string): Promise<void> {
    if (!sessionId || sessionId === this.plugin.sessionData.activeChatSessionId) {
      return;
    }

    await this.persistCurrentSession();
    const session = this.plugin.sessionData.chatSessions.find(
      (item) => item.id === sessionId
    );
    if (!session) return;

    this.plugin.llmClient.abort();
    this.isGenerating = false;
    this.plugin.sessionData.activeChatSessionId = session.id;
    this.messages = this.cloneMessages(session.messages);
    this.pendingContextRefs = [];
    await this.plugin.saveSessionData();

    this.renderMessages();
    this.renderContextChips();
    this.syncSessionControls();
  }

  private async onModeChange(mode: ChatMode): Promise<void> {
    this.plugin.settings.chatMode = mode;
    await this.plugin.saveSettings();
  }

  private async onReasoningChange(effort: string): Promise<void> {
    if (this.plugin.settings.provider === "openai") {
      this.plugin.settings.codexReasoningEffort = effort as CodexReasoningEffort;
    } else if (this.plugin.settings.provider === "claude") {
      this.plugin.settings.claudeEffort = effort as any;
    } else {
      this.plugin.settings.agentEffort = effort;
    }
    await this.plugin.saveSettings();
  }

  private async persistCurrentSession(): Promise<void> {
    const activeId = this.plugin.sessionData.activeChatSessionId;
    if (!activeId) return;

    const sessions = this.plugin.sessionData.chatSessions ?? [];
    const session = sessions.find((item) => item.id === activeId);
    if (!session) return;

    session.messages = this.cloneMessages(this.messages);
    session.updatedAt = Date.now();
    session.title = this.getSessionTitle(session);
    this.plugin.sessionData.chatSessions = [
      session,
      ...sessions.filter((item) => item.id !== activeId),
    ].slice(0, 30);
    await this.plugin.saveSessionData();
    this.syncSessionControls();
  }

  private syncSessionControls(): void {
    const sessions = this.plugin.sessionData.chatSessions ?? [];
    const activeSession = sessions.find(s => s.id === this.plugin.sessionData.activeChatSessionId) || sessions[0];
    if (this.activeSessionTitleEl) {
      const title = activeSession ? this.getSessionTitle(activeSession) : "New chat";
      this.activeSessionTitleEl.setText(title);
      this.activeSessionTitleEl.setAttribute("title", title);
    }
    if (this.sessionBtn) {
      this.sessionBtn.toggleClass("is-active", this.sessionDrawerVisible);
    }
    this.renderSessionDrawer();
  }

  private toggleSessionDrawer(): void {
    this.sessionDrawerVisible = !this.sessionDrawerVisible;
    if (this.sessionDrawerVisible) {
      this.sessionDrawerEl.show();
      this.renderSessionDrawer();
      window.setTimeout(() => this.sessionSearchEl?.focus(), 0);
    } else {
      this.hideSessionDrawer();
    }
    this.syncSessionControls();
  }

  private hideSessionDrawer(): void {
    this.sessionDrawerVisible = false;
    this.sessionDrawerEl?.hide();
    this.sessionBtn?.removeClass("is-active");
  }

  private renderSessionDrawer(): void {
    if (!this.sessionDrawerEl) return;
    const listEl = this.sessionDrawerEl.querySelector(".ai-agent-session-drawer-list") as HTMLElement | null;
    if (!listEl) return;
    listEl.empty();

    const sessions = (this.plugin.sessionData.chatSessions ?? []).filter((session) => {
      if (!this.sessionQuery) return true;
      const haystack = [
        this.getSessionTitle(session),
        ...session.messages.slice(-8).map((msg) => msg.content),
      ].join("\n").toLowerCase();
      return haystack.includes(this.sessionQuery);
    });

    if (sessions.length === 0) {
      listEl.createDiv({ cls: "ai-agent-session-drawer-empty", text: "No conversations found." });
      return;
    }

    for (const session of sessions) {
      const isActive = session.id === this.plugin.sessionData.activeChatSessionId;
      const row = listEl.createDiv({
        cls: `ai-agent-session-drawer-row${isActive ? " is-active" : ""}`,
      });
      const icon = row.createSpan("ai-agent-session-drawer-row-icon");
      setIcon(icon, isActive ? "message-circle" : "message-square");
      const body = row.createDiv("ai-agent-session-drawer-row-body");
      const header = body.createDiv("ai-agent-session-drawer-row-meta");
      header.createDiv({
        cls: "ai-agent-session-drawer-row-title",
        text: this.getSessionTitle(session),
      });
      const timestamp = session.updatedAt || session.createdAt;
      header.createDiv({
        cls: "ai-agent-session-drawer-row-time",
        text: formatRelativeSessionTime(timestamp),
        attr: {
          title: Number.isFinite(timestamp)
            ? new Date(timestamp).toLocaleString()
            : "Unknown time",
        },
      });
      body.createDiv({
        cls: "ai-agent-session-drawer-row-preview",
        text: this.sessionPreview(session),
      });
      const del = row.createEl("button", {
        cls: "ai-agent-session-drawer-delete",
        attr: { "aria-label": "Delete conversation", title: "Delete" },
      });
      setIcon(del, "trash-2");
      del.addEventListener("click", async (event) => {
        event.stopPropagation();
        await this.deleteChatSessionById(session.id);
      });
      row.addEventListener("click", () => {
        this.onSessionChange(session.id);
        this.hideSessionDrawer();
      });
    }
  }

  private sessionPreview(session: ChatSession): string {
    const last = [...session.messages].reverse().find((msg) => msg.content.trim());
    if (!last) return "No messages yet";
    const text = last.content.replace(/\s+/g, " ").trim();
    return text.length > 92 ? `${text.slice(0, 92)}...` : text;
  }

  public async deleteChatSessionById(sessionId: string): Promise<void> {
    const sessions = this.plugin.sessionData.chatSessions ?? [];
    const nextSessions = sessions.filter((s) => s.id !== sessionId);
    this.plugin.sessionData.chatSessions = nextSessions;
    this.plugin.sessionData.deletedSessionIds = Array.from(
      new Set([...(this.plugin.sessionData.deletedSessionIds || []), sessionId])
    );

    if (sessionId === this.plugin.sessionData.activeChatSessionId) {
      if (nextSessions.length > 0) {
        this.plugin.sessionData.activeChatSessionId = nextSessions[0].id;
        this.messages = this.cloneMessages(nextSessions[0].messages);
      } else {
        const newSession = this.createSession();
        this.plugin.sessionData.chatSessions = [newSession];
        this.plugin.sessionData.activeChatSessionId = newSession.id;
        this.messages = [];
      }
      this.pendingContextRefs = [];
      this.plugin.llmClient.abort();
      this.isGenerating = false;
      this.renderMessages();
      this.renderContextChips();
    }
    await this.plugin.saveSessionData();
    this.syncSessionControls();
  }

  private async deleteCurrentChatSession(): Promise<void> {
    const activeId = this.plugin.sessionData.activeChatSessionId;
    if (!activeId) return;

    const sessions = this.plugin.sessionData.chatSessions ?? [];
    const session = sessions.find((s) => s.id === activeId);
    if (!session) return;

    const nextSessions = sessions.filter((s) => s.id !== activeId);
    this.plugin.sessionData.chatSessions = nextSessions;
    this.plugin.sessionData.deletedSessionIds = Array.from(
      new Set([...(this.plugin.sessionData.deletedSessionIds || []), activeId])
    );

    if (nextSessions.length > 0) {
      this.plugin.sessionData.activeChatSessionId = nextSessions[0].id;
      this.messages = this.cloneMessages(nextSessions[0].messages);
    } else {
      const newSession = this.createSession();
      this.plugin.sessionData.chatSessions = [newSession];
      this.plugin.sessionData.activeChatSessionId = newSession.id;
      this.messages = [];
    }

    this.pendingContextRefs = [];
    this.plugin.llmClient.abort();
    this.isGenerating = false;
    await this.plugin.saveSessionData();

    new Notice("채팅 내역이 삭제되었습니다.");
    this.renderMessages();
    this.renderContextChips();
    this.syncSessionControls();
  }

  private createSession(): ChatSession {
    const now = Date.now();
    return {
      id: this.generateId(),
      title: "New chat",
      createdAt: now,
      updatedAt: now,
      messages: [],
    };
  }

  private getSessionTitle(session: ChatSession): string {
    return deriveChatSessionTitle(session);
  }

  private cloneMessages(messages: ChatMessage[]): ChatMessage[] {
    return messages.map((message) => ({
      ...message,
      contextRefs: message.contextRefs
        ? message.contextRefs.map((ref) => ({ ...ref }))
        : undefined,
      isStreaming: false,
    }));
  }

  // ── Provider / Model switching ──────────────────────────────

  private async onModelSelectChange(value: string): Promise<void> {
    if (value === CUSTOM_MODEL_VALUE) {
      this.customModelInputEl.show();
      this.customModelInputEl.value = getModelOption(
        this.plugin.getAvailableModels(),
        this.plugin.settings.provider,
        this.plugin.settings.model
      )
        ? ""
        : this.plugin.settings.model;
      this.customModelInputEl.focus();
      return;
    }

    const [providerRaw, model] = value.split("::", 2);
    const provider = providerRaw as LLMProvider;
    const catalogue = this.plugin.getAvailableModels();
    if (provider && catalogue[provider]) {
      this.plugin.settings.provider = provider;
      this.plugin.settings.model = model || getDefaultModel(catalogue, provider);
    } else {
      this.plugin.settings.model =
        value || getDefaultModel(catalogue, this.plugin.settings.provider);
    }
    await this.plugin.saveSettings();
    this.syncModelControls();
    this.restoreInputFocus();
  }

  private async onCustomModelChange(model: string): Promise<void> {
    const catalogue = this.plugin.getAvailableModels();
    this.plugin.settings.model =
      model || getDefaultModel(catalogue, this.plugin.settings.provider);
    await this.plugin.saveSettings();
    this.syncModelControls();
    this.restoreInputFocus();
  }

  public syncModelControls(): void {
    if (!this.modelSelectEl || !this.customModelInputEl) return;

    const provider = this.plugin.settings.provider;
    const currentModel = this.plugin.settings.model;
    const catalogue = this.plugin.getAvailableModels();
    const knownModel = getModelOption(catalogue, provider, currentModel);

    this.modelSelectEl.empty();
    const providerLabels: Record<LLMProvider, string> = {
      antigravity: "Antigravity",
      claude: "Claude",
      openai: "Codex",
      ollama: "Ollama",
      deepseek: "DeepSeek",
    };
    for (const providerKey of Object.keys(catalogue) as LLMProvider[]) {
      const group = this.modelSelectEl.createEl("optgroup", {
        attr: { label: providerLabels[providerKey] },
      });
      for (const option of catalogue[providerKey] || []) {
        group.createEl("option", {
          value: `${providerKey}::${option.id}`,
          text: `${providerLabels[providerKey]} · ${option.label}`,
        });
      }
    }
    this.modelSelectEl.createEl("option", {
      value: CUSTOM_MODEL_VALUE,
      text: "Custom...",
    });

    this.modelSelectEl.value = knownModel ? `${provider}::${currentModel}` : CUSTOM_MODEL_VALUE;
    this.customModelInputEl.value = knownModel ? "" : currentModel;
    if (knownModel) {
      this.customModelInputEl.hide();
    } else {
      this.customModelInputEl.show();
    }

    this.syncReasoningControl();
  }

  public syncReasoningControl(): void {
    if (!this.reasoningSelectEl) return;
    
    this.reasoningSelectEl.empty();
    
    const provider = this.plugin.settings.provider;
    const catalogue = this.plugin.getAvailableModels();
    const currentModelOption = getModelOption(catalogue, provider, this.plugin.settings.model);

    if (currentModelOption?.efforts && currentModelOption.efforts.length > 0) {
      this.reasoningSelectEl.setAttribute("aria-label", "Reasoning effort");
      this.reasoningSelectEl.setAttribute("title", "Reasoning effort level");
      
      currentModelOption.efforts.forEach((e) => {
        this.reasoningSelectEl.createEl("option", { 
          value: e, 
          text: e.charAt(0).toUpperCase() + e.slice(1) 
        });
      });
      
      const getOldVal = () => {
         if (provider === "openai") return this.plugin.settings.codexReasoningEffort;
         if (provider === "claude") return this.plugin.settings.claudeEffort;
         return this.plugin.settings.agentEffort;
      };
      const rawVal = getOldVal();
      const val = currentModelOption.efforts.includes(rawVal) ? rawVal : (currentModelOption.defaultEffort || currentModelOption.efforts[0]);
      
      this.reasoningSelectEl.value = val;
      this.reasoningSelectEl.show();
    } else {
      this.reasoningSelectEl.hide();
    }
  }

  // ── Utils ───────────────────────────────────────────────────

  private isNearBottom(threshold: number = 150): boolean {
    if (!this.messagesContainer) return true;
    return (
      this.messagesContainer.scrollHeight -
        this.messagesContainer.scrollTop -
        this.messagesContainer.clientHeight <=
      threshold
    );
  }

  private scrollToBottom(force: boolean = false): void {
    requestAnimationFrame(() => {
      if (!this.messagesContainer) return;
      if (force || this.isNearBottom()) {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
      }
    });
  }

  private restoreInputFocus(): void {
    window.setTimeout(() => {
      requestAnimationFrame(() => {
        if (!this.inputEl || this.isGenerating) return;
        this.inputEl.disabled = false;
        this.inputEl.focus();
      });
    }, 0);
  }

  private generateId(): string {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  }

  private fileToBase64(file: File | Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        // Strip data:...;base64, prefix
        resolve(result.replace(/^data:[^;]+;base64,/, ""));
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  private arrayBufferToBase64(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }
}
