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

  it("settings data.json writes go through a single serialized writer (G17-11)", () => {
    const src = mainSource();

    expect(src).not.toContain("saveData(this.settings)");
    expect(src).toContain("private settingsPersistPromise");
    expect(src).toContain("private persistSettings(): Promise<void>");
    expect(src).toContain("this.settingsPersistPromise = this.settingsPersistPromise");
    expect(src.match(/saveData\(this\._persistableSettings\(\)\)/g) || []).toHaveLength(1);
  });

  it("loadSettings restores deepseekApiKey from env DEEPSEEK_API_KEY", () => {
    const src = mainSource();
    expect(src).toContain("DEEPSEEK_API_KEY");
    expect(src).toContain("settings.deepseekApiKey = envKey");
  });
});

describe("G17-5: Check DeepSeek API Key command must check credentials", () => {
  it("routes the command through a DeepSeek key check instead of login help", () => {
    const src = mainSource();

    expect(src).toContain('id: "login-deepseek"');
    expect(src).toContain("this.checkDeepSeekApiKey();");
    expect(src).toContain("private async checkDeepSeekApiKey()");
    expect(src).toContain("this.settings.deepseekApiKey?.trim()");
    expect(src).toContain('this.authResolver.resolveToken("deepseek")');
    expect(src).not.toContain('this.startProviderLogin("deepseek")');
  });
});

describe("G17-9: global external-link patch teardown must preserve later patches", () => {
  it("restores window.open and shell.openExternal only when this plugin still owns the patch", () => {
    const src = mainSource();

    expect(src).toContain("const patchedWindowOpen");
    expect(src).toContain("if (window.open === patchedWindowOpen)");
    expect(src).toContain("if (mod.shell.openExternal === patched)");
  });
});

describe("G17-6: Zotero refresh must use the note's stamped import profile", () => {
  it("selects the refresh profile from frontmatter instead of always profiles[0]", () => {
    const src = mainSource();

    expect(src).toContain("resolveZoteroRefreshProfile(profiles, cache.frontmatter)");
    expect(src).not.toContain("const p = profiles[0]; // use first profile as default");
  });
});

describe("G17-4: model default migration must be catalogue-based", () => {
  it("does not keep an unbounded stale model denylist", () => {
    const src = mainSource();

    expect(src).toContain("private migrateUnavailableModelDefaults()");
    expect(src).toContain("const knownModel = getModelOption(");
    expect(src).toContain("if (this.settings.model && knownModel) return false;");
    expect(src).not.toContain("unavailableDefaults");
    expect(src).not.toContain("claude-opus-4-7");
  });

  it("never resets a non-empty custom model for providers with open-ended ids (Ollama)", () => {
    const src = mainSource();

    expect(src).toContain(
      'if (this.settings.model && this.settings.provider === "ollama") return false;'
    );
  });
});

describe("G17-7: Zotero reload must not rewrite a note from empty metadata", () => {
  it("guards the resolved item metadata before re-rendering the note", () => {
    const src = mainSource();

    expect(src).toContain("const metadata = await this.getZoteroItemMetadata(itemKey);");
    // An empty-object metadata result (citekey passed as item key, or item not
    // found) must abort before renderTemplate/modify.
    expect(src).toContain("Object.keys(metadata as Record<string, unknown>).length === 0");
    // …and an unresolved (empty) item key must short-circuit before the backend
    // round-trip entirely.
    expect(src).toContain("This note has no resolvable Zotero item key");
    expect(
      src.indexOf("if (!itemKey) {") < src.indexOf("await this.getZoteroItemMetadata(itemKey)")
    ).toBe(true);
  });
});

describe("G17-12: deprecated imageFolder is migrated out of stored profiles", () => {
  it("loadSettings runs the one-time asset-folder migration and persists changes", () => {
    const src = mainSource();

    expect(src).toContain("migrateZoteroProfileAssetFolders(this.settings.zoteroProfiles)");
  });
});

describe("G17-8: device registry writes use one async helper", () => {
  it("does not inline sync mkdir/write sequences in each devices.json writer", () => {
    const src = mainSource();

    expect(src).toContain('import { dirname, join } from "path";');
    expect(src).toContain("private async writeDeviceRegistry(");
    expect(src).toContain("await fs.mkdir(dirname(configPath), { recursive: true });");
    expect(src).not.toContain('const path = require("path");');
    expect(src).not.toContain("fsSync.existsSync(dir)");
  });
});
