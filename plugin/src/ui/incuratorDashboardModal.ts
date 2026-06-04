import { App, Modal, Notice, parseYaml, setIcon } from "obsidian";
import type ObsidianAIAgent from "../../main";
import type { LLMProvider, ModelOption } from "../types";

const PROVIDER_TO_PRIMARY: Record<LLMProvider, string> = {
  antigravity: "antigravity-cli",
  claude:      "claude-code",
  openai:      "codex-cli",
  ollama:      "ollama",
  deepseek:    "deepseek-api",
};
const PRIMARY_TO_PROVIDER: Record<string, LLMProvider> = {
  "antigravity-cli": "antigravity",
  "claude-code":     "claude",
  "codex-cli":       "openai",
  "ollama":          "ollama",
  "deepseek-api":    "deepseek",
};
const PROVIDER_LABELS: Record<LLMProvider, string> = {
  antigravity: "Antigravity",
  claude:      "Claude",
  openai:      "Codex",
  ollama:      "Ollama",
  deepseek:    "DeepSeek",
};

type TabId = "overview" | "jobs" | "sources" | "persona";
const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: "overview", label: "Overview", icon: "layout-dashboard" },
  { id: "jobs",     label: "Jobs",     icon: "loader" },
  { id: "sources",  label: "Sources",  icon: "list" },
  { id: "persona",  label: "Persona",  icon: "user" },
];

export class IncuratorDashboardModal extends Modal {
  plugin: ObsidianAIAgent;

  private vaultConfig: any = null;
  private activeTab: TabId = "overview";
  private tabEls  = new Map<TabId, HTMLElement>();
  private viewEls = new Map<TabId, HTMLElement>();
  private jobsTimer: number | null = null;

  private dragState = { isDragging: false, startX: 0, startY: 0, initialLeft: 0, initialTop: 0 };
  private onMouseMove = (e: MouseEvent) => {
    if (!this.dragState.isDragging) return;
    this.modalEl.style.left = `${this.dragState.initialLeft + e.clientX - this.dragState.startX}px`;
    this.modalEl.style.top  = `${this.dragState.initialTop  + e.clientY - this.dragState.startY}px`;
  };
  private onMouseUp = () => {
    if (!this.dragState.isDragging) return;
    this.dragState.isDragging = false;
    (this.modalEl.querySelector(".ai-agent-dashboard-header") as HTMLElement)
      ?.style.setProperty("cursor", "grab");
  };

  constructor(app: App, plugin: ObsidianAIAgent) {
    super(app);
    this.plugin = plugin;
  }

  async onOpen() {
    const { contentEl } = this;
    contentEl.empty();
    this.modalEl.addClass("ai-agent-dashboard-modal-wrapper");

    const sidebar = contentEl.createDiv("ai-agent-dashboard-sidebar");
    const header  = sidebar.createDiv("ai-agent-dashboard-header");
    const titleEl = header.createEl("h2");
    setIcon(titleEl.createSpan(), "database");
    titleEl.appendText(" Incurator");
    const versionEl = header.createDiv({ cls: "ai-agent-sidebar-version" });
    versionEl.setText("backend …");
    this.renderBackendVersion(versionEl);

    header.style.cursor = "grab";
    header.addEventListener("mousedown", (e) => {
      this.dragState.isDragging = true;
      header.style.cursor = "grabbing";
      this.dragState.startX = e.clientX;
      this.dragState.startY = e.clientY;
      const rect = this.modalEl.getBoundingClientRect();
      if (this.modalEl.style.position !== "absolute") {
        this.modalEl.style.position = "absolute";
        this.modalEl.style.left     = rect.left + "px";
        this.modalEl.style.top      = rect.top  + "px";
        this.modalEl.style.margin    = "0";
        this.modalEl.style.transform = "none";
      }
      this.dragState.initialLeft = parseInt(this.modalEl.style.left || "0", 10);
      this.dragState.initialTop  = parseInt(this.modalEl.style.top  || "0", 10);
      e.preventDefault();
    });
    document.addEventListener("mousemove", this.onMouseMove);
    document.addEventListener("mouseup",   this.onMouseUp);

    const nav  = sidebar.createDiv("ai-agent-dashboard-nav");
    const main = contentEl.createDiv("ai-agent-dashboard-content");

    for (const t of TABS) {
      const view = main.createDiv("ai-agent-dashboard-view");
      this.viewEls.set(t.id, view);
      const tab = nav.createDiv("ai-agent-dashboard-tab");
      setIcon(tab.createSpan(), t.icon);
      tab.appendText(` ${t.label}`);
      this.tabEls.set(t.id, tab);
      tab.onclick = () => this.switchTab(t.id);
    }

    // Refresh the bundled backend model catalogue before Dashboard dropdowns render.
    this.plugin.refreshAvailableModels().catch(() => {});

    const cfgP = this.readVaultConfig();
    this.switchTab("overview", cfgP);
  }

  onClose() {
    this.contentEl.empty();
    if (this.jobsTimer !== null) window.clearInterval(this.jobsTimer);
    document.removeEventListener("mousemove", this.onMouseMove);
    document.removeEventListener("mouseup",   this.onMouseUp);
  }

  // ---------------------------------------------------------------------------
  // Tab routing
  // ---------------------------------------------------------------------------

  private switchTab(id: TabId, cfgP?: Promise<any>) {
    this.activeTab = id;
    this.tabEls.forEach((el, tid) => el.toggleClass("is-active", tid === id));
    this.viewEls.forEach((el, vid) => el.toggleClass("is-active", vid === id));
    if (id !== "jobs" && this.jobsTimer !== null) {
      window.clearInterval(this.jobsTimer);
      this.jobsTimer = null;
    }
    const view = this.viewEls.get(id)!;
    view.empty();
    const p = cfgP ?? this.readVaultConfig();
    switch (id) {
      case "overview":  this.renderOverview(view, p);  break;
      case "jobs":      this.renderJobs(view);          break;
      case "sources":   this.renderSources(view);       break;
      case "persona":   this.renderPersona(view, p);  break;
    }
  }

