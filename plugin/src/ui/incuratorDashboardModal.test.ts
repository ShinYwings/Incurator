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

  it("clears the Jobs poller on close and before replacing it", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");

    expect(source).toMatch(
      /onClose\(\)[\s\S]*?if \(this\.jobsTimer\) \{[\s\S]*?window\.clearInterval\(this\.jobsTimer\);[\s\S]*?this\.jobsTimer = null;[\s\S]*?\}/
    );
    expect(source).toContain('if (id !== "jobs" && this.jobsTimer)');
    expect(source).toContain('if (this.jobsTimer) { window.clearInterval(this.jobsTimer); this.jobsTimer = null; }');
    expect(source).not.toContain("if (this.jobsTimer !== null)");
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

  it("exposes two vision-extraction model rows persisted via wiki config (v0.22.0)", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");

    // Two rows read the backend vision slots and persist via wiki config set.
    expect(source).toContain('["config", "set", "llm.vision_model"');
    expect(source).toContain('["config", "set", "llm.latex_extract_model"');
    expect(source).toContain("llm.vision_model as string");
    expect(source).toContain("llm.latex_extract_model as string");
    // Vision-only dropdown + effective-fallback hint for the light row.
    expect(source).toContain("m.supportsVision");
    expect(source).toContain("↳ using");
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

  it("shows skipped layer statuses explicitly in the Sources tab", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");

    expect(source).toContain('if (s === "skipped") return { str: "Skipped", cls: "badge-ready" };');
  });

  it("reads runtime status live via `wiki status --json`, never from a stale snapshot file", () => {
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "incuratorDashboardModal.ts"), "utf8");

    // The dashboard reads ALL backend info live from `wiki status --json` (status
    // + sources + jobs), so a backend change that forgets to regenerate the
    // on-disk snapshot can never surface stale data here. The snapshot FILE is no
    // longer the dashboard's source of truth — only the chat status bar uses it.
    expect(source).toMatch(
      /fetchLiveStatus[\s\S]*?runWikiCommand\(\["status", "--json"\]\)/
    );
    expect(source).toMatch(/readRuntimeStatus\(\)[\s\S]*?fetchLiveStatus\(\)/);
    expect(source).toMatch(/readRuntimeJson[\s\S]*?fetchLiveStatus\(\)/);
    // The dashboard must NOT read the on-disk runtime/*.json snapshot directly.
    expect(source).not.toMatch(/adapter\.read\(`\.curator\/runtime\//);
    // One render = one CLI call: the parsed payload is cached and invalidated on
    // tab switch / forced-refreshed after mutations.
    expect(source).toContain("this._liveStatus = null");
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
