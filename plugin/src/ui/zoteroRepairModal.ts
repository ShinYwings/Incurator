import { App, Modal, Notice, Setting } from "obsidian";
import { homedir } from "os";
import type { ZoteroPdfResolution, ZoteroStatus } from "../agent/incuratorClient";

export interface ZoteroRepairClient {
  getZoteroStatus(): Promise<ZoteroStatus>;
  initZotero(dataDir?: string, linkedBaseDir?: string): Promise<ZoteroStatus>;
}

export interface ZoteroRepairInitialState {
  attachmentKey?: string;
  status?: ZoteroStatus;
  resolution?: ZoteroPdfResolution;
}

export function describeZoteroState(state: string, attachmentKey = ""): string {
  switch (state) {
    case "ready":
      return "Backend can read Zotero on this device.";
    case "db_missing":
      return "Zotero database was not found in the configured data directory.";
    case "db_unreadable":
      return "Zotero database exists but backend could not read it.";
    case "attachment_key_missing":
      return attachmentKey
        ? `Attachment ${attachmentKey} is not present in the readable Zotero database.`
        : "The requested attachment key is not present in the readable Zotero database.";
    case "attachment_file_missing":
      return "Zotero has an attachment row, but the PDF file was not found in configured roots.";
    case "not_configured":
      return "No readable Zotero data directory is configured for this device.";
    default:
      return state || "Zotero status is unavailable.";
  }
}

export function zoteroRepairCandidates(
  status?: ZoteroStatus,
  resolution?: ZoteroPdfResolution
): string[] {
  const raw = [
    ...(status?.rootsChecked || []),
    ...(resolution?.rootsChecked || []),
    ...(resolution?.pathsChecked || []),
  ];
  const out: string[] = [];
  for (const item of raw) {
    if (!item) continue;
    const candidate = item.endsWith(".pdf") || item.endsWith(".sqlite")
      ? item.split(/[\\/]/).slice(0, -1).join("/")
      : item;
    if (candidate && !out.includes(candidate)) out.push(candidate);
  }
  return out;
}

export function compactHomePath(path: string, home = homedir()): string {
  if (!path || !home) return path;
  const normalizedHome = home.replace(/[\\/]+$/, "");
  if (path === normalizedHome) return "~";
  if (path.startsWith(`${normalizedHome}/`) || path.startsWith(`${normalizedHome}\\`)) {
    return `~/${path.slice(normalizedHome.length + 1).replace(/\\/g, "/")}`;
  }
  return path;
}

export class ZoteroRepairModal extends Modal {
  private dataDir = "";
  private linkedBaseDir = "";
  private status: ZoteroStatus | undefined;
  private resolution: ZoteroPdfResolution | undefined;

  constructor(
    app: App,
    private readonly client: ZoteroRepairClient,
    private readonly initial: ZoteroRepairInitialState = {}
  ) {
    super(app);
    this.status = initial.status;
    this.resolution = initial.resolution;
    this.dataDir = compactHomePath(initial.status?.dataDir || "~/Zotero");
  }

  onOpen(): void {
    this.render();
    if (!this.status) void this.refresh();
  }

  onClose(): void {
    this.contentEl.empty();
  }

  private currentState(): string {
    return this.resolution?.state || this.status?.state || "unknown";
  }

  private render(): void {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.addClass("ai-agent-zotero-repair-modal");

    contentEl.createEl("h2", { text: "Zotero Backend Setup" });
    contentEl.createEl("p", {
      cls: "setting-item-description",
      text: describeZoteroState(this.currentState(), this.initial.attachmentKey),
    });

    const detail = contentEl.createDiv("ai-agent-zotero-repair-detail");
    if (this.status?.dbPath) detail.createDiv({ text: `Database: ${compactHomePath(this.status.dbPath)}` });
    if (this.status?.dataDir) detail.createDiv({ text: `Data directory: ${compactHomePath(this.status.dataDir)}` });
    if (this.resolution?.zoteroDb) detail.createDiv({ text: `Database: ${compactHomePath(this.resolution.zoteroDb)}` });
    if (this.resolution?.error) detail.createDiv({ text: `Resolution: ${this.resolution.error}` });
    if (this.initial.attachmentKey) detail.createDiv({ text: `Attachment key: ${this.initial.attachmentKey}` });

    const checked = zoteroRepairCandidates(this.status, this.resolution);
    if (checked.length) {
      const list = contentEl.createEl("details");
      list.createEl("summary", { text: "Candidate roots" });
      const listBody = list.createDiv("ai-agent-zotero-repair-candidates");
      for (const item of checked.slice(0, 20)) {
        const displayItem = compactHomePath(item);
        const row = listBody.createDiv("ai-agent-zotero-repair-candidate");
        row.createSpan({ text: displayItem });
        const useBtn = row.createEl("button", { text: "Use" });
        useBtn.addEventListener("click", () => {
          if (item.endsWith("Zotero") || item.includes("zotero.sqlite")) this.dataDir = displayItem;
          else this.linkedBaseDir = displayItem;
          this.render();
        });
      }
    }

    new Setting(contentEl)
      .setName("Zotero data directory")
      .setDesc("Directory containing zotero.sqlite, or a direct zotero.sqlite path.")
      .addText((text) =>
        text
          .setPlaceholder("~/Zotero")
          .setValue(this.dataDir)
          .onChange((value) => {
            this.dataDir = value.trim();
          })
      );

    new Setting(contentEl)
      .setName("Linked attachment root")
      .setDesc("Optional root used for Zotero linked attachments.")
      .addText((text) =>
        text
          .setPlaceholder("~/Documents/Zotero")
          .setValue(this.linkedBaseDir)
          .onChange((value) => {
            this.linkedBaseDir = value.trim();
          })
      );

    const actions = contentEl.createDiv("ai-agent-ingest-modal-actions");
    actions.createEl("button", { text: "Close" }).addEventListener("click", () => this.close());
    actions.createEl("button", { text: "Refresh" }).addEventListener("click", () => void this.refresh());
    const saveBtn = actions.createEl("button", { cls: "mod-cta", text: "Save to backend" });
    saveBtn.addEventListener("click", async () => {
      saveBtn.disabled = true;
      try {
        this.status = await this.client.initZotero(this.dataDir, this.linkedBaseDir);
        this.resolution = undefined;
        new Notice(`Zotero backend config: ${this.status.state}`);
        this.render();
      } finally {
        saveBtn.disabled = false;
      }
    });
  }

  private async refresh(): Promise<void> {
    this.status = await this.client.getZoteroStatus();
    this.resolution = undefined;
    this.dataDir = compactHomePath(this.status.dataDir || this.dataDir);
    this.render();
  }
}
