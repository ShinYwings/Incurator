import {
  Plugin,
  WorkspaceLeaf,
  MarkdownView,
  MarkdownFileInfo,
  Notice,
  Editor,
} from "obsidian";
import {
  type PluginSettings,
  type ActiveContext,
  type ContextRef,
  type LLMProvider,
  type OpenTabContext,
  DEFAULT_SETTINGS,
  DEFAULT_MODELS,
  getModelOption,
} from "./src/types";
import { AIAgentSettingTab } from "./src/settings";
import { CLIAuthResolver } from "./src/auth/cliAuth";
import { LLMClient } from "./src/agent/llmClient";
import { MCPManager } from "./src/agent/mcpClient";
import { ChatSidebarView, CHAT_VIEW_TYPE } from "./src/ui/chatSidebar";
import {
  ExternalPdfView,
  EXTERNAL_PDF_VIEW_TYPE,
} from "./src/ui/externalPdfView";
import { InlinePromptWidget } from "./src/ui/inlinePrompt";
import {
  getPdfContext,
  getPdfSelection,
  withVisionFallback,
} from "./src/context/pdfCapture";

export default class ObsidianAIAgent extends Plugin {
  settings: PluginSettings = DEFAULT_SETTINGS;
  authResolver: CLIAuthResolver = new CLIAuthResolver();
  llmClient!: LLMClient;
  mcpManager: MCPManager = new MCPManager();
  inlinePrompt!: InlinePromptWidget;

  private activeContext: ActiveContext = { viewType: "other" };
  // Last non-chat leaf — preserved so context survives sidebar focus changes
  private lastContentLeaf: WorkspaceLeaf | null = null;

