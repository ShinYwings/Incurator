
import { logger } from "./src/utils/logger";
import { promises as fs } from "fs";
import { spawn } from "child_process";
import { dirname, join } from "path";
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
  normalizePluginModelEffort,
} from "./src/types";
import { AIAgentSettingTab } from "./src/settings";
import { CLIAuthResolver } from "./src/auth/cliAuth";
import { LLMClient } from "./src/agent/llmClient";
import type {
  LocalPdfToolContext,
  LocalPdfToolRunner,
  OutlineState,
} from "./src/agent/llm/localPdfTools";
import { MCPManager } from "./src/agent/mcpClient";
import { IncuratorClient } from "./src/agent/incuratorClient";
import { isIncomingPeerSnapshot, SyncScheduler } from "./src/agent/syncScheduler";
import { ChatSidebarView, CHAT_VIEW_TYPE } from "./src/ui/chatSidebar";
import {
  ExternalPdfView,
  EXTERNAL_PDF_VIEW_TYPE,
  type ExternalPdfState,
} from "./src/ui/externalPdfView";
import { asLoadedExternalPdfView } from "./src/ui/pdf/externalPdfLeaf";
import {
  registerExternalPdfByPath,
  setExternalPdfRuntimePath,
} from "./src/ui/externalPdfRegistry";
import { parseZoteroLink } from "./src/utils/zoteroUtils";

