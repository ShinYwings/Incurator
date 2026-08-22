import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { join } from "path";

const mainSrc = readFileSync(join(__dirname, "../../main.ts"), "utf-8");
const settingsSrc = readFileSync(join(__dirname, "../settings.ts"), "utf-8");

describe("DeepSeek key persistence (v0.62.4)", () => {
  it("restores AFTER the backend client is constructed, not during loadSettings", () => {
    // The first version called the restore from `loadSettings`, which runs at
    // main.ts:177 while `incuratorClient` is assigned at :204. The optional
    // chain then returned undefined and NOTHING was ever restored — the fix
    // would have shipped looking exactly like the bug it was fixing.
    const clientInit = mainSrc.indexOf("this.incuratorClient = new IncuratorClient(");
    const restoreCall = mainSrc.indexOf("await this.restoreDeepseekKeyFromStore()");
    expect(clientInit).toBeGreaterThan(-1);
    expect(restoreCall).toBeGreaterThan(-1);
    expect(restoreCall).toBeGreaterThan(clientInit);
  });

  it("awaits the restore so the first request cannot race it", () => {
    // Fire-and-forget meant a query sent during startup could still report
    // "API key is not set" — the exact symptom being fixed.
    expect(mainSrc).toContain("await this.restoreDeepseekKeyFromStore()");
    expect(mainSrc).not.toContain("void this.restoreDeepseekKeyFromStore()");
  });

  it("lets an explicitly exported env var win over the store", () => {
    const body = mainSrc.slice(mainSrc.indexOf("async restoreDeepseekKeyFromStore"));
    expect(body.slice(0, 400)).toContain("if (this.settings.deepseekApiKey) return;");
  });

  it("persists on blur, not on every keystroke", () => {
    // Obsidian fires onChange per character, so writing there spawned one
    // backend process per keystroke and stored a truncated key each time — and
    // an earlier partial could land after the complete one.
    const onChange = settingsSrc.slice(
      settingsSrc.indexOf('.setPlaceholder("sk-...")'),
      settingsSrc.indexOf('.setPlaceholder("sk-...")') + 1400
    );
    expect(onChange).toContain('addEventListener("blur"');
    const changeHandler = onChange.slice(
      onChange.indexOf(".onChange("),
      onChange.indexOf('addEventListener("blur"')
    );
    expect(changeHandler).not.toContain("setSecret");
  });
});