  // ---------------------------------------------------------------------------
  // Vault helpers
  // ---------------------------------------------------------------------------

  private async readVaultConfig(): Promise<any> {
    try {
      const raw = await this.plugin.app.vault.adapter.read(".curator/config.yml");
      this.vaultConfig = parseYaml(raw);
    } catch { this.vaultConfig = null; }
    return this.vaultConfig;
  }

  private async getLayerCounts(): Promise<Record<string, number>> {
    const adapter = this.plugin.app.vault.adapter;
    const layers: [string, string][] = [
      ["01_Contexts", "contexts"], ["02_Atoms", "atoms"],
      ["03_Concepts", "concepts"], ["04_Synthesis", "synthesis"],
    ];
    const counts: Record<string, number> = {};
    await Promise.all(layers.map(async ([dir, key]) => {
      try {
        const list = await (adapter as any).list(`.curator/Collections/${dir}`);
        counts[key] = (list?.files ?? []).filter((f: string) => f.endsWith(".md")).length;
      } catch { counts[key] = 0; }
    }));
    return counts;
  }

  private async readDevicesJson(): Promise<any> {
    try { return JSON.parse(await this.plugin.app.vault.adapter.read(".curator/devices.json")); }
    catch { return null; }
  }

  private async readRuntimeJson<T = any>(name: "status" | "jobs" | "sources"): Promise<T | null> {
    try {
      return JSON.parse(await this.plugin.app.vault.adapter.read(`.curator/runtime/${name}.json`)) as T;
    } catch {
      return null;
    }
  }

  private async refreshRuntimeSnapshots(): Promise<void> {
    await this.runWikiCommand(["status"]);
  }

  private async readRuntimeStatus(): Promise<any | null> {
    let status = await this.readRuntimeJson("status");
    if (status) return status;
    await this.refreshRuntimeSnapshots();
    status = await this.readRuntimeJson("status");
    return status;
  }

  private async renderBackendVersion(el: HTMLElement): Promise<void> {
    const status = await this.readRuntimeStatus();
    if (status?.backend_version) {
      el.setText(`backend ${status.backend_version}`);
      return;
    }
    const result = await this.runWikiCommand(["version"]);
    const match = result.output?.match(/incurator\s+([^\s]+)/i);
    el.setText(match ? `backend ${match[1]}` : "backend unknown");
  }

  private vaultBase(): string {
    try { return (this.plugin.app.vault.adapter as any).getBasePath?.() ?? ""; }
    catch { return ""; }
  }

  // ---------------------------------------------------------------------------
  // Shared helpers
  // ---------------------------------------------------------------------------

  private makeInfoTable(parent: HTMLElement): (label: string, val?: string, cls?: string) => HTMLElement {
    const table = parent.createDiv("ai-agent-dashboard-info-table");
    return (label, val, cls) => {
      const row = table.createDiv("info-row");
      row.createDiv({ cls: "info-label", text: label });
      return row.createDiv({ cls: `info-value${cls ? " " + cls : ""}`, text: val ?? "…" });
    };
  }

  private addActionBtn(parent: HTMLElement, label: string, icon: string, fn: () => Promise<void>) {
    const b = parent.createEl("button", { cls: "ai-agent-dashboard-btn" });
    b.style.padding = "4px 10px";
    b.style.fontSize = "12px";
    setIcon(b.createSpan(), icon);
    const textSpan = b.createSpan({ text: ` ${label}` });
    b.onclick = async () => {
      b.disabled = true;
      const orig = textSpan.innerText;
      textSpan.innerText = " Running…";
      try { await fn(); } catch (e) { new Notice(`Error: ${e}`); }
      finally { textSpan.innerText = orig; b.disabled = false; }
    };
  }

  private async runWikiCommand(cmdArgs: string[]): Promise<{ ok: boolean, output?: string, error?: string }> {
    return this.plugin.runBackendCommand(cmdArgs);
  }

  // ---------------------------------------------------------------------------
  // OVERVIEW TAB
  // ---------------------------------------------------------------------------

