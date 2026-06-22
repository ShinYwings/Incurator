import { App, Modal, Notice, parseYaml, setIcon } from "obsidian";
import type ObsidianAIAgent from "../../main";
import type { LLMProvider, ModelOption } from "../types";
import { resolveModelSelectValue } from "../utils/modelSelect";

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

type TabId = "overview" | "jobs" | "sources" | "traces" | "synthesis" | "insights" | "persona";
const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: "overview", label: "Overview", icon: "layout-dashboard" },
  { id: "jobs",     label: "Jobs",     icon: "loader" },
  { id: "sources",  label: "Sources",  icon: "list" },
  { id: "traces",   label: "Traces",   icon: "search" },
  { id: "synthesis", label: "Synthesis", icon: "network" },
  { id: "insights", label: "Insights", icon: "lightbulb" },
  { id: "persona",  label: "Persona",  icon: "user" },
];

export class IncuratorDashboardModal extends Modal {
  plugin: ObsidianAIAgent;

  private vaultConfig: any = null;
  private activeTab: TabId = "overview";
  private tabEls  = new Map<TabId, HTMLElement>();
  private viewEls = new Map<TabId, HTMLElement>();
  private jobsTimer: number | null = null;

  private _refreshPromise: Promise<void> | null = null;
  // Whether the most recent `wiki status` snapshot refresh succeeded. When false,
  // the on-disk runtime/status.json may be stale, so the dashboard reports the
  // backend as unavailable instead of trusting the last good snapshot.
  private _lastStatusOk = false;
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
      case "traces":    this.renderTraces(view);        break;
      case "synthesis": this.renderSynthesis(view);     break;
      case "insights":  this.renderInsights(view);      break;
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


  private async readRuntimeJson<T = any>(name: "status" | "jobs" | "sources"): Promise<T | null> {
    try {
      return JSON.parse(await this.plugin.app.vault.adapter.read(`.curator/runtime/${name}.json`)) as T;
    } catch {
      return null;
    }
  }

  private async refreshRuntimeSnapshots(): Promise<void> {
    if (!this._refreshPromise) {
      this._refreshPromise = this.runWikiCommand(["status"]).then(
        (r) => { this._lastStatusOk = r.ok === true; this._refreshPromise = null; },
        () => { this._lastStatusOk = false; this._refreshPromise = null; },
      );
    }
    return this._refreshPromise;
  }

  private async readFreshRuntimeJson<T = any>(name: "status" | "jobs" | "sources"): Promise<T | null> {
    await this.refreshRuntimeSnapshots();
    return this.readRuntimeJson<T>(name);
  }

  private async readRuntimeStatus(): Promise<any | null> {
    // Fresh-first: force a `wiki status` snapshot refresh before reading, so the
    // dashboard reflects the CURRENT backend version/provider rather than a stale
    // runtime/status.json (the reported "backend shows 0.4.3 while it is 0.5.3" /
    // "wiki config provider change not reflected" bug). refreshRuntimeSnapshots()
    // dedups concurrent callers via _refreshPromise, so one render burst triggers
    // at most one `wiki status`.
    return this.readFreshRuntimeJson("status");
  }

