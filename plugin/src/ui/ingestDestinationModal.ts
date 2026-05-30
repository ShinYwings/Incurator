import { App, Modal, Setting } from "obsidian";

export interface IngestDestinationModalResult {
  destinationRelpath: string;
  importMode: "copy" | "reference";
}

export class IngestDestinationModal extends Modal {
  private destinationRelpath: string;
  private importMode: "copy" | "reference";

  constructor(
    app: App,
    private readonly sourceName: string,
    defaultDestination: string,
    defaultImportMode: "copy" | "reference",
    private readonly onSubmit: (result: IngestDestinationModalResult) => void | Promise<void>
  ) {
    super(app);
    this.destinationRelpath = defaultDestination;
    this.importMode = defaultImportMode;
  }

  onOpen(): void {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.addClass("ai-agent-ingest-modal");

    contentEl.createEl("h2", { text: "Ingest Non-Zotero PDF" });
    contentEl.createEl("p", {
      cls: "setting-item-description",
      text: "This file was not recognized as a Zotero attachment. It will be copied to your vault by default so the Incurator AI can access and track it.",
    });
    contentEl.createEl("p", {
      cls: "setting-item-name",
      text: this.sourceName,
      attr: { style: "font-weight: 600; margin-top: 12px; margin-bottom: 8px;" }
    });

    let destinationSetting: Setting;

    new Setting(contentEl)
      .setName("Mode")
      .setDesc("Copy creates a vault-local copy (recommended for non-Zotero). Reference tries to link the external path.")
      .addDropdown((dropdown) =>
        dropdown
          .addOption("reference", "Reference external file")
          .addOption("copy", "Copy into vault")
          .setValue(this.importMode)
          .onChange((value) => {
            this.importMode = value === "copy" ? "copy" : "reference";
            destinationSetting.settingEl.toggle(this.importMode === "copy");
          })
      );

    destinationSetting = new Setting(contentEl)
      .setName("Destination")
      .setDesc("Vault folder to copy the PDF into.")
      .addText((text) => {
        text
          .setPlaceholder("04_Resources")
          .setValue(this.destinationRelpath)
          .onChange((value) => {
            this.destinationRelpath = value.trim();
          });
      });
    // Hide destination when in reference mode (no copy needed)
    destinationSetting.settingEl.toggle(this.importMode === "copy");

    const actions = contentEl.createDiv("ai-agent-ingest-modal-actions");
    const cancelBtn = actions.createEl("button", { text: "Cancel" });
    cancelBtn.addEventListener("click", () => this.close());

    const ingestBtn = actions.createEl("button", {
      cls: "mod-cta",
      text: "Ingest",
    });
    ingestBtn.addEventListener("click", async () => {
      await this.onSubmit({
        destinationRelpath: this.destinationRelpath || "04_Resources",
        importMode: this.importMode,
      });
      this.close();
    });
  }

  onClose(): void {
    this.contentEl.empty();
  }
}
