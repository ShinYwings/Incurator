import { existsSync, readFileSync } from "fs";
import { homedir, hostname, platform, release, arch } from "os";
import { resolve } from "path";
import type { PluginSettings } from "../types";

export interface SyncthingDevice {
  device_id: string;
  name: string;
  addresses: string[];
}

export interface SyncthingFolder {
  id: string;
  label: string;
  path: string;
  role?: "vault" | "zotero";
  type: string;
  device_ids: string[];
}

export interface SyncthingSnapshot {
  config_path: string | null;
  devices: SyncthingDevice[];
  folders: SyncthingFolder[];
}

export interface DeviceRegistry {
  version: number;
  updated_at: number;
  local_device_id?: string;
  syncthing: SyncthingSnapshot;
  devices: Record<string, Record<string, unknown>>;
}

const REGISTRY_VERSION = 1;

export function defaultSyncthingConfigPaths(home = homedir()): string[] {
  return [
    `${home}/.local/state/syncthing/config.xml`,
    `${home}/.config/syncthing/config.xml`,
    `${home}/Library/Application Support/Syncthing/config.xml`,
  ];
}

function attrs(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  const re = /([A-Za-z0-9_-]+)="([^"]*)"/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text))) out[match[1]] = match[2];
  return out;
}

function tagBlocks(xml: string, tag: string): string[] {
  return Array.from(xml.matchAll(new RegExp(`<${tag}\\b[\\s\\S]*?<\\/${tag}>`, "g"))).map(
    (match) => match[0]
  );
}

function firstOpenTag(block: string): string {
  return block.match(/^<[^>]+>/)?.[0] || "";
}

function tagTexts(block: string, tag: string): string[] {
  return Array.from(block.matchAll(new RegExp(`<${tag}\\b[^>]*>([\\s\\S]*?)<\\/${tag}>`, "g")))
    .map((match) => match[1].trim())
    .filter(Boolean);
}

function expandPath(path: string, home = homedir()): string {
  const expandedHome = path.startsWith("~/") ? `${home}/${path.slice(2)}` : path;
  return expandedHome.replace(/\$HOME/g, home);
}

function samePath(a: string, b: string, home = homedir()): boolean {
  return resolve(expandPath(a, home)) === resolve(expandPath(b, home));
}

export function parseSyncthingConfig(
  xml: string,
  vaultRoot: string,
  home = homedir(),
  zoteroRoots: string[] = []
): SyncthingSnapshot {
  const devicesById = new Map<string, SyncthingDevice>();
  for (const block of tagBlocks(xml, "device")) {
    const a = attrs(firstOpenTag(block));
    if (!a.id) continue;
    devicesById.set(a.id, {
      device_id: a.id,
      name: a.name || a.id.slice(0, 12),
      addresses: tagTexts(block, "address"),
    });
  }

  const folders: SyncthingFolder[] = [];
  for (const block of tagBlocks(xml, "folder")) {
    const a = attrs(firstOpenTag(block));
    if (!a.path) continue;
    const role = samePath(a.path, vaultRoot, home)
      ? "vault"
      : zoteroRoots.some((root) => samePath(a.path, root, home))
        ? "zotero"
        : undefined;
    if (!role) continue;
    folders.push({
      id: a.id || "",
      label: a.label || "",
      path: a.path,
      role,
      type: a.type || "",
      device_ids: Array.from(block.matchAll(/<device\b([^>]*)\/?>/g))
        .map((match) => attrs(match[1]).id)
        .filter(Boolean),
    });
  }

  const folderDeviceIds = new Set(folders.flatMap((folder) => folder.device_ids));
  return {
    config_path: null,
    devices: Array.from(folderDeviceIds)
      .map((id) => devicesById.get(id))
      .filter((device): device is SyncthingDevice => Boolean(device)),
    folders,
  };
}

export function findSyncthingConfigPath(paths = defaultSyncthingConfigPaths()): string | null {
  return paths.find((path) => existsSync(path)) || null;
}

export function readSyncthingSnapshot(vaultRoot: string, zoteroRoots: string[] = []): SyncthingSnapshot {
  const configPath = findSyncthingConfigPath();
  if (!configPath) return { config_path: null, devices: [], folders: [] };
  const snapshot = parseSyncthingConfig(readFileSync(configPath, "utf-8"), vaultRoot, homedir(), zoteroRoots);
  snapshot.config_path = configPath;
  return snapshot;
}

