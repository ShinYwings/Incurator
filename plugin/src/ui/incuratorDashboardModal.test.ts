import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { join } from "path";
import { describe, expect, it } from "vitest";

describe("Incurator dashboard backend boundary", () => {
  it("does not use the MCP IncuratorClient to render backend version", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");

    expect(source).toContain("backend_version");
    expect(source).toContain("runWikiCommand([\"version\"])");
    expect(source).not.toContain("checkBackendVersion");
    expect(source).not.toContain("incuratorClient.backendVersion");
  });

  it("queues build from the dashboard instead of running a blocking wait build", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");

    expect(source).toContain("runWikiCommand([\"build\"])");
    expect(source).not.toContain("runWikiCommand([\"build\", \"--wait\"])");
  });

  it("exposes a Jobs action to drain queued build work explicitly", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");

    expect(source).toContain("Run queued");
    expect(source).toContain("runWikiCommand([\"jobs\", \"run\"])");
  });

  it("exposes job cancel and rerun actions in the Jobs tab", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");

    expect(source).toContain("Cancel");
    expect(source).toContain("Rerun");
    expect(source).toContain("runWikiCommand([\"jobs\", \"cancel\"");
    expect(source).toContain("runWikiCommand([\"jobs\", \"rerun\"");
  });

  it("does not hide Syncthing-only remote devices in the dashboard", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");

    expect(source).not.toContain("!d.platform && !d.backend");
    expect(source).toContain("no synced folder");
  });

  it("shows Syncthing devices in Overview without a standalone Devices tab", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");

    expect(source).toContain("Syncthing Devices");
    expect(source).toContain("const devices = st?.devices");
    expect(source).toContain("folderLabels.join");
    expect(source).toContain("(This device)");
    expect(source).toContain("Current device on this machine");
    expect(source).not.toContain('filter(([id]: [string, any]) => id !== "local")');
    expect(source).not.toContain('folder.role === "vault" ? "Vault"');
    expect(source).not.toContain("label: \"Devices\"");
    expect(source).not.toContain("case \"devices\"");
    expect(source).not.toContain("pathRow(\"Device\")");
  });

  it("exposes a Synthesis tab backed by plugin synthesis commands", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");

    expect(source).toContain('id: "synthesis"');
    expect(source).toContain("renderSynthesis");
    expect(source).toContain("[\"plugin\", \"synthesis\", \"list\"");
    expect(source).toContain("[\"plugin\", \"synthesis\", \"show\"");
  });

  it("saves LLM primary and fallback to machine-local config scope", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");

    expect(source).toContain('["config", "set", "llm.fallback"');
    expect(source).toContain('["config", "set", "llm.fallback_effort"');
    expect(source).not.toContain('["config", "set", "--local", "llm.fallback"');
    // Do not apply with an unloaded catalogue (empty provider).
    expect(source).toContain("Models are still loading");
  });

  it("refreshes local runtime snapshots before reading status or sources", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");

    expect(source).toContain("private async readFreshRuntimeJson");
    expect(source).toContain('await this.refreshRuntimeSnapshots();');
    expect(source).toContain('await this.readFreshRuntimeJson("sources")');
  });

  it("adds a one-shot Update action and demotes granular steps to Advanced (item 13)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");

    expect(source).toContain('this.addActionBtn(acts, "Update"');
    expect(source).toContain('this.runWikiCommand(["update"])');
    expect(source).toContain('createEl("details", { cls: "ai-agent-ov-advanced" })');
    // Granular steps moved under the Advanced disclosure (adv), not top-level acts.
    expect(source).toContain('this.addActionBtn(adv, "Build"');
    expect(source).toContain('this.addActionBtn(adv, "Reset"');
  });

  it("recommends Ollama models with install/RAM status and a Pull action (item 13)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");

    expect(source).toContain("renderOllamaRecommendations");
    expect(source).toContain('["plugin", "models", "ollama", "--json"]');
    expect(source).toContain('["plugin", "models", "pull", "--model", m.id, "--json"]');
    expect(source).toContain("exceeds RAM");
    expect(source).toContain('text: "installed"');
  });

  it("offers a one-click resume for errored sources on the Sources tab (item 21)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");

    // The Sources tab detects errored sources and surfaces a retry button that
    // re-runs the build (which re-attempts pending/error L2/L3 layers).
    expect(source).toContain("ai-agent-dashboard-retry-banner");
    expect(source).toContain("Retry errored sources");
    expect(source).toContain('s.status === "error"');
    expect(source).toContain('"l1_status", "l2_status", "l3_status", "l4_status"');
    expect(source).toContain('this.runWikiCommand(["build"])');
  });

  it("reads runtime status fresh-first so backend version/provider are never stale", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");

    // readRuntimeStatus must force a fresh `wiki status` snapshot, not read the
    // cached runtime/status.json first (the stale-version / stale-provider bug).
    expect(source).toMatch(
      /readRuntimeStatus\(\)[\s\S]*?return this\.readFreshRuntimeJson\("status"\)/
    );
    expect(source).not.toMatch(
      /readRuntimeStatus\(\)[\s\S]*?let status = await this\.readRuntimeJson\("status"\);\s*\n\s*if \(status\) return status;/
    );
  });

  it("reports the backend as unavailable instead of trusting a stale snapshot", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");

    // renderBackendVersion forces a fresh read, only trusts the snapshot when the
    // refresh succeeded, and otherwise queries the binary / shows "unavailable".
    expect(source).toContain("this._lastStatusOk = r.ok === true");
    expect(source).toMatch(
      /renderBackendVersion[\s\S]*?readFreshRuntimeJson\("status"\)/
    );
    expect(source).toMatch(/if \(this\._lastStatusOk && status\?\.backend_version\)/);
    expect(source).toContain('"backend unavailable"');
  });

  it("uses only the DB-native search status contract", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const dashboard = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");
    const main = readFileSync(join(dir, "../../main.ts"), "utf8");
    const retired = "q" + "md";

    expect(dashboard).toContain("search_ready");
    expect(dashboard).toContain("search_version");
    expect(dashboard.toLowerCase()).not.toContain(retired);
    expect(main.toLowerCase()).not.toContain(retired);
  });
});
