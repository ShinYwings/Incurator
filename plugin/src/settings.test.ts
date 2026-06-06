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

  it("exposes the diff-artifact toggle, defaulting it on (item 20)", () => {
    const source = settingsSource();

    expect(source).toContain('.setName("Write edits as diff artifact")');
    expect(source).toContain("this.plugin.settings.editArtifactEnabled = value");
    expect(DEFAULT_SETTINGS.editArtifactEnabled).toBe(true);
  });
});