  private async renderOverview(el: HTMLElement, cfgP: Promise<any>) {
    const cfg = await cfgP;
    
    // ── Actions row ──────────────────────────────────────────────────────────
    const acts = el.createDiv("ai-agent-dashboard-actions");
    acts.style.borderTop = "none";
    acts.style.paddingTop = "0";
    acts.style.paddingBottom = "16px";
    acts.style.borderBottom = "1px solid var(--background-modifier-border)";
    acts.style.marginBottom = "16px";
    acts.style.flexWrap = "nowrap";
    acts.style.overflowX = "auto";
    acts.style.justifyContent = "flex-start";
    acts.style.gap = "6px";

    this.addActionBtn(acts, "Add",     "file-plus",    async () => {
      new Notice("Running Incurator add...");
      const r = await this.runWikiCommand(["add"]);
      if (r.ok) await this.refreshRuntimeSnapshots();
      new Notice(r.ok ? "Add complete." : `Add failed: ${r.error}`);
      this.switchTab(this.activeTab);
    });
    this.addActionBtn(acts, "Build",   "hammer",       async () => {
      new Notice("Queueing Incurator build...");
      const r = await this.runWikiCommand(["build"]);
      if (r.ok) await this.refreshRuntimeSnapshots();
      new Notice(r.ok ? "Build queued. Open Jobs to run or monitor queued work." : `Build failed: ${r.error}`);
      this.switchTab(this.activeTab);
    });
    this.addActionBtn(acts, "Sync",    "refresh-cw",   async () => {
      new Notice("Running Incurator sync...");
      const r = await this.runWikiCommand(["sync"]);
      if (r.ok) await this.refreshRuntimeSnapshots();
      new Notice(r.ok ? "Sync complete." : `Sync failed: ${r.error}`);
      this.switchTab(this.activeTab);
    });
    this.addActionBtn(acts, "Lint",    "check-circle", async () => {
      new Notice("Running Incurator lint...");
      const r = await this.runWikiCommand(["lint"]);
      if (r.ok) await this.refreshRuntimeSnapshots();
      new Notice(r.ok ? "Lint complete." : `Lint failed: ${r.error}`);
    });
    this.addActionBtn(acts, "Reindex", "search",       async () => {
      new Notice("Running Incurator reindex...");
      const r = await this.runWikiCommand(["reindex"]);
      if (r.ok) await this.refreshRuntimeSnapshots();
      new Notice(r.ok ? "Reindex complete." : `Reindex failed: ${r.error}`);
    });
    this.addActionBtn(acts, "Reset",   "trash-2",      async () => {
      if (!confirm("This will clear your local DB and L1-L4 content (keeping notes and configs). Proceed?")) return;
      if (!confirm("WARNING: Are you absolutely sure you want to RESET the backend? This action cannot be undone.")) return;
      new Notice("Running wiki reset...");
      const r = await this.runWikiCommand(["reset", "--force"]);
      if (r.ok) await this.refreshRuntimeSnapshots();
      new Notice(r.ok ? `Reset complete: ${r.output?.slice(-100)}` : `Reset failed: ${r.error}`);
    });

    const grid = el.createDiv("ai-agent-ov-grid");

    // ── LLM (hero card, spans full width) ────────────────────────────────────
    const llmCard = this.ovCard(grid, "span-full", null);
    llmCard.createDiv({ cls: "ai-agent-ov-card-title", text: "LLM Provider" });
    if (cfg) this.renderLLMSelector(llmCard, cfg);

    // ── Knowledge-graph counts (one compact strip — secondary info) ──────────
    const statDefs: [string, string, string][] = [
      ["L1", "contexts",    "Contexts"],
      ["L2", "atoms",       "Atoms"],
      ["L3", "concepts",    "Concepts"],
      ["L4", "synthesis",   "Synthesis"],
    ];
    const kgCard = this.ovCard(grid, "span-full ai-agent-ov-kg-card", "sources");
    kgCard.createDiv({ cls: "ai-agent-ov-card-title", text: "Knowledge Graph" });
    const kgStrip = kgCard.createDiv("ai-agent-ov-kg-strip");
    const statValEls: Record<string, HTMLElement> = {};
    for (const [tag, key, label] of statDefs) {
      const item = kgStrip.createDiv("ai-agent-ov-kg-item");
      item.createSpan({ cls: "ai-agent-ov-kg-tag", text: tag });
      statValEls[key] = item.createSpan({ cls: "ai-agent-ov-kg-num", text: "…" });
      item.createSpan({ cls: "ai-agent-ov-kg-label", text: label });
    }
    this.readRuntimeStatus().then((status) => status?.layer_counts || this.getLayerCounts()).then((c) => {
      for (const [k, e] of Object.entries(statValEls)) e.setText(String(c[k] ?? 0));
    });

    // ── Jobs card (live status) ──────────────────────────────────────────────
    const jobsCard = this.ovCard(grid, "span-2", "jobs");
    jobsCard.createDiv({ cls: "ai-agent-ov-card-title", text: "Build Jobs" });
    const jobsBody = jobsCard.createDiv({ cls: "ai-agent-ov-jobs-body" });
    jobsBody.createDiv({ cls: "ai-agent-dashboard-loading", text: "Checking…" });
    this.readRuntimeJson("jobs").then((data: any) => {
      jobsBody.empty();
      if (!data || data.idle) {
        const row = jobsBody.createDiv("ai-agent-ov-jobs-idle");
        setIcon(row.createSpan(), "check-circle");
        row.createSpan({ text: ` Idle · ${data?.done_today ?? 0} done today` });
      } else {
        const running: any[] = data.running ?? [];
        const queued:  any[] = data.queued  ?? [];
        if (running.length) {
          const j = running[0];
          const pct = j.progress_total ? Math.round((j.progress_current / j.progress_total) * 100) : 0;
          jobsBody.createDiv({ cls: "ai-agent-ov-jobs-active", text: `${j.source_name || "?"} · ${j.job_type || ""}` });
          const bar = jobsBody.createDiv("ai-agent-progress-outer");
          bar.createDiv("ai-agent-progress-inner").style.width = `${pct}%`;
        }
        if (running.length + queued.length > 1)
          jobsBody.createDiv({ cls: "ai-agent-compact-muted", text: `+${running.length + queued.length - 1} more queued` });
      }
    }).catch(() => { jobsBody.empty(); jobsBody.createSpan({ text: "—" }); });

    // ── Search card ──────────────────────────────────────────────────────────
    const s = cfg?.search ?? {};
    const searchCard = this.ovCard(grid, "span-1", null);
    searchCard.createDiv({ cls: "ai-agent-ov-card-title", text: "Search" });
    searchCard.createDiv({ cls: "ai-agent-ov-card-value", text: (s.backend || "qmd").toUpperCase() });
    searchCard.createDiv({
      cls: `ai-agent-ov-card-sub ${s.rerank !== false ? "is-ok" : ""}`,
      text: `rerank ${s.rerank !== false ? "on" : "off"}`,
    });

    // Determine Zotero initial fallback path for System card
    const z = cfg?.external?.zotero ?? {};
    const zRoots = z.roots ?? [];
    let rootsText = "no roots";
    if (zRoots.length > 0) {
      rootsText = `${zRoots.length} root(s)`;
    } else if (this.plugin.settings.zoteroBasePath) {
      rootsText = this.plugin.settings.zoteroBasePath;
    } else {
      rootsText = "~/Zotero (default)";
    }

    // ── Persona card ─────────────────────────────────────────────────────────
    const personaCard = this.ovCard(grid, "span-1", "persona");
    personaCard.createDiv({ cls: "ai-agent-ov-card-title", text: "PERSONA" });
    const pArea = cfg?.persona?.area || "General";
    personaCard.createDiv({ cls: "ai-agent-ov-card-value is-ok", text: pArea, attr: { title: pArea } }).style.fontSize = "18px";
    const pText = cfg?.persona?.text || "No description";
    personaCard.createDiv({ cls: "ai-agent-ov-card-sub", text: pText.length > 50 ? pText.slice(0, 50) + "…" : pText, attr: { title: pText } });

    // ── System card (full paths, spans full width) ───────────────────────────
    const sysCard = this.ovCard(grid, "span-full ai-agent-ov-sys-card", null);
    sysCard.createDiv({ cls: "ai-agent-ov-card-title", text: "System" });
    const sysTable = sysCard.createDiv("ai-agent-ov-path-table");
    const pathRow = (label: string, val?: string) => {
      const row = sysTable.createDiv("ai-agent-ov-path-row");
      row.createDiv({ cls: "ai-agent-ov-path-label", text: label });
      return row.createDiv({ cls: "ai-agent-ov-path-value", text: val ?? "…" });
    };
    const vaultEl = pathRow("Vault");
    const wikiEl  = pathRow("Wiki CLI");
    const qmdEl   = pathRow("QMD");
    const zoteroSysEl = pathRow("Zotero", rootsText);
    zoteroSysEl.addClass("is-ok");
    zoteroSysEl.style.cursor = "pointer";
    zoteroSysEl.addEventListener("click", async () => {
      const status = await this.plugin.incuratorClient.getZoteroStatus();
      this.plugin.openZoteroRepairModal({ status });
    });
    this.plugin.incuratorClient.getZoteroStatus().then((status) => {
      const label = status.ok
        ? status.dbPath || status.dataDir || "ready"
        : status.error || status.dataDir || status.state;
      zoteroSysEl.setText(label);
      zoteroSysEl.setAttr("title", [
        `state: ${status.state}`,
        ...status.rootsChecked.map((root) => `checked: ${root}`),
      ].join("\n"));
      zoteroSysEl.toggleClass("is-ok", status.ok);
      zoteroSysEl.toggleClass("is-warn", !status.ok);
    }).catch(() => {
      zoteroSysEl.setText("offline");
      zoteroSysEl.toggleClass("is-ok", false);
      zoteroSysEl.toggleClass("is-warn", true);
    });

    this.readRuntimeStatus().then((st: any) => {
      vaultEl.setText(st?.vault_root || this.vaultBase() || "Unknown");
      wikiEl.setText(st?.wiki_binary || "Not found");
      wikiEl.toggleClass("is-ok", !!st?.wiki_binary);
      wikiEl.toggleClass("is-warn", !st?.wiki_binary);
      qmdEl.setText(st?.qmd_binary || "Not found");
      qmdEl.toggleClass("is-ok", !!st?.qmd_binary);
      qmdEl.toggleClass("is-warn", !st?.qmd_binary);
      
      const zoteroRoots = st?.external?.zotero?.roots;
      if (Array.isArray(zoteroRoots) && zoteroRoots.length > 0) {
        const discovered = zoteroRoots.join(", ");
        if (!zoteroSysEl.getText() || zoteroSysEl.getText() === rootsText) {
          zoteroSysEl.setText(discovered);
          zoteroSysEl.setAttr("title", discovered);
        }
      }
    }).catch(() => {
      vaultEl.setText(this.vaultBase() || "offline");
      wikiEl.setText("offline"); wikiEl.addClass("is-warn");
      qmdEl.setText("offline");  qmdEl.addClass("is-warn");
    });

    // ── Sync/Curate card ─────────────────────────────────────────────────────
    const syncCard = this.ovCard(grid, "span-2", null);
    syncCard.createDiv({ cls: "ai-agent-ov-card-title", text: "Pipeline" });
    const syncTable = this.makeInfoTable(syncCard);
    syncTable("Sync workers",  String(cfg?.sync?.max_parallel_verifications ?? 4));
    syncTable("Log retention", `${cfg?.curate?.log_retention_days ?? 30} days`);

    // ── Syncthing device-folder card ────────────────────────────────────────
    const deviceCard = this.ovCard(grid, "span-2", null);
    deviceCard.createDiv({ cls: "ai-agent-ov-card-title", text: "Syncthing Devices" });
    const devListContainer = deviceCard.createDiv({ cls: "ai-agent-ov-device-list" });
    devListContainer.style.marginTop = "12px";
    devListContainer.style.display = "flex";
    devListContainer.style.flexDirection = "column";
    devListContainer.style.gap = "8px";

    this.plugin.app.vault.adapter.read(".curator/devices.json").then((raw: string) => {
      try {
        const reg = JSON.parse(raw);
        if (reg?.devices) {
          const localId = reg.local_device_id;
          const folders: any[] = Array.isArray(reg.syncthing?.folders) ? reg.syncthing.folders : [];
          let devices = Object.entries(reg.devices);
          const inferLocal = ([id, d]: [string, any]) => {
            if (id === localId) return true;
            if (!localId && (d?.platform || d?.backend)) return true;
            if (localId === "local" && d?.platform) return true;
            return false;
          };

          if (devices.length === 0) {
            devListContainer.createDiv({ text: "No devices", cls: "ai-agent-ov-card-sub" });
          } else {
            // Sort to put the local device first
            devices.sort((entryA, entryB) => {
              if (inferLocal(entryA)) return -1;
              if (inferLocal(entryB)) return 1;
              return String((entryA[1] as any).name || entryA[0]).localeCompare(String((entryB[1] as any).name || entryB[0]));
            });
            for (const [id, d] of devices) {
              const isLocal = inferLocal([id, d]);
              const syncedFolderIds = isLocal && id === "local"
                ? folders
                : folders.filter((folder) => Array.isArray(folder.device_ids) && folder.device_ids.includes(id));
              const folderLabels = syncedFolderIds
                .map((folder) => folder.label || folder.id || folder.role)
                .filter(Boolean);
              const row = devListContainer.createDiv();
              row.style.fontSize = "14px";
              row.style.display = "flex";
              row.style.alignItems = "center";
              row.style.gap = "8px";
              row.style.minWidth = "0"; // ensure truncation works
              
              const applyTruncation = (el: HTMLElement) => {
                el.style.whiteSpace = "nowrap";
                el.style.overflow = "hidden";
                el.style.textOverflow = "ellipsis";
              };

              if (isLocal) {
                row.createSpan({ text: "●", cls: "is-ok" });
                const nameEl = row.createSpan({ text: `${(d as any).name || id} (This device)`, cls: "is-ok", attr: { title: "Current device on this machine" } });
                nameEl.style.fontWeight = "600";
                nameEl.style.lineHeight = "1.2";
                applyTruncation(nameEl);
              } else {
                row.createSpan({ text: "○", attr: { style: "opacity: 0.5" } });
                const nameEl = row.createSpan({ text: (d as any).name || "Unknown", attr: { title: (d as any).device_id || id, style: "opacity: 0.8" } });
                nameEl.style.lineHeight = "1.2";
                applyTruncation(nameEl);
              }
              const foldersEl = row.createSpan({
                cls: "ai-agent-compact-muted",
                text: folderLabels.length ? ` -> ${folderLabels.join(", ")}` : " -> no synced folder",
              });
              applyTruncation(foldersEl);
            }
          }
        } else {
          devListContainer.createDiv({ text: "No sync data", cls: "ai-agent-ov-card-sub" });
        }
      } catch {
        devListContainer.createDiv({ text: "Error loading", cls: "ai-agent-ov-card-sub" });
      }
    }).catch(() => {
      devListContainer.createDiv({ text: "devices.json not found", cls: "ai-agent-ov-card-sub" });
    });

  }

