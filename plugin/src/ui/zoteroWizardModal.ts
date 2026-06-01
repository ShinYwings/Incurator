import { App, Modal, Setting, Notice, SuggestModal, AbstractInputSuggest, TFolder } from "obsidian";
import { promises as fs } from "fs";
import { IncuratorClient } from "../agent/incuratorClient";
import { PluginSettings, ZoteroImportProfile } from "../types";
import { sanitizePathSegment, TemplateRenderer } from "../zotero/templateRenderer";

export interface ZoteroSearchResult {
  key: string;
  title: string;
  itemType: string;
  creators: { firstName: string; lastName: string }[];
  date: string;
}

export function prioritizeZoteroItems(
  items: ZoteroSearchResult[],
  recentKeys: string[] | undefined
): ZoteroSearchResult[] {
  const rank = new Map((recentKeys || []).map((key, index) => [key, index]));
  return [...items].sort((a, b) => {
    const aRank = rank.get(a.key);
    const bRank = rank.get(b.key);
    if (aRank === undefined && bRank === undefined) return 0;
    if (aRank === undefined) return 1;
    if (bRank === undefined) return -1;
    return aRank - bRank;
  });
}

export function rememberRecentZoteroItem(
  settings: Pick<PluginSettings, "recentZoteroItems">,
  itemKey: string,
  limit = 50
): void {
  if (!itemKey) return;
  const existing = Array.isArray(settings.recentZoteroItems)
    ? settings.recentZoteroItems
    : [];
  settings.recentZoteroItems = [
    itemKey,
    ...existing.filter((key) => key !== itemKey),
  ].slice(0, limit);
}

// ─── Vault path autocomplete ──────────────────────────────────────────
class VaultPathSuggest extends AbstractInputSuggest<string> {
  private mode: "file" | "folder";
  private extension: string | null;
  private textInputEl: HTMLInputElement;

  constructor(app: App, inputEl: HTMLInputElement, mode: "file" | "folder", extension: string | null = null) {
    super(app, inputEl);
    this.textInputEl = inputEl;
    this.mode = mode;
    this.extension = extension;
  }

  getSuggestions(query: string): string[] {
    const lower = query.toLowerCase();
    const paths: string[] = [];

    if (this.mode === "folder") {
      const recurse = (folder: TFolder) => {
        paths.push(folder.path);
        for (const child of folder.children) {
          if (child instanceof TFolder) recurse(child);
        }
      };
      recurse(this.app.vault.getRoot());
    } else {
      for (const file of this.app.vault.getFiles()) {
        if (this.extension && file.extension !== this.extension) continue;
        paths.push(file.path);
      }
    }

    if (!lower) return paths.slice(0, 30);
    return paths.filter(p => p.toLowerCase().includes(lower)).slice(0, 30);
  }

  renderSuggestion(path: string, el: HTMLElement) {
    el.setText(path);
  }

  selectSuggestion(path: string) {
    this.textInputEl.value = path;
    this.textInputEl.dispatchEvent(new Event("input"));
    this.close();
  }
}

// ─── Zotero Search Modal ──────────────────────────────────────────────
export class ZoteroSearchModal extends SuggestModal<ZoteroSearchResult> {
  private client: IncuratorClient;
  private settings: PluginSettings;
  private saveSettings: (settings: PluginSettings) => Promise<void>;
  private recentCache: ZoteroSearchResult[] = [];
  private recentFetched = false;

  constructor(
    app: App,
    client: IncuratorClient,
    settings: PluginSettings,
    saveSettings: (settings: PluginSettings) => Promise<void>
  ) {
    super(app);
    this.client = client;
    this.settings = settings;
    this.saveSettings = saveSettings;
    this.setPlaceholder("Search Zotero items by title or author... (leave blank for recent)");
  }

  onOpen() {
    super.onOpen();
    // Force the modal to fetch and display the empty-query (recent) suggestions immediately
    setTimeout(() => {
      this.inputEl.value = "";
      this.inputEl.dispatchEvent(new Event("input"));
    }, 100);
  }

  async getSuggestions(query: string): Promise<ZoteroSearchResult[]> {
    if (!query || query.length < 2) {
      if (!this.recentFetched) {
        this.recentFetched = true;
        try {
          const res: any = await this.client.tryTool(["curator_search_zotero_items"], {
            query: "",
            custom_paths: this.settings.zoteroBasePath || "~/Zotero"
          });
          if (res?.ok && Array.isArray(res.items)) this.recentCache = res.items;
        } catch (e) {
          console.error("Failed to load recent Zotero items:", e);
        }
      }
      return prioritizeZoteroItems(this.recentCache, this.settings.recentZoteroItems);
    }
    try {
      const res: any = await this.client.tryTool(["curator_search_zotero_items"], {
        query,
        custom_paths: this.settings.zoteroBasePath || "~/Zotero"
      });
      if (res?.ok && Array.isArray(res.items)) {
        return prioritizeZoteroItems(res.items, this.settings.recentZoteroItems);
      }
    } catch (e) {
      console.error(e);
    }
    return [];
  }

