import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { join } from "path";
import { describe, expect, it } from "vitest";

function mainSource(): string {
  const dir = fileURLToPath(new URL(".", import.meta.url));
  return readFileSync(join(dir, "..", "main.ts"), "utf8");
}

describe("G17-6: deepseekApiKey must never be persisted in data.json", () => {
  it("_persistableSettings strips deepseekApiKey before saveData", () => {
    const src = mainSource();
    expect(src).toContain("_persistableSettings()");
    expect(src).toContain("deepseekApiKey: _stripped");
    expect(src).toContain("deepseekApiKey: \"\"");
  });

  it("all saveData calls route through _persistableSettings (no raw saveData(this.settings))", () => {
    const src = mainSource();
    expect(src).not.toContain("saveData(this.settings)");
    const persistableCalls = (src.match(/_persistableSettings\(\)/g) || []).length;
    // At least 5 call sites: onunload, updateSettings, saveSettings, scheduleScrollPositionSave, migrateUnavailableModelDefaults, session migration
    expect(persistableCalls).toBeGreaterThanOrEqual(5);
  });

  it("loadSettings restores deepseekApiKey from env DEEPSEEK_API_KEY", () => {
    const src = mainSource();
    expect(src).toContain("DEEPSEEK_API_KEY");
    expect(src).toContain("settings.deepseekApiKey = envKey");
  });
});