  /** Create one grid card; clicking navigates to targetTab if given. */
  private ovCard(grid: HTMLElement, extraCls: string, targetTab: TabId | null): HTMLElement {
    const card = grid.createDiv(`ai-agent-ov-card ${extraCls}`);
    if (targetTab) {
      card.addClass("is-clickable");
      card.onclick = (e) => {
        // Don't navigate when interacting with controls inside the card
        const tgt = e.target as HTMLElement;
        if (tgt.closest("select, button, input, a")) return;
        this.switchTab(targetTab);
      };
    }
    return card;
  }

  // ---------------------------------------------------------------------------
  // LLM Selector (grouped <select> like chatSidebar)
  // ---------------------------------------------------------------------------

  /** Convert a stored 'backend-provider::model' value into the catalogue value 'catProv::model'. */
  private toCatalogueValue(raw: string): string {
    const sep = raw.indexOf("::");
    if (sep < 0) return raw ? `${PRIMARY_TO_PROVIDER[raw] ?? raw}::` : "";
    const prov = raw.slice(0, sep);
    const model = raw.slice(sep + 2);
    return `${PRIMARY_TO_PROVIDER[prov] ?? prov}::${model}`;
  }

  /** Convert a catalogue value 'catProv::model' into the stored 'backend-provider::model'. */
  private toStoredValue(catValue: string): string {
    const sep = catValue.indexOf("::");
    if (sep < 0) return "";
    const catProv = catValue.slice(0, sep);
    const model = catValue.slice(sep + 2);
    const backend = PROVIDER_TO_PRIMARY[catProv as LLMProvider] ?? catProv;
    return `${backend}::${model}`;
  }

