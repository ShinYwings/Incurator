
import { promises as fs } from "fs";
import { exec } from "child_process";
import { promisify } from "util";
const execAsync = promisify(exec);
import {
  Plugin,
  WorkspaceLeaf,
  MarkdownView,
  setIcon,
  MarkdownFileInfo,
  Notice,
  Editor,
} from "obsidian";
import {
  type PluginSettings,
  type SessionData,
  type ActiveContext,
  type ContextRef,
  type LLMProvider,
  type ModelCatalogue,
  type OpenTabContext,
  DEFAULT_SETTINGS,
  DEFAULT_SESSION_DATA,
  getDefaultModel,
  getModelOption,
} from "./src/types";
import { AIAgentSettingTab } from "./src/settings";
import { CLIAuthResolver } from "./src/auth/cliAuth";
import { LLMClient } from "./src/agent/llmClient";
import { MCPManager } from "./src/agent/mcpClient";
import { IncuratorClient } from "./src/agent/incuratorClient";
import { ChatSidebarView, CHAT_VIEW_TYPE } from "./src/ui/chatSidebar";
import {
  ExternalPdfView,
  EXTERNAL_PDF_VIEW_TYPE,
  registerExternalPdfByPath
} from "./src/ui/externalPdfView";
import { parseZoteroLink } from "./src/utils/zoteroUtils";

import { ZoteroSearchModal, ZoteroWizardModal } from "./src/ui/zoteroWizardModal";
import { TemplateRenderer } from "./src/zotero/templateRenderer";
import { IncuratorDashboardModal } from "./src/ui/incuratorDashboardModal";

import { InlinePromptWidget } from "./src/ui/inlinePrompt";
import {
  getPdfContext,
  getPdfSelection,
  withVisionFallback,
} from "./src/context/pdfCapture";
import {
  normalizeLastMarkdownScrollPosition,
  normalizeFileScrollPosition,
  upsertFileScrollPosition,
} from "./src/utils/scrollPositions";
import {
  ensureIncuratorMcpServer,
  isIncuratorMcpServer,
} from "./src/utils/incuratorMcpServer";
import { mergeSessionData, normalizeSessionData } from "./src/utils/sessionData";
import {
  mergeDeviceRegistry,
  readSyncthingSnapshot,
  getLocalBackendCommand,
  resolveWikiBinary,
  type DeviceRegistry,
} from "./src/utils/deviceRegistry";

export default class ObsidianAIAgent extends Plugin {
  settings: PluginSettings = DEFAULT_SETTINGS;
  sessionData: SessionData = { ...DEFAULT_SESSION_DATA };
  authResolver: CLIAuthResolver = new CLIAuthResolver();
  llmClient!: LLMClient;
  mcpManager: MCPManager = new MCPManager();
  incuratorClient!: IncuratorClient;
  availableModels: ModelCatalogue = {};
  inlinePrompt!: InlinePromptWidget;

  private activeContext: ActiveContext = { viewType: "other" };
  // Last non-chat leaf — preserved so context survives sidebar focus changes
  private lastContentLeaf: WorkspaceLeaf | null = null;
  private scrollPositionSaveTimer: number | null = null;
  private startupRestoreUntilMs = 0;
  private vaultRoot = "";
  private ingestStatusBar: HTMLElement | null = null;
  private incuratorStatusBar: HTMLElement | null = null;

