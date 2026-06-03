export type IncuratorBackendStatusState =
  | "disabled"
  | "configured";

export interface IncuratorBackendStatus {
  state: IncuratorBackendStatusState;
  label: string;
  detail: string;
}

export function getIncuratorBackendStatus(args: {
  enabled: boolean;
  command?: string;
  commandArgs?: string[];
}): IncuratorBackendStatus {
  if (!args.enabled) {
    return {
      state: "disabled",
      label: "Disabled",
      detail: "Local Incurator backend commands are turned off.",
    };
  }

  const command = args.command?.trim() || "wiki";
  const prefix = args.commandArgs?.length ? ` ${args.commandArgs.join(" ")}` : "";
  return {
    state: "configured",
    label: "Configured",
    detail: `Backend command: ${command}${prefix}`,
  };
}