  /** Resolve a catalogue value 'catProv::model' to its ModelOption (for effort options). */
  private getModelOption(catValue: string): ModelOption | undefined {
    const sep = catValue.indexOf("::");
    if (sep < 0) return undefined;
    const prov = catValue.slice(0, sep) as LLMProvider;
    const model = catValue.slice(sep + 2);
    return (this.plugin.availableModels[prov] || []).find((m) => m.id === model);
  }

  private renderLLMSelector(container: HTMLElement, cfg: any) {
    const llm = cfg?.llm ?? {};
    const primaryCur  = this.toCatalogueValue((llm.primary  as string) || "");
    const fallbackCur = this.toCatalogueValue((llm.fallback as string) || "");
    const primaryEffCur  = (llm.primary_effort  as string) || "";
    const fallbackEffCur = (llm.fallback_effort as string) || "";

    let primarySel: HTMLSelectElement;
    let fallbackSel: HTMLSelectElement;

    // ── Primary row ──
    const pRow = container.createDiv("ai-agent-llm-row");
    pRow.createSpan({ cls: "ai-agent-llm-label", text: "Primary" });
    primarySel = pRow.createEl("select", { cls: "ai-agent-model-select-full dropdown" });
    const primaryEffortSel = pRow.createEl("select", { cls: "ai-agent-effort-select dropdown" });

    // ── Fallback row ──
    const fRow = container.createDiv("ai-agent-llm-row");
    fRow.createSpan({ cls: "ai-agent-llm-label", text: "Fallback" });
    fallbackSel = fRow.createEl("select", { cls: "ai-agent-model-select-full dropdown" });
    const fallbackEffortSel = fRow.createEl("select", { cls: "ai-agent-effort-select dropdown" });

    // Repopulate an effort dropdown from the model currently chosen in its select.
    const refreshEffort = (modelSel: HTMLSelectElement, effortSel: HTMLSelectElement, preferred: string) => {
      const opt = this.getModelOption(modelSel.value);
      const efforts = opt?.efforts ?? [];
      effortSel.empty();
      if (!efforts.length) {
        effortSel.createEl("option", { value: "", text: "—" });
        effortSel.disabled = true;
        return;
      }
      effortSel.disabled = false;
      for (const e of efforts) effortSel.createEl("option", { value: e, text: e });
      const want = efforts.includes(preferred) ? preferred : (opt?.defaultEffort || efforts[0]);
      effortSel.value = want;
    };

    const populate = (cat: any) => {
      primarySel.empty();
      fallbackSel.empty();
      this.populateModelSelect(primarySel, cat, primaryCur, false);
      this.populateModelSelect(fallbackSel, cat, fallbackCur, true);
      refreshEffort(primarySel, primaryEffortSel, primaryEffCur);
      refreshEffort(fallbackSel, fallbackEffortSel, fallbackEffCur);
    };
    // Changing a model resets its effort to that model's default.
    primarySel.onchange  = () => refreshEffort(primarySel, primaryEffortSel, "");
    fallbackSel.onchange = () => refreshEffort(fallbackSel, fallbackEffortSel, "");

    const cat = this.plugin.availableModels;
    if (Object.keys(cat).length === 0) {
      primarySel.createEl("option", { value: "", text: "Loading models…" });
      fallbackSel.createEl("option", { value: "", text: "Loading models…" });
      this.plugin.refreshAvailableModels().catch(() => {});
      const iv = window.setInterval(() => {
        const c2 = this.plugin.availableModels;
        if (Object.keys(c2).length > 0) { window.clearInterval(iv); populate(c2); }
      }, 400);
    } else {
      populate(cat);
    }

    // ── Apply button (saves both) ──
    const applyRow = container.createDiv("ai-agent-llm-row");
    const applyBtn = applyRow.createEl("button", { cls: "ai-agent-llm-apply-btn mod-cta", text: "Apply" });
    applyBtn.onclick = async () => {
      if (!this.vaultConfig) return;
      const primary = this.toStoredValue(primarySel.value);
      const fallback = fallbackSel.value ? this.toStoredValue(fallbackSel.value) : "";
      const primaryEffort = primaryEffortSel.disabled ? "" : primaryEffortSel.value;
      const fallbackEffort = (fallbackSel.value && !fallbackEffortSel.disabled) ? fallbackEffortSel.value : "";
      applyBtn.disabled = true; applyBtn.setText("Saving…");
      try {
        const [provider, model] = primary.split("::");
        const args = ["config", "provider", "--primary", provider];
        if (model) args.push("--model", model);
        if (primaryEffort) args.push("--effort", primaryEffort);
        let r = await this.runWikiCommand(args);
        if (!r.ok) {
          new Notice(`LLM save failed: ${r.error}`);
          return;
        }
        r = await this.runWikiCommand(["config", "set", "llm.fallback", fallback || ""]);
        if (!r.ok) {
          new Notice(`Fallback save failed: ${r.error}`);
          return;
        }
        r = await this.runWikiCommand(["config", "set", "llm.fallback_effort", fallbackEffort || ""]);
        if (!r.ok) {
          new Notice(`Fallback effort save failed: ${r.error}`);
          return;
        }
        await this.refreshRuntimeSnapshots();
        this.vaultConfig = await this.readVaultConfig();
        const eff = primaryEffort ? ` (${primaryEffort})` : "";
        new Notice(`LLM saved · primary ${primary}${eff}${fallback ? `  fallback ${fallback}` : ""}`);
      } finally { applyBtn.disabled = false; applyBtn.setText("Apply"); }
    };

    // ── Ollama settings (only relevant if ollama is selected anywhere) ──
    const ollama = llm.ollama ?? {};
    const ollamaRow = container.createDiv("ai-agent-llm-ollama-hint");
    ollamaRow.setText(`Ollama: ${ollama.host || "http://localhost:11434"} · ${ollama.timeout ?? 120}s`);
  }

