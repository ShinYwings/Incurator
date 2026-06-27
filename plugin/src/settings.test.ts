import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { join } from "path";
import { describe, expect, it } from "vitest";
import { DEFAULT_SETTINGS } from "./types";

function settingsSource(): string {
  const dir = fileURLToPath(new URL(".", import.meta.url));
  return readFileSync(join(dir, "settings.ts"), "utf8");
}

describe("settings UI source contract", () => {
  it("keeps backend Zotero setup as the single data-directory entry point", () => {
    const source = settingsSource();

    expect(source).toContain("Backend Zotero status");
    expect(source).toContain("Defaults to ~/Zotero");
    expect(source).not.toContain('.setName("Zotero data directory")');
  });

  it("keeps model context window information on the Model row", () => {
    const source = settingsSource();

    expect(source).toContain("Context window:");
    expect(source).not.toContain('.setName("Context window")');
  });

  it("renders Incurator backend status below the Enable row", () => {
    const source = settingsSource();

    expect(source).toContain('backendSection.createDiv("ai-agent-incurator-status ai-agent-incurator-status-below")');
    expect(source).not.toContain("backendEnableSetting.settingEl.createDiv");
    expect(source).not.toContain("ai-agent-incurator-status-inline");
    expect(source).not.toContain("Status: ${status.label}");
  });

  it("no longer exposes the removed on-disk diff-artifact toggle", () => {
    const source = settingsSource();

    expect(source).not.toContain("Write edits as diff artifact");
    expect(source).not.toContain("editArtifactEnabled");
    expect(DEFAULT_SETTINGS).not.toHaveProperty("editArtifactEnabled");
  });

  it("no longer exposes the v0.21.0 latexModel setting (moved to Dashboard, v0.22.0)", () => {
    const source = settingsSource();

    expect(source).not.toContain("Convert-to-LaTeX model (fast/light)");
    expect(source).not.toContain("this.plugin.settings.latexModel");
    expect(DEFAULT_SETTINGS).not.toHaveProperty("latexModel");
  });

  it("clears auth polling when the settings tab closes or re-renders (G17-1)", () => {
    const source = settingsSource();

    expect(source).toContain("private authPollTimer");
    expect(source).toContain("hide(): void");
    expect(source).toContain("this.stopAuthPoll();");
    expect(source).toContain("this.authPollTimer = setInterval");
    expect(source).not.toContain("let authPollTimer");
  });

  it("does not keep the dead settings-tab login helper layer (G17-2)", () => {
    const source = settingsSource();

    expect(source).not.toContain("private startProviderLogin(");
    expect(source).not.toContain("private providerLabel(");
  });
});
