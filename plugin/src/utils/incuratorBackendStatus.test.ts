import { describe, expect, it } from "vitest";
import { getIncuratorBackendStatus } from "./incuratorBackendStatus";

describe("getIncuratorBackendStatus", () => {
  it("reports disabled when the backend toggle is off", () => {
    expect(getIncuratorBackendStatus({ enabled: false, servers: [], tools: [] }).state).toBe("disabled");
  });

  it("reports connected when incurator tools are loaded", () => {
    const status = getIncuratorBackendStatus({
      enabled: true,
      servers: [],
      tools: [{ serverName: "incurator", name: "curator_source_status", description: "", inputSchema: {} }],
    });

    expect(status.state).toBe("connected");
    expect(status.detail).toContain("1 tool available");
  });

  it("reports waiting when a likely incurator server is configured but tools are not loaded", () => {
    const status = getIncuratorBackendStatus({
      enabled: true,
      servers: [{ name: "incurator", command: "wiki", args: ["mcp"], enabled: true }],
      tools: [],
    });

    expect(status.state).toBe("connecting");
  });

  it("reports missing when no incurator server or tools are present", () => {
    const status = getIncuratorBackendStatus({
      enabled: true,
      servers: [{ name: "other", command: "node", args: ["server.js"], enabled: true }],
      tools: [],
    });

    expect(status.state).toBe("missing");
  });
});
