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

    contentEl.createEl("h2", { text: "Ingest PDF" });
    contentEl.createEl("p", {
      cls: "setting-item-description",
      text: this.sourceName,
    });

    new Setting(contentEl)
      .setName("Mode")
      .setDesc("Reference keeps the external PDF in place. Copy stores a vault-local copy under 04_Resources.")
      .addDropdown((dropdown) =>
        dropdown
          .addOption("reference", "Reference external file")
          .addOption("copy", "Copy into vault")
          .setValue(this.importMode)
          .onChange((value) => {
            this.importMode = value === "copy" ? "copy" : "reference";
          })
      );

    new Setting(contentEl)
      .setName("Destination")
      .setDesc("Vault folder for copy mode. Reference mode stores only the backend source record.")
      .addText((text) => {
        text
          .setPlaceholder("04_Resources")
          .setValue(this.destinationRelpath)
          .onChange((value) => {
            this.destinationRelpath = value.trim();
          });
      });

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