import { ZoteroSearchModal, ZoteroWizardModal } from "./src/ui/zoteroWizardModal";
import {
  ZoteroRepairModal,
  type ZoteroRepairInitialState,
} from "./src/ui/zoteroRepairModal";
import { TemplateRenderer } from "./src/zotero/templateRenderer";
import { localizeAnnotationImages, migrateZoteroProfileAssetFolders } from "./src/zotero/assetLocalization";
import { resolveZoteroRefreshProfile } from "./src/zotero/profileBinding";
import {
  ZOTERO_PROFILES_PATH,
  ZoteroProfilesFile,
  ZoteroProfileStoreBlockedError,
  extractLegacyZoteroProfiles,
  parseZoteroProfilesFile,
  writeMergedZoteroProfilesStore,
} from "./src/zotero/profileStore";
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
import { hashFileSha256 } from "./src/utils/fileHash";
import { assessPluginActivation } from "./src/utils/pluginActivation";
import { isSelectionRelevantKey } from "./src/utils/selectionKeys";
import {
  buildOpenTabContextKey,
  collectOpenTabLayoutContexts,
  isEligibleOpenTabView,
} from "./src/context/openTabContext";
import {
  isSelectionInReadingView,
  selectionContainsRenderedMath,
  selectionToMarkdownWithLatex,
  sliceLinesByIndex,
  stampMathSourceData,
} from "./src/utils/textUtils";
import { rewriteCuratorLinks } from "./src/utils/curatorWikilinks";
import {
  SessionStoreBlockedError,
  readSessionStore,
  writeMergedSessionStore,
} from "./src/utils/sessionStore";
import {
  readJsonObjectState,
} from "./src/utils/durableJsonStore";
import {
  backendCommandPolicy,
  collectBackendProcess,
} from "./src/utils/backendProcess";
import { normalizeSessionData } from "./src/utils/sessionData";
import { vaultMachineCacheDir } from "./src/utils/machineCache";
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
  private lastExportedSyncFile: string | null = null;
  private syncWatcher: {
    close: () => void;
    on?: (event: "error", listener: (err: unknown) => void) => unknown;
  } | null = null;
  private syncStatusBar: HTMLElement | null = null;
  private settingsPersistPromise: Promise<void> = Promise.resolve();
  private zoteroProfilesPersistPromise: Promise<void> = Promise.resolve();
  private sessionPersistPromise: Promise<void> = Promise.resolve();
  private sessionStoreWritable = false;
  private deletedZoteroProfiles: Record<string, number> = {};
  private localIncuratorRepoPathHint = "";
  private runtimePluginBundleHash: string | null = null;

  async onload(): Promise<void> {
    logger.debug("Loading Obsidian AI Agent plugin");
    this.startupRestoreUntilMs = Date.now() + 15000;

    // ── Load settings and session data ──
    await this.loadSettings();
    await this.loadSessionData();
    await this.loadZoteroProfiles();

    // ── Initialize core services ──
    this.vaultRoot = (this.app.vault.adapter as any).getBasePath?.() || "";
    try {
      this.runtimePluginBundleHash = await hashFileSha256(
        join(this.getInstalledPluginDir(), "main.js")
      );
    } catch (error) {
      logger.warn(
        `Could not fingerprint the running plugin bundle; version verification will be used: ${error instanceof Error ? error.message : String(error)}`
      );
    }
    await this.applyLocalRepoPathHint();
    this.settings.incuratorRepoPath = this.resolveRepoPath() || "";
    await this.syncDeviceRegistryFromSyncthing();
    this.llmClient = new LLMClient(
      this.settings,
      this.authResolver,
      this.vaultRoot,
      () => this.persistSettings(),
      this.mcpManager,
      () => this.assertActivePluginBundle()
    );
    this.llmClient.setLocalPdfToolRunner(this.buildLocalPdfToolRunner());
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
            if (!itemKey && citekey) itemKey = citekey; // last-resort lookup; a citekey is NOT a Zotero item key, so this may not resolve.

            // Skip the backend round-trip entirely when nothing resolved (e.g. a
            // malformed zotero_app_url and no citekey).
            if (!itemKey) {
              throw new Error(
                "This note has no resolvable Zotero item key (missing or malformed zotero_app_url and no citekey). Re-import it from the Zotero wizard."
              );
            }

            const metadata = await this.getZoteroItemMetadata(itemKey);
            // A citekey passed as an item key (or a missing item) yields empty
            // metadata. Abort before re-rendering so the note is never rewritten
            // with blanks.
            if (
              !metadata ||
              typeof metadata !== "object" ||
              Object.keys(metadata as Record<string, unknown>).length === 0
            ) {
              throw new Error(
                itemKey === citekey
                  ? `Could not resolve this note's Zotero item from its citekey ("${citekey}"). Re-import it from the Zotero wizard so it records a zotero_app_url.`
                  : `Zotero item "${itemKey}" was not found in your Zotero library.`
              );
            }

            const renderer = new TemplateRenderer(this.app);
            const profiles = this.settings.zoteroProfiles || [];
            if (profiles.length === 0) throw new Error("No Zotero profile found. Please run the Import Wizard once first.");
            const p = resolveZoteroRefreshProfile(profiles, cache.frontmatter);
            if (!p) throw new Error("No Zotero profile found. Please run the Import Wizard once first.");

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
              } else if (asLoadedExternalPdfView(view)) {
                const pdfView = asLoadedExternalPdfView(view)!;
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
                    filePath: pdfView.getRuntimePath(),
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
        const snipView = asLoadedExternalPdfView(view);
        if (snipView) {
          if (!checking) {
            const pdfView = snipView;
            pdfView.startSnippingMode(async (base64: string, pageNum: number, regionText: string) => {
              this.ensureChatOpen().then(() => {
                const chatView = this.getChatView();
                if (chatView) {
                  const pdfCtx = pdfView.getActivePdfContext("image");
                  // Add the crop immediately with the image thumbnail so the
                  // user sees the "Selected Area" chip right away.  VLM
                  // transcription is deferred to send-time (handleSend →
                  // materializeContextRefs) via the pendingCropBase64 field.
                  chatView.addContextRef({
                    type: "pdf-page",
                    label: `${pdfView.getDisplayText()} p.${pageNum} (Crop)`,
                    content: regionText,
                    imageBase64: base64,
                    pageNum: pageNum,
                    pageLabels: pdfCtx?.pageLabels,
                    filePath: pdfView.getRuntimePath(),
                    pendingCropBase64: base64,
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
        void this.checkDeepSeekApiKey();
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
        return l.view.getState()?.zoteroAttachmentKey === effectiveKey;
      });

      let pdfState: any;
      if (leaf) {
        const existingState = leaf.view.getState() as Partial<ExternalPdfState>;
        if (existingState?.docId) {
          setExternalPdfRuntimePath(existingState.docId, pdfPath);
        }
        pdfState = {
          ...existingState,
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
    const patchedWindowOpen = (url?: string | URL, target?: string, features?: string) => {
      if (typeof url === "string" && parseZoteroLink(url)) {
        void handleZoteroUrl(url).then((handled) => {
          if (!handled) void openZoteroExternally(url);
        });
        return null;
      }
      return originalWindowOpen.call(window, url, target, features);
    };
    this.register(() => {
      if (window.open === patchedWindowOpen) {
        window.open = originalWindowOpen;
      }
    });

    window.open = patchedWindowOpen;

    // Patch electron.shell.openExternal — Obsidian uses @electron/remote on desktop
    const patchShellModule = (mod: any, label: string) => {
      if (!mod?.shell?.openExternal) return;
      const originalOpenExternal = mod.shell.openExternal;
      const orig = originalOpenExternal.bind(mod.shell);
      const patched = async (url: string, options?: any): Promise<void> => {
        if (typeof url === "string" && url.toLowerCase().startsWith("zotero://")) {
          const handled = await handleZoteroUrl(url);
          if (handled) return;
        }
        return orig(url, options);
      };
      mod.shell.openExternal = patched;
      this.register(() => {
        if (mod.shell.openExternal === patched) {
          mod.shell.openExternal = originalOpenExternal;
        }
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

    logger.debug("Obsidian AI Agent plugin loaded");
  }

  async onunload(): Promise<void> {
    logger.debug("Unloading Obsidian AI Agent plugin");
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
    await this.persistSettings();
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

  /**
   * Transcribe a PNG crop to LaTeX, reporting failure in the CALLER's terms.
   *
   * `formatPdfExtractionFailure` ends with "Attached crop fallback.", which is
   * true only for the chat snip path — there the crop image stays attached to
   * the message when transcription fails. A caller that copies to the clipboard
   * attaches nothing, so it must supply its own wording rather than tell the
   * user about a fallback that did not happen. The default keeps the chat
   * path's message byte-for-byte.
   */
  async transcribePdfCrop(
    base64: string,
    formatFailure: (detail: string) => string = (detail) =>
      this.formatPdfExtractionFailure(detail),
  ): Promise<{ latex: string; model?: string } | null> {
    if (!this.vaultRoot) {
      new Notice(formatFailure("Vault root is unavailable"));
      return null;
    }
    const repoPath = this.resolveRepoPath();
    if (!repoPath) {
      new Notice(formatFailure("Incurator repository is unavailable"));
      return null;
    }
    const baseDir = join(
      vaultMachineCacheDir(repoPath, this.vaultRoot),
      "pdf_crops"
    );
    await fs.mkdir(baseDir, { recursive: true });
    const tmpDir = await fs.mkdtemp(join(baseDir, "crop-"));
    const imageFile = join(tmpDir, "crop.png");
    try {
      await fs.writeFile(imageFile, Buffer.from(base64, "base64"));
      const result = await this.incuratorClient.transcribePdfRegion({ imageFile });
      const latex = result.latex?.trim() || "";
      if (result.ok && latex) {
        return { latex, model: result.model };
      }
      new Notice(formatFailure(result.error || "No transcription returned"));
      return null;
    } catch (err) {
      new Notice(formatFailure(err instanceof Error ? err.message : String(err)));
      return null;
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  }

  private formatPdfExtractionFailure(error: string): string {
    return `PDF extraction model failed${error ? `: ${error}` : ""}. Attached crop fallback.`;
  }

  async readRuntimeJson(name: "status" | "jobs" | "sources"): Promise<any | null> {
    const repoPath = this.resolveRepoPath();
    if (!repoPath || !this.vaultRoot) return null;
    try {
      const raw = await fs.readFile(
        join(
          vaultMachineCacheDir(repoPath, this.vaultRoot),
          "runtime",
          `${name}.json`
        ),
        "utf-8"
      );
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  async runBackendCommand(cmdArgs: string[]): Promise<{ ok: boolean; output?: string; error?: string }> {
    const cwd = this.vaultRoot || (this.app.vault.adapter as any).getBasePath?.() || "";
    if (!cwd) return { ok: false, error: "Not a local vault" };
    const command = await this.resolveBackendCommand();
    if (!command) {
      return {
        ok: false,
        error: "Incurator backend command is unresolved. Set the Incurator repository path so the plugin can use <repo>/.venv/bin/wiki.",
      };
    }
    const prefixArgs = this.settings.incuratorBackendArgs || [];
    try {
      const cp = spawn(command, [...prefixArgs, ...cmdArgs], { cwd, env: process.env });
      return await collectBackendProcess(cp, backendCommandPolicy(cmdArgs));
    } catch (error) {
      return {
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      };
    }
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
      await this.persistSettings();
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
    // Surface which launcher answered, so a version mismatch can say "you are
    // talking to a different install" instead of only "expected X, got Y".
    if (this.incuratorClient) {
      this.incuratorClient.backendCommandLabel = command || "";
    }
    await this.refreshAvailableModels();
    if (command) {
      await this.cacheBackendCommand(command);
    }
  }

  private async resolveBackendCommand(): Promise<string | null> {
    // Resolve the actual command to use:
    //   1. If user set a non-default incuratorBackendCommand, use it as-is.
    //   2. Otherwise, check devices.json for a cached per-device binary path.
    //   3. Otherwise, auto-discover the repo-root `.venv/bin/wiki`.
    // Bare PATH `wiki` is intentionally not a fallback: global/conda scripts get stale.
    let command = this.settings.incuratorBackendCommand;
    const isDefault = !command || command === "wiki";
    const repoPath = this.getEffectiveIncuratorRepoPath();

    if (isDefault) {
      // Try devices.json cache first
      let registry: Partial<DeviceRegistry> | null = null;
      try {
        const configPath = getGlobalRegistryPath(repoPath);
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
        const discovered = resolveWikiBinary(repoPath);
        if (discovered) {
          command = discovered;
          logger.debug(`Auto-discovered wiki binary: ${command}`);
        }
      }
    }
    return command && command !== "wiki" ? command : null;
  }

  /** Persist the resolved backend command into devices.json for this device. */
  private async cacheBackendCommand(command: string): Promise<void> {
    try {
      let registry: Partial<DeviceRegistry> | null = null;
      const configPath = getGlobalRegistryPath(this.getEffectiveIncuratorRepoPath());
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

          await this.writeDeviceRegistry(configPath, registry);
          logger.debug(`Cached backend command in devices.json: ${command}`);
        }
      }
    } catch (err) {
      logger.warn("Failed to cache backend command:", err);
    }
  }

  // ── Settings ────────────────────────────────────────────────

  async loadSettings(): Promise<void> {
    const raw = (await this.loadData()) || {};
    const legacy = raw as Partial<PluginSettings>;
    const devicePathsMigrated = Boolean(
      legacy.zoteroBasePath ||
      legacy.incuratorRepoPath ||
      (legacy.incuratorBackendCommand &&
        legacy.incuratorBackendCommand !== "wiki") ||
      legacy.incuratorBackendArgs?.length
    );
    this.settings = Object.assign({}, DEFAULT_SETTINGS, raw);
    // Machine-local filesystem roots are backend-owned in repo `.cache/config`.
    // Legacy plugin values are ignored and removed on the next settings write.
    this.settings.zoteroBasePath = "";
    // Restore deepseekApiKey from env (never persisted per PLUGIN_SCHEMA §2.4)
    const envKey = (typeof process !== "undefined" && process.env?.DEEPSEEK_API_KEY) || "";
    if (envKey) this.settings.deepseekApiKey = envKey;
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
    const assetFoldersMigrated = migrateZoteroProfileAssetFolders(this.settings.zoteroProfiles);
    if (
      this.migrateUnavailableModelDefaults() ||
      assetFoldersMigrated ||
      devicePathsMigrated
    ) {
      await this.persistSettings();
    }
  }

  /** Resolve the repo path: explicit override → live backend answer → cache. */
  resolveRepoPath(): string | null {
    const override = this.settings.incuratorRepoPath?.trim();
    if (override) return override;
    if (this.incuratorClient?.repoPath) return this.incuratorClient.repoPath;
    if (this.localIncuratorRepoPathHint) return this.localIncuratorRepoPathHint;
    return null;
  }

  private getEffectiveIncuratorRepoPath(): string {
    return this.settings.incuratorRepoPath?.trim() || this.localIncuratorRepoPathHint;
  }

  private getInstalledPluginDir(): string {
    if (!this.vaultRoot) {
      throw new Error("Cannot locate the active vault plugin directory.");
    }
    const manifestDir =
      this.manifest.dir || join(".obsidian", "plugins", this.manifest.id);
    return join(this.vaultRoot, manifestDir);
  }

  async assertActivePluginBundle(): Promise<void> {
    const pluginDir = this.getInstalledPluginDir();
    let manifestText: string;
    let installedBundleHash: string;
    try {
      [manifestText, installedBundleHash] = await Promise.all([
        fs.readFile(join(pluginDir, "manifest.json"), "utf8"),
        hashFileSha256(join(pluginDir, "main.js")),
      ]);
    } catch (error) {
      throw new Error(
        `Cannot verify the installed Incurator plugin bundle. Reload Obsidian after checking the plugin files. (${error instanceof Error ? error.message : String(error)})`
      );
    }
    const activation = assessPluginActivation(
      this.manifest.version,
      manifestText,
      this.runtimePluginBundleHash ?? undefined,
      installedBundleHash
    );
    if (activation.reloadRequired) {
      throw new Error(
        `Incurator was updated on disk (${activation.installedVersion}) but Obsidian is still running ${activation.runtimeVersion}. Click “Reload Obsidian” before sending another request.`
      );
    }
  }

  private async applyLocalRepoPathHint(): Promise<void> {
    if (this.settings.incuratorRepoPath?.trim() || !this.vaultRoot) return;
    const workspaceRoot = dirname(this.vaultRoot);
    for (const repoPath of [join(workspaceRoot, "Incurator"), join(workspaceRoot, "incurator")]) {
      try {
        await fs.access(join(repoPath, "setup.sh"));
        await fs.access(join(repoPath, ".venv", "bin", "wiki"));
        this.localIncuratorRepoPathHint = repoPath;
        return;
      } catch {
        // Keep probing local sibling repo names without persisting anything to data.json.
      }
    }
  }

  async updateIncuratorBackend(): Promise<boolean> {
    const repoPath = this.resolveRepoPath();
    if (!repoPath) {
      new Notice("This backend is not an editable install — nothing to update from. (Set a repository path in settings to override.)");
      return false;
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
        return false;
      }
      const destDir = this.getInstalledPluginDir();
      const fsSync = require("fs") as typeof import("fs");
      const artifacts = ["main.js", "manifest.json", "styles.css"];
      for (const fname of artifacts) {
        const src = `${repoPath}/plugin/${fname}`;
        fsSync.accessSync(src);
      }
      for (const fname of artifacts) {
        const src = `${repoPath}/plugin/${fname}`;
        fsSync.copyFileSync(src, `${destDir}/${fname}`);
      }
      new Notice("Plugin updated. Reload Obsidian to apply the changes.");
      return true;
    } catch (e: any) {
      logger.error("Failed to update Incurator backend:", e);
      new Notice("Failed to update Incurator backend: " + (e.message || "Unknown error"));
      return false;
    }
  }

  /** Return a copy of settings safe to persist — strips secrets not allowed in data.json (PLUGIN_SCHEMA §2.4). */
  private _persistableSettings(): Omit<PluginSettings, "deepseekApiKey"> & { deepseekApiKey: "" } {
    // deepseekApiKey MUST NOT be persisted: it would be leaked to Obsidian Sync
    // and any git-tracked vault. Restore from env DEEPSEEK_API_KEY at load time.
    const { deepseekApiKey: _stripped, ...rest } = this.settings;
    return {
      ...rest,
      incuratorBackendCommand: "wiki",
      incuratorBackendArgs: [],
      incuratorRepoPath: "",
      zoteroBasePath: "",
      deepseekApiKey: "",
      // v0.30.0: the durable store is .curator/zotero_profiles.json (synced);
      // data.json must never carry profiles again (PLUGIN_SCHEMA) — but ONLY
      // once the store has actually loaded/migrated. loadSettings() can
      // persist (its own migrations) BEFORE loadZoteroProfiles() runs;
      // blanking then would destroy the legacy fields — the only copy — if the
      // subsequent store write failed (PR #78 second review). Until the load
      // guard is set, the legacy values pass through unchanged.
      ...(this._zoteroProfilesLoaded
        ? { zoteroProfiles: [], recentZoteroItems: [] }
        : {}),
    };
  }

  private persistSettings(): Promise<void> {
    this.settingsPersistPromise = this.settingsPersistPromise
      .catch(() => undefined)
      .then(() => this.saveData(this._persistableSettings()));
    return this.settingsPersistPromise;
  }

  async updateSettings(updates: Partial<PluginSettings>): Promise<void> {
    Object.assign(this.settings, updates);
    await this.persistSettings();
    // Update LLM client with new settings
    this.llmClient?.updateSettings(this.settings);
  }

  async saveSettings(): Promise<void> {
    await this.persistSettings();
    // Profiles/LRU live in the synced .curator store, not data.json; every
    // explicit settings save also flushes them (guarded until initial load).
    await this.saveZoteroProfiles();
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

  // ── Zotero profiles (vault-resident, synced via .curator/zotero_profiles.json) ──

  /** Guards saveZoteroProfiles(): a save before the initial load would wipe
   *  the synced file with empty in-memory state. */
  private _zoteroProfilesLoaded = false;

  /** Load Zotero import profiles + recent-item LRU from the synced store and
   *  mirror them into settings (all call sites read settings.zoteroProfiles).
   *  Migrates legacy data.json fields on first load (PLUGIN_SCHEMA v0.30.0).
   *
   *  Missing, unreadable, and corrupt canonical states are distinguished:
   *  a present-but-invalid store must NOT fall through to the legacy
   *  migration — post-migration the legacy fields are blank, so that fallback
   *  would mark an empty list as loaded and the next save would silently
   *  overwrite the recoverable file. Never throws: a failure here must not
   *  abort plugin onload. */
  async loadZoteroProfiles(): Promise<void> {
    const canonical = await readJsonObjectState(
      this.app.vault.adapter,
      ZOTERO_PROFILES_PATH
    );
    if (canonical.kind === "corrupt" || canonical.kind === "unreadable") {
      logger.error(
        `${ZOTERO_PROFILES_PATH} is ${canonical.kind} — Zotero profiles are ` +
          "read-only this session; repair or delete the file and reload Obsidian."
      );
      new Notice(
        "Zotero profiles file is unavailable or corrupted — profiles are read-only until " +
          `${ZOTERO_PROFILES_PATH} is repaired or removed.`
      );
      return;
    }

    if (canonical.kind === "valid") {
      const store = parseZoteroProfilesFile(canonical.raw);
      if (store === null) {
        logger.error(
          `${ZOTERO_PROFILES_PATH} contains invalid data — Zotero profiles are ` +
            "read-only this session; repair or delete the file and reload Obsidian."
        );
        new Notice(
          "Zotero profiles file is corrupted — profiles are read-only until " +
            `${ZOTERO_PROFILES_PATH} is repaired or removed.`
        );
        return;
      }
      this.settings.zoteroProfiles = store.profiles;
      this.settings.recentZoteroItems = store.recentItems;
      this.deletedZoteroProfiles = store.deletedProfiles;
      this._zoteroProfilesLoaded = true;
      // File-loaded profiles may predate the assetFolder split — migrate them
      // here too (loadSettings only migrates legacy data.json profiles).
      try {
        if (migrateZoteroProfileAssetFolders(this.settings.zoteroProfiles)) {
          await this.saveZoteroProfiles();
        }
      } catch (e) {
        logger.error("zotero profile asset-folder migration save failed:", e);
      }
      return;
    }

    // Missing store — migrate legacy data.json fields if any.
    const legacy = extractLegacyZoteroProfiles(this.settings);
    this.settings.zoteroProfiles = legacy?.profiles ?? [];
    this.settings.recentZoteroItems = legacy?.recentItems ?? [];
    this.deletedZoteroProfiles = legacy?.deletedProfiles ?? {};
    this._zoteroProfilesLoaded = true;
    if (legacy) {
      // Write the new store first, then persist settings (which always blanks
      // the legacy fields) — non-destructive ordering. Best-effort: an I/O
      // failure leaves the legacy fields in data.json, so the migration simply
      // retries on the next load instead of breaking onload.
      try {
        await this.saveZoteroProfiles();
        await this.persistSettings();
      } catch (e) {
        logger.error("zotero profile legacy migration failed (will retry on next load):", e);
      }
    }
  }

  /** Persist profiles through a serialized read-merge-write queue. */
  async saveZoteroProfiles(): Promise<void> {
    if (!this._zoteroProfilesLoaded) return;
    const local: ZoteroProfilesFile = {
      profiles: (this.settings.zoteroProfiles || []).map((profile) => ({ ...profile })),
      recentItems: [...(this.settings.recentZoteroItems || [])],
      deletedProfiles: { ...this.deletedZoteroProfiles },
    };
    this.zoteroProfilesPersistPromise = this.zoteroProfilesPersistPromise
      .catch(() => undefined)
      .then(async () => {
        if (!(await this.app.vault.adapter.exists(".curator"))) {
          await this.app.vault.adapter.mkdir(".curator");
        }
        let store: ZoteroProfilesFile;
        try {
          store = await writeMergedZoteroProfilesStore(
            this.app.vault.adapter,
            ZOTERO_PROFILES_PATH,
            local
          );
        } catch (error) {
          if (error instanceof ZoteroProfileStoreBlockedError) {
            this._zoteroProfilesLoaded = false;
          }
          throw error;
        }
        this.settings.zoteroProfiles = store.profiles;
        this.settings.recentZoteroItems = store.recentItems;
        this.deletedZoteroProfiles = store.deletedProfiles;
      });
    return this.zoteroProfilesPersistPromise;
  }

  async deleteZoteroProfile(index: number): Promise<void> {
    const profile = this.settings.zoteroProfiles[index];
    if (!profile) return;
    this.deletedZoteroProfiles[profile.name] = Date.now();
    this.settings.zoteroProfiles.splice(index, 1);
    await this.saveSettings();
  }

  // ── Session data (device-local, stored in sessions.json) ────────

  private get _sessionsPath(): string {
    return ".curator/sessions.json";
  }

  async loadSessionData(): Promise<void> {
    const canonical = await readSessionStore(
      this.app.vault.adapter,
      this._sessionsPath
    );
    if (canonical.kind === "valid") {
      this.sessionData = canonical.value;
      this.sessionStoreWritable = true;
      return;
    }
    if (canonical.kind === "corrupt" || canonical.kind === "unreadable") {
      this.sessionData = { ...DEFAULT_SESSION_DATA };
      this.sessionStoreWritable = false;
      logger.error(
        `${this._sessionsPath} is ${canonical.kind}; session persistence is disabled ` +
          "until the canonical file is repaired or removed and Obsidian is reloaded."
      );
      new Notice(
        "Chat sessions file is unavailable or corrupted — existing bytes were preserved " +
          "and session saving is disabled until it is repaired or removed."
      );
      return;
    }

    this.sessionStoreWritable = true;
    // Canonical file is genuinely missing — legacy migration is now safe.
    try {
      const oldRaw = await this.app.vault.adapter.read(`${this.manifest.dir}/sessions.json`);
      this.sessionData = normalizeSessionData(
        JSON.parse(oldRaw) as Partial<SessionData>
      );
      await this.saveSessionData();
      await this.app.vault.adapter.remove(`${this.manifest.dir}/sessions.json`);
      return;
    } catch {
      // Proceed to data.json legacy migration.
    }

    const raw = (await this.loadData()) || {};
    const legacy = raw as { chatSessions?: SessionData["chatSessions"]; activeChatSessionId?: string };
    if (legacy.chatSessions?.length) {
      this.sessionData = {
        chatSessions: legacy.chatSessions,
        activeChatSessionId: legacy.activeChatSessionId,
      };
      await this.saveSessionData();
      delete (this.settings as unknown as Record<string, unknown>).chatSessions;
      delete (this.settings as unknown as Record<string, unknown>).activeChatSessionId;
      await this.persistSettings();
    } else {
      this.sessionData = { ...DEFAULT_SESSION_DATA };
    }
  }

  async saveSessionData(): Promise<void> {
    const snapshot = normalizeSessionData(
      JSON.parse(JSON.stringify(this.sessionData)) as Partial<SessionData>
    );
    this.sessionPersistPromise = this.sessionPersistPromise
      .catch(() => undefined)
      .then(() => this.writeSessionData(snapshot));
    return this.sessionPersistPromise;
  }

  private async writeSessionData(snapshot: SessionData): Promise<void> {
    if (!this.sessionStoreWritable) {
      throw new Error("canonical session store is read-only this session");
    }

    if (!(await this.app.vault.adapter.exists(".curator"))) {
      await this.app.vault.adapter.mkdir(".curator");
    }

    try {
      this.sessionData = await writeMergedSessionStore(
        this.app.vault.adapter,
        this._sessionsPath,
        snapshot
      );
    } catch (error) {
      if (error instanceof SessionStoreBlockedError) {
        this.sessionStoreWritable = false;
        new Notice(
          "Chat sessions file changed to an invalid state; saving is disabled " +
            "until it is repaired or removed and Obsidian is reloaded."
        );
      }
      throw error;
    }
  }

  private async syncDeviceRegistryFromSyncthing(): Promise<void> {
    if (!this.vaultRoot) return;
    try {
      const zoteroRoots = [this.settings.zoteroBasePath].filter(
        (value): value is string => Boolean(value && value.trim())
      );
      const snapshot = await readSyncthingSnapshotWithStatus(this.vaultRoot, zoteroRoots);

      let existing: Partial<DeviceRegistry> | null = null;
      const repoPath = this.getEffectiveIncuratorRepoPath();
      const configPath = getGlobalRegistryPath(repoPath);
      if (configPath) {
        try {
          const raw = await fs.readFile(configPath, "utf-8");
          existing = JSON.parse(raw) as Partial<DeviceRegistry>;
        } catch {
          existing = null;
        }
      }

      const registry = mergeDeviceRegistry(existing, snapshot, {
        ...this.settings,
        incuratorRepoPath: repoPath,
      });
      
      if (configPath) {
        await this.writeDeviceRegistry(configPath, registry);
      }
    } catch (err) {
      logger.warn("Device registry auto-sync failed:", err);
    }
  }

  private async writeDeviceRegistry(
    configPath: string,
    registry: Partial<DeviceRegistry>
  ): Promise<void> {
    await fs.mkdir(dirname(configPath), { recursive: true });
    await fs.writeFile(configPath, `${JSON.stringify(registry, null, 2)}\n`, "utf-8");
  }

  private migrateUnavailableModelDefaults(): boolean {
    const knownModel = getModelOption(
      this.availableModels,
      this.settings.provider,
      this.settings.model
    );
    if (this.settings.model && knownModel) {
      return normalizePluginModelEffort(this.settings, this.availableModels, false);
    }
    // Ollama serves arbitrary user-pulled model ids the bundled catalogue
    // cannot enumerate; never reset a non-empty custom Ollama model.
    if (this.settings.model && this.settings.provider === "ollama") return false;

    const backendDefault = getDefaultModel(this.availableModels, this.settings.provider) || "";
    let modelChanged = false;
    if (this.settings.model !== backendDefault) {
      this.settings.model = backendDefault;
      modelChanged = true;
    }
    const effortChanged = normalizePluginModelEffort(
      this.settings,
      this.availableModels,
      modelChanged
    );
    return modelChanged || effortChanged;
  }

  getAvailableModels(): ModelCatalogue {
    return this.availableModels;
  }

  async refreshAvailableModels(): Promise<boolean> {
    const catalogue = getBundledModelCatalogue();
    if (Object.keys(catalogue).length === 0) return false;
    this.availableModels = catalogue;
    let modelChanged = false;
    if (!this.settings.model) {
      this.settings.model = getDefaultModel(catalogue, this.settings.provider);
      modelChanged = true;
    } else if (!getModelOption(catalogue, this.settings.provider, this.settings.model)) {
      const fallback = getDefaultModel(catalogue, this.settings.provider);
      if (fallback) {
        this.settings.model = fallback;
        modelChanged = true;
      }
    }
    const effortChanged = normalizePluginModelEffort(
      this.settings,
      catalogue,
      modelChanged
    );
    if (modelChanged || effortChanged) await this.saveSettings();
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

  /** Fetch any page's text for the active PDF on demand.
   *  Quick-query cross-reference resolution uses the backend first so Reference
   *  Mode identity, durable L1, and per-device PDF caches stay aligned with
   *  sidechat. The open PDF.js viewer remains the fallback. */
  async fetchActivePdfPage(
    pageNum: number,
    expectedDocumentId?: string
  ): Promise<string | undefined> {
    const pdf = this.activeContext.pdfPage;
    // Pin the viewer and its identity BEFORE any await. The viewer fallback
    // below must never re-resolve to whatever document happens to be active
    // after the backend round-trip: a tab switch during that await would
    // otherwise read a page out of the wrong PDF, using bounds that were
    // validated against the original one (PLUGIN_SCHEMA §13.7).
    const pinnedView = this.app.workspace.getActiveViewOfType(ExternalPdfView);
    const pinnedDocumentId = pinnedView?.getDocumentId();
    if (expectedDocumentId !== undefined && pinnedDocumentId !== expectedDocumentId) {
      return undefined;
    }
    if (this.incuratorClient?.available && pdf) {
      try {
        const backendCtx = await this.incuratorClient.getPdfContext({
          filePath: pdf.filePath,
          fileHash: pdf.fileHash,
          zoteroAttachmentKey: pdf.zoteroAttachmentKey,
          pageNum,
          radius: 0,
          maxPages: 1,
        });
        const exact = backendCtx?.pages.find((page) => page.pageNum === pageNum);
        const text = exact?.text?.trim();
        if (text) return text;
      } catch (err) {
        logger.warn("Backend PDF page fetch failed; falling back to PDF.js viewer:", err);
      }
    }

    if (!pinnedView) return undefined;
    // The same view instance is reused across documents (setState), so re-check
    // identity rather than trusting the pinned reference alone.
    if (pinnedView.getDocumentId() !== pinnedDocumentId) return undefined;
    const page = await pinnedView.fetchPage(pageNum);
    return page?.text ?? undefined;
  }

  /** Return the full document BM25 index from the active ExternalPdfView (all seen pages). */
  getActivePdfDocumentIndex() {
    const pdfView = this.app.workspace.getActiveViewOfType(ExternalPdfView);
    return pdfView?.getDocumentIndex();
  }

  /** Return the document ID used when indexing the active PDF (needed to search the full index). */
  getActivePdfDocumentId(): string | undefined {
    const pdfView = this.app.workspace.getActiveViewOfType(ExternalPdfView);
    return pdfView?.getDocumentId();
  }

  /**
   * The read-only PDF page reader exposed to the model (v0.41.0, PLUGIN_SCHEMA
   * §13.7). It wraps the existing page fetch and document index only — it can
   * express nothing beyond "give me page N of the PDF already open" and "BM25
   * over the pages of that PDF already read". No filesystem, vault, Zotero, or
   * shell reach is possible through this interface.
   */
  private buildLocalPdfToolRunner(): LocalPdfToolRunner {
    return {
      describeContext: (): LocalPdfToolContext => {
        const pdf = this.activeContext.pdfPage;
        const documentId = this.getActivePdfDocumentId();
        const hasActivePdf = Boolean(pdf) && Boolean(documentId);
        // An empty outline array is ambiguous — the viewer resets it to [] on
        // load and fills it from an async parse — so absence is only *proven*
        // once `outlineResolved` says the lookup finished. Anything else counts
        // as unknown and withholds anchor search.
        const outlineState: OutlineState = !hasActivePdf
          ? "unknown"
          : !pdf?.outlineResolved
            ? "unknown"
            : pdf.outline && pdf.outline.length > 0
              ? "present"
              : "absent";
        return {
          hasActivePdf,
          pageCount: pdf?.pageCount,
          currentPage: pdf?.pageNum,
          documentId,
          outlineState,
        };
      },
      // Identity is passed down so the fetch fails closed if the document
      // changes mid-flight, rather than silently reading the swapped one.
      fetchPage: (pageNum: number) =>
        this.fetchActivePdfPage(pageNum, this.getActivePdfDocumentId()),
      // Reuses transcribePdfCrop: the same backend vision call the manual snip
      // already makes, driven by a rendered page instead of a user-drawn box.
      // The render is verified against the real file (equation 29's page
      // rasterizes legibly); the transcription leg is the existing snip path
      // unchanged, not a second implementation.
      //
      // Identity is pinned exactly as fetchActivePdfPage does it, and for the
      // same reason (PLUGIN_SCHEMA §13.7): this crosses TWO awaits — the page
      // render and the backend vision round-trip — so a tab switch mid-flight
      // would otherwise rasterize page N of whatever document is now active
      // and hand it back as page N of the one the model asked about.
      readPageImage: async (pageNum: number) => {
        const pinnedView = this.app.workspace.getActiveViewOfType(ExternalPdfView);
        const pinnedDocumentId = pinnedView?.getDocumentId();
        const expectedDocumentId = this.getActivePdfDocumentId();
        if (!pinnedView) return undefined;
        if (expectedDocumentId !== undefined && pinnedDocumentId !== expectedDocumentId) {
          return undefined;
        }
        const base64 = await pinnedView.renderPageImageBase64(pageNum);
        if (!base64) return undefined;
        // Re-check after the render: the user may have switched tabs while it
        // ran, and the vision round-trip below is the longer of the two awaits.
        if (pinnedView.getDocumentId() !== pinnedDocumentId) return undefined;
        const result = await this.transcribePdfCrop(
          base64,
          (detail) =>
            `Could not read page ${pageNum} as an image` +
            `${detail ? `: ${detail}` : ""}.`,
        );
        return result?.latex;
      },
      searchAnchor: async (query: string, topK: number) => {
        const index = this.getActivePdfDocumentIndex();
        const documentId = this.getActivePdfDocumentId();
        if (!index || !documentId) return [];
        return index.search(documentId, query, { topK });
      },
    };
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
      // External PDF: use the view's own capture method directly. A deferred
      // (Obsidian >= 1.7.2) or stale tab matches the view type but exposes no
      // methods, so it contributes identity only — capture is skipped rather
      // than throwing this whole context build (which Send, the popover, and
      // the context pins all depend on).
      const extView = asLoadedExternalPdfView(leaf.view);
      this.activeContext = {
        viewType: "pdf",
        filePath: file?.path,
        absolutePath: this.toAbsolutePath(file?.path),
        displayName: file?.basename || extView?.getDisplayText() || "External PDF",
        openTabs,
      };
      try {
        const pdfCtx = extView
          ? withVisionFallback(
              extView.getActivePdfContext(this.settings.pdfCaptureMode),
              this.settings.pdfCaptureMode,
              this.settings.pdfVisionFallback,
              () => extView.getActivePdfContext("image")?.imageBase64
            )
          : undefined;
        if (pdfCtx) this.activeContext.pdfPage = pdfCtx;
      } catch (err) {
        logger.warn("Failed to capture external PDF context:", err);
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
        logger.warn("Failed to capture PDF context:", err);
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
    const tabs = new Map<string, OpenTabContext>();

    this.app.workspace.iterateAllLeaves((leaf) => {
      const viewState = leaf.getViewState();
      const state = (viewState.state ?? {}) as Record<string, unknown>;
      const viewType = viewState.type || leaf.view.getViewType();
      if (!isEligibleOpenTabView(viewType)) return;

      const isActive = leaf === activeLeaf;
      const containerEl = (leaf as unknown as { containerEl?: HTMLElement }).containerEl;
      let isVisible = isActive;
      if (!isVisible && containerEl) {
        const rect = containerEl.getBoundingClientRect();
        isVisible = rect.width > 0 && rect.height > 0;
      }

      const liveFile = this.getLeafFile(leaf);
      const stateFile = typeof state.file === "string" ? state.file : undefined;
      const file = liveFile ?? (
        stateFile
          ? {
              path: stateFile,
              basename:
                stateFile.split("/").pop()?.replace(/\.[^/.]+$/, "") || stateFile,
            }
          : null
      );

      let content: string | undefined;
      let selectedText: string | undefined;
      let pdfPage: OpenTabContext["pdfPage"];
      let pageNum: number | undefined;
      let sourceIdentity = file?.path || leaf.view.getDisplayText() || viewType;
      if (viewType === "markdown" && file) {
        const mdView = leaf.view as unknown as {
          editor?: { getValue(): string; getSelection(): string };
        };
        if (mdView.editor) {
          content = mdView.editor.getValue();
          selectedText = mdView.editor.getSelection() || undefined;
        }
      } else if (viewType === EXTERNAL_PDF_VIEW_TYPE) {
        // A deferred (Obsidian >= 1.7.2) or stale tab answers the view type but
        // has no methods, so fall back to its persisted state instead of casting.
        const extView = asLoadedExternalPdfView(leaf.view);
        const extState = extView?.getState() ?? state as Partial<ExternalPdfState>;
        pageNum =
          typeof extState.currentPage === "number" ? extState.currentPage : undefined;
        sourceIdentity = extState.zoteroAttachmentKey
          ? `zotero:${extState.zoteroAttachmentKey}`
          : extState.externalRef
            ? `external:${extState.externalRef}`
            : extState.docId
              ? `document:${extState.docId}`
              : sourceIdentity;
        if (isVisible && extView) {
          try {
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
            logger.warn("Failed to capture open external PDF context:", err);
          }
        }
      } else if (viewType === "pdf") {
        const statePage = state.page;
        pageNum =
          typeof statePage === "number"
            ? statePage
            : typeof statePage === "string" && Number.isFinite(Number(statePage))
              ? Number(statePage)
              : undefined;
        if (isVisible && leaf.view.getViewType() === "pdf") {
          try {
            pdfPage = withVisionFallback(
              getPdfContext(leaf, this.settings.pdfCaptureMode),
              this.settings.pdfCaptureMode,
              this.settings.pdfVisionFallback,
              () => getPdfContext(leaf, "image")?.imageBase64
            ) || undefined;
            // Capture PDF text selection + cropped image for visible non-active splits.
            const pdfSel = getPdfSelection(leaf);
            if (pdfSel) {
              selectedText = pdfSel.text;
              if (pdfPage && pdfSel.imageBase64) {
                pdfPage.selectedImageBase64 = pdfSel.imageBase64;
              }
            }
          } catch (err) {
            logger.warn("Failed to capture open PDF context:", err);
          }
        }
      }
      pageNum = pdfPage?.pageNum ?? pageNum;

      const tab: OpenTabContext = {
        label:
          file?.basename ||
          (typeof state.name === "string" ? state.name : undefined) ||
          leaf.view.getDisplayText() ||
          viewType,
        viewType,
        sourceIdentity,
        filePath: file?.path,
        pageNum,
        isActive,
        isVisible,
        content,
        selectedText,
        pdfPage,
      };
      const key = buildOpenTabContextKey({
        viewType,
        sourceIdentity,
        filePath: tab.filePath,
        label: tab.label,
        pageNum: tab.pageNum,
      });
      const existing = tabs.get(key);
      if (!existing || tab.isActive || (tab.isVisible && !existing.isVisible)) {
        tabs.set(key, tab);
      }
    });

    // Obsidian may defer inactive tabs inside pop-out tab groups, so they do
    // not always exist as WorkspaceLeaf instances. The public saved layout is
    // the complete identity inventory; these fallbacks stay hidden/not-ready
    // until Obsidian materializes the corresponding leaf.
    for (const layoutTab of collectOpenTabLayoutContexts(
      this.app.workspace.getLayout()
    )) {
      const key = buildOpenTabContextKey(layoutTab);
      if (tabs.has(key)) continue;
      tabs.set(key, {
        ...layoutTab,
        isActive: false,
        isVisible: false,
      });
    }

    return Array.from(tabs.values());
  }

  private getLeafFile(leaf: WorkspaceLeaf): { path: string; basename: string } | null {
    if (leaf.view.getViewType() === EXTERNAL_PDF_VIEW_TYPE) {
      // Obsidian >= 1.7.2 restores tabs as deferred views: the type string
      // matches while the placeholder carries none of this class's methods.
      // Casting on the string alone threw out of here, and because this
      // function feeds updateActiveContext() AND the open-tab inventory, one
      // deferred PDF tab blanked the context pins and killed Send/popover.
      const extView = asLoadedExternalPdfView(leaf.view);
      // getState() no longer includes path (v0.29.0 portable storage). Use
      // getRuntimePath() as the authoritative runtime path source.
      const runtimePath = extView?.getRuntimePath();
      if (runtimePath) {
        return { path: runtimePath, basename: extView!.getDisplayText() || "External PDF" };
      }
      // Fall back to legacy state.path for transitional compatibility.
      const state = typeof (leaf.view as any).getState === "function" ? (leaf.view as any).getState() : null;
      if (state && state.path) {
        return { path: state.path, basename: state.name || "External PDF" };
      }
      return null;
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

  private async checkDeepSeekApiKey(): Promise<void> {
    if (this.settings.deepseekApiKey?.trim()) {
      new Notice("DeepSeek API key is configured in plugin settings.");
      return;
    }

    try {
      await this.authResolver.resolveToken("deepseek");
      new Notice("DeepSeek API key is configured in the environment.");
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

  /** Read-only snapshot of the sidechat's pinned context refs (v0.53.2). */
  getPinnedContextRefs(): ContextRef[] {
    return this.getChatView()?.getPinnedContextRefs() ?? [];
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
          ) => {
            close: () => void;
            on?: (event: "error", listener: (err: unknown) => void) => unknown;
          };
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
        if (!isIncomingPeerSnapshot(filename, this.lastExportedSyncFile)) return;
        this.syncScheduler?.schedule();
      });
      this.syncWatcher?.on?.("error", (err) => {
        logger.warn("sync watcher error:", err);
      });
    } catch (e) {
      logger.warn("sync watcher unavailable:", e);
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
      if (res.exported) {
        this.lastExportedSyncFile = res.exported;
      }
      const changes = (res.inserted ?? 0) + (res.updated ?? 0) + (res.deleted ?? 0);
      if (this.settings.autoSyncNotify !== false && changes > 0) {
        new Notice(
          `Knowledge sync: ${res.inserted ?? 0} new, ${res.updated ?? 0} updated, ${res.deleted ?? 0} removed.`
        );
      }
      if ((res.rejected ?? 0) > 0) {
        // Always notify, regardless of autoSyncNotify: this is data that did
        // NOT arrive, not routine progress the user opted out of.
        new Notice(
          `Knowledge sync: ${res.rejected} row(s) were refused and are NOT in ` +
            `this vault. A peer's export is likely truncated or malformed; ` +
            `re-export from that device.`
        );
      }
      if ((res.conflicts?.length ?? 0) > 0) {
        new Notice(
          `Merged ${res.conflicts!.length} Syncthing conflict file(s) (LWW). ` +
            `Conflicts archived under the local Incurator repository cache.`
        );
      }
      this.syncStatusBar?.setText(changes > 0 ? `✓ Sync ${changes}` : "");
    } catch (e) {
      logger.error("auto-sync failed:", e);
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