  renderSuggestion(item: ZoteroSearchResult, el: HTMLElement) {
    const container = el.createDiv({ cls: "zotero-search-result" });
    container.createEl("div", { text: item.title, cls: "zotero-search-title", attr: { style: "font-weight: bold;" } });
    const authors = item.creators.map(c => `${c.firstName} ${c.lastName}`).join(", ");
    container.createEl("small", {
      text: `${authors} (${item.date?.substring(0, 4) || 'N/A'}) — ${item.itemType}`,
      cls: "zotero-search-meta",
      attr: { style: "color: var(--text-muted);" }
    });
  }

  onChooseSuggestion(item: ZoteroSearchResult, evt: MouseEvent | KeyboardEvent) {
    new ZoteroWizardModal(this.app, item, this.client, this.settings, this.saveSettings).open();
  }
}

// ─── Wizard Modal ─────────────────────────────────────────────────────
export class ZoteroWizardModal extends Modal {
  private item: ZoteroSearchResult;
  private client: IncuratorClient;
  private settings: PluginSettings;
  private saveSettings: (settings: PluginSettings) => Promise<void>;

  private selectedProfile: string = "new";
  private profileName: string = "";
  private templatePath: string = "";
  private bibliographyStyle: string = "";
  private outputFolder: string = "";
  private outputSubfolder: string = "";
  private outputFilename: string = "{{title}}";
  private assetFolder: string = "05_Assets";
  private assetSubfolder: string = "{{citekey}}";

  private saveAsProfile: boolean = true;

  constructor(
    app: App,
    item: ZoteroSearchResult,
    client: IncuratorClient,
    settings: PluginSettings,
    saveSettings: (settings: PluginSettings) => Promise<void>
  ) {
    super(app);
    this.item = item;
    this.client = client;
    this.settings = settings;
    this.saveSettings = saveSettings;

    const firstProfile = this.settings.zoteroProfiles?.[0];
    if (firstProfile) {
      this.selectedProfile = firstProfile.name;
      this.loadProfile(firstProfile);
    }
  }

  onOpen() { this.display(); }

  display() {
    const { contentEl } = this;
    contentEl.empty();

    contentEl.createEl("h2", { text: "Import Zotero Item" });
    contentEl.createEl("p", { text: this.item.title, attr: { style: "font-weight: bold; margin-bottom: 20px;" } });

    const profiles = this.settings.zoteroProfiles || [];

    if (profiles.length > 0) {
      new Setting(contentEl)
        .setName("Import Profile")
        .setDesc("Select a saved profile or create a new one.")
        .addDropdown(drop => {
          drop.addOption("new", "Create New Custom Setup...");
          profiles.forEach(p => drop.addOption(p.name, p.name));
          drop.setValue(this.selectedProfile);
          drop.onChange(value => {
            this.selectedProfile = value;
            if (value !== "new") {
              const p = profiles.find(x => x.name === value);
              if (p) this.loadProfile(p);
            }
            this.display();
          });
        });
    }

    if (this.selectedProfile === "new") {
      this.renderNewProfileForm(contentEl);
    } else {
      const p = profiles.find(x => x.name === this.selectedProfile);
      if (p) {
        contentEl.createEl("div", { text: `Template: ${p.templatePath}`, cls: "setting-item-description" });
        contentEl.createEl("div", { text: `Output: ${p.outputFolder}/${p.outputSubfolder || ""}`, cls: "setting-item-description" });
        contentEl.createEl("div", { text: `Assets: ${p.assetFolder}/${p.assetSubfolder || ""}`, cls: "setting-item-description" });
        if (p.bibliographyStyle) {
          contentEl.createEl("div", { text: `Bibliography Style: ${p.bibliographyStyle}`, cls: "setting-item-description" });
        }
      }
    }

    new Setting(contentEl)
      .addButton(btn => btn
        .setButtonText("Import Item")
        .setCta()
        .onClick(async () => {
          btn.setButtonText("Importing...").setDisabled(true);
          await this.doImport();
          this.close();
        }));
  }

