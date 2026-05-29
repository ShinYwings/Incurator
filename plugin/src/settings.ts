import { App, PluginSettingTab, Setting, Notice } from "obsidian";
import type ObsidianAIAgent from "../main";
import {
  type PluginSettings,
  type LLMProvider,
  type MCPServerConfig,
  type ClaudeEffort,
  type CodexReasoningEffort,
  DEFAULT_SETTINGS,
  getDefaultModel,
  getModelOption,
} from "./types";
import { getIncuratorBackendStatus } from "./utils/incuratorBackendStatus";
import { isIncuratorMcpServer } from "./utils/incuratorMcpServer";

const CUSTOM_MODEL_VALUE = "__custom__";

function parseCommandArgs(value: string): string[] {
  const trimmed = value.trim();
  if (!trimmed) return [];
  try {
    const parsed = JSON.parse(trimmed);
    if (Array.isArray(parsed)) return parsed.map((item) => String(item));
  } catch {
    // Fall back to a simple shell-like split for the common case.
  }
  return trimmed.split(/\s+/).filter(Boolean);
}

export class AIAgentSettingTab extends PluginSettingTab {
  plugin: ObsidianAIAgent;

  constructor(app: App, plugin: ObsidianAIAgent) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    // ── Header ──
    containerEl.createEl("h1", { text: "AI Agent Settings" });

    // ── Provider Selection ──
    containerEl.createEl("h2", { text: "LLM Provider" });

    new Setting(containerEl)
      .setName("Provider")
      .setDesc("Select the LLM provider for AI operations.")
      .addDropdown((dropdown) =>
        dropdown
          .addOption("antigravity", "Google Antigravity (agy login)")
          .addOption("claude", "Anthropic Claude (Claude Code login)")
          .addOption("openai", "Codex (ChatGPT login)")
          .setValue(this.plugin.settings.provider)
          .onChange(async (value: string) => {
            const provider = value as LLMProvider;
            this.plugin.settings.provider = provider;
            this.plugin.settings.model =
              getDefaultModel(this.plugin.getAvailableModels(), provider) || "";
            await this.plugin.saveSettings();
            this.display(); // Re-render to update model field
          })
      );

    new Setting(containerEl)
      .setName("Model")
      .setDesc("Model to use for the selected provider.")
      .addDropdown((dropdown) => {
        const provider = this.plugin.settings.provider;
        const catalogue = this.plugin.getAvailableModels();
        const options = catalogue[provider] || [];
        for (const option of options) {
          const suffix = option.tier === "flash" || option.tier === "stable" ? "" : ` (${option.tier})`;
          dropdown.addOption(option.id, `${option.label}${suffix}`);
        }
        dropdown.addOption(CUSTOM_MODEL_VALUE, "Custom...");
        dropdown
          .setValue(
            getModelOption(catalogue, provider, this.plugin.settings.model)
              ? this.plugin.settings.model
              : CUSTOM_MODEL_VALUE
          )
          .onChange(async (value) => {
            if (value === CUSTOM_MODEL_VALUE) {
              if (getModelOption(catalogue, provider, this.plugin.settings.model)) {
                this.plugin.settings.model = "";
              }
            } else {
              this.plugin.settings.model = value;
            }
            await this.plugin.saveSettings();
            this.display();
          });
      });

    if (
      !getModelOption(
        this.plugin.getAvailableModels(),
        this.plugin.settings.provider,
        this.plugin.settings.model
      )
    ) {
      new Setting(containerEl)
        .setName("Custom model")
        .setDesc("Use an exact provider model id.")
        .addText((text) =>
          text
            .setPlaceholder(
              getDefaultModel(
                this.plugin.getAvailableModels(),
                this.plugin.settings.provider
              ) || "exact-model-id"
            )
            .setValue(this.plugin.settings.model)
            .onChange(async (value) => {
              this.plugin.settings.model =
                value.trim() ||
                getDefaultModel(
                  this.plugin.getAvailableModels(),
                  this.plugin.settings.provider
                );
              await this.plugin.saveSettings();
            })
      );
    }

