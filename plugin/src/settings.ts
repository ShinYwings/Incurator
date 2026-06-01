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
    containerEl.addClass("ai-agent-settings-root");

    // ═══════════════════════════════════════════════════════════════
    // 1. AI Provider
    // ═══════════════════════════════════════════════════════════════
    const providerSection = containerEl.createDiv("ai-agent-settings-section");
    this.renderSectionHeader(providerSection, "AI Provider", "bot");

    new Setting(providerSection)
      .setName("Provider")
      .setDesc("LLM backend for chat and inline editing.")
      .addDropdown((dropdown) =>
        dropdown
          .addOption("antigravity", "Google Antigravity")
          .addOption("claude", "Anthropic Claude")
          .addOption("openai", "OpenAI Codex")
          .addOption("ollama", "Ollama (local)")
          .addOption("deepseek", "DeepSeek API")
          .setValue(this.plugin.settings.provider)
          .onChange(async (value: string) => {
            const provider = value as LLMProvider;
            this.plugin.settings.provider = provider;
            this.plugin.settings.model =
              getDefaultModel(this.plugin.getAvailableModels(), provider) || "";
            await this.plugin.saveSettings();
            this.display();
          })
      );

    if (this.plugin.settings.provider === "ollama") {
      // Ollama: host URL + model text field with fetch button
      new Setting(providerSection)
        .setName("Ollama host")
        .setDesc("URL of the running Ollama server.")
        .addText((text) =>
          text
            .setPlaceholder("http://localhost:11434")
            .setValue(this.plugin.settings.ollamaHost || "http://localhost:11434")
            .onChange(async (value) => {
              this.plugin.settings.ollamaHost = value.trim() || "http://localhost:11434";
              await this.plugin.saveSettings();
            })
        );

      const modelSetting = new Setting(providerSection)
        .setName("Model")
        .setDesc("Type a model name or fetch from server.")
        .addText((text) =>
          text
            .setPlaceholder("qwen2.5:7b")
            .setValue(this.plugin.settings.model)
            .onChange(async (value) => {
              this.plugin.settings.model = value.trim();
              await this.plugin.saveSettings();
            })
        );

      modelSetting.addButton((btn) =>
        btn.setButtonText("Fetch models").onClick(async () => {
          btn.setDisabled(true);
          btn.setButtonText("Fetching…");
          try {
            const host = (this.plugin.settings.ollamaHost || "http://localhost:11434").replace(/\/$/, "");
            const res = await fetch(`${host}/api/tags`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json() as { models?: Array<{ name: string }> };
            const names = (data.models || []).map((m) => m.name).filter(Boolean);
            if (names.length === 0) {
              new Notice("No models found. Run: ollama pull <model>");
            } else {
              new Notice(`Available: ${names.join(", ")}`);
              if (!this.plugin.settings.model) {
                this.plugin.settings.model = names[0];
                await this.plugin.saveSettings();
                this.display();
              }
            }
          } catch (e) {
            new Notice(`Could not reach Ollama: ${e}`);
          } finally {
            btn.setDisabled(false);
            btn.setButtonText("Fetch models");
          }
        })
      );
    } else {
      new Setting(providerSection)
        .setName("Model")
        .addDropdown((dropdown) => {
          const provider = this.plugin.settings.provider;
          const catalogue = this.plugin.getAvailableModels();
          const options = catalogue[provider] || [];
          for (const option of options) {
            dropdown.addOption(option.id, option.label);
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
        new Setting(providerSection)
          .setName("Custom model ID")
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
    }

    // Show only the parameter for the CURRENT provider + model
    const currentProvider = this.plugin.settings.provider;
    const currentModelOption = getModelOption(
      this.plugin.getAvailableModels(),
      currentProvider,
      this.plugin.settings.model
    );
    const modelThinks = currentProvider === "claude" || currentProvider === "openai";

    // Model info line: context window
    if (currentModelOption?.contextWindow) {
      const ctxK = Math.round(currentModelOption.contextWindow / 1000);
      new Setting(providerSection)
        .setName("Context window")
        .setDesc(`This model supports up to ${ctxK}K tokens of context.`);
    }

    if (currentModelOption?.efforts && currentModelOption.efforts.length > 0) {
      new Setting(providerSection)
        .setName("Reasoning effort")
        .setDesc("Controls reasoning depth for this model.")
        .addDropdown((dropdown) => {
          currentModelOption.efforts!.forEach((e) => {
            dropdown.addOption(e, e.charAt(0).toUpperCase() + e.slice(1));
          });
          const getOldVal = () => {
             if (currentProvider === "openai") return this.plugin.settings.codexReasoningEffort;
             if (currentProvider === "claude") return this.plugin.settings.claudeEffort;
             return this.plugin.settings.agentEffort;
          };
          const rawVal = getOldVal();
          const val = currentModelOption.efforts!.includes(rawVal) ? rawVal : (currentModelOption.defaultEffort || currentModelOption.efforts![0]);

          dropdown.setValue(val)
            .onChange(async (value) => {
              if (currentProvider === "openai") this.plugin.settings.codexReasoningEffort = value as any;
              else if (currentProvider === "claude") this.plugin.settings.claudeEffort = value as any;
              else this.plugin.settings.agentEffort = value;
              await this.plugin.saveSettings();
            });
        });
    }

    if (currentProvider === "antigravity") {
      new Setting(providerSection)
        .setName("Response timeout (seconds)")
        .setDesc("Max wait for agy to finish generating a response.")
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
    }

    if (currentProvider === "deepseek") {
      new Setting(providerSection)
        .setName("API key")
        .setDesc("DeepSeek uses an API key, not OAuth. Leave blank to use DEEPSEEK_API_KEY from the environment.")
        .addText((text) => {
          text.inputEl.type = "password";
          text
            .setPlaceholder("sk-...")
            .setValue(this.plugin.settings.deepseekApiKey || "")
            .onChange(async (value) => {
              this.plugin.settings.deepseekApiKey = value.trim();
              await this.plugin.saveSettings();
            });
        });
    }

    // Auth status inline — Ollama shows a server status check instead
    if (currentProvider === "ollama") {
      const ollamaRow = new Setting(providerSection).setName("Server status");
      const ollamaBadge = ollamaRow.settingEl.createSpan("ai-agent-auth-inline-badge");
      const checkOllama = async () => {
        ollamaBadge.empty();
        ollamaBadge.createSpan({ text: "Checking…" });
        try {
          const host = (this.plugin.settings.ollamaHost || "http://localhost:11434").replace(/\/$/, "");
          const res = await fetch(`${host}/api/tags`);
          if (res.ok) {
            const data = await res.json() as { models?: Array<{ name: string }> };
            const count = data.models?.length ?? 0;
            ollamaBadge.empty();
            ollamaBadge.createSpan({ cls: "ai-agent-auth-ok", text: `✓ Running — ${count} model${count !== 1 ? "s" : ""} installed` });
          } else {
            throw new Error(`HTTP ${res.status}`);
          }
        } catch {
          ollamaBadge.empty();
          ollamaBadge.createSpan({ cls: "ai-agent-auth-fail", text: "✗ Not reachable — run: ollama serve" });
        }
      };
      ollamaRow.addButton((btn) => btn.setButtonText("Check").onClick(checkOllama));
      checkOllama();
    } else if (currentProvider === "deepseek") {
      const authRow = new Setting(providerSection).setName("Authentication");
      const authBadge = authRow.settingEl.createSpan("ai-agent-auth-inline-badge");
      authRow.addButton((button) =>
        button.setButtonText("Check API key").onClick(() => {
          this.plugin.authResolver.invalidate("deepseek");
          this.renderAuthStatusInline(authBadge, button.buttonEl);
        })
      );
      this.renderAuthStatusInline(authBadge);
    } else {
      const authRow = new Setting(providerSection).setName("Authentication");
      const authBadge = authRow.settingEl.createSpan("ai-agent-auth-inline-badge");

      let loginBtn: HTMLButtonElement;
      let authPollTimer: ReturnType<typeof setInterval> | null = null;

      const stopAuthPoll = () => {
        if (authPollTimer !== null) { clearInterval(authPollTimer); authPollTimer = null; }
      };

      authRow.addButton((button) => {
        loginBtn = button.buttonEl;
        button.setButtonText("Login").setCta().onClick(() => {
          stopAuthPoll();
          try {
            this.plugin.authResolver.startLogin(this.plugin.settings.provider);
          } catch (err: unknown) {
            const message = err instanceof Error ? err.message : String(err);
            authBadge.empty();
            authBadge.createSpan({ cls: "ai-agent-auth-fail", text: `✗ ${message}` });
            return;
          }
          authBadge.empty();
          authBadge.createSpan({ text: "⏳ Waiting for login..." });
          let tries = 0;
          authPollTimer = setInterval(() => {
            tries++;
            this.plugin.authResolver.invalidate(this.plugin.settings.provider);
            this.renderAuthStatusInline(authBadge, loginBtn).then((ok) => {
              if (ok || tries >= 22) stopAuthPoll();
            });
          }, 4000);
        });
      });

      this.renderAuthStatusInline(authBadge, loginBtn!);
    }

    new Setting(providerSection)
      .setName("Streaming responses")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.streamingEnabled)
          .onChange(async (value) => {
            this.plugin.settings.streamingEnabled = value;
            await this.plugin.saveSettings();
          })
      );

    new Setting(providerSection)
      .setName("Diff mode")
      .setDesc("How inline edits are displayed.")
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

    // ═══════════════════════════════════════════════════════════════
    // 2. PDF Viewer
    // ═══════════════════════════════════════════════════════════════
    const pdfSection = containerEl.createDiv("ai-agent-settings-section");
    this.renderSectionHeader(pdfSection, "PDF Viewer", "file-text");

    new Setting(pdfSection)
      .setName("Capture mode")
      .setDesc("Text only: fast. Image only: for scanned PDFs (vision model required). Text + Image: most accurate.")
      .addDropdown((dropdown) =>
        dropdown
          .addOption("text", "Text only")
          .addOption("image", "Image only (Vision)")
          .addOption("both", "Text + Image")
          .setValue(this.plugin.settings.pdfCaptureMode)
          .onChange(async (value: string) => {
            this.plugin.settings.pdfCaptureMode = value as "text" | "image" | "both";
            await this.plugin.saveSettings();
          })
      );

    new Setting(pdfSection)
      .setName("Auto-search PDF for relevant pages")
      .setDesc("Before each question, search the whole PDF for pages most relevant to your query.")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.pdfRagEnabled)
          .onChange(async (value) => {
            this.plugin.settings.pdfRagEnabled = value;
            await this.plugin.saveSettings();
          })
      );

    // Advanced PDF settings (collapsed)
    const pdfAdvanced = pdfSection.createEl("details", { cls: "ai-agent-settings-details" });
    pdfAdvanced.createEl("summary", { text: "Advanced" });

    new Setting(pdfAdvanced)
      .setName("Page window radius")
      .setDesc("Include this many pages before/after the current page (0–5).")
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

    new Setting(pdfAdvanced)
      .setName("Include table of contents")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.pdfOutlineEnabled)
          .onChange(async (value) => {
            this.plugin.settings.pdfOutlineEnabled = value;
            await this.plugin.saveSettings();
          })
      );

    new Setting(pdfAdvanced)
      .setName("RAG top K")
      .setDesc("Max page chunks to include from auto-search.")
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

    new Setting(pdfAdvanced)
      .setName("Vision fallback for scanned PDFs")
      .setDesc("Auto-attach page image when no text is extractable.")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.pdfVisionFallback)
          .onChange(async (value) => {
            this.plugin.settings.pdfVisionFallback = value;
            await this.plugin.saveSettings();
          })
      );

    new Setting(pdfAdvanced)
      .setName("Background page indexing")
      .setDesc("Index all pages of open PDFs in the background for faster search.")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.pdfFullDocumentIndex)
          .onChange(async (value) => {
            this.plugin.settings.pdfFullDocumentIndex = value;
            await this.plugin.saveSettings();
          })
      );

    // ═══════════════════════════════════════════════════════════════
    // 3. Incurator Backend
    // ═══════════════════════════════════════════════════════════════
    const backendSection = containerEl.createDiv("ai-agent-settings-section");
    this.renderSectionHeader(backendSection, "Incurator Backend", "cpu");

    const incuratorSetting = new Setting(backendSection)
      .setName("Enable")
      .setDesc("Connect to the Incurator MCP backend for source tracking, ingest, and vault search.")
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

    new Setting(backendSection)
      .setName("Default import mode")
      .setDesc("How non-Zotero PDFs are ingested. Zotero PDFs always use Reference.")
      .addDropdown((dropdown) =>
        dropdown
          .addOption("copy", "Copy into vault")
          .addOption("reference", "Reference in place")
          .setValue(this.plugin.settings.incuratorDefaultImportMode)
          .onChange(async (value) => {
            this.plugin.settings.incuratorDefaultImportMode =
              value === "copy" ? "copy" : "reference";
            await this.plugin.saveSettings();
          })
      );

    new Setting(backendSection)
      .setName("Copy destination folder")
      .setDesc("Vault folder for imported PDFs (Copy mode).")
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

    new Setting(backendSection)
      .setName("Auto-poll ingest status")
      .setDesc("Refresh status badges while ingest jobs are running.")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.incuratorStatusPolling)
          .onChange(async (value) => {
            this.plugin.settings.incuratorStatusPolling = value;
            await this.plugin.saveSettings();
          })
      );

    // Advanced Incurator settings (collapsed)
    const incuratorAdvanced = backendSection.createEl("details", {
      cls: "ai-agent-settings-details",
    });
    incuratorAdvanced.createEl("summary", { text: "Advanced" });

    new Setting(incuratorAdvanced)
      .setName("Backend command")
      .setDesc("Leave as 'wiki' for auto-discovery. Set an absolute path to override.")
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

    new Setting(incuratorAdvanced)
      .setName("Backend arguments")
      .setDesc("Space-separated or JSON array.")
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

    new Setting(incuratorAdvanced)
      .setName("Repository path")
      .setDesc("Absolute path to the Incurator repo (for 1-click updates).")
      .addText((text) =>
        text
          .setPlaceholder("/path/to/Incurator")
          .setValue(this.plugin.settings.incuratorRepoPath)
          .onChange(async (value) => {
            this.plugin.settings.incuratorRepoPath = value.trim();
            await this.plugin.saveSettings();
          })
      );

    // ═══════════════════════════════════════════════════════════════
    // 4. Zotero Integration
    // ═══════════════════════════════════════════════════════════════
    const zoteroSection = containerEl.createDiv("ai-agent-settings-section");
    this.renderSectionHeader(zoteroSection, "Zotero Integration", "book-open");

    new Setting(zoteroSection)
      .setName("Zotero Data Directory (External Linking)")
      .setDesc(
        "Path to the folder containing zotero.sqlite. " +
          "Zotero PDFs will use this path to create external links (instead of copying) when ingested."
      )
      .addText((text) =>
        text
          .setPlaceholder("~/Zotero")
          .setValue(this.plugin.settings.zoteroBasePath)
          .onChange(async (value) => {
            this.plugin.settings.zoteroBasePath = value.trim();
            await this.plugin.saveSettings();
          })
      );

    // Zotero Import Profiles
    const profiles = this.plugin.settings.zoteroProfiles || [];
    if (profiles.length > 0) {
      const profilesDetails = zoteroSection.createEl("details", {
        cls: "ai-agent-settings-details",
      });
      profilesDetails.createEl("summary", {
        text: `Import Profiles (${profiles.length})`,
      });
      profilesDetails.createEl("p", {
        cls: "setting-item-description",
        text: "Profiles are created in the Import Zotero Item wizard. Edit or delete them here.",
      });
      for (let i = 0; i < profiles.length; i++) {
        this.renderZoteroProfile(profilesDetails, i);
      }
    }

    // ═══════════════════════════════════════════════════════════════
    // 5. MCP Servers
    // ═══════════════════════════════════════════════════════════════
    const mcpSection = containerEl.createDiv("ai-agent-settings-section");
    this.renderSectionHeader(mcpSection, "MCP Servers", "plug");

    const userMcpServers = this.plugin.settings.mcpServers
      .map((s, i) => ({ server: s, index: i }))
      .filter(({ server }) => !isIncuratorMcpServer(server));

    if (userMcpServers.length === 0) {
      mcpSection.createEl("p", {
        cls: "setting-item-description",
        text: "No custom MCP servers configured.",
        attr: { style: "color: var(--text-muted); font-style: italic;" },
      });
    } else {
      for (const { index } of userMcpServers) {
        this.renderMCPServer(mcpSection, index);
      }
    }

    new Setting(mcpSection).addButton((button) =>
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

  // ── Helpers ────────────────────────────────────────────────────

  private renderSectionHeader(
    containerEl: HTMLElement,
    title: string,
    _icon?: string,
  ): void {
    containerEl.createEl("h2", {
      text: title,
      cls: "ai-agent-settings-section-header",
    });
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

  private async renderAuthStatusInline(container: HTMLElement, loginBtn?: HTMLButtonElement): Promise<boolean> {
    const provider = this.plugin.settings.provider;
    if (provider === "deepseek") {
      container.empty();
      if (this.plugin.settings.deepseekApiKey || process.env.DEEPSEEK_API_KEY) {
        container.createSpan({ cls: "ai-agent-auth-ok", text: "✓ API key configured" });
        if (loginBtn) {
          loginBtn.textContent = "Check API key";
          loginBtn.classList.remove("mod-cta");
        }
        return true;
      }
      container.createSpan({ cls: "ai-agent-auth-fail", text: "✗ Set DeepSeek API key or DEEPSEEK_API_KEY" });
      if (loginBtn) {
        loginBtn.textContent = "Check API key";
        loginBtn.classList.add("mod-cta");
      }
      return false;
    }
    try {
      const token = await this.plugin.authResolver.resolveToken(provider);
      if (token) {
        container.empty();
        container.createSpan({ cls: "ai-agent-auth-ok", text: "✓ Authenticated" });
        if (loginBtn) {
          loginBtn.textContent = "Re-authenticate";
          loginBtn.classList.remove("mod-cta");
        }
        return true;
      }
    } catch (e: unknown) {
      container.empty();
      const message = e instanceof Error ? e.message : String(e);
      container.createSpan({ cls: "ai-agent-auth-fail", text: `✗ ${message}` });
      if (loginBtn) {
        loginBtn.textContent = "Login";
        loginBtn.classList.add("mod-cta");
      }
    }
    return false;
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
      case "ollama":
        return "Ollama";
      case "deepseek":
        return "DeepSeek";
    }
  }
}
