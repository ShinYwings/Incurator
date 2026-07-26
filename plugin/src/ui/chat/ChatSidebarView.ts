import { logger } from "../../utils/logger";
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
  FileSystemAdapter,
} from "obsidian";
import { existsSync, readdirSync, readFileSync, statSync } from "fs";
import { join } from "path";
import type ObsidianAIAgent from "../../../main";
import { IncuratorClient } from "../../agent/incuratorClient";
import {
  EXTERNAL_PDF_CONTEXT_EVENT,
  EXTERNAL_PDF_VIEW_TYPE,
  ExternalPdfView,
} from "../externalPdfView";
import {
  registerExternalPdf,
} from "../externalPdfRegistry";
import {
  assetStatusKey,
  resolveAssetSource,
  zoteroConfigEpoch,
  ZoteroPathCache,
} from "../../context/assetSource";
import { isAddedState } from "../../context/sourceStatus";
import { IngestDestinationModal } from "../ingestDestinationModal";
import { getPdfContext, withVisionFallback } from "../../context/pdfCapture";
import { attachLatexCopyHandler, collapseStreamingEditBlocks, normalizeLatexDelimiters, stampMathSourceData, stripDanglingEditMarkers, truncateToLength } from "../../utils/textUtils";
import { inferIngestDestination } from "../../utils/pathUtils";
import { hashFileSha256 } from "../../utils/fileHash";
import { classifyProposalStatus, findSearchBlock, findSearchBlockAvoiding } from "../../utils/editMatch";
import { buildContinuationPrompt, stitchContinuation } from "../../utils/streamContinuation";
import { DiffViewer } from "../diffViewer";
import { renderCuratorQueryTrace } from "../incuratorQueryTrace";
import {
  escapeAttribute,
  formatCuratorContextPack,
  formatIncuratorHits,
  formatOutline,
  formatPdfWindow,
  formatRagHits,
} from "../../context/providerContextFormat";
import { buildBaseSystemPrompt, editableSelectionInstruction, getEditLoopContract, wrapLatestUserMessageForLanguageBridge } from "../../context/systemPrompt";
import { buildRecencyAnchor, SIDECHAT_PROFILE } from "../../context/promptRegistry";
import { parseEditLoopPhases, validateEditLoop, type EditLoopParse } from "../../context/editLoopContract";
import { detectLanguage } from "../../context/languageBridge";
import {
  deriveChatSessionTitle,
  formatRelativeSessionTime,
} from "../../context/chatSessionSummary";
import {
  contextPriorityInstruction,
  contextPromptLabel,
  hasPrimaryUserContext,
  includedContextRefs,
  isPrimaryUserContext,
  shouldIncludeContext,
  shouldSuppressEditAffordances,
} from "../../context/chatContextPriority";
import { buildMarkdownOutline } from "../../context/quickQueryContext";
import {
  buildOpenTabContextKey,
  shouldIncludeOpenTab,
} from "../../context/openTabContext";
import { parseAnswerLinkTarget, type AnswerLinkTarget } from "../../context/answerLinkNavigation";
import { resolveSelectionReferencesBlock } from "../../context/pdfReferenceContext";
import {
  shouldRunCuratorDomainQuery,
  shouldUseBackendPdfContext,
} from "../../context/providerContextPolicy";
import {
  detectGitSidechatCommand,
  type GitSidechatCommand,
} from "../gitSidechatCommands";
import {
  type ChatMessage,
  type ChatMode,
  type ChatSession,
  type CodexReasoningEffort,
  type ContextRef,
  type CuratorQueryResult,
  type CuratorFeedbackType,
  type IncuratorSourceStatus,
  type LLMMessage,
  type LLMContentPart,
  type OpenTabContext,
  type PdfPageContext,
  type LLMProvider,
  type StreamChunk,
  getDefaultModel,
  getModelOption,
  modelSupportsVision,
  normalizePluginModelEffort,
} from "../../types";

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
  private activeContextExcludedKeys: Set<string> = new Set();
  private activeContextIncludedKeys: Set<string> = new Set();
  private isGenerating = false;
  private thinkingTimer: ReturnType<typeof setInterval> | null = null;
  private thinkingStartTime = 0;
  private splitDropOverlay: HTMLElement | null = null;
  private splitDropSide: "left" | "right" | "top" | "bottom" | "center" = "center";
  private splitDropTarget: WorkspaceLeaf | null = null;
  private incuratorClient: IncuratorClient | null = null;
  private incuratorStatusByPath = new Map<string, IncuratorSourceStatus>();
  // In-memory Zotero attachment_key -> absPath cache (Plan G item c). Invalidated
  // by config epoch + missing file; cleared on view unload (never persisted).
  private zoteroPathCache = new ZoteroPathCache({ fileExists: (p) => existsSync(p) });
  private incuratorStatusInFlight = new Set<string>();
  private fileHashByPath = new Map<string, string>();
  private prepareStatusText = "";
  private lastQueryTrace: CuratorQueryResult | null = null;
  // Bug 2 (v0.14.1): serialize diff-review opens so a second pill click cannot
  // re-point the singleton DiffViewer mid-open (file-switch race).
  private reviewInFlight = false;
  /** Canonical path of the file whose review is currently opening (P4b coalesce). */
  private reviewInFlightTarget: string | null = null;
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
    this.registerEvent(
      this.app.workspace.on("layout-change", () => {
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
        // Preserve the physical asset identity (Plan G item d): an external image
        // must keep its OS/vault path so backend asset routing is not severed.
        // Electron's File carries `.path` at runtime though the DOM type omits it.
        filePath: explicitPath ?? (file as { path?: string }).path,
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
    try {
      await this.plugin.assertActivePluginBundle();
    } catch (error) {
      new Notice(error instanceof Error ? error.message : String(error));
      return;
    }

    // Guard: Ollama requires a model name before sending
    if (this.plugin.settings.provider === "ollama" && !this.plugin.settings.model.trim()) {
      new Notice("Ollama: no model selected. Go to Settings → AI Provider and enter a model name (e.g. qwen2.5:7b).");
      return;
    }

    this.lastQueryTrace = null;
    const capturedActiveCtx = this.plugin.refreshActiveContext();
    // v0.28.0: snapshot the refs to send THIS turn before non-pinned ones are
    // cleared below, but DON'T materialize (crop VLM / image work) yet — that is
    // deferred to AFTER the thinking indicator renders so Send never freezes
    // (fixes the v0.27.9 residual block). Chips render now from the raw refs.
    const pendingForSend = this.pendingContextRefs;
    const contextRefs = [
      ...this.buildAutoContextRefs(capturedActiveCtx),
      ...pendingForSend,
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
    // Render the thinking indicator NOW, before the deferred materialize await,
    // so Send is instant. Reset prepareStatusText so the "Thinking… (Ns)" timer
    // starts fresh even if a prior send errored out with a stale status.
    this.prepareStatusText = "";
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

    this.isGenerating = true;
    setIcon(this.sendBtn, "square");
    this.sendBtn.setAttribute("aria-label", "Stop generating");

    try {
      // Deferred crop materialization runs HERE, during the visible thinking
      // phase (vision → keep image, no backend round-trip; non-vision →
      // transcribe). Refresh the user message's refs with the materialized
      // content before building the LLM payload.
      this.setPrepareStatus("Preparing context...");
      const materialized = await this.materializeContextRefs(pendingForSend);
      const finalRefs = [
        ...this.buildAutoContextRefs(capturedActiveCtx),
        ...materialized,
      ].filter(shouldIncludeContext);
      userMsg.contextRefs = finalRefs.length > 0 ? finalRefs : undefined;
      await this.persistCurrentSession();
      const llmMessages = await this.buildLLMMessages(capturedActiveCtx);
      this.prepareStatusText = "";
      await this.streamAssistantWithContinuation(llmMessages, assistantMsg);
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

  /** Max auto-continuation rounds for an output-token-truncated answer (v0.24.0). */
  private static readonly MAX_CONTINUATIONS = 3;

  /**
   * Stream the assistant answer, auto-continuing when the provider stops on its
   * output-token cap (`finish_reason: "length"` / Gemini `MAX_TOKENS`). The
   * message stays `isStreaming` across every round so the edit pills and
   * `maybeAutoOpenDiff` only fire AFTER truncation is fully resolved — never on
   * an in-flight partial (reviewer #5). Continuations are spliced with overlap
   * de-dup so the model re-emitting its tail does not corrupt the edit block.
   */
  private async streamAssistantWithContinuation(
    llmMessages: LLMMessage[],
    assistantMsg: ChatMessage
  ): Promise<void> {
    let truncated = await this.streamOneRound(llmMessages, assistantMsg, true, "");
    if (truncated) {
      truncated = await this.runContinuationRounds(
        llmMessages,
        assistantMsg,
        assistantMsg.continuationsDone ?? 0
      );
    }
    // Still truncated after the cap → leave the flag set so the render path can
    // offer a manual "Continue" button. A fully-resolved answer clears it.
    assistantMsg.truncated = truncated;
    assistantMsg.isStreaming = false;
    this.renderAssistantMessage(assistantMsg);
  }

  /**
   * Issue continuation requests until the answer stops truncating, the round cap
   * is hit, or a round adds zero new text (stuck-model guard). Each round appends
   * the current partial as an assistant turn + a continuation user turn, then
   * splices the new stream onto the partial with overlap de-dup. Returns whether
   * the answer is STILL truncated after the loop.
   */
  private async runContinuationRounds(
    llmMessages: LLMMessage[],
    assistantMsg: ChatMessage,
    startRounds: number
  ): Promise<boolean> {
    let rounds = startRounds;
    let truncated = true;
    while (truncated && rounds < ChatSidebarView.MAX_CONTINUATIONS) {
      // Stop spawning continuation requests if the user hit "Stop generating"
      // (isGenerating cleared) — otherwise an aborted turn keeps burning tokens.
      if (!this.isGenerating) break;
      rounds++;
      const base = assistantMsg.content;
      const continuationMessages: LLMMessage[] = [
        ...llmMessages,
        { role: "assistant", content: base },
        { role: "user", content: buildContinuationPrompt(base) },
      ];
      truncated = await this.streamOneRound(continuationMessages, assistantMsg, false, base);
      assistantMsg.continuationsDone = rounds;
      // Zero-delta guard: a continuation that added nothing new means the model
      // is stuck — stop rather than spin to the cap (red_teamer #1).
      if (assistantMsg.content === base) break;
    }
    return truncated;
  }

  /**
   * Manual "Continue" fallback used when auto-continue exhausted its rounds and
   * the answer is still cut off. Rebuilds the conversation, drops the trailing
   * assistant turn (re-added as the continuation base), and resumes with a fresh
   * round budget. Never runs while another generation is in flight.
   */
  private async continueTruncatedMessage(assistantMsg: ChatMessage): Promise<void> {
    if (this.isGenerating || assistantMsg.isStreaming) return;
    this.isGenerating = true;
    setIcon(this.sendBtn, "square");
    this.sendBtn.setAttribute("aria-label", "Stop generating");
    assistantMsg.isStreaming = true;
    assistantMsg.truncated = false;
    try {
      // buildLLMMessages serializes the WHOLE active session. If the user clicked
      // Continue on an OLD truncated message, everything after it would leak into
      // the prompt out of order. Temporarily slice the history to end at this
      // message, then restore it (the object ref is shared, so streamed deltas
      // still land on the right message).
      const allMessages = this.messages;
      const idx = allMessages.indexOf(assistantMsg);
      let built: LLMMessage[];
      try {
        if (idx >= 0) this.messages = allMessages.slice(0, idx + 1);
        built = await this.buildLLMMessages(this.plugin.refreshActiveContext());
      } finally {
        this.messages = allMessages;
      }
      // buildLLMMessages includes the truncated assistant as the final turn;
      // drop it so runContinuationRounds re-adds it as the continuation base.
      const last = built[built.length - 1];
      const llmMessages =
        last && last.role === "assistant" ? built.slice(0, -1) : built;
      const truncated = await this.runContinuationRounds(llmMessages, assistantMsg, 0);
      assistantMsg.truncated = truncated;
    } catch (err) {
      assistantMsg.content += `\n\n❌ Continue failed: ${err instanceof Error ? err.message : String(err)}`;
    } finally {
      assistantMsg.isStreaming = false;
      this.isGenerating = false;
      setIcon(this.sendBtn, "send");
      this.sendBtn.setAttribute("aria-label", "Send message");
      this.renderMessages(false);
      await this.maybeAutoOpenDiff(assistantMsg);
      await this.persistCurrentSession();
    }
  }

  /**
   * One streaming pass. The first round appends deltas directly; continuation
   * rounds accumulate into a local buffer and splice onto `base` each tick so
   * the live view de-duplicates the seam. Returns whether THIS round ended on a
   * truncation. Never flips `isStreaming` (the caller owns finalization).
   */
  private async streamOneRound(
    messages: LLMMessage[],
    assistantMsg: ChatMessage,
    isFirstRound: boolean,
    base: string
  ): Promise<boolean> {
    let truncated = false;
    let continuationBuf = "";
    await this.plugin.llmClient.streamChat(messages, (chunk: StreamChunk) => {
      if (chunk.truncated) truncated = true;
      if (chunk.text) {
        if (isFirstRound) {
          assistantMsg.content += chunk.text;
        } else {
          continuationBuf += chunk.text;
          assistantMsg.content = stitchContinuation(base, continuationBuf);
        }
      }
      this.renderAssistantMessage(assistantMsg);
    });
    return truncated;
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
    // Localized-question edit-affordance suppression (v0.21.0): when the latest
    // turn is a primary-focus selection asked as a question (not an edit request),
    // omit BOTH the editable-selection affordance and the edit-review-loop contract
    // so the recency anchor's "answer only, do not modify the document" is unopposed.
    const suppressEditAffordances = shouldSuppressEditAffordances({
      hasPrimarySelection: lastUserHasPrimaryContext,
      isEditRequest: latestIsMarkdownEditRequest,
    });
    const editInstruction = suppressEditAffordances
      ? ""
      : editableSelectionInstruction(
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

    const promptTabs = this.getPromptIncludedTabs(activeCtx);
    if (promptTabs.length > 0) {
      const tabLines = promptTabs
        .map((tab) => {
          const marker = tab.isActive ? "*" : "-";
          const path = tab.filePath ? ` (${tab.filePath})` : "";
          return `${marker} ${tab.label} [${tab.viewType}]${path}`;
        })
        .join("\n");
      systemText += `\n\nOpen Obsidian tabs (* = active):\n${tabLines}`;

      const nonActiveMdTabs = promptTabs.filter(
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

      const markdownOutlines = promptTabs
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

    const activeTabIncluded = promptTabs.some((tab) => tab.isActive);
    if (activeCtx?.filePath && activeTabIncluded) {
      const displayPath = activeCtx.absolutePath || activeCtx.filePath;
      systemText += `\n\nCurrently active file: ${displayPath}`;
    }
    if (activeCtx?.viewType === "pdf" && activeCtx.pdfPage && activeTabIncluded) {
      systemText += `\n\nThe user is viewing a PDF. Current page: ${activeCtx.pdfPage.pageNum}`;
    }

    // Edit-loop contract (v0.14.0): append LAST so it sits at the position of
    // strongest LLM attention. Triggered for any edit-likely turn — a Markdown
    // edit request, an editable selection, an open Markdown edit target, or a
    // multi-turn continuation of an edit loop the previous answer already opened.
    const priorAnswerOpenedEditLoop = (() => {
      for (let i = this.messages.length - 1; i >= 0; i--) {
        const msg = this.messages[i];
        if (msg.role === "assistant") return validateEditLoop(msg.content).hasEdits;
      }
      return false;
    })();
    const editLoopLikely =
      !suppressEditAffordances &&
      (latestIsMarkdownEditRequest ||
        editableRefs.length > 0 ||
        Boolean(openMarkdownEditTargets) ||
        priorAnswerOpenedEditLoop);
    if (editLoopLikely) {
      systemText += `\n\n<edit_review_loop>\n${getEditLoopContract()}\n</edit_review_loop>`;
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

      let textContent =
        msg === lastUserMessage
          ? wrapLatestUserMessageForLanguageBridge(msg.content, detectLanguage(msg.content))
          : msg.content;
      if (msg === lastUserMessage) {
        // Recency anchor (v0.19.0): re-assert the surface invariants at the very
        // end of the payload so a localized selection (e.g. Cmd+Shift+L) asked
        // about late in a long session is not overridden by earlier whole-file
        // tasks. Appended to the latest user turn, which always survives the
        // CONTINUITY_MESSAGE_LIMIT history slice.
        textContent +=
          "\n\n" +
          buildRecencyAnchor(SIDECHAT_PROFILE, {
            hasPrimarySelection: lastUserHasPrimaryContext,
          });
      }
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
    const tabs = this.getPromptIncludedTabs(activeCtx);
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
      lines.push(`Prompt-included context: ${autoRefs.map((ref) => ref.label).join(", ")}`);
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
    const pdfTabs = this.getPromptIncludedTabs(activeCtx).filter(
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
      let sourceStatus = this.incuratorStatusByPath.get(this.refStatusKey(statusRef));
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
        this.setPrepareStatus("Fetching Incurator evidence pack...");
        const packLimit = Math.max(
          1000,
          Math.min(16000, Math.floor((this.plugin.settings.maxContextLength || 128000) * 0.18))
        );
        const contextPack = await this.timedContextCall(
          "curator_context_fetch",
          wsPath || "default",
          () => client.fetchContext(query, {
            workspacePath: wsPath,
            limitTokens: packLimit,
          })
        );
        if (contextPack.ok) {
          sections.push(formatCuratorContextPack(contextPack, query));
          this.lastQueryTrace = {
            ok: true,
            question: query,
            route: contextPack.route as CuratorQueryResult["route"],
            trace_id: contextPack.trace_id,
            pack_id: contextPack.pack_id,
            snapshot: contextPack.snapshot,
            budget: contextPack.budget,
            source_span_ids: contextPack.source_span_ids,
            community_report_ids: contextPack.community_report_ids,
            synthesis_node_ids: contextPack.synthesis_node_ids,
            memory_path_ids: contextPack.memory_path_ids,
            warnings: contextPack.warnings,
            context_pack: contextPack,
            trace: {
              matched_concepts: [],
              source_ids: [],
              source_paths: [],
              trace_id: contextPack.trace_id,
              route: contextPack.route,
              pack_id: contextPack.pack_id,
              snapshot: contextPack.snapshot,
              budget: contextPack.budget,
              prompt_trace_ids: [],
              source_span_ids: contextPack.source_span_ids,
              latency_ms: 0,
              l3_complete: true,
            },
          };
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
    logger.debug(`${label} ${elapsedMs}ms`, subject);
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
    if (ref.openTabKey) return ref.openTabKey;
    const viewType =
      ref.sourceViewType && ref.sourceViewType !== "auto"
        ? ref.sourceViewType
        : ref.type === "file"
          ? "markdown"
          : ref.type;
    return buildOpenTabContextKey({
      viewType,
      filePath: ref.filePath,
      label: ref.label.replace(/ p\.\d+$/, ""),
      pageNum: ref.pageNum,
    });
  }

  private getOpenTabKey(tab: OpenTabContext): string {
    return buildOpenTabContextKey({
      viewType: tab.viewType,
      sourceIdentity: tab.sourceIdentity,
      filePath: tab.filePath,
      label: tab.label,
      pageNum: tab.pageNum,
    });
  }

  private isOpenTabReady(tab: OpenTabContext): boolean {
    if (tab.viewType === "markdown") return tab.content !== undefined;
    return Boolean(tab.pdfPage);
  }

  private shouldIncludeOpenTabContext(tab: OpenTabContext): boolean {
    const key = this.getOpenTabKey(tab);
    return shouldIncludeOpenTab({
      isVisible: tab.isVisible,
      isReady: this.isOpenTabReady(tab),
      explicitlyIncluded: this.activeContextIncludedKeys.has(key),
      explicitlyExcluded: this.activeContextExcludedKeys.has(key),
    });
  }

  private getPromptIncludedTabs(
    activeCtx: ReturnType<ObsidianAIAgent["refreshActiveContext"]>
  ): OpenTabContext[] {
    return (activeCtx?.openTabs ?? []).filter((tab) =>
      this.shouldIncludeOpenTabContext(tab)
    );
  }

  private buildAutoContextRefs(
    activeCtx: ReturnType<ObsidianAIAgent["refreshActiveContext"]>
  ): ContextRef[] {
    if (!activeCtx?.openTabs) return [];

    const refs: ContextRef[] = [];
    const seen = new Set<string>();

    for (const tab of activeCtx.openTabs) {
      let ref: ContextRef | null = null;
      const openTabKey = this.getOpenTabKey(tab);
      const autoContextReady = this.isOpenTabReady(tab);
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
          openTabKey,
          autoContextReady,
        };
      } else if (tab.viewType === "pdf" || tab.viewType === EXTERNAL_PDF_VIEW_TYPE) {
        if (!tab.pdfPage) {
          ref = {
            type: "pdf-page",
            label: tab.pageNum ? `${tab.label} p.${tab.pageNum}` : tab.label,
            content: "",
            filePath: tab.filePath,
            pageNum: tab.pageNum,
            sourceViewType: "auto",
            openTabKey,
            autoContextReady: false,
          };
        } else {
          let finalContent = tab.pdfPage.text
            ? this.truncateContext(tab.pdfPage.text)
            : "(No extractable text on this page. If you need visual information, please attach the image manually.)";

          const hasTextSelection = tab.selectedText && tab.selectedText.trim();
          const hasImageSelection = Boolean(
            tab.pdfPage.selectedImageBase64 ||
            (tab.pdfPage.isScannedLike && tab.pdfPage.imageBase64)
          );

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
            openTabKey,
            autoContextReady,
            // Only send the full page image if the PDF is scanned (vision fallback).
            // Otherwise, only send an explicitly cropped image (if any).
            imageBase64: tab.pdfPage.selectedImageBase64 || (tab.pdfPage.isScannedLike ? tab.pdfPage.imageBase64 : undefined),
          };
        }
      }

      if (!ref) continue;
      const key = this.getAutoContextKey(ref);
      if (seen.has(key)) continue;
      ref.includeInPrompt = this.shouldIncludeOpenTabContext(tab);
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

  private createPinnedPdfRef(tab: OpenTabContext): ContextRef | null {
    const pdfCtx = tab.pdfPage;
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
      openTabKey: this.getOpenTabKey(tab),
    };
  }

  /** Whether the active MAIN chat model can receive images (vision-capable). */
  private mainChatModelSupportsVision(): boolean {
    return modelSupportsVision(
      this.plugin.getAvailableModels(),
      this.plugin.settings.provider,
      this.plugin.settings.model
    );
  }

  private async materializeContextRefs(refs: ContextRef[]): Promise<ContextRef[]> {
    return Promise.all(
      refs.map(async (ref) => {
        let out = ref.isPinned ? await this.refreshPinnedContextRef(ref) : { ...ref };

        // Deferred handling for PDF crops captured instantly via Cmd+Shift+X.
        // v0.28.0: when the MAIN chat model is vision-capable, pass the crop image
        // DIRECTLY (it flows through the CLI scoped-Read image channel) instead of a
        // redundant backend transcribe round-trip that — in the default config —
        // resolves to the same provider. regionText stays as a caption. A non-vision
        // main model still transcribes to text (its only channel). Either branch runs
        // AFTER the thinking indicator renders (handleSend), so Send never blocks.
        if (out.pendingCropBase64) {
          if (!this.mainChatModelSupportsVision()) {
            const extracted = await this.plugin.transcribePdfCrop(out.pendingCropBase64);
            if (extracted?.latex) {
              out.content = extracted.latex;
              // Text-only model: drop the image it cannot use; LaTeX is the channel.
              out.imageBase64 = undefined;
            }
          }
          // Vision path keeps out.imageBase64 + out.content (regionText) as-is.
          // Clear the pending flag so a pinned crop won't re-run on resend.
          ref.pendingCropBase64 = undefined;
          delete out.pendingCropBase64;
        }

        return out;
      })
    );
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

  /**
   * Promote the given answer into a durable 02_Wiki/ page (explicit user action
   * from the Sources & Trace panel). Passes the trace's source_span_ids so the
   * promoted page lists its source documents, making them appear in Obsidian's
   * Graph view / Backlinks.
   */
  private async promoteAnswerToWiki(
    result: CuratorQueryResult,
    msg: ChatMessage
  ): Promise<void> {
    // Resolve the question from the user message immediately preceding THIS
    // answer, never the newest one globally — otherwise promoting a historical
    // answer would pair it with an unrelated later question.
    const msgIndex = this.messages.indexOf(msg);
    const searchSlice = msgIndex >= 0 ? this.messages.slice(0, msgIndex) : this.messages;
    const lastUser = [...searchSlice].reverse().find((m) => m.role === "user");
    const question = (result.question || lastUser?.content || "").trim();
    const answer = (msg.content || "").trim();
    if (!question || !answer) {
      new Notice("Nothing to promote yet — ask a question first.");
      return;
    }
    const workspacePath = (this.app.vault.adapter as any).getBasePath?.() || "";
    new Notice("Saving answer to 02_Wiki…");
    const res = await this.getIncuratorClient().promoteAnswer(
      question,
      answer,
      workspacePath,
      result.source_span_ids
    );
    if (res.ok) {
      new Notice(`Saved to ${res.promoted_to || "02_Wiki"}.`);
    } else {
      new Notice(`Save to 02_Wiki failed: ${res.error || "unknown error"}`);
    }
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

  /**
   * Single canonical key for the backend source-status map (Plan G, audit
   * item 3). Identity-first (Zotero key before any resolved path) so the badge
   * reader and the post-ingest writer always agree, even when a Zotero PDF's
   * local path only becomes known after the add completes.
   */
  private refStatusKey(ref: ContextRef): string {
    return assetStatusKey({
      absPath: this.getPdfRefSourcePath(ref),
      relpath: ref.filePath,
      zoteroKey: ref.zoteroAttachmentKey,
      fileHash: ref.fileHash,
      displayName: (ref.label || "source").replace(/ p\.\d+$/, ""),
      resolutionStatus: "resolved",
    });
  }

  /** Config epoch for the Zotero path cache (Plan G item c). Any change to the
   * Zotero data dir, active vault, or profile asset roots invalidates the cache.
   *
   * Device-aware: absolute paths differ per machine/OS (macOS `/Users/...` vs
   * Linux `/home/...`, and `~` expands per home dir). The epoch folds in the
   * platform and the OS-resolved base path so a cache (in-memory and per-device
   * already) can never serve a path resolved for a different device/OS. Synced
   * absolute paths are never trusted — they are re-resolved here per device. */
  private zoteroCacheEpoch(): string {
    return zoteroConfigEpoch({
      workspaceId: this.app.vault.getName(),
    });
  }

  private async resolvePdfRefSourcePath(ref: ContextRef, status?: IncuratorSourceStatus): Promise<string | undefined> {
    const direct = this.getPdfRefSourcePath(ref) || status?.sourcePath || status?.currentPath;
    if (direct) return direct;
    if (!ref.zoteroAttachmentKey) return undefined;
    const client = this.getIncuratorClient();
    // Route Zotero resolution through the cached resolver (item c): a cache hit
    // skips repeated backend round-trips within this process.
    let lastResolution: Awaited<ReturnType<typeof client.resolveZoteroPdf>> | undefined;
    const resolved = await resolveAssetSource(
      {
        zoteroKey: ref.zoteroAttachmentKey,
        displayName: (ref.label || "source").replace(/ p\.\d+$/, ""),
      },
      {
        resolveZoteroViaBackend: async (key) => {
          lastResolution = await client.resolveZoteroPdf(key);
          return lastResolution.ok && lastResolution.path ? lastResolution.path : undefined;
        },
        cache: this.zoteroPathCache,
        epoch: this.zoteroCacheEpoch(),
        fileExists: (p) => existsSync(p),
      }
    );
    if (resolved.absPath) return resolved.absPath;
    if (lastResolution) {
      this.plugin.openZoteroRepairModal({ attachmentKey: ref.zoteroAttachmentKey, resolution: lastResolution });
      new Notice(`Zotero PDF unavailable: ${lastResolution.error || lastResolution.state || "backend could not resolve attachment"}`);
    } else {
      new Notice("Zotero PDF unavailable: backend offline and no local copy found.");
    }
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
    this.incuratorStatusByPath.set(this.refStatusKey(ref), status);
    ref.backendStatus = status;
    return status;
  }

  private renderIncuratorStatusBadge(
    chip: HTMLElement,
    ref: ContextRef
  ): void {
    if (ref.type !== "pdf-page" || this.plugin.settings.incuratorEnabled === false) return;

    const sourcePath = this.getPdfRefSourcePath(ref);
    const statusKey = this.refStatusKey(ref);
    const cached = this.incuratorStatusByPath.get(statusKey) || ref.backendStatus;
    const badge = chip.createSpan("ai-agent-context-chip-status");
    this.updateIncuratorStatusBadge(
      badge,
      cached || { state: sourcePath || ref.zoteroAttachmentKey ? "unknown" : "untracked" }
    );

    badge.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const fallback: IncuratorSourceStatus = { state: "unknown", sourcePath };
      const latest =
        this.incuratorStatusByPath.get(statusKey) ||
        ref.backendStatus ||
        cached ||
        fallback;
      this.onIncuratorStatusClick(ref, latest);
    });

    // Refresh for any resolvable identity — including a Zotero PDF whose local
    // path is not yet known (audit item 3: badge must not stay stale).
    if (sourcePath || ref.zoteroAttachmentKey) {
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
    const statusKey = this.refStatusKey(ref);
    if (this.incuratorStatusInFlight.has(statusKey)) return;

    this.incuratorStatusInFlight.add(statusKey);
    try {
      const status = await this.ensureIncuratorStatusForRef(ref);
      this.incuratorStatusByPath.set(statusKey, status);
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
      this.incuratorStatusInFlight.delete(statusKey);
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
    // Single canonical key (Plan G item 3): same key as the badge reader, stable
    // for a Zotero source whether or not its local path is resolved yet.
    const statusKey = this.refStatusKey(ref);
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
      this.incuratorStatusByPath.set(statusKey, nextStatus);
      ref.backendStatus = nextStatus;
      this.renderContextChips();
      if (nextStatus.state === "error" || nextStatus.state === "unknown") {
        new Notice(`Zotero reference registration failed: ${nextStatus.message || "backend did not return a usable source status"}`);
      } else {
        new Notice("Zotero PDF registered as an external reference.");
      }
      return;
    }

    // Zotero-managed PDFs: skip modal, auto-register as reference. Zotero identity
    // is a DURABLE property of the context ref (AssetSource.zoteroKey), never
    // inferred by scanning open UI leaves — so it still resolves after the PDF
    // tab is closed, and there is no `as any` view-state probing (Plan G item 4).
    const isZoteroPdf = Boolean(ref.zoteroAttachmentKey);
    if (isZoteroPdf) {
      const pendingStatus: IncuratorSourceStatus = {
        state: "running",
        sourcePath,
        message: "Adding Zotero PDF as an Incurator reference source...",
      };
      this.incuratorStatusByPath.set(statusKey, pendingStatus);
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
      this.incuratorStatusByPath.set(statusKey, nextStatus);
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
        this.incuratorStatusByPath.set(statusKey, pendingStatus);
        ref.backendStatus = pendingStatus;
        this.renderContextChips();
        const nextStatus = await this.getIncuratorClient().ingestPdf({
          sourcePath: nonZoteroSourcePath,
          displayName: ref.label.replace(/ p\.\d+$/, ""),
          destinationRelpath,
          importMode,
        });
        this.incuratorStatusByPath.set(statusKey, nextStatus);
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
      const applyLabel = updateClient.updateActionLabel || "Run Setup";
      let reloadReady = false;

      btn.addEventListener("click", async () => {
        if (reloadReady) {
          window.location.reload();
          return;
        }
        btn.disabled = true;
        btn.setText("Running setup...");
        const updateReady = await this.plugin.updateIncuratorBackend();
        btn.disabled = false;
        if (updateReady) {
          reloadReady = true;
          btn.setText("Reload Obsidian");
        } else {
          btn.setText(applyLabel);
        }
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
    if (msg.id !== undefined) msgEl.dataset.msgId = msg.id;

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
      // Edit-loop state machine (v0.14.0): a conforming edit answer renders as
      // observable Analysed/Reviewed/Updated/Reviewed phase sections with the
      // diff anchored under UPDATED. A non-conforming (loop-skipping) answer is
      // hard-gated: prose + a blocked banner, no auto-review pills.
      const loop = validateEditLoop(msg.content);
      const phaseParse = parseEditLoopPhases(msg.content);

      if (phaseParse.phases.length > 0 && loop.ok) {
        this.renderEditLoopPhases(contentEl, msg, multiProposals, phaseParse);
      } else {
        remainingContent = this.stripEditBlocksFromText(remainingContent, multiProposals).trim();

        const mdWrapper = contentEl.createDiv("ai-agent-markdown-wrapper");
        if (remainingContent) {
          const processedContent = this.processMarkdownForThoughts(remainingContent, false);
          this.renderAssistantMarkdown(processedContent, mdWrapper);
        }

        // v0.24.0: loop demoted to a hint. When the model skipped the review
        // loop we show a soft, non-blocking note (with an optional re-run), but
        // the edit pills ALWAYS render so the diff is reviewable.
        if (loop.hasEdits && !loop.ok) {
          this.renderEditLoopHint(contentEl);
        }
        for (const prop of multiProposals) {
          this.renderInlineMultiDiff(contentEl, prop, msg, multiProposals);
        }
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

    // Resolve THIS message's trace from its own embedded curator_query result, so
    // re-rendering history never reuses one global trace for every message. The
    // live singleton (this.lastQueryTrace) is only the streaming fallback for the
    // active/terminal message (whose trace isn't embedded yet while it streams).
    let traceToRender: CuratorQueryResult | null = null;
    const toolMatch = msg.content.match(/✅ \*\*mcp_[^*]*curator_query\*\* result:\n```(?:json)?\n([\s\S]*?)\n```/);
    if (toolMatch) {
      try {
        const parsed = JSON.parse(toolMatch[1]);
        if (parsed.trace || parsed.trace_id) {
          traceToRender = parsed;
        }
      } catch { }
    }
    const isLastMessage =
      this.messages.length > 0 && msg === this.messages[this.messages.length - 1];
    if (isLastMessage) {
      if (traceToRender) {
        this.lastQueryTrace = traceToRender;
      } else {
        traceToRender = this.lastQueryTrace;
      }
    }
    if (traceToRender) {
      // Promote is safe on any message (it reads this message's own trace). The
      // mutating pack actions (expand/verify/refetch/feedback) are gated to the
      // active message only — historical panels are inert so they cannot corrupt
      // the live query state via the singleton.
      const boundTrace = traceToRender;
      const promoteOpts = {
        onPromote: () => void this.promoteAnswerToWiki(boundTrace, msg),
        interactive: isLastMessage,
      };
      const thoughtBlock = contentEl.querySelector("details.ai-agent-thought-block");
      const panelEl = (thoughtBlock as HTMLElement) ?? contentEl;
      renderCuratorQueryTrace(panelEl, boundTrace as any, this.app, promoteOpts);
      if (isLastMessage) {
        this.attachContextTraceActionHandlers(panelEl);
      }
    }
    window.setTimeout(() => this.attachAssistantAnswerLinkNavigation(contentEl), 0);
    attachLatexCopyHandler(contentEl, htmlToMarkdown);

    // v0.24.0: answer still cut off by the output-token cap after auto-continue
    // exhausted its rounds — offer an explicit manual Continue.
    if (!msg.isStreaming && msg.truncated) {
      this.renderTruncationContinue(contentEl, msg);
    }
  }

  /** Render the "answer was cut off" notice + manual Continue button (v0.24.0). */
  private renderTruncationContinue(contentEl: HTMLElement, msg: ChatMessage): void {
    const banner = contentEl.createDiv("ai-agent-truncation-continue");
    banner.createSpan({
      cls: "ai-agent-truncation-continue-text",
      text: "⚠️ The model hit its output-token limit and the answer is still cut off.",
    });
    const btn = banner.createEl("button", {
      cls: "ai-agent-truncation-continue-btn",
      text: "↪ Continue",
      attr: { title: "Ask the model to resume from where it stopped" },
    });
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (this.isGenerating) {
        new Notice("Already generating — wait for the current turn to finish.");
        return;
      }
      void this.continueTruncatedMessage(msg);
    });
  }

  private attachContextTraceActionHandlers(container: HTMLElement): void {
    const marked = container as HTMLElement & { __incuratorTraceActionsBound?: boolean };
    if (marked.__incuratorTraceActionsBound) return;
    marked.__incuratorTraceActionsBound = true;
    container.addEventListener("context:expand", (event) => {
      this.handleContextTraceAction("context:expand", event as CustomEvent);
    });
    container.addEventListener("context:verify", (event) => {
      this.handleContextTraceAction("context:verify", event as CustomEvent);
    });
    container.addEventListener("context:refetch", (event) => {
      this.handleContextTraceRefetch(event as CustomEvent);
    });
    container.addEventListener("context:feedback", (event) => {
      this.handleContextTraceFeedback(event as CustomEvent);
    });
  }

  private async handleContextTraceFeedback(event: CustomEvent): Promise<void> {
    event.stopPropagation();
    const detail = (event.detail || {}) as {
      trace_id?: string;
      pack_id?: string;
      feedback_type?: CuratorFeedbackType;
      item_id?: string;
      reviewed_span_ids?: string[];
    };
    if (!detail.trace_id || !detail.pack_id || !detail.feedback_type) {
      new Notice("Feedback is missing trace, pack, or type metadata.");
      return;
    }

    const client = this.getIncuratorClient();
    if (!client.available) {
      new Notice("Incurator backend is not available.");
      return;
    }

    const workspacePath = (this.app.vault.adapter as any).getBasePath?.() || "";
    const recorded = await client.feedbackContext({
      traceId: detail.trace_id,
      packId: detail.pack_id,
      feedbackType: detail.feedback_type,
      statement: `User marked evidence ${detail.item_id ?? ""} as ${detail.feedback_type}.`,
      client: "obsidian",
      purpose: "ground",
      targetItemId: detail.item_id,
      targetRecordId: detail.item_id,
      reviewedSpanIds: detail.reviewed_span_ids,
      workspacePath,
    });
    new Notice(
      recorded.ok
        ? "Feedback recorded."
        : recorded.error || "Recording feedback failed."
    );
  }

  private async handleContextTraceAction(
    action: "context:expand" | "context:verify",
    event: CustomEvent
  ): Promise<void> {
    event.stopPropagation();
    const detail = (event.detail || {}) as {
      pack_id?: string;
      snapshot_id?: string;
      handle?: string;
    };
    if (!detail.pack_id || !detail.snapshot_id || !detail.handle) {
      new Notice("Context action is missing pack, snapshot, or handle metadata.");
      return;
    }

    const client = this.getIncuratorClient();
    if (!client.available) {
      new Notice("Incurator backend is not available.");
      return;
    }

    const workspacePath = (this.app.vault.adapter as any).getBasePath?.() || "";
    const packLimit = Math.max(
      1000,
      Math.min(16000, Math.floor((this.plugin.settings.maxContextLength || 128000) * 0.18))
    );
    if (action === "context:expand") {
      const expanded = await client.expandContext({
        packId: detail.pack_id,
        handles: [detail.handle],
        expectedSnapshotId: detail.snapshot_id,
        workspacePath,
        limitTokens: packLimit,
      });
      this.mergeContextExpansion(expanded, detail.handle);
      this.markContextSnapshotConflict(expanded);
      new Notice(expanded.ok ? "Context evidence expanded." : this.contextActionError(expanded, "Context expansion failed."));
    } else {
      const verified = await client.verifyContext({
        packId: detail.pack_id,
        verificationHandle: detail.handle,
        expectedSnapshotId: detail.snapshot_id,
        workspacePath,
      });
      this.mergeContextVerification(verified, detail.handle);
      this.markContextSnapshotConflict(verified);
      new Notice(verified.ok ? "Context evidence verified." : this.contextActionError(verified, "Context verification failed."));
    }
    this.renderMessages(false);
  }

  private async handleContextTraceRefetch(event: CustomEvent): Promise<void> {
    event.stopPropagation();
    const query = this.lastQueryTrace?.question || "";
    if (!query.trim()) {
      new Notice("Context refetch needs the original question.");
      return;
    }
    const client = this.getIncuratorClient();
    if (!client.available) {
      new Notice("Incurator backend is not available.");
      return;
    }
    const workspacePath = (this.app.vault.adapter as any).getBasePath?.() || "";
    const packLimit = Math.max(
      1000,
      Math.min(16000, Math.floor((this.plugin.settings.maxContextLength || 128000) * 0.18))
    );
    const refreshed = await client.fetchContext(query, {
      workspacePath,
      limitTokens: packLimit,
    });
    if (!refreshed.ok) {
      new Notice(refreshed.error || "Context refetch failed.");
      return;
    }
    this.replaceContextPack(refreshed);
    new Notice("Context evidence refreshed.");
    this.renderMessages(false);
  }

  private mergeContextExpansion(expanded: Awaited<ReturnType<IncuratorClient["expandContext"]>>, handle: string): void {
    const pack = this.lastQueryTrace?.context_pack;
    if (!pack || !expanded.ok) return;
    const existing = new Set((pack.items || []).map((item) => item.record_id));
    pack.items = [
      ...(pack.items || []),
      ...((expanded.items || []).filter((item) => !existing.has(item.record_id))),
    ];
    pack.next = (pack.next || []).filter((entry) => entry.handle !== handle);
    pack.warnings = [...(pack.warnings || []), ...(expanded.warnings || [])];
  }

  private mergeContextVerification(verified: Awaited<ReturnType<IncuratorClient["verifyContext"]>>, handle: string): void {
    const pack = this.lastQueryTrace?.context_pack;
    if (!pack || !verified.ok || !verified.item) return;
    pack.items = (pack.items || []).map((item) => {
      if (item.verification_handle === handle) {
        return { ...item, ...verified.item };
      }
      return item;
    });
  }

  private contextActionError(pack: Awaited<ReturnType<IncuratorClient["expandContext"]>>, fallback: string): string {
    if (pack.error_type === "snapshot_conflict" || pack.operation === "snapshot_conflict") {
      return "Context snapshot changed. Refetch the evidence pack.";
    }
    return pack.error || fallback;
  }

  private markContextSnapshotConflict(pack: Awaited<ReturnType<IncuratorClient["expandContext"]>>): void {
    if (pack.error_type !== "snapshot_conflict" && pack.operation !== "snapshot_conflict") return;
    const current = this.lastQueryTrace?.context_pack;
    if (!current || !this.lastQueryTrace) return;
    this.lastQueryTrace.context_pack = {
      ...current,
      ...pack,
      ok: false,
      operation: "snapshot_conflict",
      pack_id: current.pack_id,
      snapshot: current.snapshot,
      budget: current.budget,
      items: current.items,
      next: current.next,
      warnings: [
        ...(current.warnings || []),
        ...(pack.warnings || []),
        "snapshot_conflict: refetch required before expanding or verifying this pack",
      ],
    };
  }

  private replaceContextPack(pack: Awaited<ReturnType<IncuratorClient["fetchContext"]>>): void {
    if (!this.lastQueryTrace) return;
    this.lastQueryTrace.context_pack = pack;
    this.lastQueryTrace.route = pack.route as CuratorQueryResult["route"];
    this.lastQueryTrace.trace_id = pack.trace_id;
    this.lastQueryTrace.pack_id = pack.pack_id;
    this.lastQueryTrace.snapshot = pack.snapshot;
    this.lastQueryTrace.budget = pack.budget;
    this.lastQueryTrace.source_span_ids = pack.source_span_ids;
    this.lastQueryTrace.community_report_ids = pack.community_report_ids;
    this.lastQueryTrace.synthesis_node_ids = pack.synthesis_node_ids;
    this.lastQueryTrace.memory_path_ids = pack.memory_path_ids;
    this.lastQueryTrace.warnings = pack.warnings;
    this.lastQueryTrace.trace = {
      ...(this.lastQueryTrace.trace || {
        matched_concepts: [],
        source_ids: [],
        source_paths: [],
        latency_ms: 0,
        l3_complete: true,
      }),
      trace_id: pack.trace_id,
      route: pack.route,
      pack_id: pack.pack_id,
      snapshot: pack.snapshot,
      budget: pack.budget,
      source_span_ids: pack.source_span_ids,
    };
  }

  private attachAssistantAnswerLinkNavigation(container: HTMLElement): void {
    const links = Array.from(container.querySelectorAll<HTMLAnchorElement>("a"));
    for (const link of links) {
      const href = link.getAttribute("data-href") ?? link.getAttribute("href");
      const target = parseAnswerLinkTarget(href, link.textContent || "");
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
    if (target.kind === "vault") {
      this.app.workspace.openLinkText(target.linkpath, "", false);
      return;
    }

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

  // Bug 27: resolveVaultFile decodes path before checking; Bug 2: each pill routes to its own target
  private renderInlineMultiDiff(
    container: HTMLElement,
    prop: MultiEditProposal,
    msg: ChatMessage,
    allProposals: MultiEditProposal[]
  ): void {
    // Bug 27: Use resolveVaultFile to handle URL-encoded or leading-slash paths
    const file = this.resolveVaultFile(prop.filepath);
    const wrapper = container.createDiv("ai-agent-applied-change");

    let isNewFile = false;
    if (!file) {
      if (prop.search.includes("<<< NEW FILE >>>") || prop.search.trim() === "") {
        isNewFile = true;
      } else {
        const errEl = wrapper.createSpan({ cls: "ai-agent-applied-change-error" });
        errEl.setText(`⚠ File not found: ${prop.filepath}`);
        return;
      }
    }

    const header = wrapper.createDiv("ai-agent-applied-change-header");
    header.createSpan({ cls: "ai-agent-applied-change-icon", text: isNewFile ? "📄" : "✏️" });
    const nameEl = header.createSpan({ cls: "ai-agent-applied-change-name" });
    nameEl.setText(prop.filepath);
    nameEl.title = "Review edit in editor";
    let proposalStatus: "reviewable" | "applied" | "not_found" = "reviewable";

    // Bug 2: Wire "Review in file" directly to reviewFileEditProposals for this target
    const reviewInEditor = async () => {
      const opened = await this.reviewFileEditProposals(prop.filepath, allProposals);
      if (!opened) return;
      statusBtn.setText("🔍 Opened Diff");
      statusBtn.style.color = "var(--text-accent)";
      statusBtn.style.borderColor = "var(--text-accent)";
      statusBtn.style.background = "transparent";
    };

    wrapper.style.cursor = "pointer";
    // Bug 9 follow-up: once live status says applied/not_found, suppress the
    // wrapper and button click handlers before they can run a doomed SEARCH.
    wrapper.addEventListener("click", (e) => {
      if (proposalStatus === "reviewable") return;
      e.preventDefault();
      e.stopImmediatePropagation();
    }, { capture: true });
    wrapper.addEventListener("click", async (e) => {
      e.stopPropagation();
      await reviewInEditor();
    });

    const statusBtn = header.createEl("button", {
      cls: "ai-agent-applied-status",
      text: "🔍 Review in file",
      attr: { title: "Click to open Diff Viewer" },
    });
    statusBtn.style.color = "var(--text-muted)";
    statusBtn.style.borderColor = "var(--background-modifier-border)";
    statusBtn.style.background = "transparent";
    statusBtn.style.cursor = "pointer";
    statusBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      await reviewInEditor();
    });

    // Bug 9 (v0.14.1): derive the pill status from the LIVE file so a proposal
    // that was already accepted (or never matched) reads honestly instead of
    // surfacing "could not find" only after a wasted click.
    if (!isNewFile && file) {
      void this.app.vault.cachedRead(file).then((content) => {
        if (!wrapper.isConnected) return;
        const status = classifyProposalStatus(content, prop.search, prop.replace);
        proposalStatus = status;
        if (status === "applied") {
          statusBtn.setText("✓ Applied");
          statusBtn.style.color = "var(--text-success, var(--text-accent))";
          statusBtn.title = "This edit already appears in the file";
        } else if (status === "not_found") {
          statusBtn.setText("⚠ Not found");
          statusBtn.style.color = "var(--text-error)";
          statusBtn.title = "The SEARCH text no longer matches this file";
        }
      });
    }
  }

  /** Remove `ai-agent-edit` proposal blocks from prose so they never render raw. */
  private stripEditBlocksFromText(text: string, proposals: MultiEditProposal[]): string {
    let out = text;
    for (const prop of proposals) {
      const escaped = prop.originalBlock.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const withTicks = new RegExp(`\`\`\`(?:\\w+)?\\n?${escaped}\\n?\`\`\``, "g");
      if (withTicks.test(out)) {
        out = out.replace(withTicks, "");
      } else {
        out = out.replace(prop.originalBlock, "");
      }
    }
    return out;
  }

  /**
   * Render a conforming edit answer as observable phase sections (v0.14.0).
   * Each `[[PHASE:...]]` segment becomes a labeled collapsible block; the diff
   * review pills are anchored inside the UPDATED phase.
   */
  private renderEditLoopPhases(
    contentEl: HTMLElement,
    msg: ChatMessage,
    multiProposals: MultiEditProposal[],
    phaseParse: EditLoopParse
  ): void {
    const content = msg.content;
    const phases = phaseParse.phases;

    const preamble = content.slice(0, phases[0].index).trim();
    if (preamble) {
      const pre = contentEl.createDiv("ai-agent-markdown-wrapper");
      this.renderAssistantMarkdown(this.processMarkdownForThoughts(preamble, false), pre);
    }

    let reviewSeen = 0;
    let diffsRendered = false;
    for (let i = 0; i < phases.length; i++) {
      const marker = `[[PHASE:${phases[i].label}]]`;
      const bodyStart = phases[i].index + marker.length;
      const bodyEnd = i + 1 < phases.length ? phases[i + 1].index : content.length;
      const body = content.slice(bodyStart, bodyEnd);

      let labelText: string;
      if (phases[i].label === "ANALYSED") labelText = "🔍 Analysed";
      else if (phases[i].label === "UPDATED") labelText = "✏️ Updated";
      else labelText = ++reviewSeen === 1 ? "🪞 Reviewed (plan)" : "✅ Reviewed (result)";

      const section = contentEl.createEl("details", {
        cls: "ai-agent-edit-phase",
        attr: { open: "", "data-phase": phases[i].label },
      });
      section.createEl("summary", { text: labelText });
      const sectionBody = section.createDiv("ai-agent-edit-phase-body");

      const prose = this.stripEditBlocksFromText(body, multiProposals).trim();
      if (prose) {
        this.renderAssistantMarkdown(this.processMarkdownForThoughts(prose, false), sectionBody);
      }
      // Render the diff pills once, under the first UPDATED phase only — a
      // model emitting multiple UPDATED markers must not duplicate the pills.
      if (phases[i].label === "UPDATED" && !diffsRendered) {
        diffsRendered = true;
        for (const prop of multiProposals) {
          this.renderInlineMultiDiff(sectionBody, prop, msg, multiProposals);
        }
      }
    }
  }

  /**
   * Render a soft, non-blocking hint shown when an edit answer skipped the
   * Analysed→Reviewed→Updated→Reviewed loop (v0.24.0). The edits are still fully
   * reviewable (pills render below); this only offers an optional re-run for
   * users who want the model's self-review. Replaces the old hard-gate banner
   * that suppressed the diff entirely.
   */
  private renderEditLoopHint(contentEl: HTMLElement): void {
    const hint = contentEl.createDiv("ai-agent-edit-loop-hint");
    hint.createSpan({
      cls: "ai-agent-edit-loop-hint-text",
      text: "ℹ️ The model skipped its self-review steps. The edits below are still reviewable.",
    });
    const rerunBtn = hint.createEl("button", {
      cls: "ai-agent-edit-loop-rerun",
      text: "Re-run with review",
      attr: { title: "Ask the model to redo the answer with Analysed → Reviewed → Updated → Reviewed" },
    });
    rerunBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (this.isGenerating) return;
      this.inputEl.value =
        "Redo your previous answer following the edit-review loop: " +
        "emit [[PHASE:ANALYSED]], [[PHASE:REVIEWED]], [[PHASE:UPDATED]] (with the ai-agent-edit blocks), then [[PHASE:REVIEWED]].";
      void this.handleSend();
    });
  }

  // Bug 15: autoApplyProposals deleted — was a workaround that bypassed DiffViewer

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
    // Strip edit-loop phase sentinels (v0.14.0) so a marker never renders as raw
    // text in fallback paths; conforming answers render them as phase sections.
    let processed = stripDanglingEditMarkers(this.normalizeLatexDelimiters(content))
      .replace(/\[\[PHASE:(?:ANALYSED|REVIEWED|UPDATED)\]\]/g, "");
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

    // Bug 30: Use resolveVaultFile for path normalization; proxy multi-edits to reviewFileEditProposals
    const file = this.resolveVaultFile(ref.filePath);
    if (!file) {
      new Notice(`Could not find ${ref.filePath}`);
      return;
    }

    if (multiProposals.length > 0) {
      // Bug 2, 30: Route all multi-edit proposals through the target-isolated router
      await this.reviewFileEditProposals(ref.filePath, multiProposals);
      return;
    }

    // Legacy single-range edit path (unchanged)
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
      leaf = this.app.workspace.getLeaf("tab");
      await (leaf as WorkspaceLeaf).openFile(file, { active: true });
      const newVs = (leaf as WorkspaceLeaf).getViewState();
      await (leaf as WorkspaceLeaf).setViewState({
        ...newVs,
        state: { ...newVs.state, mode: "source" },
      });
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
    const start = { line: Math.max(0, (ref.lineStart ?? 1) - 1), ch: 0 };
    const endLine = Math.max(0, (ref.lineEnd ?? ref.lineStart ?? 1) - 1);
    const lineText = editor.getLine(endLine);
    const end = { line: endLine, ch: lineText?.length ?? 0 };
    const originalText = editor.getRange(start, end);
    const replacementText = modifiedText || "";

    // Bug 30: Use Singleton instead of new DiffViewer()
    const result = DiffViewer.getInstance(this.plugin).show(targetLeaf.view, originalText, replacementText, start, end);
    if (!result.opened) {
      new Notice(
        result.reason === "no_changes"
          ? "The proposed edit already matches the file — nothing to review."
          : "The editor was not ready to show the diff. Try clicking Review again.",
        8000
      );
    }
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

    // v0.24.0: the four-phase review loop is now a QUALITY HINT, not a hard gate.
    // A valid, matchable edit is always reviewable regardless of whether a weak
    // model emitted the [[PHASE:...]] markers — the old gate left token-limited
    // and low-instruction-following models with "I made an edit" but no diff.

    const files = new Set(proposals.map((p) => {
      const f = this.resolveVaultFile(p.filepath);
      return f ? f.path : p.filepath;
    }));
    if (files.size !== 1) return;
    const target = proposals[0].filepath;
    // Bug 28: use resolveVaultFile for consistent path normalization
    const file = this.resolveVaultFile(target);
    const isNewFile = proposals.some(p => p.search.includes("<<< NEW FILE >>>") || p.search.trim() === "");
    if (!file && !isNewFile) return;

    const active = this.app.workspace.getActiveViewOfType(MarkdownView);
    if (active && active.file?.path !== target) return; // different note focused → keep pill

    // Bug 28: route through reviewFileEditProposals, not the broken reviewAssistantEdit
    msg.diffAutoOpened = await this.reviewFileEditProposals(target, proposals);
  }

  // Bug 32: Strips absolute filesystem paths and URL-encoding before vault lookup
  private resolveVaultFile(raw: string): TFile | null {
    // Reviewer fix 3: Normalize backslashes to forward slashes for Windows paths
    let normalized = raw.replace(/\\/g, "/");
    const adapter = this.app.vault.adapter;
    if (adapter instanceof FileSystemAdapter) {
      const basePath = adapter.getBasePath().replace(/\\/g, "/");
      if (normalized.startsWith(basePath)) {
        normalized = normalized.slice(basePath.length);
        if (normalized.startsWith("/")) normalized = normalized.slice(1);
      }
    }
    const candidates = [
      normalized,
      normalized.trim(),
      normalized.startsWith("/") ? normalized.slice(1) : normalized,
    ];
    try {
      candidates.push(decodeURIComponent(normalized), decodeURIComponent(normalized.trim()));
    } catch { /* safely ignore URIError */ }
    for (const path of candidates) {
      const f = this.app.vault.getAbstractFileByPath(path);
      if (f instanceof TFile) return f;
    }

    // Bug 7 (v0.14.1): final fallback — case-insensitive, whitespace-trimmed
    // match by FULL path over the vault's Markdown files. This covers case drift
    // and trailing spaces that exact path lookup misses. We deliberately do NOT
    // fall back to a basename-only match: a same-named file in a different folder
    // is a different note, and resolving to it would silently retarget the edit.
    const wantPath = normalized.trim().toLowerCase().replace(/^\/+/, "");
    const byPath = this.app.vault.getMarkdownFiles().find((f) => f.path.toLowerCase() === wantPath);
    return byPath ?? null;
  }

  // Bug 2 (v0.14.1): serialize opens so a second pill click cannot re-point the
  // singleton DiffViewer while the first open is still awaiting (file-switch race).
  // Returns true only when a diff was actually opened, so callers don't mislabel
  // a guard-dropped or unmatched click as "opened".
  private async reviewFileEditProposals(targetFilepath: string, allProposals: MultiEditProposal[]): Promise<boolean> {
    const resolvedTarget = this.resolveVaultFile(targetFilepath)?.path ?? targetFilepath;
    if (this.reviewInFlight) {
      // v0.24.0 (P4b): auto-open (at stream end) holds this mutex through the
      // 2-frame CM6 mount; a pill click for the SAME file in that window used to
      // pop a scary "already opening" error. Coalesce same-target races silently
      // — the in-flight open is already doing exactly what the click wanted. Only
      // a genuinely different target gets the advisory notice.
      if (resolvedTarget !== this.reviewInFlightTarget) {
        new Notice("A diff review is already opening — try again in a moment.");
      }
      return false;
    }
    this.reviewInFlight = true;
    this.reviewInFlightTarget = resolvedTarget;
    try {
      return await this.reviewFileEditProposalsImpl(targetFilepath, allProposals);
    } finally {
      this.reviewInFlight = false;
      this.reviewInFlightTarget = null;
    }
  }

  // Bugs 26, 34: Target-isolated routing with Source-Mode Mounting and failure tracking
  private async reviewFileEditProposalsImpl(targetFilepath: string, allProposals: MultiEditProposal[]): Promise<boolean> {
    let file = this.resolveVaultFile(targetFilepath);

    // Reviewer fix 4: Filter proposals by canonical vault path
    const fileProposals = allProposals.filter(p => {
      const pFile = this.resolveVaultFile(p.filepath);
      return (pFile && file) ? (pFile.path === file.path) : (p.filepath === targetFilepath);
    });

    // Reviewer fix 1: Detect new file proposal and initialize it as empty
    if (!file) {
      const isNewFile = fileProposals.some(p => p.search.includes("<<< NEW FILE >>>") || p.search.trim() === "");
      if (isNewFile) {
        try {
          file = await this.app.vault.create(targetFilepath, "");
          new Notice(`Created new file for review: ${targetFilepath}`);
        } catch (e) {
          new Notice(`Failed to create new file: ${targetFilepath}`);
          return false;
        }
      } else {
        new Notice(`File not found: ${targetFilepath}`);
        return false;
      }
    }

    // Bug 26: Find an existing source-mode leaf or open one with 2-frame CM6 mount delay
    let leaf: WorkspaceLeaf | null = null;
    this.app.workspace.iterateAllLeaves((l) => {
      if (leaf || l === this.leaf) return;
      const v = l.view;
      const vs = l.getViewState();
      if (v instanceof MarkdownView && v.file?.path === file.path && vs.state?.mode === "source") {
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
    if (!(targetLeaf.view instanceof MarkdownView)) return false;
    const editor = targetLeaf.view.editor;

    const originalFullText = editor.getValue();

    // v0.24.0 (P4b): match every proposal against the ORIGINAL text (not the
    // running result), so applying edit 1 can no longer break edit 2's SEARCH —
    // the old order-dependent cascade that surfaced spurious "could not be
    // matched" warnings on multi-edit answers. We then compose non-overlapping
    // splices and distinguish three outcomes: applied, true overlap-conflict,
    // and genuine not-found.
    const spans: Array<{ start: number; end: number; replace: string }> = [];
    let notFoundCount = 0;
    let conflictCount = 0;
    for (const proposal of fileProposals) {
      // Skip spans already claimed by earlier proposals, so two edits targeting
      // different occurrences of the same SEARCH string both resolve (the second
      // advances past the first occurrence instead of self-overlapping).
      const match = findSearchBlockAvoiding(originalFullText, proposal.search, spans);
      if (match) {
        spans.push({ start: match.start, end: match.end, replace: proposal.replace });
        continue;
      }
      // Distinguish a genuine miss (SEARCH not in the file) from a true overlap
      // conflict (every occurrence is already claimed by another edit).
      if (findSearchBlock(originalFullText, proposal.search)) conflictCount++;
      else notFoundCount++;
    }

    const appliedCount = spans.length;
    if (appliedCount > 0) {
      // Splice right-to-left so earlier offsets stay valid.
      spans.sort((a, b) => b.start - a.start);
      let modifiedFullText = originalFullText;
      for (const s of spans) {
        modifiedFullText = modifiedFullText.slice(0, s.start) + s.replace + modifiedFullText.slice(s.end);
      }

      const skipped = notFoundCount + conflictCount;
      if (skipped > 0) {
        const parts: string[] = [];
        if (notFoundCount > 0) parts.push(`${notFoundCount} not found in the file`);
        if (conflictCount > 0) parts.push(`${conflictCount} overlapping another edit`);
        new Notice(`Reviewing ${appliedCount} change(s); skipped ${skipped} (${parts.join(", ")}).`, 8000);
      }

      // Bug 21: Provide correct selectionEnd for API compatibility
      const lastLine = Math.max(0, editor.lineCount() - 1);
      const selectionEnd = { line: lastLine, ch: editor.getLine(lastLine)?.length ?? 0 };
      // Bug 30: Singleton prevents DOM/listener leaks
      const result = DiffViewer.getInstance(this.plugin).show(
        targetLeaf.view,
        originalFullText,
        modifiedFullText,
        { line: 0, ch: 0 },
        selectionEnd
      );
      if (!result.opened) {
        // v0.24.0: no more silent failure — surface exactly why nothing opened.
        new Notice(
          result.reason === "no_changes"
            ? "The proposed edit already matches the file — nothing to review."
            : "The editor was not ready to show the diff. Try clicking Review again.",
          8000
        );
        return false;
      }
      if (skipped === 0) {
        new Notice(`Reviewing ${appliedCount} proposed change${appliedCount === 1 ? "" : "s"} in ${file.basename}`);
      }
      return true;
    } else {
      new Notice(
        conflictCount > 0
          ? "All proposed edits overlapped each other — none could be applied."
          : "Could not find the SEARCH text in the target Markdown file (the model's quoted lines did not match).",
        8000
      );
      return false;
    }
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
    const byId = msg.id !== undefined
      ? this.messagesContainer.querySelector<HTMLElement>(`[data-msg-id="${msg.id}"]`)
      : null;
    const allMsgEls = this.messagesContainer.querySelectorAll(
      ".ai-agent-chat-msg-assistant"
    );
    const targetEl = byId ?? allMsgEls[allMsgEls.length - 1];

    if (targetEl) {
      const roleEl = targetEl.querySelector(".ai-agent-chat-msg-role");
      if (roleEl) {
        this.renderAssistantMessageActions(roleEl, msg);
      }
      const contentEl = targetEl.querySelector(".ai-agent-chat-msg-content");
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
    try {
    if (!this.contextChipsContainer) return;
    this.contextChipsContainer.empty();

    const activeCtx = this.plugin.refreshActiveContext();
    const freshAutoRefs = this.buildAutoContextRefs(activeCtx);
    const autoRefs = freshAutoRefs;

    // Auto context chips show every open Markdown/PDF tab, including hidden leaves.
    for (const ref of autoRefs) {
      let isSuppressed = false;
      for (const pinned of this.pendingContextRefs) {
        // Text/line-range/selections never suppress the full file auto chip
        if (pinned.type === "line-range" || pinned.type === "text" || pinned.type === "selection") continue;
        
        // Explicit PDF crops/selections never suppress the full PDF page auto chip
        if (pinned.type === "pdf-page" && pinned.label && (pinned.label.includes("(Crop)") || pinned.label.includes("(Selection)"))) continue;

        // If it's a full file or full PDF page pin, check if it matches this auto chip
        if (this.getAutoContextKey(pinned) === this.getAutoContextKey(ref)) {
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
          this.activeContextIncludedKeys.delete(activeKey);
          this.activeContextExcludedKeys.add(activeKey);
        } else {
          if (ref.autoContextReady === false) {
            new Notice(
              "This tab is not ready for context capture. Select the tab once, then try again."
            );
            return;
          }
          this.activeContextExcludedKeys.delete(activeKey);
          this.activeContextIncludedKeys.add(activeKey);
        }
        this.renderContextChips();
      });
      const removeBtn = chip.createSpan({ cls: "ai-agent-context-chip-remove", text: "×" });
      removeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        this.activeContextIncludedKeys.delete(activeKey);
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
    } catch (err) {
      logger.warn("renderContextChips failed:", err);
    }
  }

  private showAddContextMenu(e: MouseEvent): void {
    const openTabs = this.plugin.refreshActiveContext()?.openTabs ?? [];
    const addableTabs = openTabs.filter(
      (tab) =>
        !this.pendingContextRefs.some(
          (ref) => this.getAutoContextKey(ref) === this.getOpenTabKey(tab)
        )
    );

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
              if (ref) {
                this.addContextRef(ref);
              } else {
                new Notice(
                  "This tab is not ready for context capture. Select the tab once, then try again."
                );
              }
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
    // Normalize effort in-memory first so both model + effort are saved together.
    this.syncModelControls(true);
    await this.plugin.saveSettings();
    this.restoreInputFocus();
  }

  private async onCustomModelChange(model: string): Promise<void> {
    const catalogue = this.plugin.getAvailableModels();
    this.plugin.settings.model =
      model || getDefaultModel(catalogue, this.plugin.settings.provider);
    this.syncModelControls(true);
    await this.plugin.saveSettings();
    this.restoreInputFocus();
  }

  public syncModelControls(persist: boolean = false): void {
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

    this.syncReasoningControl(persist);
  }

  public syncReasoningControl(persist: boolean = false): void {
    if (!this.reasoningSelectEl) return;
    
    this.reasoningSelectEl.empty();
    
    const provider = this.plugin.settings.provider;
    const catalogue = this.plugin.getAvailableModels();
    const currentModelOption = getModelOption(catalogue, provider, this.plugin.settings.model);
    normalizePluginModelEffort(this.plugin.settings, catalogue, persist);

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