  private async renderBackendVersion(el: HTMLElement): Promise<void> {
    const status = await this.readFreshRuntimeJson("status");
    // Only trust the snapshot version if the refresh actually succeeded; a failed
    // `wiki status` leaves a possibly-stale snapshot on disk, which must not be
    // shown as if current.
    if (this._lastStatusOk && status?.backend_version) {
      el.setText(`backend ${status.backend_version}`);
      return;
    }
    // Snapshot stale or backend unreachable → query the binary directly.
    const result = await this.runWikiCommand(["version"]);
    const match = result.output?.match(/incurator\s+([^\s]+)/i);
    el.setText(match ? `backend ${match[1]}` : "backend unavailable");
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

  /** Run a `wiki plugin …` command and parse its JSON stdout. */
  private async runPluginJson(cmdArgs: string[]): Promise<any | null> {
    const r = await this.runWikiCommand(cmdArgs);
    const text = r.output || "";
    const start = text.indexOf("{");
    const end = text.lastIndexOf("}");
    if (start < 0 || end <= start) return r.ok ? {} : null;
    try { return JSON.parse(text.slice(start, end + 1)); }
    catch { return null; }
  }

  // ---------------------------------------------------------------------------
  // TRACES TAB — durable QTR- query traces (DB-native search, v0.3.2)
  // ---------------------------------------------------------------------------

  private async renderTraces(el: HTMLElement) {
    const header = el.createDiv("ai-agent-jobs-header");
    header.createEl("h3", { text: "Query traces", cls: "ai-agent-dashboard-section-title" });
    const refreshBtn = header.createEl("button", { cls: "ai-agent-dashboard-btn" });
    setIcon(refreshBtn.createSpan(), "refresh-cw");
    refreshBtn.appendText(" Refresh");

    el.createDiv({
      cls: "ai-agent-ov-card-sub",
      text: "Live QTR traces from the current vault database. Select a row to inspect retrieval, rerank, warnings, and evidence.",
    });
    const layout = el.createDiv("ai-agent-dashboard-split");
    const listEl = layout.createDiv("ai-agent-dashboard-info-table");
    const detailEl = layout.createDiv("ai-agent-dashboard-info-table");
    detailEl.setText("Select a trace.");

    const load = async () => {
      listEl.setText("Loading…");
      detailEl.setText("Select a trace.");
      const data = await this.runPluginJson(["plugin", "trace", "list", "--limit", "50"]);
      listEl.empty();
      const traces = data?.traces || [];
      if (!data?.ok || traces.length === 0) {
        listEl.setText(data?.ok ? "No query traces yet. Run a search first." : data?.error || "Backend unavailable.");
        return;
      }
      for (const t of traces) {
        const row = listEl.createDiv("info-row");
        row.style.cursor = "pointer";
        const left = row.createDiv({ cls: "info-label" });
        left.setText(`${t.traceId || "QTR-?"}\n${(t.createdAt || "").replace("T", " ").slice(0, 19)}`);
        const right = row.createDiv({ cls: "info-value" });
        const warn = (t.warnings && t.warnings.length) || t.fallbackMode;
        right.setText(`${t.route || "?"} · ${t.latencyMs ?? "?"}ms${t.fallbackMode ? " · " + t.fallbackMode : ""}`);
        right.toggleClass("is-warn", !!warn);
        right.toggleClass("is-ok", !warn);
        row.addEventListener("click", () => this.showTraceDetail(detailEl, t.traceId));
      }
      await this.showTraceDetail(detailEl, traces[0].traceId);
    };
    refreshBtn.onclick = () => load();
    await load();
  }

  private async showTraceDetail(el: HTMLElement, traceId: string) {
    el.empty();
    el.setText("Loading trace…");
    const data = await this.runPluginJson(["plugin", "trace", "show", "--trace-id", traceId]);
    const tr = data?.trace;
    el.empty();
    if (!data?.ok || !tr) {
      el.setText(data?.error || "Could not load trace.");
      return;
    }
    el.createDiv({ cls: "ai-agent-ov-card-title", text: `Trace ${traceId}` });
    const tbl = this.makeInfoTable(el);
    tbl("Route", `${tr.route}${tr.routeReason ? " (" + tr.routeReason + ")" : ""}`);
    tbl("Latency", `${tr.latencyMs ?? "?"} ms`);
    const rt = tr.retrievalTrace || {};
    tbl("Mode/Intent", `${rt.mode || "?"} / ${rt.intent || "?"}`);
    tbl("Fallback", rt.fallback_mode || "none", rt.fallback_mode ? "is-warn" : "is-ok");
    if (tr.warnings && tr.warnings.length) tbl("Warnings", tr.warnings.join("; "), "is-warn");
    const ev = tr.evidence || [];
    tbl("Evidence", ev.length ? ev.map((e: any) => e.record_id || e.doc_id || e.id).filter(Boolean).join(", ") : "—");
    const promptIds = tr.retrievalTrace?.prompt_trace_ids || tr.promptTraceIds || tr.prompt_trace_ids || [];
    if (Array.isArray(promptIds) && promptIds.length) tbl("Prompt traces", promptIds.join(", "));
    const contributions = rt.rrf || rt.contributions || rt.fused || [];
    if (Array.isArray(contributions) && contributions.length) {
      tbl("RRF/rerank", contributions.slice(0, 5).map((c: any) => c.doc_id || c.record_id || c.id || JSON.stringify(c)).join(", "));
    }
  }

  // ---------------------------------------------------------------------------
  // SYNTHESIS TAB — read-only L4 -> L1 audit chains
  // ---------------------------------------------------------------------------

  private async renderSynthesis(el: HTMLElement) {
    const header = el.createDiv("ai-agent-jobs-header");
    header.createEl("h3", { text: "Synthesis", cls: "ai-agent-dashboard-section-title" });
    const refreshBtn = header.createEl("button", { cls: "ai-agent-dashboard-btn" });
    setIcon(refreshBtn.createSpan(), "refresh-cw");
    refreshBtn.appendText(" Refresh");

    el.createDiv({ cls: "ai-agent-ov-card-sub", text: "Generated L4 synthesis nodes from the current vault. Select one to inspect its source support." });
    const layout = el.createDiv("ai-agent-dashboard-split");
    const listEl = layout.createDiv("ai-agent-dashboard-info-table");
    const detailEl = layout.createDiv("ai-agent-dashboard-info-table");
    detailEl.setText("Select a synthesis.");

    const load = async () => {
      listEl.setText("Loading…");
      detailEl.setText("Select a synthesis.");
      const data = await this.runPluginJson(["plugin", "synthesis", "list", "--limit", "50"]);
      listEl.empty();
      const nodes = data?.synthesis || [];
      if (!data?.ok || nodes.length === 0) {
        listEl.setText(data?.ok ? "No synthesis nodes yet. Run build first." : data?.error || "Backend unavailable.");
        return;
      }
      for (const node of nodes) {
        const row = listEl.createDiv("info-row");
        row.style.cursor = "pointer";
        const left = row.createDiv({ cls: "info-label" });
        left.setText(`${node.id || "SYN-?"}\n${typeof node.confidence === "number" ? node.confidence.toFixed(2) : "—"}`);
        const right = row.createDiv({ cls: "info-value" });
        right.setText(node.title || "Untitled synthesis");
        row.addEventListener("click", () => this.showSynthesisDetail(detailEl, node.id));
      }
      await this.showSynthesisDetail(detailEl, nodes[0].id);
    };
    refreshBtn.onclick = () => load();
    await load();
  }

  private async showSynthesisDetail(el: HTMLElement, synthesisId: string) {
    el.empty();
    el.setText("Loading synthesis…");
    const data = await this.runPluginJson(["plugin", "synthesis", "show", "--synthesis-id", synthesisId]);
    const audit = data?.audit;
    const syn = audit?.synthesis;
    el.empty();
    if (!data?.ok || !audit || !syn) {
      el.setText(data?.error || "Could not load synthesis.");
      return;
    }
    el.createDiv({ cls: "ai-agent-ov-card-title", text: syn.title || synthesisId });
    const tbl = this.makeInfoTable(el);
    tbl("Synthesis", syn.id || synthesisId);
    tbl("Confidence", typeof syn.confidence === "number" ? syn.confidence.toFixed(2) : "—");
    tbl("Statement", syn.statement || "—");
    tbl("Reports", (audit.community_reports || []).map((r: any) => r.id).filter(Boolean).join(", ") || "—");
    tbl("Entities", (audit.entities || []).map((r: any) => r.canonical_name || r.id).filter(Boolean).slice(0, 8).join(", ") || "—");
    tbl("Relations", (audit.relations || []).map((r: any) => r.id).filter(Boolean).join(", ") || "—");
    tbl("Knowledge units", (audit.knowledge_units || []).map((r: any) => r.id).filter(Boolean).join(", ") || "—");
    tbl("Source spans", (audit.source_spans || []).map((r: any) => r.id).filter(Boolean).join(", ") || "—");
    const prompts = audit.prompt_runs || [];
    if (prompts.length) tbl("Prompt traces", prompts.map((p: any) => p.traceId || p.trace_id).filter(Boolean).join(", "));
    const warnings = [...(audit.warnings || []), ...(audit.dependency_warnings || [])];
    if (warnings.length) tbl("Warnings", warnings.join("; "), "is-warn");
  }

  // ---------------------------------------------------------------------------
  // INSIGHTS TAB — derived insight candidates (promote / reject)
  // ---------------------------------------------------------------------------

  private async renderInsights(el: HTMLElement) {
    const header = el.createDiv("ai-agent-jobs-header");
    header.createEl("h3", { text: "Insight candidates", cls: "ai-agent-dashboard-section-title" });
    const refreshBtn = header.createEl("button", { cls: "ai-agent-dashboard-btn" });
    setIcon(refreshBtn.createSpan(), "refresh-cw");
    refreshBtn.appendText(" Refresh");

    el.createDiv({ cls: "ai-agent-ov-card-sub", text: "Backend-owned insight candidates from the current vault. Select one before promoting or rejecting." });
    const layout = el.createDiv("ai-agent-dashboard-split");
    const listEl = layout.createDiv("ai-agent-dashboard-info-table");
    const detailEl = layout.createDiv("ai-agent-dashboard-info-table");
    detailEl.setText("Select an insight.");

    const load = async () => {
      listEl.setText("Loading…");
      detailEl.setText("Select an insight.");
      const data = await this.runPluginJson(["plugin", "insight", "list", "--status", "pending"]);
      listEl.empty();
      const candidates = data?.candidates || [];
      if (!data?.ok || candidates.length === 0) {
        listEl.setText(data?.ok ? "No pending insight candidates." : data?.error || "Backend unavailable.");
        return;
      }
      for (const c of candidates) {
        const row = listEl.createDiv("info-row");
        row.style.cursor = "pointer";
        const left = row.createDiv({ cls: "info-label" });
        left.setText(`${c.id || "INS-?"}\n${c.classification || "insight"}`);
        const mid = row.createDiv({ cls: "info-value" });
        mid.setText((c.statement || "").slice(0, 140));
        row.addEventListener("click", () => this.showInsightDetail(detailEl, c.id, load));
      }
      await this.showInsightDetail(detailEl, candidates[0].id, load);
    };
    refreshBtn.onclick = () => load();
    await load();
  }

  private async showInsightDetail(el: HTMLElement, insightId: string, reload: () => Promise<void>) {
    el.empty();
    el.setText("Loading insight…");
    const data = await this.runPluginJson(["plugin", "insight", "show", "--insight-id", insightId]);
    const c = data?.candidate;
    el.empty();
    if (!data?.ok || !c) {
      el.setText(data?.error || "Could not load insight.");
      return;
    }
    el.createDiv({ cls: "ai-agent-ov-card-title", text: c.id || insightId });
    const tbl = this.makeInfoTable(el);
    tbl("Classification", c.classification || "insight");
    tbl("Status", c.status || "unknown", c.status === "pending" ? "is-ok" : "");
    tbl("Confidence", typeof c.confidence === "number" ? c.confidence.toFixed(2) : "—");
    tbl("Affected nodes", Array.isArray(c.affectedNodeIds) && c.affectedNodeIds.length ? c.affectedNodeIds.join(", ") : "—");
    tbl("Statement", c.statement || "—");
    if (c.reason) tbl("Reason", c.reason);

    const actions = el.createDiv("ai-agent-dashboard-actions");
    this.addActionBtn(actions, "Promote", "check", async () => {
      const r = await this.runPluginJson(["plugin", "insight", "promote", "--insight-id", c.id]);
      new Notice(r?.ok ? `Promoted ${c.id} to ${r.promotedTo || "02_Wiki"}.` : `Promote failed: ${r?.error || "unknown error"}`);
      await reload();
    });
    this.addActionBtn(actions, "Reject", "x", async () => {
      const r = await this.runPluginJson(["plugin", "insight", "reject", "--insight-id", c.id, "--reason", "Rejected from dashboard"]);
      new Notice(r?.ok ? `Rejected ${c.id}.` : `Reject failed: ${r?.error || "unknown error"}`);
      await reload();
    });
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

    // Primary action: the one-shot pipeline (add → build → embed → sync).
    this.addActionBtn(acts, "Update", "rocket", async () => {
      new Notice("Updating vault (add → build → embed → sync)…");
      const r = await this.runWikiCommand(["update"]);
      if (r.ok) await this.refreshRuntimeSnapshots();
      new Notice(r.ok ? "Vault up to date." : `Update failed: ${r.error}`);
      this.switchTab(this.activeTab);
    });

    // The granular steps live under an Advanced disclosure so Update is the
    // obvious default; they remain available for fine-grained control.
    const advanced = acts.createEl("details", { cls: "ai-agent-ov-advanced" });
    advanced.createEl("summary", { text: "Advanced" });
    const adv = advanced.createDiv("ai-agent-ov-advanced-actions");
    this.addActionBtn(adv, "Add",     "file-plus",    async () => {
      new Notice("Running Incurator add...");
      const r = await this.runWikiCommand(["add"]);
      if (r.ok) await this.refreshRuntimeSnapshots();
      new Notice(r.ok ? "Add complete." : `Add failed: ${r.error}`);
      this.switchTab(this.activeTab);
    });
    this.addActionBtn(adv, "Build",   "hammer",       async () => {
      new Notice("Queueing Incurator build...");
      const r = await this.runWikiCommand(["build"]);
      if (r.ok) await this.refreshRuntimeSnapshots();
      new Notice(r.ok ? "Build queued. Open Jobs to run or monitor queued work." : `Build failed: ${r.error}`);
      this.switchTab(this.activeTab);
    });
    this.addActionBtn(adv, "Sync",    "refresh-cw",   async () => {
      new Notice("Running Incurator sync...");
      const r = await this.runWikiCommand(["sync"]);
      if (r.ok) await this.refreshRuntimeSnapshots();
      new Notice(r.ok ? "Sync complete." : `Sync failed: ${r.error}`);
      this.switchTab(this.activeTab);
    });
    this.addActionBtn(adv, "Lint",    "check-circle", async () => {
      new Notice("Running Incurator lint...");
      const r = await this.runWikiCommand(["lint"]);
      if (r.ok) await this.refreshRuntimeSnapshots();
      new Notice(r.ok ? "Lint complete." : `Lint failed: ${r.error}`);
    });
    this.addActionBtn(adv, "Reindex", "search",       async () => {
      new Notice("Running Incurator reindex...");
      const r = await this.runWikiCommand(["reindex"]);
      if (r.ok) await this.refreshRuntimeSnapshots();
      new Notice(r.ok ? "Reindex complete." : `Reindex failed: ${r.error}`);
    });
    this.addActionBtn(adv, "Reset",   "trash-2",      async () => {
      if (!confirm("This will clear your local DB and L1-L4 content (keeping notes and configs). Proceed?")) return;
      if (!confirm("WARNING: Are you absolutely sure you want to RESET the backend? This action cannot be undone.")) return;
      new Notice("Running wiki reset...");
      const r = await this.runWikiCommand(["reset", "--force"]);
      if (r.ok) await this.refreshRuntimeSnapshots();
      new Notice(r.ok ? `Reset complete: ${r.output?.slice(-100)}` : `Reset failed: ${r.error}`);
    });

    const grid = el.createDiv("ai-agent-ov-grid");

    // ── LLM (hero card, spans full width) ────────────────────────────────────
    // The plugin reads ALL config from runtime/status.json (merged by the backend
    // from .cache/config/ + .curator/config.yml).  This avoids the class of bugs
    // where machine-local keys (llm, search, external) are absent from the
    // synced project config.
    const status = await this.readRuntimeStatus();
    const llmCard = this.ovCard(grid, "span-full", null);
    llmCard.createDiv({ cls: "ai-agent-ov-card-title", text: "LLM Provider" });
    const effectiveCfg = status || cfg || {};
    if (effectiveCfg) this.renderLLMSelector(llmCard, effectiveCfg);

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



    // Determine Zotero initial fallback path for System card
    const z = status?.external?.zotero ?? {};
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
    // persona lives in config.yml under 'persona' key, populated via load_config
    // defaults, and is already included in runtime/status.json by build_status_snapshot()
    const personaCard = this.ovCard(grid, "span-2", "persona");
    personaCard.createDiv({ cls: "ai-agent-ov-card-title", text: "PERSONA" });
    const pAreaEl = personaCard.createDiv({ cls: "ai-agent-ov-card-value is-ok", text: "…" });
    pAreaEl.style.fontSize = "18px";
    const pTextEl = personaCard.createDiv({ cls: "ai-agent-ov-card-sub", text: "" });
    this.readRuntimeStatus().then((st: any) => {
      const p = st?.persona ?? cfg?.persona ?? {};
      const pArea = p.area || "Unset (run `wiki persona`)";
      pAreaEl.setText(pArea);
      pAreaEl.setAttr("title", pArea);
      const pText = p.text || "No description configured";
      pTextEl.setText(pText.length > 50 ? pText.slice(0, 50) + "…" : pText);
      pTextEl.setAttr("title", pText);
    });

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

    // ── Search Engine card ───────────────────────────────────────────────────
    const searchCard = this.ovCard(grid, "span-full ai-agent-ov-sys-card", null);
    searchCard.createDiv({ cls: "ai-agent-ov-card-title", text: "Search Engine" });
    const searchTable = searchCard.createDiv("ai-agent-ov-path-table");
    const searchRow = (label: string, val?: string) => {
      const row = searchTable.createDiv("ai-agent-ov-path-row");
      row.createDiv({ cls: "ai-agent-ov-path-label", text: label });
      return row.createDiv({ cls: "ai-agent-ov-path-value", text: val ?? "…" });
    };
    const searchEl = searchRow("Engine");
    const embedEl = searchRow("Embed model");
    const rerankEl = searchRow("Reranker");

    // Click the reranker/embed rows to (re)provision the search stack — repairs
    // missing/unhealthy models via `wiki plugin models refresh`.
    const refreshModels = async (target: HTMLElement) => {
      const orig = target.getText();
      target.setText("refreshing…");
      target.toggleClass("is-warn", false);
      const r = await this.runWikiCommand(["plugin", "models", "refresh"]);
      new Notice(r.ok ? "Search models refreshed." : `Model refresh failed: ${r.error}`);
      if (!r.ok) target.setText(orig);
      await this.refreshRuntimeSnapshots();
      this.switchTab(this.activeTab);
    };
    for (const el of [embedEl, rerankEl]) {
      el.style.cursor = "pointer";
      el.setAttr("title", "Click to (re)download & verify search models");
      el.addEventListener("click", () => refreshModels(el));
    }

    this.readRuntimeStatus().then((st: any) => {
      vaultEl.setText(st?.vault_root || this.vaultBase() || "Unknown");
      wikiEl.setText(st?.wiki_binary || "Not found");
      wikiEl.toggleClass("is-ok", !!st?.wiki_binary);
      wikiEl.toggleClass("is-warn", !st?.wiki_binary);
      const searchReady = !!st?.search_ready;
      const searchLabel = st?.search_version
        ? `${st.search_version}${st?.vector_ready ? " · vector" : " · FTS5-only (Models missing)"}`
        : "Not found";
      searchEl.setText(searchLabel);
      searchEl.toggleClass("is-ok", !!searchReady);
      searchEl.toggleClass("is-warn", !searchReady);

      // v0.3.2: search model identity + health (embed / reranker)
      const sm = st?.search_models;
      const fmtModel = (m: any, disabledHint = "") => {
        if (!m || !m.model) return disabledHint || "not configured";
        const where = m.provider === "llama-cpp" ? "GGUF" : m.provider;
        return `${m.model} (${where})${m.ready ? "" : m.present ? " · runtime missing" : " · not downloaded"}`;
      };
      embedEl.setText(fmtModel(sm?.embed));
      embedEl.toggleClass("is-ok", !!sm?.embed?.ready);
      embedEl.toggleClass("is-warn", !sm?.embed?.ready);
      const rr = sm?.reranker;
      rerankEl.setText(rr && rr.enabled === false ? "disabled" : fmtModel(rr));
      rerankEl.toggleClass("is-ok", !!rr?.ready);
      rerankEl.toggleClass("is-warn", !!rr && rr.enabled !== false && !rr.ready);

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
      searchEl.setText("offline");  searchEl.addClass("is-warn");
      embedEl.setText("offline"); embedEl.addClass("is-warn");
      rerankEl.setText("offline"); rerankEl.addClass("is-warn");
    });

    // ── Sync/Curate card ─────────────────────────────────────────────────────
    const syncCard = this.ovCard(grid, "span-2", null);
    syncCard.createDiv({ cls: "ai-agent-ov-card-title", text: "Pipeline" });
    const syncTable = this.makeInfoTable(syncCard);
    syncTable("Sync workers",  String((status?.sync ?? cfg?.sync)?.max_parallel_verifications ?? 4));
    syncTable("Log retention", `${(status?.curate ?? cfg?.curate)?.log_retention_days ?? 30} days`);

    // ── Syncthing device-folder card ────────────────────────────────────────
    const deviceCard = this.ovCard(grid, "span-2", null);
    deviceCard.createDiv({ cls: "ai-agent-ov-card-title", text: "Syncthing Devices" });
    const devListContainer = deviceCard.createDiv({ cls: "ai-agent-ov-device-list" });
    devListContainer.style.marginTop = "12px";
    devListContainer.style.display = "flex";
    devListContainer.style.flexDirection = "column";
    devListContainer.style.gap = "8px";

    this.readRuntimeStatus().then((st: any) => {
      try {
        const devices = st?.devices;
        if (!Array.isArray(devices) || devices.length === 0) {
          devListContainer.createDiv({ text: "No devices", cls: "ai-agent-ov-card-sub" });
          return;
        }

        for (const d of devices) {
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

          if (d.is_local) {
            row.createSpan({ text: "●", cls: "is-ok" });
            const nameEl = row.createSpan({ text: `${d.name} (This device)`, cls: "is-ok", attr: { title: "Current device on this machine" } });
            nameEl.style.fontWeight = "600";
            nameEl.style.lineHeight = "1.2";
            applyTruncation(nameEl);
          } else {
            row.createSpan({ text: "○", attr: { style: "opacity: 0.5" } });
            const nameEl = row.createSpan({ text: d.name || "Unknown", attr: { title: d.device_id, style: "opacity: 0.8" } });
            nameEl.style.lineHeight = "1.2";
            applyTruncation(nameEl);
          }
          const folderLabels = Array.isArray(d.folders) ? d.folders : [];
          const foldersEl = row.createSpan({
            cls: "ai-agent-compact-muted",
            text: folderLabels.length ? ` -> ${folderLabels.join(", ")}` : " -> no synced folder",
          });
          applyTruncation(foldersEl);
        }
      } catch {
        devListContainer.createDiv({ text: "Error loading", cls: "ai-agent-ov-card-sub" });
      }
    }).catch(() => {
      devListContainer.createDiv({ text: "No sync data", cls: "ai-agent-ov-card-sub" });
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

    // ── Vision extraction rows (v0.22.0; SCHEMA §2.5, SYSTEM_BEHAVIOR §26.2a) ──
    const visionCur = this.toCatalogueValue((llm.vision_model as string) || "");
    const extractCur = this.toCatalogueValue((llm.latex_extract_model as string) || "");
    const vRow = container.createDiv("ai-agent-llm-row");
    vRow.createSpan({ cls: "ai-agent-llm-label", text: "PDF ingest (vision)" });
    const visionSel = vRow.createEl("select", { cls: "ai-agent-model-select-full dropdown" });
    const eRow = container.createDiv("ai-agent-llm-row");
    eRow.createSpan({ cls: "ai-agent-llm-label", text: "LaTeX/region (light)" });
    const extractSel = eRow.createEl("select", { cls: "ai-agent-model-select-full dropdown" });
    const extractHint = eRow.createSpan({ cls: "ai-agent-llm-fallback-hint" });
    // Light row empty → show the effective resolved model so the fallback is visible.
    const refreshExtractHint = () => {
      extractHint.setText(
        extractSel.value ? "" : `↳ using ${visionSel.value || "(disabled / pymupdf4llm)"}`,
      );
    };

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

    // Vision-only model dropdown: only models with supportsVision, plus a leading
    // "disabled / fall back" option. Mirrors the catalogue value scheme.
    const populateVisionSelect = (sel: HTMLSelectElement, cat: any, current: string, emptyLabel: string) => {
      sel.empty();
      sel.createEl("option", { value: "", text: emptyLabel });
      for (const provKey of Object.keys(cat) as LLMProvider[]) {
        const models: ModelOption[] = cat[provKey] || [];
        const vision = models.filter((m) => m.supportsVision);
        if (!vision.length) continue;
        const grp = sel.createEl("optgroup", { attr: { label: PROVIDER_LABELS[provKey] } });
        for (const m of vision) {
          grp.createEl("option", { value: `${provKey}::${m.id}`, text: `${PROVIDER_LABELS[provKey]} · ${m.label || m.id}` });
        }
      }
      sel.value = Array.from(sel.options).some((o) => o.value === current) ? current : "";
    };

    const populate = (cat: any) => {
      primarySel.empty();
      fallbackSel.empty();
      this.populateModelSelect(primarySel, cat, primaryCur, false);
      this.populateModelSelect(fallbackSel, cat, fallbackCur, true);
      refreshEffort(primarySel, primaryEffortSel, primaryEffCur);
      refreshEffort(fallbackSel, fallbackEffortSel, fallbackEffCur);
      populateVisionSelect(visionSel, cat, visionCur, "— (disabled, use pymupdf4llm)");
      populateVisionSelect(extractSel, cat, extractCur, "— (use PDF ingest model)");
      refreshExtractHint();
    };
    // Changing a model resets its effort to that model's default.
    primarySel.onchange  = () => refreshEffort(primarySel, primaryEffortSel, "");
    fallbackSel.onchange = () => refreshEffort(fallbackSel, fallbackEffortSel, "");
    visionSel.onchange = refreshExtractHint;
    extractSel.onchange = refreshExtractHint;

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
      // Guard against applying before the model catalogue has loaded — an empty
      // primary would otherwise send `config provider --primary ""`, which the
      // backend resolves to an interactive Ollama model picker that aborts.
      const [provider, model] = primary.split("::");
      if (!provider) {
        new Notice("Models are still loading — pick a Primary model first.");
        return;
      }
      const fallback = fallbackSel.value ? this.toStoredValue(fallbackSel.value) : "";
      const primaryEffort = primaryEffortSel.disabled ? "" : primaryEffortSel.value;
      const fallbackEffort = (fallbackSel.value && !fallbackEffortSel.disabled) ? fallbackEffortSel.value : "";
      applyBtn.disabled = true; applyBtn.setText("Saving…");
      try {
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
        // Vision extraction models (v0.22.0). Empty value = disabled / fall back.
        const visionModel = visionSel.value ? this.toStoredValue(visionSel.value) : "";
        const extractModel = extractSel.value ? this.toStoredValue(extractSel.value) : "";
        r = await this.runWikiCommand(["config", "set", "llm.vision_model", visionModel]);
        if (!r.ok) {
          new Notice(`Vision model save failed: ${r.error}`);
          return;
        }
        r = await this.runWikiCommand(["config", "set", "llm.latex_extract_model", extractModel]);
        if (!r.ok) {
          new Notice(`Region model save failed: ${r.error}`);
          return;
        }
        const eff = primaryEffort ? ` (${primaryEffort})` : "";
        new Notice(`LLM saved · primary ${primary}${eff}${fallback ? `  fallback ${fallback}` : ""}`);
      } finally { applyBtn.disabled = false; applyBtn.setText("Apply"); }
    };

    // ── Ollama settings (only shown when Ollama is primary or fallback) ──
    const ollama = llm.ollama ?? {};
    const ollamaRow = container.createDiv("ai-agent-llm-ollama-hint");
    ollamaRow.setText(`Ollama: ${ollama.host || "http://localhost:11434"} · ${ollama.timeout ?? 120}s`);

    // ── Ollama recommendations: install status + RAM fit + one-click Pull ──
    // Show when Ollama is selected in ANY slot (primary, fallback, vision, extract).
    const ollamaModelsEl = container.createDiv("ai-agent-llm-ollama-models");
    const isOllamaSelected = () =>
      primarySel.value.startsWith("ollama::") || fallbackSel.value.startsWith("ollama::") ||
      visionSel.value.startsWith("ollama::") || extractSel.value.startsWith("ollama::");
    const refreshOllamaSection = () => {
      const show = isOllamaSelected();
      ollamaRow.style.display = show ? "" : "none";
      ollamaModelsEl.style.display = show ? "" : "none";
      if (show && ollamaModelsEl.childElementCount === 0) {
        void this.renderOllamaRecommendations(ollamaModelsEl);
      }
    };
    for (const sel of [primarySel, fallbackSel, visionSel, extractSel]) {
      sel.addEventListener("change", refreshOllamaSection);
    }
    // Initial visibility from config values (dropdowns may still be loading).
    const cfgUsesOllama =
      (llm.primary || "").includes("ollama") || (llm.fallback || "").includes("ollama") ||
      (llm.vision_model || "").includes("ollama") || (llm.latex_extract_model || "").includes("ollama");
    ollamaRow.style.display = cfgUsesOllama ? "" : "none";
    ollamaModelsEl.style.display = cfgUsesOllama ? "" : "none";
    if (cfgUsesOllama) {
      void this.renderOllamaRecommendations(ollamaModelsEl);
    }
  }

  /** Render the models.json Ollama recommendations with install/RAM-fit status. */
  private async renderOllamaRecommendations(el: HTMLElement): Promise<void> {
    el.empty();
    el.createDiv({ cls: "ai-agent-ov-card-sub", text: "Loading Ollama models…" });
    const data = await this.runPluginJson(["plugin", "models", "ollama", "--json"]);
    el.empty();
    if (!data?.ok || !Array.isArray(data.models)) {
      el.createDiv({ cls: "ai-agent-ov-card-sub", text: "Ollama recommendations unavailable." });
      return;
    }
    el.createDiv({
      cls: "ai-agent-ov-card-sub",
      text: `Recommended Ollama models · this machine has ~${data.ram_gb} GB RAM`,
    });
    for (const m of data.models as Array<any>) {
      const row = el.createDiv("ai-agent-ollama-model-row");
      row.createSpan({ cls: "ai-agent-ollama-model-name", text: m.label || m.id });
      if (m.installed) {
        row.createSpan({ cls: "ai-agent-ollama-badge is-ok", text: "installed" });
      } else if (!m.fits_ram) {
        row.createSpan({ cls: "ai-agent-ollama-badge is-warn", text: "exceeds RAM" });
      }
      if (!m.installed) {
        const pull = row.createEl("button", { cls: "ai-agent-dashboard-btn", text: "Pull" });
        pull.onclick = async () => {
          pull.disabled = true;
          pull.setText("Pulling…");
          const r = await this.runPluginJson(["plugin", "models", "pull", "--model", m.id, "--json"]);
          new Notice(r?.ok ? `Pulled ${m.id}` : `Pull failed: ${r?.error || m.id}`);
          await this.renderOllamaRecommendations(el);
        };
      }
    }
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
    const decision = resolveModelSelectValue(
      Array.from(sel.options).map(o => o.value),
      current,
    );
    if (decision.action === "select") {
      sel.value = decision.value;
    } else if (decision.action === "inject") {
      // Active backend model isn't in the bundled catalogue (e.g. a custom local
      // Ollama model). Surface it as its own option so the display stays faithful
      // to `wiki status` instead of snapping back to the first catalogue entry.
      const sep = decision.value.indexOf("::");
      const prov = sep >= 0 ? decision.value.slice(0, sep) : "";
      const model = (sep >= 0 ? decision.value.slice(sep + 2) : decision.value).trim();
      const provLabel = PROVIDER_LABELS[prov as LLMProvider];
      const text = provLabel ? `${provLabel} · ${model} (current)` : `${model} (current)`;
      sel.createEl("option", { value: decision.value, text });
      sel.value = decision.value;
    } else if (!allowNone && sel.options.length) {
      sel.selectedIndex = 0;
    } else if (allowNone) {
      sel.value = "";
    }
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
    }, 2000);
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
      pr.createSpan({ cls: "ai-agent-progress-label", text: total ? `${cur}/${total}` : "running…" });
      // Cancel button for running jobs too
      const actions = row.createDiv("ai-agent-job-actions");
      const cancelBtn = actions.createEl("button", { cls: "ai-agent-dashboard-btn" });
      setIcon(cancelBtn.createSpan(), "x");
      cancelBtn.appendText(" Cancel");
      cancelBtn.onclick = async () => {
        cancelBtn.disabled = true;
        const result = await this.runWikiCommand(["jobs", "cancel", String(job.job_id)]);
        if (result.ok) await this.refreshRuntimeSnapshots();
        new Notice(result.ok ? `Cancelled job #${job.job_id}.` : `Cancel failed: ${result.error}`);
        this.switchTab("jobs");
      };
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
      const result = await this.readFreshRuntimeJson("sources") as any;
      loading.remove();
      if (result === null) { el.createDiv({ cls: "ai-agent-dashboard-empty", text: "Failed to load sources — backend unavailable." }); return; }
      if (!result.sources?.length) { el.createDiv({ cls: "ai-agent-dashboard-empty", text: "No sources tracked yet." }); return; }

      // Resume after a mid-build error (item 21): if any source errored (e.g.
      // "Antigravity capacity exhausted (429)"), surface a one-click resume that
      // re-attempts the errored L2/L3 layers with the currently configured
      // provider — so after switching models the user knows exactly what to press.
      const isErrored = (s: any): boolean =>
        s.status === "error" ||
        ["l1_status", "l2_status", "l3_status", "l4_status"].some((k) => s[k] === "error");
      const erroredCount = result.sources.filter(isErrored).length;
      if (erroredCount > 0) {
        const banner = el.createDiv("ai-agent-dashboard-retry-banner");
        banner.createSpan({
          text: `${erroredCount} source(s) stopped on an error. Switch the model in Settings if needed, then resume:`,
        });
        const retryBtn = banner.createEl("button", { cls: "ai-agent-dashboard-btn" });
        setIcon(retryBtn.createSpan(), "refresh-cw");
        retryBtn.appendText(" Retry errored sources");
        retryBtn.addEventListener("click", async () => {
          retryBtn.disabled = true;
          retryBtn.setText("Resuming…");
          // `wiki build` re-attempts every source whose L2/L3 is pending OR error,
          // continuing from where the build stopped with the current provider.
          const r = await this.runWikiCommand(["build"]);
          new Notice(
            r.ok
              ? "Resume queued — errored sources will rebuild. Open Jobs to monitor."
              : `Retry failed: ${r.error}`
          );
          el.empty();
          await this.renderSources(el);
        });
      }

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
    const status = await this.readRuntimeStatus();
    if (!cfg && !status) {
      const errDiv = el.createDiv({ cls: "ai-agent-dashboard-error", text: "Could not read .curator/config.yml — run \"wiki init\" first." });
      const retryBtn = el.createEl("button", { cls: "ai-agent-dashboard-btn", text: "Retry" });
      retryBtn.style.marginTop = "12px";
      retryBtn.onclick = () => this.switchTab("persona");
      return;
    }

    const persona = status?.persona ?? cfg?.persona ?? {};
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
          const r = await this.runWikiCommand(["config", "set", "--local", key, value]);
          if (!r.ok) {
            new Notice(`Save failed: ${r.error}`);
            return;
          }
        }
        new Notice("Persona saved.");
      } catch (e) { new Notice(`Save failed: ${e}`); }
      finally { saveBtn.disabled = false; saveBtn.setText("Save Persona"); }
    };
  }

}
