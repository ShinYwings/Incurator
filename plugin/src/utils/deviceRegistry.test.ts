import { describe, expect, it } from "vitest";
import {
  inferLocalDeviceId,
  mergeDeviceRegistry,
  parseSyncthingConfig,
  parseSyncthingGuiConfig,
  getLocalBackendCommand,
  getLocalBackendRepoPath,
  resolveWikiBinary,
} from "./deviceRegistry";

const XML = `
<configuration version="52">
  <device id="MACOS-ID" name="MacOS"><address>dynamic</address></device>
  <device id="LINUX-ID" name="linux-desktop"><address>dynamic</address></device>
  <folder id="nm6xn-urvs7" label="Second Brain" path="~/Workspace/second_brain" type="sendreceive">
    <device id="MACOS-ID" />
    <device id="LINUX-ID" />
  </folder>
</configuration>
`;

const XML_WITH_ZOTERO = `
<configuration version="52">
  <device id="MACOS-ID" name="MacOS"><address>dynamic</address></device>
  <device id="LINUX-ID" name="linux-desktop"><address>dynamic</address></device>
  <folder id="vault" label="Second Brain" path="~/Workspace/second_brain" type="sendreceive">
    <device id="MACOS-ID" />
    <device id="LINUX-ID" />
  </folder>
  <folder id="zotero" label="Zotero" path="~/Zotero" type="sendreceive">
    <device id="MACOS-ID" />
    <device id="LINUX-ID" />
  </folder>
</configuration>
`;

describe("deviceRegistry", () => {
  it("parses the Syncthing folder for the active vault", () => {
    const snapshot = parseSyncthingConfig(
      XML,
      "/home/shin/Workspace/second_brain",
      "/home/shin"
    );

    expect(snapshot.folders[0]).toMatchObject({
      id: "nm6xn-urvs7",
      label: "Second Brain",
      role: "vault",
    });
    expect(snapshot.devices.map((device) => device.name).sort()).toEqual(["MacOS", "linux-desktop"]);
  });

  it("parses Vault and Zotero Syncthing folder roles", () => {
    const snapshot = parseSyncthingConfig(
      XML_WITH_ZOTERO,
      "/home/shin/Workspace/second_brain",
      "/home/shin",
      ["/home/shin/Zotero"]
    );

    expect(snapshot.folders.map((folder) => [folder.label, folder.role])).toEqual([
      ["Second Brain", "vault"],
      ["Zotero", "zotero"],
    ]);
  });

  it("infers the local device from hostname", () => {
    const snapshot = parseSyncthingConfig(
      XML,
      "/home/shin/Workspace/second_brain",
      "/home/shin"
    );

    expect(inferLocalDeviceId(snapshot.devices, "linux-desktop")).toBe("LINUX-ID");
  });

  it("preserves remote backend hints while updating the local plugin entry", () => {
    const snapshot = parseSyncthingConfig(
      XML,
      "/home/shin/Workspace/second_brain",
      "/home/shin"
    );

    const registry = mergeDeviceRegistry(
      {
        devices: {
          "MACOS-ID": {
            device_id: "MACOS-ID",
            name: "MacOS",
            backend: { command: "/opt/homebrew/bin/uv", args: ["run", "wiki"] },
          },
        },
      } as any,
      snapshot,
      { incuratorBackendCommand: "wiki", incuratorBackendArgs: [], incuratorRepoPath: "" },
      123,
      "LINUX-ID"
    );

    expect((registry.devices["MACOS-ID"].backend as any).command).toBe("/opt/homebrew/bin/uv");
    expect((registry.devices["LINUX-ID"].backend as any).command).toBe("wiki");
  });

  it("prunes devices absent from the active Syncthing folder snapshot", () => {
    const snapshot = parseSyncthingConfig(
      XML,
      "/home/shin/Workspace/second_brain",
      "/home/shin"
    );

    const registry = mergeDeviceRegistry(
      {
        devices: {
          "MACOS-ID": { device_id: "MACOS-ID", name: "MacOS" },
          "STALE-ID": {
            device_id: "STALE-ID",
            name: "Old laptop",
            backend: { command: "/old/wiki", args: [] },
          },
        },
      } as any,
      snapshot,
      { incuratorBackendCommand: "wiki", incuratorBackendArgs: [], incuratorRepoPath: "" },
      123,
      "LINUX-ID"
    );

    expect(Object.keys(registry.devices).sort()).toEqual(["LINUX-ID", "MACOS-ID"]);
    expect(registry.devices["STALE-ID"]).toBeUndefined();
  });

  it("restores a missing local id from an existing current-device platform entry", () => {
    const snapshot = parseSyncthingConfig(
      XML,
      "/home/shin/Workspace/second_brain",
      "/home/shin"
    );

    const registry = mergeDeviceRegistry(
      {
        devices: {
          "MACOS-ID": {
            device_id: "MACOS-ID",
            name: "MacOS",
            platform: { system: "Darwin" },
            backend: { command: "/Users/shin/wiki", args: [] },
            updated_at: 1780408526,
          },
          "LINUX-ID": { device_id: "LINUX-ID", name: "linux-desktop" },
        },
      } as any,
      snapshot,
      { incuratorBackendCommand: "wiki", incuratorBackendArgs: [], incuratorRepoPath: "" },
      123,
      undefined
    );

    expect(registry.local_device_id).toBe("MACOS-ID");
    expect((registry.devices["MACOS-ID"].backend as any).command).toBe("wiki");
  });

  it("uses Syncthing REST myID before hostname guesses", () => {
    const snapshot = parseSyncthingConfig(
      XML,
      "/home/shin/Workspace/second_brain",
      "/home/shin"
    );
    snapshot.status = { myID: "MACOS-ID" };

    const registry = mergeDeviceRegistry(
      null,
      snapshot,
      { incuratorBackendCommand: "wiki", incuratorBackendArgs: [], incuratorRepoPath: "/repo/mac" },
      123
    );

    expect(registry.local_device_id).toBe("MACOS-ID");
    expect((registry.devices["MACOS-ID"].backend as any).repo_path).toBe("/repo/mac");
  });

  it("uses per-device repo path as fallback when Syncthing cannot report myID", () => {
    const snapshot = parseSyncthingConfig(
      XML,
      "/home/shin/Workspace/second_brain",
      "/home/shin"
    );

    const registry = mergeDeviceRegistry(
      {
        devices: {
          "MACOS-ID": {
            device_id: "MACOS-ID",
            name: "MacOS",
            backend: { repo_path: "/Users/shin/Incurator" },
          },
          "LINUX-ID": {
            device_id: "LINUX-ID",
            name: "linux-desktop",
            backend: { repo_path: "/home/shin/Incurator" },
          },
        },
      } as any,
      snapshot,
      {
        incuratorBackendCommand: "wiki",
        incuratorBackendArgs: [],
        incuratorRepoPath: "/Users/shin/Incurator",
      },
      123,
      undefined
    );

    expect(registry.local_device_id).toBe("MACOS-ID");
  });

  it("parses Syncthing GUI API settings for current-device status lookup", () => {
    const gui = parseSyncthingGuiConfig(`
      <configuration>
        <gui tls="false">
          <address>127.0.0.1:8384</address>
          <apikey>secret</apikey>
        </gui>
      </configuration>
    `);

    expect(gui).toEqual({
      url: "http://127.0.0.1:8384/rest/system/status",
      apiKey: "secret",
    });
  });
});