  private populateModelSelect(sel: HTMLSelectElement, cat: any, current: string, allowNone: boolean) {
    if (allowNone) sel.createEl("option", { value: "", text: "None (no fallback)" });
    for (const provKey of Object.keys(cat) as LLMProvider[]) {
      const models: ModelOption[] = cat[provKey] || [];
      if (!models.length) continue;
      const grp = sel.createEl("optgroup", { attr: { label: PROVIDER_LABELS[provKey] } });
      for (const m of models) {
        grp.createEl("option", {
          value: `${provKey}::${m.id}`,
          text:  `${PROVIDER_LABELS[provKey]} · ${m.label || m.id}`,
        });
      }
    }
    if (current && Array.from(sel.options).some(o => o.value === current)) sel.value = current;
    else if (!allowNone && sel.options.length) sel.selectedIndex = 0;
    else if (allowNone) sel.value = "";
  }

  // ---------------------------------------------------------------------------
  // JOBS TAB
  // ---------------------------------------------------------------------------

  private async renderJobs(el: HTMLElement) {
    const hdr = el.createDiv("ai-agent-jobs-header");
    hdr.createEl("h3", { text: "Build Jobs", cls: "ai-agent-dashboard-section-title" });
    const runBtn = hdr.createEl("button", { cls: "ai-agent-dashboard-btn" });
    setIcon(runBtn.createSpan(), "play");
    runBtn.appendText(" Run queued");
    const refreshBtn = hdr.createEl("button", { cls: "ai-agent-dashboard-btn" });
    setIcon(refreshBtn.createSpan(), "refresh-cw");
    refreshBtn.appendText(" Refresh");

    const body = el.createDiv("ai-agent-jobs-body");
    const load = async () => {
      body.empty();
      let data = await this.readRuntimeJson("jobs") as any;
      if (!data) {
        await this.refreshRuntimeSnapshots();
        data = await this.readRuntimeJson("jobs") as any;
      }
      this.renderJobsBody(body, data);
    };
    runBtn.onclick = async () => {
      runBtn.disabled = true;
      new Notice("Running queued Incurator build jobs...");
      const result = await this.runWikiCommand(["jobs", "run"]);
      if (result.ok) await this.refreshRuntimeSnapshots();
      new Notice(result.ok ? "Queued build jobs processed." : `Build jobs failed: ${result.error}`);
      runBtn.disabled = false;
      await load();
    };
    refreshBtn.onclick = () => load();
    await load();
    this.jobsTimer = window.setInterval(() => {
      if (this.activeTab === "jobs") load();
    }, 5000);
  }

