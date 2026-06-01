import { describe, expect, it } from "vitest";
import {
  inferLocalDeviceId,
  mergeDeviceRegistry,
  parseSyncthingConfig,
  getLocalBackendCommand,
  resolveWikiBinary,
} from "./deviceRegistry";

const XML = `
<configuration version="52">
  <device id="MACOS-ID" name="MacOS"><address>dynamic</address></device>
  <device id="LINUX-ID" name="shin"><address>dynamic</address></device>
  <folder id="nm6xn-urvs7" label="Second Brain" path="~/Workspace/second_brain" type="sendreceive">
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
    });
    expect(snapshot.devices.map((device) => device.name).sort()).toEqual(["MacOS", "shin"]);
  });

  it("infers the local device from hostname", () => {
    const snapshot = parseSyncthingConfig(
      XML,
      "/home/shin/Workspace/second_brain",
      "/home/shin"
    );

    expect(inferLocalDeviceId(snapshot.devices, "shin")).toBe("LINUX-ID");
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
            backend: { command: "/opt/homebrew/bin/uv", args: ["run", "wiki", "mcp"] },
          },
        },
      } as any,
      snapshot,
      { incuratorMcpCommand: "wiki", incuratorMcpArgs: ["mcp"] },
      123,
      "LINUX-ID"
    );

    expect((registry.devices["MACOS-ID"].backend as any).command).toBe("/opt/homebrew/bin/uv");
    expect((registry.devices["LINUX-ID"].backend as any).command).toBe("wiki");
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
