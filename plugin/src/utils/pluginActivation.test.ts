import { describe, expect, it } from "vitest";
import { assessPluginActivation } from "./pluginActivation";

describe("plugin activation guard", () => {
  it("allows provider launch when the running and installed versions match", () => {
    expect(
      assessPluginActivation("0.36.7", '{"id":"incurator-obsidian-agent","version":"0.36.7"}')
    ).toEqual({
      runtimeVersion: "0.36.7",
      installedVersion: "0.36.7",
      reloadRequired: false,
    });
  });

  it("blocks provider launch when disk contains a newer plugin bundle", () => {
    expect(
      assessPluginActivation("0.36.6", '{"id":"incurator-obsidian-agent","version":"0.36.7"}')
    ).toEqual({
      runtimeVersion: "0.36.6",
      installedVersion: "0.36.7",
      reloadRequired: true,
    });
  });

  it("blocks same-version replacement when the running bundle hash changed", () => {
    expect(
      assessPluginActivation(
        "0.36.7",
        '{"id":"incurator-obsidian-agent","version":"0.36.7"}',
        "running-hash",
        "installed-hash"
      )
    ).toEqual({
      runtimeVersion: "0.36.7",
      installedVersion: "0.36.7",
      runtimeBundleHash: "running-hash",
      installedBundleHash: "installed-hash",
      reloadRequired: true,
    });
  });

  it("fails closed when the installed manifest cannot be verified", () => {
    expect(() => assessPluginActivation("0.36.7", "{broken")).toThrow(
      /installed plugin manifest/i
    );
    expect(() => assessPluginActivation("0.36.7", '{"version":""}')).toThrow(
      /installed plugin version/i
    );
  });
});