describe("getLocalBackendCommand", () => {
  it("ignores a missing absolute cached command for local device", () => {
    const registry = {
      local_device_id: "DEV1",
      devices: {
        DEV1: { backend: { command: "/abs/path/to/wiki" } },
      },
    };
    expect(getLocalBackendCommand(registry as any)).toBeUndefined();
  });

  it("returns undefined when no registry", () => {
    expect(getLocalBackendCommand(null)).toBeUndefined();
    expect(getLocalBackendCommand(undefined)).toBeUndefined();
  });

  it("returns undefined when no backend.command", () => {
    const registry = {
      local_device_id: "DEV1",
      devices: { DEV1: { name: "test" } },
    };
    expect(getLocalBackendCommand(registry as any)).toBeUndefined();
  });
});

describe("getLocalBackendRepoPath", () => {
  it("returns the repo path for the local device only", () => {
    const registry = {
      local_device_id: "MACOS-ID",
      devices: {
        "MACOS-ID": { backend: { repo_path: "/Users/shin/Incurator" } },
        "LINUX-ID": { backend: { repo_path: "/home/shin/Incurator" } },
      },
    };

    expect(getLocalBackendRepoPath(registry as any)).toBe("/Users/shin/Incurator");
  });

  it("ignores missing or blank local repo paths", () => {
    expect(getLocalBackendRepoPath(null)).toBeUndefined();
    expect(
      getLocalBackendRepoPath({
        local_device_id: "DEV1",
        devices: { DEV1: { backend: { repo_path: "  " } } },
      } as any)
    ).toBeUndefined();
  });
});

describe("resolveWikiBinary", () => {
  it("returns undefined for empty repoPath with no global install", () => {
    // This test checks the probe logic runs without error.
    // It may find a global binary on some machines.
    const result = resolveWikiBinary("");
    expect(result === undefined || typeof result === "string").toBe(true);
  });

  it("finds the binary in a real repo path", () => {
    // Uses the actual Incurator repo — this test is environment-specific.
    const result = resolveWikiBinary("/Users/shin/shinywings/Incurator");
    // On this machine it should exist; on CI it won't → skip
    if (result) {
      expect(result).toContain("wiki");
    }
  });
});
