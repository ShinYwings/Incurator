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
    expect(source).toContain("folder.label || folder.id || folder.role");
    expect(source).toContain("(This device)");
    expect(source).toContain("Current device on this machine");
    expect(source).toContain("!localId && (d?.platform || d?.backend)");
    expect(source).toContain("let devices = Object.entries(reg.devices)");
    expect(source).not.toContain('filter(([id]: [string, any]) => id !== "local")');
    expect(source).not.toContain('folder.role === "vault" ? "Vault"');
    expect(source).not.toContain("label: \"Devices\"");
    expect(source).not.toContain("case \"devices\"");
    expect(source).not.toContain("pathRow(\"Device\")");
  });
});
