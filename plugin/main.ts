
import { promises as fs } from "fs";
import { spawn } from "child_process";
import {
  Plugin,
  WorkspaceLeaf,
  MarkdownView,
  setIcon,
  MarkdownFileInfo,
  Notice,
  Editor,
  htmlToMarkdown,
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
import { SyncScheduler } from "./src/agent/syncScheduler";
import { ChatSidebarView, CHAT_VIEW_TYPE } from "./src/ui/chatSidebar";
import {
  ExternalPdfView,
  EXTERNAL_PDF_VIEW_TYPE,
  type ExternalPdfState,
} from "./src/ui/externalPdfView";
import {
  registerExternalPdfByPath,
  replaceExternalPdfDocPath,
} from "./src/ui/externalPdfRegistry";
import { parseZoteroLink } from "./src/utils/zoteroUtils";

import { ZoteroSearchModal, ZoteroWizardModal } from "./src/ui/zoteroWizardModal";
import {
  ZoteroRepairModal,
  type ZoteroRepairInitialState,
} from "./src/ui/zoteroRepairModal";
import { TemplateRenderer } from "./src/zotero/templateRenderer";
import { localizeAnnotationImages } from "./src/zotero/assetLocalization";
import { IncuratorDashboardModal } from "./src/ui/incuratorDashboardModal";

import { InlinePromptWidget } from "./src/ui/inlinePrompt";
import { QuickQueryPopover } from "./src/ui/quickQueryPopover";
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
import { getBundledModelCatalogue } from "./src/utils/bundledModelCatalogue";
import { isSelectionRelevantKey } from "./src/utils/selectionKeys";
import {
  isSelectionInReadingView,
  selectionContainsRenderedMath,
  selectionToMarkdownWithLatex,
  sliceLinesByIndex,
  stampMathSourceData,
} from "./src/utils/textUtils";
import { rewriteCuratorLinks } from "./src/utils/curatorWikilinks";
import { mergeSessionData, normalizeSessionData } from "./src/utils/sessionData";
import {
  mergeDeviceRegistry,
  readSyncthingSnapshotWithStatus,
  getLocalBackendCommand,
  getLocalBackendRepoPath,
  resolveWikiBinary,
  getGlobalRegistryPath,
  type DeviceRegistry,
} from "./src/utils/deviceRegistry";

function isLegacyIncuratorMcpServer(server: { name?: string; command?: string; args?: string[] }): boolean {
  const name = (server.name || "").toLowerCase();
  const command = (server.command || "").toLowerCase();
  const args = (server.args || []).join(" ").toLowerCase();
  return (
    name === "incurator" ||
    name.includes("incurator") ||
    name.includes("curator") ||
    ((command.endsWith("wiki") || command.includes("incurator")) && args.includes("mcp"))
  );
}

export default class ObsidianAIAgent extends Plugin {
  settings: PluginSettings = DEFAULT_SETTINGS;
  sessionData: SessionData = { ...DEFAULT_SESSION_DATA };
  authResolver: CLIAuthResolver = new CLIAuthResolver();
  llmClient!: LLMClient;
  mcpManager: MCPManager = new MCPManager();
  incuratorClient!: IncuratorClient;
  availableModels: ModelCatalogue = getBundledModelCatalogue();
  inlinePrompt!: InlinePromptWidget;
  quickQuery!: QuickQueryPopover;

  private activeContext: ActiveContext = { viewType: "other" };
  // Last non-chat leaf — preserved so context survives sidebar focus changes
  private lastContentLeaf: WorkspaceLeaf | null = null;
  private scrollPositionSaveTimer: number | null = null;
  private startupRestoreUntilMs = 0;
  private vaultRoot = "";
  private ingestStatusBar: HTMLElement | null = null;
  private incuratorStatusBar: HTMLElement | null = null;
  private syncScheduler: SyncScheduler | null = null;
  private syncWatcher: { close: () => void } | null = null;
  private syncStatusBar: HTMLElement | null = null;

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
      () => this.saveData(this.settings),
      this.mcpManager
    );
    this.incuratorClient = new IncuratorClient(
      this.settings,
      this.manifest.version,
      this.runBackendJsonCommand.bind(this)
    );
    this.inlinePrompt = new InlinePromptWidget(this);
    this.quickQuery = new QuickQueryPopover(this);

    // ── In-line Copilot: drag-to-select quick query popover ──
    // Register on the main document AND every Obsidian popout window so the
    // "Ask AI" button appears regardless of which window holds the selection
    // (report item 5: popover missing in new windows).
    const registerQuickQueryDom = (doc: Document) => {
      this.registerDomEvent(doc, "mouseup", () => {
        // Defer so the browser finalizes the selection before we read it.
        (doc.defaultView ?? window).setTimeout(
          () => this.quickQuery.handleSelectionChange(doc),
          0
        );
      });
      // Keyboard selections produce no mouseup, so the Ask AI button never
      // appeared. Fire the same handler on any selection-relevant key, WITHOUT
      // inspecting the modifier state at release time: if the user lifts Shift a
      // hair before the arrow key, the arrow's keyup reports shiftKey=false, so a
      // modifier check would miss the gesture. handleSelectionChange itself reads
      // the live selection and shows OR hides the button, so collapse keys (plain
      // arrows, Escape, Backspace, Delete, Enter, PageUp/Down) also correctly
      // dismiss a lingering button. selectionchange is avoided (fires on every
      // caret move); these discrete keyups + the cheap isCollapsed early-out are
      // enough.
      this.registerDomEvent(doc, "keyup", (e: KeyboardEvent) => {
        if (!isSelectionRelevantKey(e.key)) return;
        (doc.defaultView ?? window).setTimeout(
          () => this.quickQuery.handleSelectionChange(doc),
          0
        );
      });
      this.registerDomEvent(
        doc,
        "mousedown",
        (e: MouseEvent) => this.quickQuery.handleDocumentClick(e.target),
        { capture: true }
      );
    };

    // ── Reading-view math source stamping ──
    // Obsidian's reading view renders math as CHTML with NO LaTeX source in the
    // DOM. Re-parse each rendered section's source and stamp it onto the `.math`
    // elements as `data-tex` (exact-count guarded, so a mis-parse can never stamp a
    // wrong source) so a reading-view copy can recover `$...$` / `$$...$$`.
    this.registerMarkdownPostProcessor((el, ctx) => {
      if (!el.querySelector(".math")) return;
      const info = ctx.getSectionInfo(el);
      if (!info) return;
      // Extract the section's source lines by index (no full-document split — this
      // runs per math block on every render).
      const source = sliceLinesByIndex(info.text, info.lineStart, info.lineEnd);
      stampMathSourceData(el, source);
    });

    // ── Curator DAG wikilink resolution ──
    // The L1–L4 DAG lives under the hidden `.curator/Collections/` folder, which
    // Obsidian's metadataCache never indexes, so `[[02_Atoms/ATM-…]]` renders as a
    // dead, unresolved link. Rewrite curator-layer links into clickable links that
    // open the hidden page. `MarkdownRenderer.render` runs registered post-processors,
    // so this single hook covers the chat sidebar answer, the quick-query popover
    // answer, and the reading view of an opened DAG page (DRY).
    this.registerMarkdownPostProcessor((el) => {
      rewriteCuratorLinks(el, {
        open: (linktext) => void this.app.workspace.openLinkText(linktext, "", false),
        exists: (path) => this.app.vault.getAbstractFileByPath(path) != null,
      });
    });

    // ── Note reading-view LaTeX-preserving copy / cut ──
    // When a reading-view note selection contains rendered math, copy it as Markdown
    // with the formula's LaTeX source restored (from the stamped `data-tex`) instead
    // of the empty MathJax SVG. Gated to reading view + math: Live Preview / source
    // mode copy the document source natively, and non-math selections fall through
    // to the native clipboard untouched. Reading view is read-only, so `cut` cannot
    // delete anything and is treated as a copy. Registered per document AND popout,
    // capture-phase to run before any view-level handler.
    const registerNoteLatexCopyDom = (doc: Document) => {
      const handle = (e: ClipboardEvent) => {
        if (!e.clipboardData) return;
        const sel = doc.getSelection();
        if (!isSelectionInReadingView(sel)) return;
        if (!selectionContainsRenderedMath(sel)) return;
        const md = selectionToMarkdownWithLatex(sel, htmlToMarkdown);
        if (!md) return;
        e.preventDefault();
        e.clipboardData.setData("text/plain", md);
      };
      this.registerDomEvent(doc, "copy", handle, { capture: true });
      this.registerDomEvent(doc, "cut", handle, { capture: true });
    };

    registerQuickQueryDom(document);
    registerNoteLatexCopyDom(document);
    this.registerEvent(
      this.app.workspace.on("window-open", (_workspaceWindow, win: Window) => {
        registerQuickQueryDom(win.document);
        registerNoteLatexCopyDom(win.document);
      })
    );

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

    // ── Cross-device knowledge auto-sync (Syncthing) ──
    this.setupAutoSync();

    // ── Register commands ──

    // Cmd+K: Inline edit


    this.addCommand({
      id: "incurator-zotero-refresh",
      name: "Reload Source (Zotero item / PDF)",
      hotkeys: [{ modifiers: ["Mod", "Shift"], key: "r" }],
      checkCallback: (checking: boolean) => {
        // PDF view active → reload it from disk (same path as the toolbar button).
        const pdfView = this.app.workspace.getActiveViewOfType(ExternalPdfView);
        if (pdfView) {
          if (checking) return true;
          pdfView.reloadFromDisk();
          return true;
        }

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

            const metadata = await this.getZoteroItemMetadata(itemKey);

            const renderer = new TemplateRenderer(this.app);
            const profiles = this.settings.zoteroProfiles || [];
            if (profiles.length === 0) throw new Error("No Zotero profile found. Please run the Import Wizard once first.");
            const p = profiles[0]; // use first profile as default

            // Localize annotation region images into the vault asset folder using
            // the SAME path resolution as the import wizard (assetFolder/
            // assetSubfolder, with legacy imageFolder migration). Previously this
            // read the deprecated `imageFolder` field, which was empty after
            // migration, so reload emitted absolute Zotero cache paths. The shared
            // helper also overwrites an asset whose source region changed.
            await localizeAnnotationImages(this.app, renderer, p, metadata);

            const existingContent = await this.app.vault.read(file);
            const markdown = await renderer.renderTemplate(p.templatePath, metadata, existingContent);

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
          this,
          this.settings,
          async (settings) => {
            this.settings = settings;
            await this.saveSettings();
          }
        ).open();
      },
    });

    // No default hotkey: Cmd+K is reserved by Obsidian/another binding. Users can
    // assign their own hotkey to this command in Settings → Hotkeys.
    this.addCommand({
      id: "inline-edit",
      name: "Inline Edit",
      editorCallback: (_editor: Editor, ctx: MarkdownView | MarkdownFileInfo) => {
        if (ctx instanceof MarkdownView) {
          this.inlinePrompt.open(ctx);
        }
      },
    });

    // Cmd+Shift+K: In-line Copilot quick query on the current selection
    this.addCommand({
      id: "quick-query-selection",
      name: "Quick Query on Selection (Cmd+Shift+K)",
      callback: () => {
        this.quickQuery.openForCurrentSelection();
      },
      hotkeys: [{ modifiers: ["Mod", "Shift"], key: "k" }],
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
            if (!selectedText) {
              const pdfSel = getPdfSelection(leaf);
              if (pdfSel) selectedText = pdfSel.text;
            }
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
                    label: `${pdfView.getDisplayText()} p.${pdfCtx.pageNum} (Selection)`,
                    content: pdfCtx.text,
                    imageBase64: pdfCtx.imageBase64,
                    pageNum: pdfCtx.pageNum,
                    pageLabels: pdfCtx.pageLabels,
                    filePath: pdfView.getState()?.path,
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
            pdfView.startSnippingMode((base64: string, pageNum: number, regionText: string) => {
              this.ensureChatOpen().then(() => {
                const chatView = this.getChatView();
                if (chatView) {
                  // Capture ONLY the text lines inside the cropped rectangle
                  // (region-scoped), not the whole page. This becomes the crop's
                  // <primary_focus_selection> content so the model treats the
                  // snipped region as the core subject instead of burying it
                  // under the full-page background context — while never
                  // re-injecting the entire page text + RAG hits. Scanned crops
                  // yield "" and fall back to an image-only primary reference.
                  const pdfCtx = pdfView.getActivePdfContext("image");
                  chatView.addContextRef({
                    type: "pdf-page",
                    label: `${pdfView.getDisplayText()} p.${pageNum} (Crop)`,
                    content: regionText,
                    imageBase64: base64,
                    pageNum: pageNum,
                    pageLabels: pdfCtx?.pageLabels,
                    filePath: pdfView.getState()?.path,
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

    this.addCommand({
      id: "login-deepseek",
      name: "Check DeepSeek API Key",
      callback: () => {
        this.startProviderLogin("deepseek");
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
    // Removed per user request to avoid redundant status bars.

    // ── Initialize active context for current leaf ──
    const currentLeaf = this.app.workspace.getMostRecentLeaf();
    if (currentLeaf && currentLeaf.view.getViewType() !== CHAT_VIEW_TYPE) {
      this.lastContentLeaf = currentLeaf;
      this.updateActiveContext(currentLeaf);
    }

    // ── Zotero link interceptor (Global Patch) ──
    // Intercepts zotero://open-pdf and zotero://select clicks globally (including Live Preview).
    // Opens the resolved PDF in the built-in ExternalPdfView instead of launching Zotero.

    const originalWindowOpen = window.open;
    const externalOpeners: Array<(url: string) => Promise<void>> = [];
    try {
      const electron = require("electron");
      if (electron?.shell?.openExternal) {
        externalOpeners.push(electron.shell.openExternal.bind(electron.shell));
      }
    } catch { /* noop */ }
    try {
      const remote = require("@electron/remote");
      if (remote?.shell?.openExternal) {
        externalOpeners.push(remote.shell.openExternal.bind(remote.shell));
      }
    } catch { /* noop */ }

    const openZoteroExternally = async (url: string): Promise<void> => {
      const opener = externalOpeners[0];
      if (opener) return opener(url);
      originalWindowOpen.call(window, url, "_blank");
    };

    // Shared handler: resolve a zotero:// URL and open in ExternalPdfView
    const handleZoteroUrl = async (url: string): Promise<boolean> => {
      const zoteroInfo = parseZoteroLink(url);
      if (!zoteroInfo) return false;

      const attachmentKey = zoteroInfo.attachmentKey;
      let resolved: { path: string; attachmentKey: string } | null = null;

      try {
        resolved = await this.resolveZoteroPdf(attachmentKey);
      } catch (e: any) {
        new Notice(`Zotero PDF unavailable: ${e?.message || e}`);
        resolved = null;
      }

      if (!resolved) return false; // Let OS handle it

      const pdfPath = resolved.path;
      // Effective child attachment key — annotations are keyed by this, so a
      // parent (select) link can still jump to and highlight the annotation.
      const effectiveKey = resolved.attachmentKey;

      let leaf = this.app.workspace.getLeavesOfType(EXTERNAL_PDF_VIEW_TYPE).find(l => {
        return l.view.getState()?.path === pdfPath;
      }) || this.app.workspace.getLeavesOfType(EXTERNAL_PDF_VIEW_TYPE).find(l => {
        return l.view.getState()?.zoteroAttachmentKey === effectiveKey;
      });

      let pdfState: any;
      if (leaf) {
        const existingState = leaf.view.getState() as Partial<ExternalPdfState>;
        if (existingState?.docId) {
          replaceExternalPdfDocPath(existingState.docId, pdfPath);
        }
        pdfState = {
          ...existingState,
          path: pdfPath,
          zoteroAttachmentKey: effectiveKey,
        };
      } else {
        pdfState = registerExternalPdfByPath(pdfPath, effectiveKey);
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
        void handleZoteroUrl(link.href).then((handled) => {
          if (!handled) void openZoteroExternally(link.href);
        });
      }
    };
    this.registerDomEvent(document, 'click', interceptZoteroClick, { capture: true });
    this.registerDomEvent(document, 'auxclick', interceptZoteroClick, { capture: true });

    // On macOS, Obsidian/Electron may send zotero:// directly to the OS via
    // electron.shell.openExternal instead of window.open. Patch both.
    this.register(() => {
      window.open = originalWindowOpen;
    });

    window.open = (url?: string | URL, target?: string, features?: string) => {
      if (typeof url === "string" && parseZoteroLink(url)) {
        void handleZoteroUrl(url).then((handled) => {
          if (!handled) void openZoteroExternally(url);
        });
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

    // ── Start user-configured external MCP servers ──
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
    if (this.scrollPositionSaveTimer !== null) {
      window.clearTimeout(this.scrollPositionSaveTimer);
    }
    // ensure inline prompt is unmounted
    this.inlinePrompt.unload();
    this.quickQuery?.unload();

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
      const result: any = await this.readRuntimeJson("jobs");
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
      // Runtime snapshot not available yet — keep last text.
    }
  }

  async readRuntimeJson(name: "status" | "jobs" | "sources"): Promise<any | null> {
    try {
      const raw = await this.app.vault.adapter.read(`.curator/runtime/${name}.json`);
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  async runBackendCommand(cmdArgs: string[]): Promise<{ ok: boolean; output?: string; error?: string }> {
    const cwd = this.vaultRoot || (this.app.vault.adapter as any).getBasePath?.() || "";
    if (!cwd) return { ok: false, error: "Not a local vault" };
    const command = await this.resolveBackendCommand();
    const prefixArgs = this.settings.incuratorBackendArgs || [];
    return new Promise((resolve) => {
      const cp = spawn(command, [...prefixArgs, ...cmdArgs], { cwd, env: process.env });
      let out = "";
      let err = "";
      cp.stdout?.on("data", (d: Buffer) => out += d.toString());
      cp.stderr?.on("data", (d: Buffer) => err += d.toString());
      cp.on("error", (e) => resolve({ ok: false, error: e.message }));
      cp.on("close", (code) => {
        if (code === 0) resolve({ ok: true, output: out });
        else resolve({ ok: false, output: out, error: err || out || `Exit code ${code}` });
      });
    });
  }

  async runBackendJsonCommand(cmdArgs: string[]): Promise<any> {
    const result = await this.runBackendCommand(cmdArgs);
    const text = (result.output || "").trim();
    if (!text) {
      throw new Error(result.error || "Backend command returned no JSON");
    }
    try {
      return JSON.parse(text);
    } catch {
      const start = text.indexOf("{");
      const end = text.lastIndexOf("}");
      if (start >= 0 && end > start) {
        return JSON.parse(text.slice(start, end + 1));
      }
      throw new Error(result.error || `Backend command returned invalid JSON: ${text.slice(0, 200)}`);
    }
  }

  async searchZoteroItems(query: string, limit = 20): Promise<any[]> {
    return await this.incuratorClient.searchZoteroItems(query, limit);
  }

  async getZoteroItemMetadata(itemKey: string, citationStyle = ""): Promise<any> {
    return await this.incuratorClient.getZoteroItemMetadata(itemKey, citationStyle);
  }

  async getZoteroAnnotations(attachmentKey: string): Promise<any[]> {
    return await this.incuratorClient.getZoteroAnnotations(attachmentKey);
  }

  openZoteroRepairModal(initial: ZoteroRepairInitialState = {}): void {
    new ZoteroRepairModal(this.app, this.incuratorClient, initial).open();
  }

  async resolveZoteroPdf(
    attachmentKey: string
  ): Promise<{ path: string; attachmentKey: string } | null> {
    const res = await this.incuratorClient.resolveZoteroPdf(attachmentKey);
    if (res.ok && res.path) {
      // Prefer the backend's effective attachment key: a parent item key (from
      // zotero_app_url) resolves to its child PDF attachment, and annotations are
      // keyed by that child — so this is what must drive annotation lookups/jumps.
      return { path: res.path, attachmentKey: res.attachmentKey || attachmentKey };
    }
    this.openZoteroRepairModal({ attachmentKey, resolution: res });
    throw new Error(res.error || res.state || "Zotero PDF not found");
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
      await this.saveSettings();
    }
  }

  async ensureIncuratorBackend(): Promise<void> {
    const command = await this.resolveBackendCommand();
    await this.refreshAvailableModels();
    if (command !== "wiki") {
      await this.cacheBackendCommand(command);
    }
  }

  private async resolveBackendCommand(): Promise<string> {
    // Resolve the actual command to use:
    //   1. If user set a non-default incuratorBackendCommand, use it as-is.
    //   2. Otherwise, check devices.json for a cached per-device binary path.
    //   3. Otherwise, auto-discover from incuratorRepoPath / common PATH dirs.
    //   4. Fallback: bare "wiki" (works if wiki is on PATH).
    let command = this.settings.incuratorBackendCommand;
    const isDefault = !command || command === "wiki";

    if (isDefault) {
      // Try devices.json cache first
      let registry: Partial<DeviceRegistry> | null = null;
      try {
        const configPath = getGlobalRegistryPath(this.settings.incuratorRepoPath);
        if (configPath) {
          const raw = await fs.readFile(configPath, "utf-8");
          registry = JSON.parse(raw) as Partial<DeviceRegistry>;
        }
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
    return command || "wiki";
  }

  /** Persist the resolved backend command into devices.json for this device. */
  private async cacheBackendCommand(command: string): Promise<void> {
    try {
      let registry: Partial<DeviceRegistry> | null = null;
      const configPath = getGlobalRegistryPath(this.settings.incuratorRepoPath);
      if (configPath) {
        try {
          const raw = await fs.readFile(configPath, "utf-8");
          registry = JSON.parse(raw) as Partial<DeviceRegistry>;
        } catch { /* none yet */ }
      }

      // Update the local device's backend.command
      if (registry?.local_device_id && registry.devices && configPath) {
        const local = registry.devices[registry.local_device_id];
        if (local) {
          (local as Record<string, unknown>).backend = {
            ...((local as Record<string, unknown>).backend as Record<string, unknown> || {}),
            command,
          };
          registry.updated_at = Math.floor(Date.now() / 1000);
          
          // Ensure parent dir exists
          const path = require("path");
          const fsSync = require("fs");
          const dir = path.dirname(configPath);
          if (!fsSync.existsSync(dir)) fsSync.mkdirSync(dir, { recursive: true });
          
          await fs.writeFile(configPath, `${JSON.stringify(registry, null, 2)}\n`, "utf-8");
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
    try {
      const configPath = getGlobalRegistryPath(this.settings.incuratorRepoPath);
      if (configPath) {
        const registry = JSON.parse(
          await fs.readFile(configPath, "utf-8")
        ) as Partial<DeviceRegistry>;
        const localRepoPath = getLocalBackendRepoPath(registry);
        if (localRepoPath) this.settings.incuratorRepoPath = localRepoPath;
      }
    } catch {
      // No per-device registry yet; the plugin setting remains the fallback.
    }
    this.settings.mcpServers = (this.settings.mcpServers || []).filter(
      (server) => !isLegacyIncuratorMcpServer(server)
    );
    this.settings.providerUsage = {
      ...DEFAULT_SETTINGS.providerUsage,
      ...(this.settings.providerUsage || {}),
    };
    if (this.migrateUnavailableModelDefaults()) {
      await this.saveData(this.settings);
    }
  }

  /** Resolve the repo path: explicit override → live backend answer → cache. */
  resolveRepoPath(): string | null {
    const override = this.settings.incuratorRepoPath?.trim();
    if (override) return override;
    if (this.incuratorClient?.repoPath) return this.incuratorClient.repoPath;
    return null;
  }

  async updateIncuratorBackend(): Promise<void> {
    const repoPath = this.resolveRepoPath();
    if (!repoPath) {
      new Notice("This backend is not an editable install — nothing to update from. (Set a repository path in settings to override.)");
      return;
    }

    try {
      // First verify it's a valid path and has setup.sh
      const setupPath = `${repoPath}/setup.sh`;
      await fs.access(setupPath);

      // Copy pre-built plugin files from the repo into this vault's plugin directory.
      // setup.sh is responsible for building; this just deploys the result.
      const vaultBase = (this.app.vault.adapter as any).getBasePath?.() || this.vaultRoot;
      if (!vaultBase) {
        new Notice("Cannot locate vault path. Update the plugin manually.");
        return;
      }
      const destDir = `${vaultBase}/.obsidian/plugins/incurator-obsidian-agent`;
      const fsSync = require("fs") as typeof import("fs");
      let copied = 0;
      for (const fname of ["main.js", "manifest.json", "styles.css"]) {
        const src = `${repoPath}/plugin/${fname}`;
        try {
          fsSync.copyFileSync(src, `${destDir}/${fname}`);
          copied++;
        } catch { /* ignore — file may not exist if setup.sh hasn't run yet */ }
      }
      if (copied === 0) {
        new Notice("Plugin files not found in repo. Run setup.sh first, then try again.");
        return;
      }
      new Notice("Plugin updated. Reload Obsidian to apply the changes.");
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
    await this.syncDeviceRegistryFromSyncthing();
    // Update LLM client with new settings
    this.llmClient?.updateSettings(this.settings);
    // Notify sidebar to sync UI controls
    const leaves = this.app.workspace.getLeavesOfType(CHAT_VIEW_TYPE);
    for (const leaf of leaves) {
      if (leaf.view instanceof ChatSidebarView) {
        leaf.view.syncModelControls();
        leaf.view.syncReasoningControl();
      }
    }
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
      const zoteroRoots = [this.settings.zoteroBasePath].filter(
        (value): value is string => Boolean(value && value.trim())
      );
      const snapshot = await readSyncthingSnapshotWithStatus(this.vaultRoot, zoteroRoots);

      let existing: Partial<DeviceRegistry> | null = null;
      const configPath = getGlobalRegistryPath(this.settings.incuratorRepoPath);
      if (configPath) {
        try {
          const raw = await fs.readFile(configPath, "utf-8");
          existing = JSON.parse(raw) as Partial<DeviceRegistry>;
        } catch {
          existing = null;
        }
      }

      const registry = mergeDeviceRegistry(existing, snapshot, this.settings);
      
      if (configPath) {
        const path = require("path");
        const fsSync = require("fs");
        const dir = path.dirname(configPath);
        if (!fsSync.existsSync(dir)) fsSync.mkdirSync(dir, { recursive: true });
        
        await fs.writeFile(configPath, `${JSON.stringify(registry, null, 2)}\n`, "utf-8");
      }
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

  async refreshAvailableModels(): Promise<boolean> {
    const catalogue = getBundledModelCatalogue();
    if (Object.keys(catalogue).length === 0) return false;
    this.availableModels = catalogue;
    if (!this.settings.model) {
      this.settings.model = getDefaultModel(catalogue, this.settings.provider);
      await this.saveSettings();
      return true;
    }
    if (!getModelOption(catalogue, this.settings.provider, this.settings.model)) {
      const fallback = getDefaultModel(catalogue, this.settings.provider);
      if (fallback) {
        this.settings.model = fallback;
        await this.saveSettings();
      }
    }
    return true;
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
        if (pdfSelection) {
          this.activeContext.selectedText = pdfSelection.text;
          if (this.activeContext.pdfPage && pdfSelection.imageBase64) {
            this.activeContext.pdfPage.selectedImageBase64 = pdfSelection.imageBase64;
          }
        }
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
          // Capture PDF text selection + cropped image for external PDF tabs.
          const pdfSel = getPdfSelection(leaf);
          if (pdfSel) {
            selectedText = pdfSel.text;
            if (pdfPage && pdfSel.imageBase64) {
              pdfPage.selectedImageBase64 = pdfSel.imageBase64;
            }
          }
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
          // Capture PDF text selection + cropped image for non-active tabs too.
          // Without this, selectedImageBase64 is always undefined in openTabs,
          // causing buildAutoContextRefs to fall back to the full-page image.
          const pdfSel = getPdfSelection(leaf);
          if (pdfSel) {
            selectedText = pdfSel.text;
            if (pdfPage && pdfSel.imageBase64) {
              pdfPage.selectedImageBase64 = pdfSel.imageBase64;
            }
          }
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
      pageLabels: pdfCtx.pageLabels,
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

  /**
   * Cross-device knowledge auto-sync over Syncthing (one-writer-per-file).
   * All triggers — Obsidian load, the .curator/sync file watcher, the fallback
   * poll, and the manual ribbon — funnel through a single coalescing scheduler so
   * passes never overlap. The heavy JSONL work runs in the backend subprocess via
   * `wiki db autosync`, never on the Obsidian UI thread.
   */
  private setupAutoSync(): void {
    if (this.settings.incuratorEnabled === false) return;
    if (this.settings.autoSyncEnabled === false) return;

    this.syncStatusBar = this.addStatusBarItem();
    this.syncStatusBar.setText("");

    this.syncScheduler = new SyncScheduler(() => this.runAutoSyncPass(), 4000);

    // Manual trigger.
    this.addRibbonIcon("refresh-cw", "Sync Knowledge DB", () => {
      void this.syncScheduler?.runNow();
    });

    this.app.workspace.onLayoutReady(() => {
      if (this.settings.autoSyncOnLoad !== false) {
        void this.syncScheduler?.runNow();
      }
      this.startSyncWatcher();
    });

    // Fallback poll: covers platforms where fs.watch misses events and the case
    // where the sync dir did not exist yet when the watcher was first started.
    this.registerInterval(
      window.setInterval(() => {
        this.syncScheduler?.schedule();
      }, 60000)
    );

    this.register(() => {
      this.syncWatcher?.close();
      this.syncScheduler?.dispose();
    });
  }

  /** Watch .curator/sync for peer files (desktop only; degrades on mobile). */
  private startSyncWatcher(): void {
    if (this.settings.autoSyncWatch === false) return;
    const fsmod = (window as { require?: (m: string) => unknown }).require?.("fs") as
      | {
          watch?: (
            p: string,
            opts: { persistent: boolean },
            cb: (evt: string, filename: string) => void
          ) => { close: () => void };
          existsSync?: (p: string) => boolean;
        }
      | undefined;
    if (!fsmod?.watch) return; // mobile / no node fs → on-load + poll only
    const base =
      this.vaultRoot || (this.app.vault.adapter as { getBasePath?: () => string }).getBasePath?.() || "";
    if (!base) return;
    const dir = `${base}/.curator/sync`;
    try {
      if (fsmod.existsSync && !fsmod.existsSync(dir)) return;
      this.syncWatcher = fsmod.watch(dir, { persistent: false }, (_evt, filename) => {
        if (!filename || !filename.endsWith(".jsonl")) return;
        this.syncScheduler?.schedule();
      });
    } catch (e) {
      console.warn("[Incurator] sync watcher unavailable:", e);
    }
  }

  /** One auto-sync pass: import peers, merge conflicts, export self if changed. */
  private async runAutoSyncPass(): Promise<void> {
    if (this.settings.incuratorEnabled === false) return;
    this.syncStatusBar?.setText("⟳ Sync");
    try {
      const res = await this.incuratorClient.dbAutosync();
      if (!res.ok) {
        this.syncStatusBar?.setText("⚠ Sync Failed");
        new Notice(`Auto-sync failed: ${res.error || "Unknown error"}. Check if Incurator Repo Path is set in settings.`);
        return;
      }
      const changes = (res.inserted ?? 0) + (res.updated ?? 0) + (res.deleted ?? 0);
      if (this.settings.autoSyncNotify !== false && changes > 0) {
        new Notice(
          `Knowledge sync: ${res.inserted ?? 0} new, ${res.updated ?? 0} updated, ${res.deleted ?? 0} removed.`
        );
      }
      if ((res.conflicts?.length ?? 0) > 0) {
        new Notice(
          `Merged ${res.conflicts!.length} Syncthing conflict file(s) (LWW). ` +
            `Backups archived under .curator/runtime/sync_conflicts.`
        );
      }
      this.syncStatusBar?.setText(changes > 0 ? `✓ Sync ${changes}` : "");
    } catch (e) {
      console.error("[Incurator] auto-sync failed:", e);
      this.syncStatusBar?.setText("");
    }
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
          const status = await this.readRuntimeJson("status");
          if (status && status.search_ready) {
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