  async onload(): Promise<void> {
    console.log("Loading Obsidian AI Agent plugin");

    // ── Load settings ──
    await this.loadSettings();

    // ── Initialize core services ──
    const vaultRoot = (this.app.vault.adapter as any).getBasePath?.() || "";
    this.llmClient = new LLMClient(
      this.settings,
      this.authResolver,
      vaultRoot,
      () => this.saveData(this.settings)
    );
    this.inlinePrompt = new InlinePromptWidget(this);

    // ── Register settings tab ──
    this.addSettingTab(new AIAgentSettingTab(this.app, this));

    // ── Register chat sidebar view ──
    this.registerView(CHAT_VIEW_TYPE, (leaf: WorkspaceLeaf) => {
      return new ChatSidebarView(leaf, this);
    });

    this.registerView(EXTERNAL_PDF_VIEW_TYPE, (leaf: WorkspaceLeaf) => {
      return new ExternalPdfView(leaf);
    });

    // ── Ribbon icon (left sidebar) ──
    this.addRibbonIcon("bot", "Open AI Agent Chat", () => {
      this.toggleChatSidebar();
    });

    // ── Register commands ──

    // Cmd+K: Inline edit
    this.addCommand({
      id: "inline-edit",
      name: "Inline Edit (Cmd+K)",
      editorCallback: (_editor: Editor, ctx: MarkdownView | MarkdownFileInfo) => {
        if (ctx instanceof MarkdownView) {
          this.inlinePrompt.open(ctx);
        }
      },
      hotkeys: [{ modifiers: ["Mod"], key: "k" }],
    });

    // Cmd+Shift+L: Line reference → chat
    this.addCommand({
      id: "line-reference",
      name: "Add Reference to Chat",
      checkCallback: (checking: boolean) => {
        const leaf = this.app.workspace.getMostRecentLeaf();
        if (!leaf) return false;
        
        const view = leaf.view;
        if (view instanceof MarkdownView) {
          if (!checking) {
            this.addLineReference(view.editor, view);
          }
          return true;
        } else if (view.getViewType() === EXTERNAL_PDF_VIEW_TYPE || view.getViewType() === "pdf") {
          if (!checking) {
            let selectedText = window.getSelection()?.toString().trim();
            this.ensureChatOpen().then(() => {
              const chatView = this.getChatView();
              if (!chatView) return;

              if (selectedText) {
                chatView.addContextRef({
                  type: "text",
                  label: "Selected Text",
                  content: selectedText,
                });
              } else if (view.getViewType() === EXTERNAL_PDF_VIEW_TYPE) {
                const pdfView = view as ExternalPdfView;
                const pdfCtx = withVisionFallback(
                  pdfView.getActivePdfContext(this.settings.pdfCaptureMode),
                  this.settings.pdfCaptureMode,
                  this.settings.pdfVisionFallback,
                  () => pdfView.getActivePdfContext("image")?.imageBase64
                );
                if (pdfCtx) {
                  chatView.addContextRef({
                    type: "pdf-page",
                    label: `${pdfView.getDisplayText()} p.${pdfCtx.pageNum}`,
                    content: pdfCtx.text,
                    imageBase64: pdfCtx.imageBase64,
                    pageNum: pdfCtx.pageNum,
                  });
                }
              }
            });
          }
          return true;
        }
        return false;
      },
      hotkeys: [{ modifiers: ["Mod", "Shift"], key: "l" }],
    });

    // Cmd+Shift+X: Snip PDF Region to Chat
    this.addCommand({
      id: "snip-pdf-to-chat",
      name: "Snip PDF Region to Chat",
      checkCallback: (checking: boolean) => {
        const leaf = this.app.workspace.getMostRecentLeaf();
        if (!leaf) return false;
        
        const view = leaf.view;
        if (view.getViewType() === EXTERNAL_PDF_VIEW_TYPE) {
          if (!checking) {
            const pdfView = view as ExternalPdfView;
            pdfView.startSnippingMode((base64: string, pageNum: number) => {
              this.ensureChatOpen().then(() => {
                const chatView = this.getChatView();
                if (chatView) {
                  chatView.addContextRef({
                    type: "image",
                    label: `${pdfView.getDisplayText()} p.${pageNum} (Crop)`,
                    content: "",
                    imageBase64: base64,
                  });
                }
              });
            });
          }
          return true;
        }
        return false;
      },
      hotkeys: [{ modifiers: ["Mod", "Shift"], key: "x" }],
    });

    // Cmd+Shift+;: Toggle chat sidebar
    this.addCommand({
      id: "toggle-chat",
      name: "Toggle AI Chat Sidebar",
      callback: () => {
        this.toggleChatSidebar();
      },
      hotkeys: [{ modifiers: ["Mod", "Shift"], key: ";" }],
    });

    this.addCommand({
      id: "login-current-provider",
      name: "Login to Current AI Provider",
      callback: () => {
        this.startProviderLogin(this.settings.provider);
      },
    });

    this.addCommand({
      id: "login-antigravity",
      name: "Login to Antigravity CLI",
      callback: () => {
        this.startProviderLogin("antigravity");
      },
    });

    this.addCommand({
      id: "login-claude",
      name: "Login to Claude CLI",
      callback: () => {
        this.startProviderLogin("claude");
      },
    });

    this.addCommand({
      id: "login-openai",
      name: "Login to OpenAI Codex CLI",
      callback: () => {
        this.startProviderLogin("openai");
      },
    });

    // Send selection to chat
    this.addCommand({
      id: "send-selection-to-chat",
      name: "Send Selection to Chat",
      editorCallback: (editor: Editor, ctx: MarkdownView | MarkdownFileInfo) => {
        if (ctx instanceof MarkdownView) {
          this.sendSelectionToChat(editor, ctx);
        }
      },
    });

    // Send PDF page to chat
    this.addCommand({
      id: "send-pdf-page-to-chat",
      name: "Send Current PDF Page to Chat",
      checkCallback: (checking: boolean) => {
        const leaf = this.app.workspace.getMostRecentLeaf();
        if (!leaf || leaf.view.getViewType() !== "pdf") return false;
        if (!checking) {
          this.sendPdfPageToChat(leaf);
        }
        return true;
      },
    });

    // ── Track active tab ──
    this.registerEvent(
      this.app.workspace.on("active-leaf-change", (leaf) => {
        // Don't overwrite PDF/markdown context when the chat sidebar gets focus
        if (leaf?.view.getViewType() === CHAT_VIEW_TYPE) return;
        this.lastContentLeaf = leaf;
        this.updateActiveContext(leaf);
      })
    );

    // ── Scroll & Cursor Restore ──
    this.registerEvent(
      this.app.workspace.on("file-open", (file) => {
        if (!file || !this.settings.fileScrollPositions) return;
        const pos = this.settings.fileScrollPositions[file.path];
        if (pos) {
          const view = this.app.workspace.getActiveViewOfType(MarkdownView);
          if (view && view.file?.path === file.path && view.getMode() === "source") {
            // Slight delay ensures Obsidian has fully rendered the file content
            setTimeout(() => {
              view.editor.scrollTo(0, pos.scroll);
              view.editor.setCursor({ line: pos.line, ch: pos.ch });
            }, 50);
          }
        }
      })
    );

    this.registerInterval(
      window.setInterval(() => {
        const view = this.app.workspace.getActiveViewOfType(MarkdownView);
        if (view && view.file && view.getMode() === "source") {
          const scrollInfo = view.editor.getScrollInfo();
          const cursor = view.editor.getCursor();
          
          if (!this.settings.fileScrollPositions) {
            this.settings.fileScrollPositions = {};
          }
          
          const path = view.file.path;
          this.settings.fileScrollPositions[path] = {
            scroll: scrollInfo.top,
            line: cursor.line,
            ch: cursor.ch
          };
          
          // Cap at 100 entries
          const keys = Object.keys(this.settings.fileScrollPositions);
          if (keys.length > 100) {
            delete this.settings.fileScrollPositions[keys[0]];
          }
        }
      }, 3000)
    );

    // ── Initialize active context for current leaf ──
    const currentLeaf = this.app.workspace.getMostRecentLeaf();
    if (currentLeaf && currentLeaf.view.getViewType() !== CHAT_VIEW_TYPE) {
      this.lastContentLeaf = currentLeaf;
      this.updateActiveContext(currentLeaf);
    }

    // ── Start MCP servers ──
    if (this.settings.mcpServers.length > 0) {
      // Delay MCP startup to not block plugin load
      setTimeout(() => {
        this.mcpManager.startAll(this.settings.mcpServers);
      }, 2000);
    }

    console.log("Obsidian AI Agent plugin loaded");
  }