  async onload(): Promise<void> {
    console.log("Loading Obsidian AI Agent plugin");
    this.startupRestoreUntilMs = Date.now() + 15000;

    // ── Load settings and session data ──
    await this.loadSettings();
    await this.loadSessionData();

    // ── Initialize core services ──
    this.vaultRoot = (this.app.vault.adapter as any).getBasePath?.() || "";
    await this.syncDeviceRegistryFromSyncthing();
    this.llmClient = new LLMClient(
      this.settings,
      this.authResolver,
      this.vaultRoot,
      () => this.saveData(this.settings)
    );
    this.incuratorClient = new IncuratorClient(
      this.mcpManager,
      this.settings,
    );
    this.inlinePrompt = new InlinePromptWidget(this);

    // ── Register settings tab ──
    this.addSettingTab(new AIAgentSettingTab(this.app, this));

    // ── Register chat sidebar view ──
    this.registerView(CHAT_VIEW_TYPE, (leaf: WorkspaceLeaf) => {
      return new ChatSidebarView(leaf, this);
    });

    this.registerView(EXTERNAL_PDF_VIEW_TYPE, (leaf: WorkspaceLeaf) => {
      return new ExternalPdfView(leaf, this);
    });

    // ── Ribbon icon (left sidebar) ──
    this.addRibbonIcon("bot", "Open AI Agent Chat", () => {
      this.toggleChatSidebar();
    });

    // ── Dashboard Ribbon Icon ──
    this.addRibbonIcon("database", "Open Incurator Dashboard", () => {
      new IncuratorDashboardModal(this.app, this).open();
    });

    // ── Status Bar ──
    this.setupIncuratorStatusBar();

    // ── Register commands ──

    // Cmd+K: Inline edit


    this.addCommand({
      id: "incurator-zotero-refresh",
      name: "Refresh Zotero Item",
      checkCallback: (checking: boolean) => {
        const file = this.app.workspace.getActiveFile();
        if (!file) return false;
        const cache = this.app.metadataCache.getFileCache(file as any);
        if (!cache?.frontmatter) return false;

        const citekey = cache.frontmatter.citekey;
        const zoteroUrl = cache.frontmatter.zotero_app_url;

        if (!citekey && !zoteroUrl) return false;

        if (checking) return true;

        (async () => {
          new Notice("Refreshing Zotero Item...");
          try {
            // Find the item key from frontmatter
            let itemKey = "";
            if (zoteroUrl) {
                const match = zoteroUrl.match(/items\/([A-Z0-9]+)/i);
                if (match) itemKey = match[1];
            }
            if (!itemKey && citekey) itemKey = citekey; // fallback to citekey if URL missing (backend will need to handle this)

            const res: any = await this.incuratorClient.tryTool(["curator_get_zotero_item_metadata"], {
                item_key: itemKey,
                custom_paths: this.settings.zoteroBasePath || "~/Zotero"
            });

            if (!res || !res.ok || !res.metadata) throw new Error(res?.error || "Unknown error");

            const renderer = new TemplateRenderer(this.app);
            const profiles = this.settings.zoteroProfiles || [];
            if (profiles.length === 0) throw new Error("No Zotero profile found. Please run the Import Wizard once first.");
            const p = profiles[0]; // use first profile as default

            // If imageFolder is specified, copy images first
            if (p.imageFolder) {
              const imgFolder = this.app.vault.getAbstractFileByPath(p.imageFolder);
              if (!imgFolder) await this.app.vault.createFolder(p.imageFolder);

              for (const ann of res.metadata.annotations || []) {
                if (ann.imageRelativePath) {
                  try {
                    const imgBuffer = await fs.readFile(ann.imageRelativePath);
                    const filename = `${ann.key || ann.id}.png`;
                    let destPath = p.imageFolder;
                    if (!destPath.endsWith("/")) destPath += "/";
                    destPath += filename;

                    const existing = this.app.vault.getAbstractFileByPath(destPath);
                    if (!existing) {
                      await this.app.vault.createBinary(destPath, imgBuffer);
                    }
                    ann.imageRelativePath = destPath;
                  } catch (e) {
                    console.error("Failed to copy image for annotation on refresh", ann.key, e);
                  }
                }
              }
            }

            const existingContent = await this.app.vault.read(file);
            const markdown = await renderer.renderTemplate(p.templatePath, res.metadata, existingContent);

            await this.app.vault.modify(file, markdown);
            new Notice("Zotero note refreshed successfully!");
          } catch(e: any) {
            new Notice("Failed to refresh: " + e.message);
          }
        })();
        return true;
      }
    });

    this.addCommand({
      id: "incurator-zotero-import",
      name: "Import Zotero Item (Wizard)",
      callback: () => {
        new ZoteroSearchModal(
          this.app,
          this.incuratorClient,
          this.settings,
          async (settings) => {
            this.settings = settings;
            await this.saveSettings();
          }
        ).open();
      },
    });

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
      id: "open-ai-agent-chat",
      name: "Open Chat",
      callback: () => {
        this.toggleChatSidebar();
      },
    });

    this.addCommand({
      id: "open-incurator-dashboard",
      name: "Open Incurator Dashboard",
      callback: () => {
        new IncuratorDashboardModal(this.app, this).open();
      },
    });

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
      this.app.workspace.on("file-open", (file) => {
        if (!file || !("extension" in file) || (file as any).extension !== "md") return;
        const cache = this.app.metadataCache.getFileCache(file as any);
        const zoteroUrl = cache?.frontmatter?.zotero_app_url;
        const citekey = cache?.frontmatter?.citekey;
        if (!zoteroUrl && !citekey) return;

        // Give it a tiny bit of time for the view to fully mount
        setTimeout(() => {
          const view = this.app.workspace.getActiveViewOfType(MarkdownView);
          if (view && view.file?.path === file.path) {
            if (!view.containerEl.querySelector('.incurator-refresh-btn')) {
              const btn = view.addAction('sync', 'Refresh Zotero Item (Incurator)', () => {
                // @ts-ignore
                this.app.commands.executeCommandById("incurator-obsidian-agent:incurator-zotero-refresh");
              });
              btn.classList.add('incurator-refresh-btn');
              btn.style.color = 'var(--interactive-accent)';
            }
          }
        }, 300);
      })
    );

    this.registerEvent(
      this.app.workspace.on("file-menu", (menu, file) => {
        if (!file || !("extension" in file) || (file as any).extension !== "md") return;
        const cache = this.app.metadataCache.getFileCache(file as any);
        if (!cache?.frontmatter) return;

        const zoteroUrl = cache.frontmatter.zotero_app_url;
        if (!zoteroUrl) return;

        menu.addItem((item) => {
          item
            .setTitle("Refresh Zotero Item")
            .setIcon("sync")
            .onClick(() => {
              // @ts-ignore
              this.app.commands.executeCommandById("incurator-obsidian-agent:incurator-zotero-refresh");
            });
        });
      })
    );

    this.registerEvent(
      this.app.workspace.on("active-leaf-change", (leaf) => {
        // Don't overwrite PDF/markdown context when the chat sidebar gets focus
        if (leaf?.view.getViewType() === CHAT_VIEW_TYPE) return;
        this.lastContentLeaf = leaf;
        this.updateActiveContext(leaf);
        if (Date.now() < this.startupRestoreUntilMs) {
          this.restoreLastMarkdownScrollPosition();
        }
      })
    );

    // ── Scroll & Cursor Restore ──
    this.registerEvent(
      this.app.workspace.on("file-open", (file) => {
        if (!file) return;
        this.restoreLastMarkdownScrollPosition();
      })
    );

    this.app.workspace.onLayoutReady(() => {
      this.restoreLastMarkdownScrollPosition();
    });

    this.registerInterval(
      window.setInterval(() => {
        this.captureActiveMarkdownScrollPosition();
      }, 3000)
    );

    // ── Ingest status bar (right side) ──
    this.ingestStatusBar = this.addStatusBarItem();
    this.ingestStatusBar.setText("⚡ Incurator");
    this.ingestStatusBar.style.cursor = "pointer";
    this.ingestStatusBar.addEventListener("click", () => {
      const dashboardPath = ".curator/dashboard.md";
      const file = this.app.vault.getAbstractFileByPath(dashboardPath);
      if (file) this.app.workspace.openLinkText(dashboardPath, "", false);
    });
    this.registerInterval(
      window.setInterval(() => this.refreshIngestStatusBar(), 5000)
    );

    // ── Initialize active context for current leaf ──
    const currentLeaf = this.app.workspace.getMostRecentLeaf();
    if (currentLeaf && currentLeaf.view.getViewType() !== CHAT_VIEW_TYPE) {
      this.lastContentLeaf = currentLeaf;
      this.updateActiveContext(currentLeaf);
    }

    // ── Zotero link interceptor (Global Patch) ──
    // Intercepts zotero://open-pdf and zotero://select clicks globally (including Live Preview).
    // Opens the resolved PDF in the built-in ExternalPdfView instead of launching Zotero.

    // Shared handler: resolve a zotero:// URL and open in ExternalPdfView
    const handleZoteroUrl = async (url: string): Promise<boolean> => {
      const zoteroInfo = parseZoteroLink(url);
      if (!zoteroInfo) return false;

      const attachmentKey = zoteroInfo.attachmentKey;
      let pdfPath: string | null = null;

      if (this.incuratorClient && this.incuratorClient.available) {
        pdfPath = await this.incuratorClient.resolveZoteroPdf(attachmentKey);
      }

      if (!pdfPath) return false; // Let OS handle it

      let leaf = this.app.workspace.getLeavesOfType(EXTERNAL_PDF_VIEW_TYPE).find(l => {
        return l.view.getState()?.path === pdfPath;
      });

      let pdfState: any;
      if (leaf) {
        pdfState = {
          ...leaf.view.getState(),
          zoteroAttachmentKey: attachmentKey,
        };
      } else {
        pdfState = registerExternalPdfByPath(pdfPath, attachmentKey);
        leaf = this.app.workspace.getLeaf("split");
      }

      if (zoteroInfo.pageNum) {
        pdfState.currentPage = zoteroInfo.pageNum;
      }
      if (zoteroInfo.annotationKey) {
        pdfState.targetAnnotationKey = zoteroInfo.annotationKey;
      }

      await leaf.setViewState({ type: EXTERNAL_PDF_VIEW_TYPE, active: true, state: pdfState });
      if (leaf) this.app.workspace.revealLeaf(leaf);
      return true;
    };

    // DOM interceptor for click and auxclick on <a href="zotero://...">
    const interceptZoteroClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      const link = target.closest('a[href]') as HTMLAnchorElement | null;

      if (link && link.href && link.href.toLowerCase().startsWith("zotero://")) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        handleZoteroUrl(link.href);
      }
    };
    this.registerDomEvent(document, 'click', interceptZoteroClick, { capture: true });
    this.registerDomEvent(document, 'auxclick', interceptZoteroClick, { capture: true });

    // On macOS, Obsidian/Electron may send zotero:// directly to the OS via
    // electron.shell.openExternal instead of window.open. Patch both.
    const originalWindowOpen = window.open;
    this.register(() => {
      window.open = originalWindowOpen;
    });

    window.open = (url?: string | URL, target?: string, features?: string) => {
      if (typeof url === "string" && parseZoteroLink(url)) {
        handleZoteroUrl(url);
        return null;
      }
      return originalWindowOpen.call(window, url, target, features);
    };

    // Patch electron.shell.openExternal — Obsidian uses @electron/remote on desktop
    const patchShellModule = (mod: any, label: string) => {
      if (!mod?.shell?.openExternal) return;
      const orig = mod.shell.openExternal.bind(mod.shell);
      const patched = async (url: string, options?: any): Promise<void> => {
        if (typeof url === "string" && url.toLowerCase().startsWith("zotero://")) {
          const handled = await handleZoteroUrl(url);
          if (handled) return;
        }
        return orig(url, options);
      };
      mod.shell.openExternal = patched;
      this.register(() => {
        mod.shell.openExternal = orig;
      });
    };

    try { patchShellModule(require("electron"), "electron"); } catch { /* noop */ }
    try { patchShellModule(require("@electron/remote"), "@electron/remote"); } catch { /* noop */ }

    if (this.settings.incuratorEnabled) {
      await this.ensureIncuratorBackend();
    }

    // ── Start MCP servers ──
    const otherMcpServers = this.settings.mcpServers.filter(
      (server) => !isIncuratorMcpServer(server)
    );
    if (otherMcpServers.length > 0) {
      // Delay MCP startup to not block plugin load
      setTimeout(() => {
        this.mcpManager.startAll(otherMcpServers);
      }, 2000);
    }

    console.log("Obsidian AI Agent plugin loaded");
  }

  async onunload(): Promise<void> {
    console.log("Unloading Obsidian AI Agent plugin");
    if (this.scrollPositionSaveTimer !== null) {
      window.clearTimeout(this.scrollPositionSaveTimer);
    }
    // ensure inline prompt is unmounted
    this.inlinePrompt.unload();

    // Shut down MCP servers
    await this.mcpManager.shutdownAll();

    // Detach sidebar views
    this.app.workspace.detachLeavesOfType(CHAT_VIEW_TYPE);

    // Save final settings and session data
    await this.saveData(this.settings);
    await this.saveSessionData();
  }

  private async refreshIngestStatusBar(): Promise<void> {
    if (!this.ingestStatusBar || !this.settings.incuratorEnabled) return;
    try {
      const result: any = await this.incuratorClient.tryTool(["check_ingest_status"], {});
      if (!result) return;
      if (result.idle) {
        const done = result.done_today ?? 0;
        this.ingestStatusBar.setText(done > 0 ? `✓ ${done} done today` : "✓ Incurator idle");
      } else {
        const r = result.running?.length ?? 0;
        const q = result.queued?.length ?? 0;
        this.ingestStatusBar.setText(`⚡ ${r} running / ${q} queued`);
      }
    } catch {
      // MCP not connected — keep last text
    }
  }

  private captureActiveMarkdownScrollPosition(): void {
    const view = this.app.workspace.getActiveViewOfType(MarkdownView);
    if (!view?.file || view.getMode() !== "source") return;

    const scrollInfo = view.editor.getScrollInfo();
    const cursor = view.editor.getCursor();
    const now = Date.now();
    const position = {
      scroll: scrollInfo.top,
      line: cursor.line,
      ch: cursor.ch,
    };
    this.settings.fileScrollPositions = upsertFileScrollPosition(
      this.settings.fileScrollPositions || {},
      view.file.path,
      position,
      100,
      now
    );
    this.settings.lastMarkdownScrollPosition = {
      path: view.file.path,
      ...position,
      updatedAt: now,
    };
    this.scheduleScrollPositionSave();
  }

  private restoreLastMarkdownScrollPosition(): void {
    const last = normalizeLastMarkdownScrollPosition(
      this.settings.lastMarkdownScrollPosition
    );
    if (!last) return;
    this.restoreMarkdownScrollPosition(last.path, last);
  }

  private restoreMarkdownScrollPosition(
    path: string,
    position?: ReturnType<typeof normalizeFileScrollPosition>
  ): void {
    const pos =
      position ||
      normalizeFileScrollPosition(this.settings.fileScrollPositions?.[path]);
    if (!pos) return;

    const delays = [50, 150, 350, 750, 1200];
    for (const delay of delays) {
      window.setTimeout(() => {
        const view = this.findMarkdownView(path);
        if (!view || view.getMode() !== "source") return;
        view.editor.setCursor({ line: pos.line, ch: pos.ch });
        view.editor.scrollTo(0, pos.scroll);
      }, delay);
    }
  }

  private findMarkdownView(path: string): MarkdownView | null {
    const active = this.app.workspace.getActiveViewOfType(MarkdownView);
    if (active?.file?.path === path) return active;

    for (const leaf of this.app.workspace.getLeavesOfType("markdown")) {
      if (leaf.view instanceof MarkdownView && leaf.view.file?.path === path) {
        return leaf.view;
      }
    }
    return null;
  }

  private scheduleScrollPositionSave(): void {
    if (this.scrollPositionSaveTimer !== null) return;
    this.scrollPositionSaveTimer = window.setTimeout(async () => {
      this.scrollPositionSaveTimer = null;
      await this.saveData(this.settings);
    }, 500);
  }

  async setIncuratorBackendEnabled(enabled: boolean): Promise<void> {
    this.settings.incuratorEnabled = enabled;
    if (enabled) {
      await this.ensureIncuratorBackend();
    } else {
      const incuratorServers = this.settings.mcpServers.filter(isIncuratorMcpServer);
      for (const server of incuratorServers) {
        server.enabled = false;
        await this.mcpManager.shutdown(server.name);
      }
      await this.saveSettings();
    }
  }

  async ensureIncuratorBackend(): Promise<void> {
    // Resolve the actual command to use:
    //   1. If user set a non-default incuratorMcpCommand (manual override), use it as-is.
    //   2. Otherwise, check devices.json for a cached per-device binary path.
    //   3. Otherwise, auto-discover from incuratorRepoPath / common PATH dirs.
    //   4. Fallback: bare "wiki" (works if wiki is on PATH).
    let command = this.settings.incuratorMcpCommand;
    const isDefault = !command || command === "wiki";

    if (isDefault) {
      // Try devices.json cache first
      let registry: Partial<DeviceRegistry> | null = null;
      try {
        const raw = await this.app.vault.adapter.read(".curator/devices.json");
        registry = JSON.parse(raw) as Partial<DeviceRegistry>;
      } catch { /* no devices.json yet */ }

      const cached = getLocalBackendCommand(registry);
      if (cached && cached !== "wiki") {
        command = cached;
      } else {
        // Auto-discover
        const discovered = resolveWikiBinary(this.settings.incuratorRepoPath);
        if (discovered) {
          command = discovered;
          console.log(`[Incurator] Auto-discovered wiki binary: ${command}`);
        }
      }
    }

    const result = ensureIncuratorMcpServer(
      this.settings.mcpServers,
      this.vaultRoot,
      command,
      this.settings.incuratorMcpArgs
    );
    this.settings.mcpServers = result.servers;
    if (result.changed) {
      await this.saveSettings();
    }
    await this.mcpManager.start(result.server);
    await this.refreshAvailableModels();

    // Cache resolved command in devices.json so next load reads from cache
    if (isDefault && command !== "wiki") {
      this.cacheBackendCommand(command);
    }
  }

  /** Persist the resolved backend command into devices.json for this device. */
  private async cacheBackendCommand(command: string): Promise<void> {
    try {
      let registry: Partial<DeviceRegistry> | null = null;
      try {
        const raw = await this.app.vault.adapter.read(".curator/devices.json");
        registry = JSON.parse(raw) as Partial<DeviceRegistry>;
      } catch { /* none yet */ }

      // Update the local device's backend.command
      if (registry?.local_device_id && registry.devices) {
        const local = registry.devices[registry.local_device_id];
        if (local) {
          (local as Record<string, unknown>).backend = {
            ...((local as Record<string, unknown>).backend as Record<string, unknown> || {}),
            command,
          };
          registry.updated_at = Math.floor(Date.now() / 1000);
          if (!(await this.app.vault.adapter.exists(".curator"))) {
            await this.app.vault.adapter.mkdir(".curator");
          }
          await this.app.vault.adapter.write(
            ".curator/devices.json",
            `${JSON.stringify(registry, null, 2)}\n`
          );
          console.log(`[Incurator] Cached backend command in devices.json: ${command}`);
        }
      }
    } catch (err) {
      console.warn("[Incurator] Failed to cache backend command:", err);
    }
  }

  // ── Settings ────────────────────────────────────────────────

  async loadSettings(): Promise<void> {
    const raw = (await this.loadData()) || {};
    this.settings = Object.assign({}, DEFAULT_SETTINGS, raw);
    this.settings.providerUsage = {
      ...DEFAULT_SETTINGS.providerUsage,
      ...(this.settings.providerUsage || {}),
    };
    if (this.migrateUnavailableModelDefaults()) {
      await this.saveData(this.settings);
    }
  }

  async updateIncuratorBackend(): Promise<void> {
    const repoPath = this.settings.incuratorRepoPath;
    if (!repoPath) {
      new Notice("Incurator repository path is not configured. Please set it in the plugin settings.");
      return;
    }

    try {
      // First verify it's a valid path and has setup.sh
      const setupPath = `${repoPath}/setup.sh`;
      await fs.access(setupPath);

      // Run git pull and setup.sh
      new Notice("Updating Incurator backend... Please wait.");
      await execAsync("git pull && ./setup.sh", { cwd: repoPath });
      
      new Notice("Incurator backend updated successfully! Please reload the plugin or restart Obsidian.");
    } catch (e: any) {
      console.error("Failed to update Incurator backend:", e);
      new Notice("Failed to update Incurator backend: " + (e.message || "Unknown error"));
    }
  }

  async updateSettings(updates: Partial<PluginSettings>): Promise<void> {
    await this.saveData(this.settings);
    // Update LLM client with new settings
    this.llmClient?.updateSettings(this.settings);
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
    // Update LLM client with new settings
    this.llmClient?.updateSettings(this.settings);
  }

  // ── Session data (device-local, stored in sessions.json) ────────

  private get _sessionsPath(): string {
    return ".curator/sessions.json";
  }

  async loadSessionData(): Promise<void> {
    try {
      const raw = await this.app.vault.adapter.read(this._sessionsPath);
      const parsed = JSON.parse(raw) as Partial<SessionData>;
      this.sessionData = normalizeSessionData(parsed);
    } catch {
      // File missing or unreadable in .curator — check legacy locations for migration
      try {
        const oldRaw = await this.app.vault.adapter.read(`${this.manifest.dir}/sessions.json`);
        this.sessionData = normalizeSessionData(JSON.parse(oldRaw) as Partial<SessionData>);
        await this.saveSessionData();
        await this.app.vault.adapter.remove(`${this.manifest.dir}/sessions.json`);
        return;
      } catch {
        // Proceed to check data.json legacy migration if standalone sessions.json is also missing
      }

      const raw = (await this.loadData()) || {};
      const legacy = raw as { chatSessions?: SessionData["chatSessions"]; activeChatSessionId?: string };
      if (legacy.chatSessions?.length) {
        this.sessionData = {
          chatSessions: legacy.chatSessions,
          activeChatSessionId: legacy.activeChatSessionId,
        };
        // Persist to new location and remove from settings
        await this.saveSessionData();
        delete (this.settings as unknown as Record<string, unknown>).chatSessions;
        delete (this.settings as unknown as Record<string, unknown>).activeChatSessionId;
        await this.saveData(this.settings);
      } else {
        this.sessionData = { ...DEFAULT_SESSION_DATA };
      }
    }
  }

  async saveSessionData(): Promise<void> {
    let sessionData = this.sessionData;
    try {
      const raw = await this.app.vault.adapter.read(this._sessionsPath);
      const remote = normalizeSessionData(JSON.parse(raw) as Partial<SessionData>);
      sessionData = mergeSessionData(this.sessionData, remote);
      this.sessionData = sessionData;
    } catch {
      // Missing or unreadable sessions.json: write the current in-memory session state.
    }

    if (!(await this.app.vault.adapter.exists(".curator"))) {
      await this.app.vault.adapter.mkdir(".curator");
    }

    await this.app.vault.adapter.write(
      this._sessionsPath,
      JSON.stringify(sessionData, null, 2)
    );
  }

  private async syncDeviceRegistryFromSyncthing(): Promise<void> {
    if (!this.vaultRoot) return;
    try {
      const snapshot = readSyncthingSnapshot(this.vaultRoot);
      if (snapshot.devices.length === 0 && snapshot.folders.length === 0) return;

      let existing: Partial<DeviceRegistry> | null = null;
      try {
        const raw = await this.app.vault.adapter.read(".curator/devices.json");
        existing = JSON.parse(raw) as Partial<DeviceRegistry>;
      } catch {
        existing = null;
      }

      const registry = mergeDeviceRegistry(existing, snapshot, this.settings);
      if (!(await this.app.vault.adapter.exists(".curator"))) {
        await this.app.vault.adapter.mkdir(".curator");
      }
      await this.app.vault.adapter.write(
        ".curator/devices.json",
        `${JSON.stringify(registry, null, 2)}\n`
      );
    } catch (err) {
      console.warn("[Incurator] Device registry auto-sync failed:", err);
    }
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

    const knownModel = getModelOption(
      this.availableModels,
      this.settings.provider,
      this.settings.model
    );
    if (unavailableDefaults.has(this.settings.model) || (!this.settings.model && !knownModel)) {
      const backendDefault = getDefaultModel(this.availableModels, this.settings.provider);
      this.settings.model = backendDefault || "";
      return true;
    }
    return false;
  }

  getAvailableModels(): ModelCatalogue {
    return this.availableModels;
  }

  async refreshAvailableModels(): Promise<void> {
    if (!this.incuratorClient?.available) return;
    const catalogue = await this.incuratorClient.getAvailableModels();
    if (Object.keys(catalogue).length === 0) return;
    this.availableModels = catalogue;
    if (!this.settings.model) {
      this.settings.model = getDefaultModel(catalogue, this.settings.provider);
      await this.saveSettings();
      return;
    }
    if (!getModelOption(catalogue, this.settings.provider, this.settings.model)) {
      const fallback = getDefaultModel(catalogue, this.settings.provider);
      if (fallback) {
        this.settings.model = fallback;
        await this.saveSettings();
      }
    }
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
    if (leaf.view.getViewType() === EXTERNAL_PDF_VIEW_TYPE) {
      const state = typeof (leaf.view as any).getState === "function" ? (leaf.view as any).getState() : null;
      if (state && state.path) {
        return { path: state.path, basename: state.name || "External PDF" };
      }
    }
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

  private setupIncuratorStatusBar() {
    this.incuratorStatusBar = this.addStatusBarItem();
    this.incuratorStatusBar.addClass("ai-agent-incurator-status-bar");
    this.incuratorStatusBar.setText("⚪️ Incurator");
    
    // Style cursor as pointer
    this.incuratorStatusBar.style.cursor = "pointer";
    this.incuratorStatusBar.style.padding = "0 8px";
    this.incuratorStatusBar.style.fontWeight = "600";

    this.incuratorStatusBar.onClickEvent(() => {
      new IncuratorDashboardModal(this.app, this).open();
    });

    // Simple polling to update status bar
    this.registerInterval(
      window.setInterval(async () => {
        if (!this.settings.incuratorEnabled) {
          if (this.incuratorStatusBar) this.incuratorStatusBar.setText("⚪️ Incurator: Disabled");
          return;
        }
        
        try {
          const status = await this.incuratorClient.getBackendStatus();
          if (status && status.qmd_ready) {
            this.incuratorStatusBar?.setText("🟢 Incurator");
          } else if (status && !status.error) {
            this.incuratorStatusBar?.setText("🟡 Incurator: Starting...");
          } else {
            this.incuratorStatusBar?.setText("🔴 Incurator: Error");
          }
        } catch {
          this.incuratorStatusBar?.setText("🔴 Incurator: Disconnected");
        }
      }, 10000)
    );
    
    // Initial check
    setTimeout(() => {
      if (this.settings.incuratorEnabled) {
        this.incuratorStatusBar?.setText("🟡 Incurator");
      }
    }, 1000);
  }
}

