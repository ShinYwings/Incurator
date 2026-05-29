import type { MCPServerConfig } from "../types";

export const INCURATOR_MCP_SERVER_NAME = "incurator";

export function createIncuratorMcpServer(
  vaultRoot: string,
  command = "wiki",
  args: string[] = ["mcp"]
): MCPServerConfig {
  return {
    name: INCURATOR_MCP_SERVER_NAME,
    command,
    args,
    env: vaultRoot ? { VAULT_ROOT: vaultRoot } : undefined,
    enabled: true,
  };
}

export function isIncuratorMcpServer(server: MCPServerConfig): boolean {
  const name = server.name.toLowerCase();
  const command = server.command.toLowerCase();
  const args = server.args.join(" ").toLowerCase();
  return (
    name.includes("incurator") ||
    name.includes("curator") ||
    (command === "wiki" && args.includes("mcp"))
  );
}

export function ensureIncuratorMcpServer(
  servers: MCPServerConfig[],
  vaultRoot: string,
  command = "wiki",
  args: string[] = ["mcp"]
): { servers: MCPServerConfig[]; server: MCPServerConfig; changed: boolean } {
  // The canonical stored shape has no VAULT_ROOT; it is injected at runtime per device.
  const storedConfig: Omit<MCPServerConfig, "env"> = {
    name: INCURATOR_MCP_SERVER_NAME,
    command: command || "wiki",
    args: args.length ? args : ["mcp"],
    enabled: true,
  };

  // Runtime config: VAULT_ROOT injected fresh, never persisted
  const runtimeConfig: MCPServerConfig = {
    ...storedConfig,
    env: vaultRoot ? { VAULT_ROOT: vaultRoot } : undefined,
  };

  const index = servers.findIndex(isIncuratorMcpServer);
  if (index === -1) {
    return { servers: [...servers, { ...storedConfig }], server: runtimeConfig, changed: true };
  }

  const current = servers[index];
  // Strip any stale VAULT_ROOT from the stored entry
  const { env: _env, ...currentWithoutEnv } = current;
  const needsUpdate =
    currentWithoutEnv.name !== storedConfig.name ||
    currentWithoutEnv.command !== storedConfig.command ||
    JSON.stringify(currentWithoutEnv.args) !== JSON.stringify(storedConfig.args) ||
    currentWithoutEnv.enabled !== storedConfig.enabled ||
    _env?.VAULT_ROOT !== undefined; // stored entry still has VAULT_ROOT → clean it up

  if (needsUpdate) {
    const updated = [...servers];
    updated[index] = { ...storedConfig };
    return { servers: updated, server: runtimeConfig, changed: true };
  }

  return { servers, server: runtimeConfig, changed: false };
}