  async onunload(): Promise<void> {
    console.log("Unloading Obsidian AI Agent plugin");

    // Close inline prompt
    this.inlinePrompt.close();

    // Shut down MCP servers
    await this.mcpManager.shutdownAll();

    // Detach sidebar views
    this.app.workspace.detachLeavesOfType(CHAT_VIEW_TYPE);

    // Save final settings (including scroll positions)
    await this.saveData(this.settings);
  }

  // ── Settings ────────────────────────────────────────────────

  async loadSettings(): Promise<void> {
    this.settings = Object.assign(
      {},
      DEFAULT_SETTINGS,
      await this.loadData()
    );
    this.settings.providerUsage = {
      ...DEFAULT_SETTINGS.providerUsage,
      ...(this.settings.providerUsage || {}),
    };
    if (this.migrateUnavailableModelDefaults()) {
      await this.saveData(this.settings);
    }
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
    // Update LLM client with new settings
    this.llmClient?.updateSettings(this.settings);
  }

  private migrateUnavailableModelDefaults(): boolean {
    const unavailableDefaults = new Set([
      "gpt-5.4-nano",
      "gpt-5.1",
      "gpt-5",
      "gpt-5-mini",
      "gpt-5-nano",
      "codex-mini-latest",
      "gpt-5.2-codex",
      "gpt-5.1-codex",
      "gpt-5.1-codex-max",
      "gpt-5.1-codex-mini",
      "gpt-5-codex",
      "claude-opus-4-7",
      "claude-sonnet-4-6",
      "claude-sonnet-4-6-20260101",
      "claude-haiku-4-5-20251001-old",
    ]);

    if (
      unavailableDefaults.has(this.settings.model) ||
      !getModelOption(this.settings.provider, this.settings.model)
    ) {
      this.settings.model = DEFAULT_MODELS[this.settings.provider];
      return true;
    }
    return false;
  }

