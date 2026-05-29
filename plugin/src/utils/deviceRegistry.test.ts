import { describe, expect, it } from "vitest";
import {
  inferLocalDeviceId,
  mergeDeviceRegistry,
  parseSyncthingConfig,
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
