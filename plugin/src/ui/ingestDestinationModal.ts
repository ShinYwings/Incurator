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

    contentEl.createEl("h2", { text: "Add PDF to Incurator" });
    contentEl.createEl("p", {
      cls: "setting-item-description",
      text: "Register this PDF as an Incurator source. Reference mode keeps the original file in place and creates a lightweight link stub in 04_Resources.",
    });
    contentEl.createEl("p", {
      cls: "setting-item-name",
      text: this.sourceName,
      attr: { style: "font-weight: 600; margin-top: 12px; margin-bottom: 8px;" }
    });

    let destinationSetting: Setting;

    let submitBtn: HTMLButtonElement | null = null;
    const updateSubmitText = () => {
      if (submitBtn) submitBtn.textContent = this.importMode === "copy" ? "Copy and add" : "Add as reference";
    };

    new Setting(contentEl)
      .setName("Mode")
      .setDesc("Reference creates a lightweight 04_Resources link stub. Copy is only for files you want the vault to manage directly.")
      .addDropdown((dropdown) =>
        dropdown
          .addOption("reference", "Reference external file")
          .addOption("copy", "Copy into vault")
          .setValue(this.importMode)
          .onChange((value) => {
            this.importMode = value === "copy" ? "copy" : "reference";
            destinationSetting.settingEl.toggle(this.importMode === "copy");
            updateSubmitText();
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

    const errorEl = contentEl.createDiv({ cls: "setting-item-description" });
    errorEl.hide();

    submitBtn = actions.createEl("button", {
      cls: "mod-cta",
      text: this.importMode === "copy" ? "Copy and add" : "Add as reference",
    });
    submitBtn.addEventListener("click", async () => {
      submitBtn.disabled = true;
      cancelBtn.disabled = true;
      errorEl.hide();
      try {
        await this.onSubmit({
          destinationRelpath: this.destinationRelpath || "04_Resources",
          importMode: this.importMode,
        });
        this.close();
      } catch (err) {
        errorEl.setText(err instanceof Error ? err.message : String(err));
        errorEl.show();
        submitBtn.disabled = false;
        cancelBtn.disabled = false;
      }
    });
  }

  onClose(): void {
    this.contentEl.empty();
  }
}
