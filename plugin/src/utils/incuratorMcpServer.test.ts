import { describe, expect, it } from "vitest";
import {
  createIncuratorMcpServer,
  ensureIncuratorMcpServer,
  isIncuratorMcpServer,
} from "./incuratorMcpServer";

describe("incuratorMcpServer", () => {
  it("creates the default wiki mcp server for a vault", () => {
    expect(createIncuratorMcpServer("/vault")).toEqual({
      name: "incurator",
      command: "wiki",
      args: ["mcp"],
      env: { VAULT_ROOT: "/vault" },
      enabled: true,
    });
  });

  it("recognizes the default incurator server", () => {
    expect(isIncuratorMcpServer(createIncuratorMcpServer("/vault"))).toBe(true);
  });

  it("adds an incurator server when missing", () => {
    const result = ensureIncuratorMcpServer([], "/vault");

    expect(result.changed).toBe(true);
    expect(result.servers).toHaveLength(1);
    expect(result.server.env?.VAULT_ROOT).toBe("/vault");
  });

  it("enables and fills a disabled incurator server", () => {
    const result = ensureIncuratorMcpServer(
      [{ name: "incurator", command: "wiki", args: ["mcp"], enabled: false }],
      "/vault"
    );

    expect(result.changed).toBe(true);
    expect(result.server.enabled).toBe(true);
    expect(result.server.env?.VAULT_ROOT).toBe("/vault");
  });

  it("uses a per-device backend command when configured", () => {
    const result = ensureIncuratorMcpServer(
      [],
      "/vault",
      "/opt/homebrew/bin/uv",
      ["--directory", "/Users/me/Incurator/backend", "run", "wiki", "mcp"]
    );

    expect(result.servers[0]).toEqual({
      name: "incurator",
      command: "/opt/homebrew/bin/uv",
      args: ["--directory", "/Users/me/Incurator/backend", "run", "wiki", "mcp"],
      enabled: true,
    });
    expect(result.server.env?.VAULT_ROOT).toBe("/vault");
  });
});