  private loadProfile(p: ZoteroImportProfile) {
    this.templatePath = p.templatePath;
    this.bibliographyStyle = p.bibliographyStyle || "";
    this.outputFolder = p.outputFolder;
    this.outputSubfolder = p.outputSubfolder ?? "";
    this.outputFilename = p.outputFilename || "{{title}}";
    // Migrate legacy imageFolder → assetFolder/assetSubfolder
    if (p.assetFolder !== undefined) {
      this.assetFolder = p.assetFolder;
      this.assetSubfolder = p.assetSubfolder || "{{citekey}}";
    } else {
      const legacy = (p as any).imageFolder as string | undefined;
      if (legacy) {
        const lastSlash = legacy.lastIndexOf("/");
        this.assetFolder = lastSlash >= 0 ? legacy.substring(0, lastSlash) : legacy;
        this.assetSubfolder = lastSlash >= 0 ? legacy.substring(lastSlash + 1) : "{{citekey}}";
      }
    }
  }

  private renderNewProfileForm(contentEl: HTMLElement) {
    // Template Path
    const tplSetting = new Setting(contentEl)
      .setName("Template Path")
      .setDesc("e.g. 00_System/Templates/Zotero/paper_template.md");
    tplSetting.addText(text => {
      text.setValue(this.templatePath).onChange(val => this.templatePath = val);
      text.inputEl.style.width = "100%";
      new VaultPathSuggest(this.app, text.inputEl, "file", "md");
    });

    // Bibliography Style
    new Setting(contentEl)
      .setName("Bibliography Style")
      .setDesc("CSL style name installed in Zotero (e.g. ACM SIGGRAPH, IEEE, APA 7th edition).")
      .addText(text => {
        text.setPlaceholder("e.g. ACM SIGGRAPH")
          .setValue(this.bibliographyStyle)
          .onChange(val => this.bibliographyStyle = val);
        text.inputEl.style.width = "100%";
      });

    // ── Output section ───────────────────────────────────────────────
    contentEl.createEl("h3", { text: "Output (Note)", attr: { style: "margin: 16px 0 4px; font-size: var(--font-ui-small); color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em;" } });

    const outFolderSetting = new Setting(contentEl)
      .setName("Base Folder")
      .setDesc("e.g. 03_Notes/Papers");
    outFolderSetting.addText(text => {
      text.setValue(this.outputFolder).onChange(val => this.outputFolder = val);
      text.inputEl.style.width = "100%";
      new VaultPathSuggest(this.app, text.inputEl, "folder");
    });

    new Setting(contentEl)
      .setName("Subfolder")
      .setDesc("Created inside Base Folder. Supports {{citekey}}, {{title}}, etc. Leave blank to skip.")
      .addText(text => {
        text.setValue(this.outputSubfolder).onChange(val => this.outputSubfolder = val);
        text.inputEl.style.width = "100%";
      });

    new Setting(contentEl)
      .setName("Filename")
      .setDesc("Note filename without .md. Supports {{title}}, {{citekey}}, etc.")
      .addText(text => {
        text.setValue(this.outputFilename).onChange(val => this.outputFilename = val);
        text.inputEl.style.width = "100%";
      });

    // ── Asset section ────────────────────────────────────────────────
    contentEl.createEl("h3", { text: "Assets (PDF Images)", attr: { style: "margin: 16px 0 4px; font-size: var(--font-ui-small); color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em;" } });

    const assetFolderSetting = new Setting(contentEl)
      .setName("Base Folder")
      .setDesc("e.g. 05_Assets");
    assetFolderSetting.addText(text => {
      text.setValue(this.assetFolder).onChange(val => this.assetFolder = val);
      text.inputEl.style.width = "100%";
      new VaultPathSuggest(this.app, text.inputEl, "folder");
    });

    new Setting(contentEl)
      .setName("Subfolder")
      .setDesc("Subfolder name per item. Supports {{citekey}}, {{title}}, etc.")
      .addText(text => {
        text.setValue(this.assetSubfolder).onChange(val => this.assetSubfolder = val);
        text.inputEl.style.width = "100%";
      });

    // ── Save as profile ──────────────────────────────────────────────
    new Setting(contentEl)
      .setName("Save this setup as a Profile")
      .addToggle(toggle => toggle
        .setValue(this.saveAsProfile)
        .onChange(val => { this.saveAsProfile = val; this.display(); }));

    if (this.saveAsProfile) {
      new Setting(contentEl)
        .setName("Profile Name")
        .setDesc("e.g. Import a paper from Zotero")
        .addText(text => text.setValue(this.profileName).onChange(val => this.profileName = val));
    }
  }

  private joinPath(...parts: string[]): string {
    return parts.filter(Boolean).join("/").replace(/\/+/g, "/");
  }

  private async renderPathTemplate(renderer: TemplateRenderer, template: string, metadata: any): Promise<string> {
    const rendered = await renderer.renderString(template || "", metadata);
    return rendered
      .split("/")
      .map((part) => sanitizePathSegment(part))
      .filter(Boolean)
      .join("/");
  }

