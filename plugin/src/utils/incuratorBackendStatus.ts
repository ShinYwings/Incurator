import type { MCPServerConfig, MCPTool } from "../types";

export type IncuratorBackendStatusState =
  | "disabled"
  | "connected"
  | "connecting"
  | "missing";

export interface IncuratorBackendStatus {
  state: IncuratorBackendStatusState;
  label: string;
  detail: string;
}

export function getIncuratorBackendStatus(args: {
  enabled: boolean;
  servers: MCPServerConfig[];
  tools: Array<MCPTool & { serverName: string }>;
}): IncuratorBackendStatus {
  if (!args.enabled) {
    return {
      state: "disabled",
      label: "Disabled",
      detail: "Incurator MCP tools are turned off.",
    };
  }

  const tools = args.tools.filter(isIncuratorTool);
  if (tools.length > 0) {
    const serverNames = Array.from(new Set(tools.map((tool) => tool.serverName)));
    return {
      state: "connected",
      label: "Connected",
      detail: `${serverNames.join(", ")} · ${tools.length} tool${tools.length === 1 ? "" : "s"} available`,
    };
  }

  const configured = args.servers.filter(isLikelyIncuratorServer);
  if (configured.length > 0) {
    const enabled = configured.filter((server) => server.enabled);
    if (enabled.length > 0) {
      return {
        state: "connecting",
        label: "Waiting",
        detail: `${enabled.map((server) => server.name || server.command).join(", ")} configured, no tools loaded yet`,
      };
    }
    return {
      state: "disabled",
      label: "Server Disabled",
      detail: "An Incurator MCP server is configured but disabled below.",
    };
  }

  return {
    state: "missing",
    label: "Not Configured",
    detail: "Add an Incurator MCP server below, for example command `wiki` with arg `mcp`.",
  };
}

function isIncuratorTool(tool: MCPTool & { serverName: string }): boolean {
  return (
    tool.serverName.toLowerCase().includes("incurator") ||
    tool.name.toLowerCase().includes("incurator") ||
    tool.name.toLowerCase().startsWith("curator_")
  );
}

function isLikelyIncuratorServer(server: MCPServerConfig): boolean {
  const name = server.name.toLowerCase();
  const command = server.command.toLowerCase();
  const args = server.args.join(" ").toLowerCase();
  return (
    name.includes("incurator") ||
    name.includes("curator") ||
    command.endsWith("wiki") ||
    command.includes("incurator") ||
    args.includes("mcp")
  );
}