  // ── Active Context ──────────────────────────────────────────

  getActiveContext(): ActiveContext {
    return this.activeContext;
  }

  refreshActiveContext(): ActiveContext {
    // Always re-capture from the last non-chat leaf so the PDF/markdown context
    // is fresh even when the chat input is currently focused.
    this.updateActiveContext(this.lastContentLeaf);
    return this.activeContext;
  }

  private toAbsolutePath(vaultRelPath: string | undefined): string | undefined {
    if (!vaultRelPath) return undefined;
    const adapter = this.app.vault.adapter as unknown as {
      getFullPath?: (p: string) => string;
      basePath?: string;
    };
    if (typeof adapter.getFullPath === "function") {
      return adapter.getFullPath(vaultRelPath);
    }
    if (typeof adapter.basePath === "string" && adapter.basePath) {
      return `${adapter.basePath}/${vaultRelPath}`;
    }
    return vaultRelPath;
  }

  private updateActiveContext(leaf: WorkspaceLeaf | null): void {
    const openTabs = this.getOpenTabContexts(leaf);

    if (!leaf) {
      this.activeContext = { viewType: "other", openTabs };
      return;
    }

    const viewType = leaf.view.getViewType();
    const file = this.getLeafFile(leaf) || this.app.workspace.getActiveFile();

    if (viewType === "markdown") {
      const mdView = leaf.view as MarkdownView;
      this.activeContext = {
        viewType: "markdown",
        filePath: file?.path,
        absolutePath: this.toAbsolutePath(file?.path),
        displayName: file?.basename || mdView.getDisplayText(),
        fileContent: mdView.editor.getValue(),
        selectedText: mdView.editor.getSelection() || undefined,
        openTabs,
      };

      if (mdView.editor.getSelection()) {
        const from = mdView.editor.getCursor("from");
        const to = mdView.editor.getCursor("to");
        this.activeContext.selectionStart = from.line + 1;
        this.activeContext.selectionEnd = to.line + 1;
      }
    } else if (viewType === EXTERNAL_PDF_VIEW_TYPE) {
      // External PDF: use the view's own capture method directly
      const extView = leaf.view as ExternalPdfView;
      this.activeContext = {
        viewType: "pdf",
        filePath: file?.path,
        absolutePath: this.toAbsolutePath(file?.path),
        displayName: file?.basename || extView.getDisplayText(),
        openTabs,
      };
      try {
        const pdfCtx = withVisionFallback(
          extView.getActivePdfContext(this.settings.pdfCaptureMode),
          this.settings.pdfCaptureMode,
          this.settings.pdfVisionFallback,
          () => extView.getActivePdfContext("image")?.imageBase64
        );
        if (pdfCtx) this.activeContext.pdfPage = pdfCtx;
      } catch (err) {
        console.warn("[AI Agent] Failed to capture external PDF context:", err);
      }
    } else if (viewType === "pdf") {
      this.activeContext = {
        viewType: "pdf",
        filePath: file?.path,
        absolutePath: this.toAbsolutePath(file?.path),
        displayName: file?.basename || leaf.view.getDisplayText(),
        openTabs,
      };
      try {
        const pdfCtx = withVisionFallback(
          getPdfContext(leaf, this.settings.pdfCaptureMode),
          this.settings.pdfCaptureMode,
          this.settings.pdfVisionFallback,
          () => getPdfContext(leaf, "image")?.imageBase64
        );
        if (pdfCtx) this.activeContext.pdfPage = pdfCtx;

        const pdfSelection = getPdfSelection(leaf);
        if (pdfSelection) this.activeContext.selectedText = pdfSelection;
      } catch (err) {
        console.warn("[AI Agent] Failed to capture PDF context:", err);
      }
    } else if (viewType === "canvas") {
      this.activeContext = {
        viewType: "canvas",
        filePath: file?.path,
        absolutePath: this.toAbsolutePath(file?.path),
        displayName: file?.basename || leaf.view.getDisplayText(),
        openTabs,
      };
    } else {
      this.activeContext = {
        viewType: "other",
        filePath: file?.path,
        absolutePath: this.toAbsolutePath(file?.path),
        displayName: file?.basename || leaf.view.getDisplayText(),
        openTabs,
      };
    }
  }