export function inferLocalDeviceId(devices: SyncthingDevice[], host = hostname()): string | undefined {
  const names = new Set([host.toLowerCase(), host.split(".")[0].toLowerCase()]);
  const match = devices.find((device) => names.has(device.name.toLowerCase()));
  return match?.device_id;
}

function inferRegistryLocalDeviceId(
  devices: Record<string, Record<string, unknown>>,
  activeDeviceIds?: Set<string>
): string | undefined {
  const candidates = Object.entries(devices)
    .filter(([id, device]) => (!activeDeviceIds || activeDeviceIds.has(id)) && (device.platform || device.backend))
    .map(([id, device]) => [Number(device.updated_at || 0), id] as const)
    .sort((a, b) => b[0] - a[0]);
  return candidates[0]?.[1];
}

export function mergeDeviceRegistry(
  existing: Partial<DeviceRegistry> | null | undefined,
  snapshot: SyncthingSnapshot,
  settings: Pick<PluginSettings, "incuratorBackendCommand" | "incuratorBackendArgs">,
  now = Math.floor(Date.now() / 1000),
  localDeviceId = inferLocalDeviceId(snapshot.devices)
): DeviceRegistry {
  const activeDeviceIds = new Set(snapshot.devices.map((device) => device.device_id));
  const existingDevices = existing?.devices || {};
  if (!localDeviceId && snapshot.devices.length) {
    localDeviceId = inferRegistryLocalDeviceId(existingDevices, activeDeviceIds);
  }
  if (localDeviceId) activeDeviceIds.add(localDeviceId);
  if (activeDeviceIds.size === 0) activeDeviceIds.add("local");
  localDeviceId = localDeviceId || (snapshot.devices.length ? undefined : "local");

  const devices: Record<string, Record<string, unknown>> = {};
  for (const id of activeDeviceIds) {
    devices[id] = { ...(existingDevices[id] || {}) };
  }

  for (const device of snapshot.devices) {
    devices[device.device_id] = {
      ...(devices[device.device_id] || {}),
      device_id: device.device_id,
      name: device.name,
      syncthing: device,
    };
  }

  if (localDeviceId) {
    const localName =
      snapshot.devices.find((device) => device.device_id === localDeviceId)?.name || hostname();
    devices[localDeviceId] = {
      ...(devices[localDeviceId] || {}),
      device_id: localDeviceId,
      name: localName,
      platform: {
        system: platform(),
        release: release(),
        machine: arch(),
        source: "obsidian-plugin",
      },
      backend: {
        command: settings.incuratorBackendCommand || "wiki",
        args: settings.incuratorBackendArgs?.length ? settings.incuratorBackendArgs : [],
      },
      updated_at: now,
    };
  }

  return {
    version: REGISTRY_VERSION,
    updated_at: now,
    local_device_id: localDeviceId,
    syncthing: snapshot,
    devices,
  };
}

/**
 * Read the cached backend command for the local device from a DeviceRegistry.
 * Returns undefined if not found.
 */
export function getLocalBackendCommand(
  registry: Partial<DeviceRegistry> | null | undefined
): string | undefined {
  if (!registry?.local_device_id || !registry.devices) return undefined;
  const local = registry.devices[registry.local_device_id];
  const backend = local?.backend as { command?: string } | undefined;
  const command = backend?.command;
  
  if (command && command.startsWith("/") && !existsSync(command)) {
    console.warn(`[Incurator] Cached backend command not found: ${command}. Falling back to auto-discovery.`);
    return undefined;
  }
  
  return command || undefined;
}

/**
 * Auto-discover the absolute path to the `wiki` binary.
 *
 * Probe order:
 *   1. `<repoPath>/backend/.venv/bin/wiki`  (venv inside repo)
 *   2. `<repoPath>/.venv/bin/wiki`          (root-level venv)
 *   3. Common global install dirs that Obsidian's minimal PATH might miss
 *
 * Returns the absolute path if found, otherwise undefined.
 */
export function resolveWikiBinary(repoPath: string): string | undefined {
  const candidates: string[] = [];

  if (repoPath) {
    const expanded = expandPath(repoPath);
    candidates.push(
      resolve(expanded, "backend/.venv/bin/wiki"),
      resolve(expanded, ".venv/bin/wiki"),
    );
  }

  // Common global dirs (Apple Silicon homebrew, Intel homebrew, user-local)
  const home = homedir();
  candidates.push(
    `${home}/.local/bin/wiki`,
    "/opt/homebrew/bin/wiki",
    "/usr/local/bin/wiki",
  );

  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }
  return undefined;
}