  private renderJobsBody(el: HTMLElement, data: any) {
    if (!data) { el.createDiv({ cls: "ai-agent-dashboard-empty", text: "Worker not available." }); return; }

    const running: any[] = data.running ?? [];
    const queued:  any[] = data.queued  ?? [];
    const done:    any[] = data.done    ?? [];
    const doneCount = data.done_today ?? 0;

    if (data.idle && !done.length) {
      const card = el.createDiv("ai-agent-dashboard-status-idle");
      setIcon(card.createDiv("ai-agent-status-icon").createSpan(), "check-circle");
      const txt = card.createDiv();
      txt.createDiv({ cls: "ai-agent-status-title",    text: "Idle" });
      txt.createDiv({ cls: "ai-agent-status-subtitle", text: "No jobs today." });
      return;
    }

    if (running.length) {
      el.createDiv({ cls: "ai-agent-status-section-label", text: `Active (${running.length})` });
      for (const j of running) this.renderJobRow(el, j, "running");
    }
    if (queued.length) {
      el.createDiv({ cls: "ai-agent-status-section-label", text: `Queued (${queued.length})` });
      for (const j of queued) this.renderJobRow(el, j, "queued");
    }
    if (data.failed?.length) {
      el.createDiv({ cls: "ai-agent-status-section-label", text: `Failed (${data.failed.length})` });
      for (const j of data.failed) this.renderJobRow(el, j, "failed");
    }
    if (data.cancelled?.length) {
      el.createDiv({ cls: "ai-agent-status-section-label", text: `Cancelled (${data.cancelled.length})` });
      for (const j of data.cancelled) this.renderJobRow(el, j, "cancelled");
    }
    if (done.length) {
      el.createDiv({ cls: "ai-agent-status-section-label", text: `Completed today (${doneCount})` });
      for (const j of done) this.renderJobRow(el, j, "done");
    }
  }

  private renderJobRow(el: HTMLElement, job: any, state: "running" | "queued" | "done" | "failed" | "cancelled") {
    const row = el.createDiv("ai-agent-dashboard-job-item");
    if (state === "done") row.addClass("is-done");

    const hdr = row.createDiv("ai-agent-job-title-row");
    if (state === "done") setIcon(hdr.createSpan(), "check");
    if (state === "failed") setIcon(hdr.createSpan(), "alert-triangle");
    if (state === "cancelled") setIcon(hdr.createSpan(), "circle-slash");
    hdr.createSpan({ cls: "ai-agent-job-name", text: job.source_name || "Unknown" });
    const meta = [job.job_type, job.phase].filter(Boolean).join(" · ");
    if (meta) hdr.createSpan({ cls: "ai-agent-job-phase", text: meta });
    if (state === "done" && job.finished_at) {
      const t = new Date(job.finished_at);
      hdr.createSpan({ cls: "ai-agent-job-time", text: t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) });
    }

    if (state === "running") {
      const cur = job.progress_current || 0, total = job.progress_total || 0;
      const pr = row.createDiv("ai-agent-progress-row");
      const outer = pr.createDiv("ai-agent-progress-outer");
      outer.createDiv("ai-agent-progress-inner").style.width = `${total ? (cur / total) * 100 : 0}%`;
      pr.createSpan({ cls: "ai-agent-progress-label", text: total ? `${cur}/${total}` : "…" });
    }