  private getOpenTabContexts(activeLeaf: WorkspaceLeaf | null): OpenTabContext[] {
    const tabs: OpenTabContext[] = [];

    this.app.workspace.iterateAllLeaves((leaf) => {
      if (leaf.view.getViewType() === CHAT_VIEW_TYPE) return;

      // Only include leaves actually visible on screen.
      // Leaves in a non-active tab group have a containerEl with zero dimensions.
      const containerEl = (leaf as unknown as { containerEl?: HTMLElement }).containerEl;
      if (containerEl) {
        const rect = containerEl.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) return;
      }

      const file = this.getLeafFile(leaf);
      const viewType = leaf.view.getViewType();
      const isActive = leaf === activeLeaf;

      let content: string | undefined;
      let selectedText: string | undefined;
      let pdfPage: OpenTabContext["pdfPage"];
      if (viewType === "markdown" && file) {
        const mdView = leaf.view as unknown as {
          editor?: { getValue(): string; getSelection(): string };
        };
        if (mdView.editor) {
          content = mdView.editor.getValue();
          selectedText = mdView.editor.getSelection() || undefined;
        }
      } else if (viewType === EXTERNAL_PDF_VIEW_TYPE) {
        try {
          const extView = leaf.view as ExternalPdfView;
          pdfPage = withVisionFallback(
            extView.getActivePdfContext(this.settings.pdfCaptureMode),
            this.settings.pdfCaptureMode,
            this.settings.pdfVisionFallback,
            () => extView.getActivePdfContext("image")?.imageBase64
          ) || undefined;
        } catch (err) {
          console.warn("[AI Agent] Failed to capture open external PDF context:", err);
        }
      } else if (viewType === "pdf") {
        try {
          pdfPage = withVisionFallback(
            getPdfContext(leaf, this.settings.pdfCaptureMode),
            this.settings.pdfCaptureMode,
            this.settings.pdfVisionFallback,
            () => getPdfContext(leaf, "image")?.imageBase64
          ) || undefined;
        } catch (err) {
          console.warn("[AI Agent] Failed to capture open PDF context:", err);
        }
      }

      tabs.push({
        label: file?.basename || leaf.view.getDisplayText() || viewType,
        viewType,
        filePath: file?.path,
        isActive,
        content,
        selectedText,
        pdfPage,
      });
    });

