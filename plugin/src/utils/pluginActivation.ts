export interface PluginActivationState {
  runtimeVersion: string;
  installedVersion: string;
  runtimeBundleHash?: string;
  installedBundleHash?: string;
  reloadRequired: boolean;
}

export function assessPluginActivation(
  runtimeVersion: string,
  installedManifestText: string,
  runtimeBundleHash?: string,
  installedBundleHash?: string
): PluginActivationState {
  let parsed: unknown;
  try {
    parsed = JSON.parse(installedManifestText);
  } catch (error) {
    throw new Error(
      `Installed plugin manifest is malformed: ${error instanceof Error ? error.message : String(error)}`
    );
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Installed plugin manifest must be a JSON object.");
  }
  const installedVersion = (parsed as Record<string, unknown>).version;
  if (typeof installedVersion !== "string" || !installedVersion.trim()) {
    throw new Error("Installed plugin version is missing.");
  }
  return {
    runtimeVersion,
    installedVersion,
    ...(runtimeBundleHash ? { runtimeBundleHash } : {}),
    ...(installedBundleHash ? { installedBundleHash } : {}),
    reloadRequired:
      runtimeBundleHash && installedBundleHash
        ? runtimeBundleHash !== installedBundleHash
        : runtimeVersion !== installedVersion,
  };
}