    // ── Provider Parameters ──
    containerEl.createEl("h2", { text: "Provider Parameters" });

    new Setting(containerEl)
      .setName("Codex thinking level")
      .setDesc("Passed to Codex as model_reasoning_effort.")
      .addDropdown((dropdown) =>
        dropdown
          .addOption("low", "Low")
          .addOption("medium", "Medium")
          .addOption("high", "High")
          .addOption("xhigh", "XHigh")
          .setValue(this.plugin.settings.codexReasoningEffort)
          .onChange(async (value) => {
            this.plugin.settings.codexReasoningEffort =
              value as CodexReasoningEffort;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Claude effort")
      .setDesc("Passed to Claude Code as --effort.")
      .addDropdown((dropdown) =>
        dropdown
          .addOption("low", "Low")
          .addOption("medium", "Medium")
          .addOption("high", "High")
          .addOption("xhigh", "XHigh")
          .addOption("max", "Max")
          .setValue(this.plugin.settings.claudeEffort)
          .onChange(async (value) => {
            this.plugin.settings.claudeEffort = value as ClaudeEffort;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Antigravity print timeout")
      .setDesc("Antigravity CLI does not expose a thinking level; this controls --print-timeout.")
      .addText((text) =>
        text
          .setPlaceholder("300")
          .setValue(String(this.plugin.settings.antigravityPrintTimeoutSec))
          .onChange(async (value) => {
            const seconds = Number.parseInt(value, 10);
            if (Number.isFinite(seconds)) {
              this.plugin.settings.antigravityPrintTimeoutSec = Math.max(30, seconds);
              await this.plugin.saveSettings();
            }
          })
      );

    containerEl.createEl("h2", { text: "Usage" });
    this.renderUsageSummary(containerEl);

    // ── Auth Status ──
    containerEl.createEl("h2", { text: "Authentication Status" });
    const authStatusEl = containerEl.createDiv("ai-agent-auth-status");
    this.renderAuthStatus(authStatusEl);

    new Setting(containerEl)
      .setName("CLI browser login")
      .setDesc("Open a terminal and start the selected provider's browser login flow.")
      .addButton((button) =>
        button
          .setButtonText(`Login to ${this.providerLabel(this.plugin.settings.provider)}`)
          .setCta()
          .onClick(() => {
            this.startProviderLogin(this.plugin.settings.provider);
          })
      )
      .addButton((button) =>
        button.setButtonText("Refresh status").onClick(() => {
          this.plugin.authResolver.invalidate(this.plugin.settings.provider);
          this.display();
        })
      );

    // ── Chat & Context ──
    containerEl.createEl("h2", { text: "Chat & Context" });

    new Setting(containerEl)
      .setName("Streaming responses")
      .setDesc("Stream LLM responses token-by-token.")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.streamingEnabled)
          .onChange(async (value) => {
            this.plugin.settings.streamingEnabled = value;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Max context length")
      .setDesc("Maximum token budget for the system prompt context (default 128000).")
      .addText((text) =>
        text
          .setPlaceholder("128000")
          .setValue(String(this.plugin.settings.maxContextLength))
          .onChange(async (value) => {
            const parsed = Number.parseInt(value, 10);
            if (Number.isFinite(parsed) && parsed >= 4000) {
              this.plugin.settings.maxContextLength = parsed;
              await this.plugin.saveSettings();
            }
          })
      );

    // ── Editing Behavior ──
    containerEl.createEl("h2", { text: "Editing & Rendering" });

    new Setting(containerEl)
      .setName("Diff mode")
      .setDesc("How to display inline edit results.")
      .addDropdown((dropdown) =>
        dropdown
          .addOption("inline", "Inline highlights")
          .addOption("side-by-side", "Side-by-side modal")
          .setValue(this.plugin.settings.diffMode)
          .onChange(async (value: string) => {
            this.plugin.settings.diffMode = value as "inline" | "side-by-side";
            await this.plugin.saveSettings();
          })
      );

    // ── PDF Context ──
    containerEl.createEl("h2", { text: "PDF Context" });

    new Setting(containerEl)
      .setName("PDF capture mode")
      .setDesc(
        "How to capture the active PDF page for context. 'Both' sends text + screenshot."
      )
      .addDropdown((dropdown) =>
        dropdown
          .addOption("text", "Text only")
          .addOption("image", "Image only (Vision API)")
          .addOption("both", "Text + Image")
          .setValue(this.plugin.settings.pdfCaptureMode)
          .onChange(async (value: string) => {
            this.plugin.settings.pdfCaptureMode = value as
              | "text"
              | "image"
              | "both";
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("PDF window radius")
      .setDesc("Neighboring pages to include around the current PDF page.")
      .addText((text) =>
        text
          .setPlaceholder("1")
          .setValue(String(this.plugin.settings.pdfWindowRadius))
          .onChange(async (value) => {
            const parsed = Number.parseInt(value, 10);
            if (Number.isFinite(parsed)) {
              this.plugin.settings.pdfWindowRadius = Math.max(0, Math.min(5, parsed));
              await this.plugin.saveSettings();
            }
          })
      );

    new Setting(containerEl)
      .setName("Include PDF outline")
      .setDesc("Send available PDF table-of-contents information to the agent.")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.pdfOutlineEnabled)
          .onChange(async (value) => {
            this.plugin.settings.pdfOutlineEnabled = value;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("PDF local RAG")
      .setDesc("Search open PDFs for relevant pages before each question.")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.pdfRagEnabled)
          .onChange(async (value) => {
            this.plugin.settings.pdfRagEnabled = value;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("PDF RAG top K")
      .setDesc("Maximum matching PDF page chunks to include.")
      .addText((text) =>
        text
          .setPlaceholder("5")
          .setValue(String(this.plugin.settings.pdfRagTopK))
          .onChange(async (value) => {
            const parsed = Number.parseInt(value, 10);
            if (Number.isFinite(parsed)) {
              this.plugin.settings.pdfRagTopK = Math.max(1, Math.min(20, parsed));
              await this.plugin.saveSettings();
            }
          })
      );

    new Setting(containerEl)
      .setName("Vision fallback for scanned PDFs")
      .setDesc("Attach the current PDF page image when text extraction looks poor.")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.pdfVisionFallback)
          .onChange(async (value) => {
            this.plugin.settings.pdfVisionFallback = value;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Background PDF indexing")
      .setDesc("Index open PDFs in the background for immediate page search.")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.pdfFullDocumentIndex)
          .onChange(async (value) => {
            this.plugin.settings.pdfFullDocumentIndex = value;
            await this.plugin.saveSettings();
          })
      );

    containerEl.createEl("h2", { text: "PDF & Incurator" });

    const incuratorSetting = new Setting(containerEl)
      .setName("Use Incurator backend")
      .setDesc("Use Incurator MCP for source status, ingest, and vault search.")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.incuratorEnabled)
          .onChange(async (value) => {
            await this.plugin.setIncuratorBackendEnabled(value);
            this.renderIncuratorBackendStatus(incuratorStatusEl);
          })
      );
    const incuratorStatusEl = incuratorSetting.settingEl.createDiv("ai-agent-incurator-status");
    this.renderIncuratorBackendStatus(incuratorStatusEl);

    new Setting(containerEl)
      .setName("Incurator MCP command")
      .setDesc("Per-device backend command. Use `wiki` when Incurator is installed on PATH.")
      .addText((text) =>
        text
          .setPlaceholder("wiki")
          .setValue(this.plugin.settings.incuratorMcpCommand)
          .onChange(async (value) => {
            this.plugin.settings.incuratorMcpCommand =
              value.trim() || DEFAULT_SETTINGS.incuratorMcpCommand;
            await this.plugin.saveSettings();
            if (this.plugin.settings.incuratorEnabled) {
              await this.plugin.setIncuratorBackendEnabled(true);
              this.renderIncuratorBackendStatus(incuratorStatusEl);
            }
          })
      );

    new Setting(containerEl)
      .setName("Incurator MCP args")
      .setDesc("Arguments for the backend command. Accepts JSON array or space-separated args.")
      .addText((text) =>
        text
          .setPlaceholder("mcp")
          .setValue(this.plugin.settings.incuratorMcpArgs.join(" "))
          .onChange(async (value) => {
            const args = parseCommandArgs(value);
            this.plugin.settings.incuratorMcpArgs =
              args.length ? args : [...DEFAULT_SETTINGS.incuratorMcpArgs];
            await this.plugin.saveSettings();
            if (this.plugin.settings.incuratorEnabled) {
              await this.plugin.setIncuratorBackendEnabled(true);
              this.renderIncuratorBackendStatus(incuratorStatusEl);
            }
          })
      );

    new Setting(containerEl)
      .setName("Incurator repository path")
      .setDesc("Absolute path to the Incurator git repository for 1-click auto-updates.")
      .addText((text) =>
        text
          .setPlaceholder("/absolute/path/to/Incurator")
          .setValue(this.plugin.settings.incuratorRepoPath)
          .onChange(async (value) => {
            this.plugin.settings.incuratorRepoPath = value.trim();
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Default PDF destination")
      .setDesc("Base vault folder for imported external PDFs.")
      .addText((text) =>
        text
          .setPlaceholder("04_Resources")
          .setValue(this.plugin.settings.incuratorDefaultDestination)
          .onChange(async (value) => {
            this.plugin.settings.incuratorDefaultDestination =
              value.trim() || DEFAULT_SETTINGS.incuratorDefaultDestination;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Default PDF import mode")
      .setDesc("Reference keeps Zotero or external PDFs in place; copy imports them into 04_Resources.")
      .addDropdown((dropdown) =>
        dropdown
          .addOption("reference", "Reference external file")
          .addOption("copy", "Copy into vault")
          .setValue(this.plugin.settings.incuratorDefaultImportMode)
          .onChange(async (value) => {
            this.plugin.settings.incuratorDefaultImportMode =
              value === "copy" ? "copy" : "reference";
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Poll Incurator ingest status")
      .setDesc("Refresh PDF chip backend status while ingest jobs are running.")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.incuratorStatusPolling)
          .onChange(async (value) => {
            this.plugin.settings.incuratorStatusPolling = value;
            await this.plugin.saveSettings();
          })
      );

    containerEl.createEl("h2", { text: "Zotero Integration" });

    new Setting(containerEl)
      .setName("Zotero custom directories (Optional)")
      .setDesc(
        "Comma-separated list of Zotero data paths (e.g. ~/Zotero, D:\\Zotero). " +
          "The plugin automatically checks standard paths, so you only need to add custom ones here."
      )
      .addText((text) =>
        text
          .setPlaceholder("~/MyZotero, D:\\Zotero")
          .setValue(this.plugin.settings.zoteroBasePath)
          .onChange(async (value) => {
            this.plugin.settings.zoteroBasePath = value.trim();
            await this.plugin.saveSettings();
          })
      );

    containerEl.createEl("h3", { text: "Import Profiles" });
    containerEl.createEl("p", {
      cls: "setting-item-description",
      text: "Profiles are created in the Import Zotero Item wizard. Edit or delete them here.",
    });

    const profiles = this.plugin.settings.zoteroProfiles || [];
    if (profiles.length === 0) {
      containerEl.createEl("p", {
        cls: "setting-item-description",
        text: "No profiles saved yet.",
        attr: { style: "color: var(--text-muted); font-style: italic;" },
      });
    } else {
      for (let i = 0; i < profiles.length; i++) {
        this.renderZoteroProfile(containerEl, i);
      }
    }

    // ── MCP Servers ──
    containerEl.createEl("h2", { text: "MCP Servers" });

    const mcpDesc = containerEl.createEl("p", {
      cls: "setting-item-description",
    });
    mcpDesc.setText(
      "Configure local MCP (Model Context Protocol) servers for tool use."
    );

    for (let i = 0; i < this.plugin.settings.mcpServers.length; i++) {
      if (isIncuratorMcpServer(this.plugin.settings.mcpServers[i])) continue;
      this.renderMCPServer(containerEl, i);
    }

    new Setting(containerEl).addButton((button) =>
      button
        .setButtonText("Add MCP Server")
        .setCta()
        .onClick(async () => {
          this.plugin.settings.mcpServers.push({
            name: "",
            command: "",
            args: [],
            enabled: true,
          });
          await this.plugin.saveSettings();
          this.display();
        })
    );
  }

  private renderZoteroProfile(containerEl: HTMLElement, index: number): void {
    const profile = this.plugin.settings.zoteroProfiles[index];

    const details = containerEl.createEl("details", {
      attr: { style: "border: 1px solid var(--background-modifier-border); border-radius: 6px; margin-bottom: 8px; padding: 0;" }
    });

    // ── Summary row (always visible) ──────────────────────────────
    const summary = details.createEl("summary", {
      attr: { style: "display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; cursor: pointer; list-style: none; user-select: none;" }
    });
    const summaryLeft = summary.createSpan({ attr: { style: "font-weight: 600; font-size: var(--font-ui-medium);" } });
    summaryLeft.setText(profile.name || `Profile ${index + 1}`);

    const deleteBtn = summary.createEl("button", {
      attr: { style: "background: none; border: none; cursor: pointer; color: var(--text-error); padding: 2px 6px; font-size: 16px;", title: "Delete profile" }
    });
    deleteBtn.setText("✕");
    deleteBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      this.plugin.settings.zoteroProfiles.splice(index, 1);
      await this.plugin.saveSettings();
      this.display();
    });

    // ── Expanded fields ───────────────────────────────────────────
    const body = details.createDiv({ attr: { style: "padding: 0 14px 10px;" } });

    const field = (name: string, desc: string, get: () => string, set: (v: string) => void, wide = false) => {
      const s = new Setting(body).setName(name);
      if (desc) s.setDesc(desc);
      s.addText(text => {
        if (wide) text.inputEl.style.width = "100%";
        text.setValue(get()).onChange(async val => {
          set(val);
          await this.plugin.saveSettings();
        });
      });
    };

    field("Profile Name", "", () => profile.name, v => { profile.name = v; summaryLeft.setText(v || `Profile ${index + 1}`); }, true);
    field("Template Path", "e.g. 00_System/Templates/Zotero/paper_template.md", () => profile.templatePath, v => profile.templatePath = v, true);
    field("Bibliography Style", "CSL style name installed in Zotero", () => profile.bibliographyStyle || "", v => profile.bibliographyStyle = v, true);

    body.createEl("p", { text: "Output (Note)", attr: { style: "margin: 12px 0 2px; font-size: var(--font-ui-small); color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em;" } });
    field("Base Folder", "e.g. 03_Notes/Papers", () => profile.outputFolder, v => profile.outputFolder = v, true);
    field("Subfolder", "Supports {{citekey}}, {{title}}, etc.", () => profile.outputSubfolder || "", v => profile.outputSubfolder = v, true);
    field("Filename", "Without .md. e.g. {{title}}", () => profile.outputFilename || "{{title}}", v => profile.outputFilename = v, true);

    body.createEl("p", { text: "Assets (PDF Images)", attr: { style: "margin: 12px 0 2px; font-size: var(--font-ui-small); color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em;" } });
    field("Base Folder", "e.g. 05_Assets", () => profile.assetFolder || "", v => profile.assetFolder = v, true);
    field("Subfolder", "Supports {{citekey}}, {{title}}, etc.", () => profile.assetSubfolder || "", v => profile.assetSubfolder = v, true);
  }

  private renderMCPServer(containerEl: HTMLElement, index: number): void {
    const server = this.plugin.settings.mcpServers[index];
    const wrapper = containerEl.createDiv("ai-agent-mcp-server");

    const headerSetting = new Setting(wrapper)
      .setName(`Server ${index + 1}`)
      .setDesc(server.enabled ? "Status: 🟡 Connecting..." : "Status: ⚪️ Disabled");

    let isTesting = false;
    const testConnection = async (toggleComponent?: any) => {
      if (isTesting || !server.enabled) return;
      isTesting = true;
      headerSetting.setDesc("Status: 🟡 Connecting...");
      try {
        const info = await this.plugin.llmClient.testMcpConnection(server.name);
        if (server.enabled) {
          headerSetting.setDesc(`Status: 🟢 Connected (${info.name} v${info.version})`);
        }
      } catch (e: any) {
        if (server.enabled) {
          headerSetting.setDesc(`Status: 🔴 Error`);
          new Notice(`MCP Connection Failed: ${e.message}`);
          // Auto-disable if connection fails
          server.enabled = false;
          await this.plugin.saveSettings();
          if (toggleComponent) toggleComponent.setValue(false);
          headerSetting.setDesc("Status: ⚪️ Disabled (Connection Failed)");
        }
      } finally {
        isTesting = false;
      }
    };

    headerSetting.addToggle((toggle) => {
      toggle.setValue(server.enabled).onChange(async (value) => {
        server.enabled = value;
        await this.plugin.saveSettings();
        if (value) {
          testConnection(toggle);
        } else {
          headerSetting.setDesc("Status: ⚪️ Disabled");
        }
      });
      // Initial test if already enabled
      if (server.enabled) {
        testConnection(toggle);
      }
    });

    headerSetting.addButton((button) =>
      button
        .setIcon("trash")
        .setWarning()
        .onClick(async () => {
          this.plugin.settings.mcpServers.splice(index, 1);
          await this.plugin.saveSettings();
          this.display();
        })
    );

    new Setting(wrapper).setName("Name").addText((text) =>
      text
        .setPlaceholder("my-mcp-server")
        .setValue(server.name)
        .onChange(async (value) => {
          server.name = value;
          await this.plugin.saveSettings();
        })
    );

    new Setting(wrapper).setName("Command").addText((text) =>
      text
        .setPlaceholder("/usr/local/bin/my-server")
        .setValue(server.command)
        .onChange(async (value) => {
          server.command = value;
          await this.plugin.saveSettings();
        })
    );

    new Setting(wrapper)
      .setName("Arguments")
      .setDesc("Space-separated arguments")
      .addText((text) =>
        text
          .setPlaceholder("--stdio --verbose")
          .setValue(server.args.join(" "))
          .onChange(async (value) => {
            server.args = value
              .split(" ")
              .map((s) => s.trim())
              .filter(Boolean);
            await this.plugin.saveSettings();
          })
      );

    new Setting(wrapper)
      .setName("Environment Variables (JSON)")
      .setDesc('e.g. {"VAULT_ROOT": "/path/to/vault"}')
      .addTextArea((text) => {
        text.setPlaceholder('{"KEY": "value"}');
        text.setValue(server.env ? JSON.stringify(server.env, null, 2) : "");
        text.onChange(async (value) => {
          try {
            const trimmed = value.trim();
            if (!trimmed) {
              server.env = undefined;
            } else {
              server.env = JSON.parse(trimmed);
            }
            text.inputEl.style.borderColor = "";
            await this.plugin.saveSettings();
          } catch (e) {
            text.inputEl.style.borderColor = "red";
          }
        });
      });
  }

  private renderIncuratorBackendStatus(containerEl: HTMLElement): void {
    containerEl.empty();
    const status = getIncuratorBackendStatus({
      enabled: this.plugin.settings.incuratorEnabled,
      servers: this.plugin.settings.mcpServers,
      tools: this.plugin.mcpManager.getAllTools(),
    });

    containerEl.toggleClass("is-disabled", status.state === "disabled");
    containerEl.toggleClass("is-connected", status.state === "connected");
    containerEl.toggleClass("is-connecting", status.state === "connecting");
    containerEl.toggleClass("is-missing", status.state === "missing");

    const dot = containerEl.createSpan("ai-agent-incurator-status-dot");
    dot.setAttr("aria-hidden", "true");

    const text = containerEl.createDiv("ai-agent-incurator-status-text");
    text.createDiv({
      cls: "ai-agent-incurator-status-label",
      text: `Status: ${status.label}`,
    });
    text.createDiv({
      cls: "ai-agent-incurator-status-detail",
      text: status.detail,
    });

    const refresh = containerEl.createEl("button", {
      cls: "ai-agent-incurator-status-refresh",
      text: "Refresh",
    });
    refresh.addEventListener("click", () => this.renderIncuratorBackendStatus(containerEl));
  }

  private async renderAuthStatus(container: HTMLElement): Promise<void> {
    const provider = this.plugin.settings.provider;
    const statusEl = container.createDiv("ai-agent-auth-status-item");

    try {
      const token = await this.plugin.authResolver.resolveToken(provider);
      if (token) {
        statusEl.createSpan({ cls: "ai-agent-auth-ok", text: "✓ " });
        statusEl.createSpan({
          text: `${provider} — authenticated`,
        });
      }
    } catch (e: unknown) {
      statusEl.createSpan({ cls: "ai-agent-auth-fail", text: "✗ " });
      const message = e instanceof Error ? e.message : String(e);
      statusEl.createSpan({
        text: `${provider} — ${message}`,
      });
    }
  }

  private renderUsageSummary(containerEl: HTMLElement): void {
    const wrapper = containerEl.createDiv("ai-agent-usage-summary");
    for (const provider of ["antigravity", "claude", "openai"] as LLMProvider[]) {
      const usage =
        this.plugin.settings.providerUsage[provider] ||
        DEFAULT_SETTINGS.providerUsage[provider];
      const label = this.providerLabel(provider);
      const lastUsed = usage.lastUsedAt
        ? new Date(usage.lastUsedAt).toLocaleString()
        : "Never";
      const totalTokens =
        usage.inputTokens +
        usage.cachedInputTokens +
        usage.outputTokens +
        usage.reasoningOutputTokens;
      const row = wrapper.createDiv("ai-agent-usage-row");
      row.createSpan({ cls: "ai-agent-usage-provider", text: label });
      row.createSpan({
        cls: "ai-agent-usage-detail",
        text: `${usage.requests} requests · ${totalTokens.toLocaleString()} tokens · last ${lastUsed}`,
      });
    }

    new Setting(containerEl).addButton((button) =>
      button
        .setButtonText("Reset usage")
        .setWarning()
        .onClick(async () => {
          this.plugin.settings.providerUsage = JSON.parse(
            JSON.stringify(DEFAULT_SETTINGS.providerUsage)
          );
          await this.plugin.saveSettings();
          this.display();
        })
    );
  }

  private startProviderLogin(provider: LLMProvider): void {
    try {
      this.plugin.authResolver.startLogin(provider);
      new Notice(
        `Opened ${this.providerLabel(provider)} login in your terminal.`
      );
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      new Notice(message);
    }
  }

  private providerLabel(provider: LLMProvider): string {
    switch (provider) {
      case "antigravity":
        return "Antigravity";
      case "claude":
        return "Claude";
      case "openai":
        return "Codex";
    }
  }
}