    return tabs;
  }

  private getLeafFile(leaf: WorkspaceLeaf): { path: string; basename: string } | null {
    const view = leaf.view as unknown as {
      file?: { path: string; basename: string };
    };
    return view.file || null;
  }

  // ── Commands ────────────────────────────────────────────────

  private async toggleChatSidebar(): Promise<void> {
    const existing =
      this.app.workspace.getLeavesOfType(CHAT_VIEW_TYPE);

    if (existing.length > 0) {
      // If already open, close it
      existing.forEach((leaf) => leaf.detach());
    } else {
      // Open in right sidebar
      const leaf =
        this.app.workspace.getRightLeaf(false);
      if (leaf) {
        await leaf.setViewState({
          type: CHAT_VIEW_TYPE,
          active: true,
        });
        this.app.workspace.revealLeaf(leaf);
      }
    }
  }

  private addLineReference(
    editor: Editor,
    view: MarkdownView
  ): void {
    const file = view.file;
    if (!file) return;

    const selection = editor.getSelection();
    const from = editor.getCursor("from");
    const to = editor.getCursor("to");

    const lineStart = from.line + 1;
    const lineEnd = to.line + 1;
    const label =
      lineStart === lineEnd
        ? `${file.basename}:L${lineStart}`
        : `${file.basename}:L${lineStart}-${lineEnd}`;

    const content = selection || editor.getLine(from.line);

    const ref: ContextRef = {
      type: "line-range",
      label,
      content,
      filePath: file.path,
      lineStart,
      lineEnd,
    };

    // Open chat sidebar and add the reference
    this.ensureChatOpen().then(() => {
      const chatView = this.getChatView();
      if (chatView) {
        chatView.addContextRef(ref);
        chatView.focusInput();
      }
    });

    new Notice(`Referenced ${label}`);
  }

  private sendSelectionToChat(
    editor: Editor,
    view: MarkdownView
  ): void {
    const selection = editor.getSelection();
    if (!selection) {
      new Notice("No text selected");
      return;
    }

    const file = view.file;
    const ref: ContextRef = {
      type: "selection",
      label: file
        ? `Selection from ${file.basename}`
        : "Selected text",
      content: selection,
      filePath: file?.path,
    };

    this.ensureChatOpen().then(() => {
      const chatView = this.getChatView();
      if (chatView) {
        chatView.addContextRef(ref);
        chatView.focusInput();
      }
    });
  }

  private sendPdfPageToChat(leaf: WorkspaceLeaf): void {
    const pdfCtx = withVisionFallback(
      getPdfContext(leaf, this.settings.pdfCaptureMode),
      this.settings.pdfCaptureMode,
      this.settings.pdfVisionFallback,
      () => getPdfContext(leaf, "image")?.imageBase64
    );
    if (!pdfCtx) {
      new Notice("Could not capture PDF page");
      return;
    }

    const file = this.app.workspace.getActiveFile();
    const ref: ContextRef = {
      type: "pdf-page",
      label: file
        ? `${file.basename} p.${pdfCtx.pageNum}`
        : `PDF page ${pdfCtx.pageNum}`,
      content: pdfCtx.text,
      imageBase64: pdfCtx.imageBase64,
      filePath: file?.path,
      pageNum: pdfCtx.pageNum,
    };

    this.ensureChatOpen().then(() => {
      const chatView = this.getChatView();
      if (chatView) {
        chatView.addContextRef(ref);
        chatView.focusInput();
      }
    });

    new Notice(`Captured PDF page ${pdfCtx.pageNum}`);
  }

  private startProviderLogin(provider: LLMProvider): void {
    try {
      this.authResolver.startLogin(provider);
      new Notice(`Opened ${provider} login in your terminal`);
    } catch (err: unknown) {
      new Notice(err instanceof Error ? err.message : String(err));
    }
  }

  // ── Helpers ─────────────────────────────────────────────────

  private async ensureChatOpen(): Promise<void> {
    const existing =
      this.app.workspace.getLeavesOfType(CHAT_VIEW_TYPE);
    if (existing.length === 0) {
      const leaf =
        this.app.workspace.getRightLeaf(false);
      if (leaf) {
        await leaf.setViewState({
          type: CHAT_VIEW_TYPE,
          active: true,
        });
        this.app.workspace.revealLeaf(leaf);
      }
    }
  }

  private getChatView(): ChatSidebarView | null {
    const leaves =
      this.app.workspace.getLeavesOfType(CHAT_VIEW_TYPE);
    if (leaves.length > 0) {
      return leaves[0].view as ChatSidebarView;
    }
    return null;
  }
}