    if (state === "queued" || state === "done" || state === "failed" || state === "cancelled") {
      const actions = row.createDiv("ai-agent-job-actions");
      const actionBtn = actions.createEl("button", {
        cls: "ai-agent-dashboard-btn",
      });
      if (state === "queued") {
        setIcon(actionBtn.createSpan(), "x");
        actionBtn.appendText(" Cancel");
        actionBtn.onclick = async () => {
          actionBtn.disabled = true;
          const result = await this.runWikiCommand(["jobs", "cancel", String(job.job_id)]);
          if (result.ok) await this.refreshRuntimeSnapshots();
          new Notice(result.ok ? `Cancelled job #${job.job_id}.` : `Cancel failed: ${result.error}`);
          this.switchTab("jobs");
        };
      } else {
        setIcon(actionBtn.createSpan(), "rotate-ccw");
        actionBtn.appendText(" Rerun");
        actionBtn.onclick = async () => {
          actionBtn.disabled = true;
          const result = await this.runWikiCommand(["jobs", "rerun", String(job.job_id)]);
          if (result.ok) await this.refreshRuntimeSnapshots();
          new Notice(result.ok ? `Requeued job #${job.job_id}.` : `Rerun failed: ${result.error}`);
          this.switchTab("jobs");
        };
      }
    }
  }

  // ---------------------------------------------------------------------------
  // SOURCES TAB
  // ---------------------------------------------------------------------------

  private async renderSources(el: HTMLElement) {
    el.createEl("h3", { text: "Recent Sources", cls: "ai-agent-dashboard-section-title" });
    const loading = el.createDiv({ cls: "ai-agent-dashboard-loading", text: "Loading…" });
    try {
      let result = await this.readRuntimeJson("sources") as any;
      if (!result) {
        await this.refreshRuntimeSnapshots();
        result = await this.readRuntimeJson("sources") as any;
      }
      loading.remove();
      if (!result?.sources?.length) { el.createDiv({ cls: "ai-agent-dashboard-empty", text: "No sources tracked yet." }); return; }

      const container = el.createDiv("ai-agent-dashboard-table-container");
      const header = container.createDiv("ai-agent-dashboard-table-header");
      for (const c of ["Source", "L1", "L2", "L3", "L4"]) header.createDiv({ text: c });

      const badge = (s: string) => {
        if (s === "error") return { str: "Error", cls: "badge-error" };
        if (["done","complete"].includes(s)) return { str: "Done", cls: "badge-curated" };
        if (s === "running") return { str: "Run", cls: "badge-indexed" };
        return { str: "—", cls: "badge-ready" };
      };

      for (const src of result.sources) {
        const row = container.createDiv("ai-agent-dashboard-table-row");
        let path = src.relpath || src.source_path || `#${src.id}`;
        if (path.length > 50) path = "…" + path.slice(-47);
        const pathCell = row.createDiv("ai-agent-dashboard-source-path");
        pathCell.style.display = "flex";
        pathCell.style.flexDirection = "column";
        pathCell.style.gap = "4px";
        pathCell.createDiv({ text: path });
        
        if (src.layer_error) {
          const errDiv = pathCell.createDiv({ text: `Reason: ${src.layer_error}` });
          errDiv.style.color = "var(--text-error)";
          errDiv.style.fontSize = "11px";
          errDiv.style.whiteSpace = "normal";
          errDiv.style.lineHeight = "1.2";
        }
        
        for (const b of [
          badge(src.l1_status || (src.l1_complete ? "done" : "")),
          badge(src.l2_status || ""),
          badge(src.l3_status || ""),
          badge(src.l4_status || ""),
        ]) row.createDiv().createSpan({ cls: `ai-agent-dashboard-badge ${b.cls}`, text: b.str });
      }
    } catch (e) { loading.remove(); el.createDiv({ cls: "ai-agent-dashboard-error", text: `Error: ${e}` }); }
  }

  // ---------------------------------------------------------------------------
  // PERSONA TAB
  // ---------------------------------------------------------------------------

  private async renderPersona(el: HTMLElement, cfgP: Promise<any>) {
    el.createEl("h3", { text: "Vault Persona", cls: "ai-agent-dashboard-section-title" });
    const cfg = await cfgP;
    if (!cfg) { el.createDiv({ cls: "ai-agent-dashboard-error", text: "Could not read config.yml." }); return; }

    const persona = cfg.persona ?? {};
    const form = el.createDiv("ai-agent-persona-form");

    const field = (label: string, desc?: string) => {
      const g = form.createDiv("ai-agent-config-group");
      g.createEl("label", { text: label });
      if (desc) g.createDiv({ cls: "setting-desc", text: desc });
      return g;
    };

    const areaInput = field("Domain Area").createEl("input", { cls: "ai-agent-dashboard-text-input", type: "text" });
    areaInput.value = persona.area || "";

    const textArea = field("Description", "How the Curator interprets and organizes knowledge.").createEl("textarea", { cls: "ai-agent-persona-textarea" });
    textArea.value = persona.text || "";
    textArea.rows = 4;

    const artsInput = field("Knowledge Artifacts", "Comma-separated types.").createEl("input", { cls: "ai-agent-dashboard-text-input", type: "text" });
    artsInput.value = (persona.knowledge_artifacts || []).join(", ");

    const verifyInput = field("Verification Philosophy").createEl("input", { cls: "ai-agent-dashboard-text-input", type: "text" });
    verifyInput.value = persona.verification_philosophy || "";

    const intentSel = field("Exhibition Intent").createEl("select", { cls: "dropdown" });
    for (const v of ["knowledge-worker", "researcher", "student", "engineer"]) {
      const opt = intentSel.createEl("option", { value: v, text: v });
      if (v === persona.exhibition_intent) opt.selected = true;
    }

    const saveBtn = form.createEl("button", { cls: "mod-cta ai-agent-dashboard-btn", text: "Save Persona" });
    saveBtn.onclick = async () => {
      saveBtn.disabled = true; saveBtn.setText("Saving…");
      try {
        const updates: Array<[string, string]> = [
          ["persona.area", areaInput.value.trim()],
          ["persona.text", textArea.value.trim()],
          [
            "persona.knowledge_artifacts",
            JSON.stringify(artsInput.value.split(",").map((s: string) => s.trim()).filter(Boolean)),
          ],
          ["persona.verification_philosophy", verifyInput.value.trim()],
          ["persona.exhibition_intent", intentSel.value],
          ["persona.updated_at", new Date().toISOString()],
        ];
        for (const [key, value] of updates) {
          const r = await this.runWikiCommand(["config", "set", key, value]);
          if (!r.ok) {
            new Notice(`Save failed: ${r.error}`);
            return;
          }
        }
        await this.refreshRuntimeSnapshots();
        this.vaultConfig = await this.readVaultConfig();
        new Notice("Persona saved.");
      } catch (e) { new Notice(`Save failed: ${e}`); }
      finally { saveBtn.disabled = false; saveBtn.setText("Save Persona"); }
    };
  }

}
