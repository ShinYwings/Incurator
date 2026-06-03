import { describe, expect, it } from "vitest";
import { getIncuratorBackendStatus } from "./incuratorBackendStatus";

describe("getIncuratorBackendStatus", () => {
  it("reports disabled when the backend toggle is off", () => {
    const status = getIncuratorBackendStatus({ enabled: false });
    expect(status.state).toBe("disabled");
    expect(status.detail).toContain("turned off");
  });

  it("reports configured local backend command when enabled", () => {
    const status = getIncuratorBackendStatus({
      enabled: true,
      command: "wiki",
      commandArgs: [],
    });

    expect(status.state).toBe("configured");
    expect(status.detail).toBe("Backend command: wiki");
  });

  it("shows optional launcher prefix args", () => {
    const status = getIncuratorBackendStatus({
      enabled: true,
      command: "/opt/homebrew/bin/uv",
      commandArgs: ["--directory", "/repo/backend", "run", "wiki"],
    });

    expect(status.detail).toContain("/opt/homebrew/bin/uv --directory /repo/backend run wiki");
  });
});
