import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { join } from "path";

import type { ZoteroImportProfile } from "./types";

/**
 * v0.42.1 regression: editing a Zotero import profile in Settings silently lost
 * everything after the first keystroke.
 *
 * Reported symptom: changing the template path from
 * `.../book_template.md` to `.../paper_template.md` saved
 * `.../boo_template.md` — the value after exactly ONE backspace.
 *
 * Cause: `saveSettings()` → `saveZoteroProfiles()` ends with
 * `this.settings.zoteroProfiles = store.profiles`, replacing the array AND its
 * objects with ones re-read from the merged on-disk store. The settings UI
 * captured `const profile = settings.zoteroProfiles[index]` once at render time,
 * so the first keystroke's save detached that reference and every later
 * keystroke mutated an orphan nothing persists.
 */

const settingsSource = () => readFileSync(join(__dirname, "settings.ts"), "utf8");

/** Minimal stand-in for the plugin's settings object + the store swap. */
function makeHost(initial: ZoteroImportProfile) {
  const host = {
    settings: { zoteroProfiles: [{ ...initial }] as ZoteroImportProfile[] },
    saveCount: 0,
    async saveSettings() {
      this.saveCount++;
      // The real saveZoteroProfiles snapshots, persists, then REPLACES the array
      // with freshly-parsed objects. Identity churn is the whole bug.
      const snapshot = this.settings.zoteroProfiles.map((p) => ({ ...p }));
      this.settings.zoteroProfiles = snapshot;
    },
  };
  return host;
}

const baseProfile: ZoteroImportProfile = {
  name: "Books",
  templatePath: "00_System/Templates/Zotero/book_template.md",
  outputFolder: "03_Notes/Papers",
  outputSubfolder: "",
  outputFilename: "{{title}}",
  assetFolder: "",
  assetSubfolder: "",
  bibliographyStyle: "",
};

describe("Zotero profile editing survives the store swap", () => {
  it("loses later keystrokes when the profile reference is captured once (the old bug)", async () => {
    const host = makeHost(baseProfile);
    const captured = host.settings.zoteroProfiles[0]; // render-time capture

    // Obsidian's onChange delivers the FULL field value per keystroke.
    for (const value of [
      "00_System/Templates/Zotero/boo_template.md",
      "00_System/Templates/Zotero/paper_template.md",
    ]) {
      captured.templatePath = value;
      await host.saveSettings();
    }

    // Reproduces the report: the persisted value froze at the first edit.
    expect(host.settings.zoteroProfiles[0].templatePath).toBe(
      "00_System/Templates/Zotero/boo_template.md"
    );
  });

  it("persists the final value when each write resolves the live profile", async () => {
    const host = makeHost(baseProfile);
    const liveProfile = () => host.settings.zoteroProfiles[0];

    for (const value of [
      "00_System/Templates/Zotero/boo_template.md",
      "00_System/Templates/Zotero/paper_template.md",
    ]) {
      const target = liveProfile();
      target.templatePath = value;
      await host.saveSettings();
    }

    expect(host.settings.zoteroProfiles[0].templatePath).toBe(
      "00_System/Templates/Zotero/paper_template.md"
    );
  });

  it("keeps unrelated fields intact across the swap", async () => {
    const host = makeHost(baseProfile);
    const target = host.settings.zoteroProfiles[0];
    target.templatePath = "00_System/Templates/Zotero/paper_template.md";
    await host.saveSettings();

    const saved = host.settings.zoteroProfiles[0];
    expect(saved.name).toBe("Books");
    expect(saved.outputFolder).toBe("03_Notes/Papers");
    expect(saved.outputFilename).toBe("{{title}}");
  });
});

describe("settings.ts profile editor wiring", () => {
  it("resolves the live profile per write instead of a captured reference", () => {
    const src = settingsSource();
    expect(src).toContain("const liveProfile = ()");
    expect(src).toContain("const target = liveProfile();");
  });

  it("commits on blur, since the editor has no Save button", () => {
    const src = settingsSource();
    expect(src).toContain('text.inputEl.addEventListener("blur"');
    expect(src).toContain("void commit(text.inputEl.value)");
  });

  it("no longer mutates a render-time captured profile in the setters", () => {
    const src = settingsSource();
    // The old shape wrote straight to the captured `profile` object.
    expect(src).not.toContain("v => profile.templatePath = v");
    expect(src).not.toContain("v => profile.outputFolder = v");
    expect(src).not.toContain("v => profile.assetFolder = v");
  });
});