  private async renderFilenameTemplate(renderer: TemplateRenderer, template: string, metadata: any): Promise<string> {
    const rendered = await renderer.renderString(template || "", metadata);
    return sanitizePathSegment(rendered);
  }

  async doImport() {
    try {
      if (this.selectedProfile === "new" && this.saveAsProfile && this.profileName) {
        if (!this.settings.zoteroProfiles) this.settings.zoteroProfiles = [];
        this.settings.zoteroProfiles.unshift({
          name: this.profileName,
          templatePath: this.templatePath,
          bibliographyStyle: this.bibliographyStyle,
          outputFolder: this.outputFolder,
          outputSubfolder: this.outputSubfolder,
          outputFilename: this.outputFilename,
          assetFolder: this.assetFolder,
          assetSubfolder: this.assetSubfolder,
        });
        if (this.settings.zoteroProfiles.length > 20) {
          this.settings.zoteroProfiles = this.settings.zoteroProfiles.slice(0, 20);
        }
        await this.saveSettings(this.settings);
      }

      const res: any = await this.client.tryTool(["curator_get_zotero_item_metadata"], {
        item_key: this.item.key,
        custom_paths: this.settings.zoteroBasePath || "~/Zotero",
        citation_style: this.bibliographyStyle || "",
      });

      if (!res || !res.ok || !res.metadata) {
        throw new Error("Failed to fetch Zotero metadata: " + (res?.error || "Unknown error"));
      }

      const metadata = res.metadata;
      const renderer = new TemplateRenderer(this.app);

      // ── Resolve all Nunjucks path templates ─────────────────────
      const resolvedSubfolder = await this.renderPathTemplate(renderer, this.outputSubfolder, metadata);
      const resolvedFilename =
        await this.renderFilenameTemplate(renderer, this.outputFilename || "{{title}}", metadata) || "Untitled";
      const resolvedAssetSubfolder = await this.renderPathTemplate(renderer, this.assetSubfolder, metadata);

      const outputFolderFull = this.joinPath(this.outputFolder, resolvedSubfolder);
      const resolvedAssetFolder = this.joinPath(this.assetFolder, resolvedAssetSubfolder);

      // ── Ensure folders exist ────────────────────────────────────
      if (outputFolderFull) {
        const f = this.app.vault.getAbstractFileByPath(outputFolderFull);
        if (!f) await this.app.vault.createFolder(outputFolderFull);
      }
      if (resolvedAssetFolder) {
        const f = this.app.vault.getAbstractFileByPath(resolvedAssetFolder);
        if (!f) await this.app.vault.createFolder(resolvedAssetFolder);
      }

      // ── Copy PDF images into vault ──────────────────────────────
      for (const ann of metadata.annotations || []) {
        if (ann.imageRelativePath && resolvedAssetFolder) {
          try {
            const imgBuffer = await fs.readFile(ann.imageRelativePath);
            const destPath = this.joinPath(resolvedAssetFolder, `${ann.key || ann.id}.png`);
            if (!this.app.vault.getAbstractFileByPath(destPath)) {
              await this.app.vault.createBinary(destPath, imgBuffer as any);
            }
            ann.imageRelativePath = destPath;
          } catch (e) {
            console.error("Failed to copy image for annotation", ann.key, e);
          }
        } else if (ann.imageRelativePath && !resolvedAssetFolder) {
          ann.imageRelativePath = "";
        }
      }

      // ── Render template and write note ──────────────────────────
      const outputPath = this.joinPath(outputFolderFull, `${resolvedFilename}.md`);

      let existingContent = "";
      const existingFile = this.app.vault.getAbstractFileByPath(outputPath);
      if (existingFile && "stat" in existingFile) {
        existingContent = await this.app.vault.read(existingFile as any);
      }

      const markdown = await renderer.renderTemplate(this.templatePath, metadata, existingContent);

      if (existingFile && "stat" in existingFile) {
        await this.app.vault.modify(existingFile as any, markdown);
        new Notice("Zotero note updated successfully!");
      } else {
        await this.app.vault.create(outputPath, markdown);
        new Notice("Zotero note created successfully!");
      }

      const newFile = this.app.vault.getAbstractFileByPath(outputPath);
      if (newFile && "stat" in newFile) {
        this.app.workspace.getLeaf(false).openFile(newFile as any);
      }

      rememberRecentZoteroItem(this.settings, this.item.key);
      await this.saveSettings(this.settings);

    } catch (e) {
      console.error(e);
      new Notice("Import failed: " + (e as Error).message);
    }
  }

  onClose() {
    this.contentEl.empty();
  }
}
