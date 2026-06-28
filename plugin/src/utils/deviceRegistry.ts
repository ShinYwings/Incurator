import { logger } from "./logger";
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
  status?: { myID?: string };
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

export function expandPath(path: string, home = homedir()): string {
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

export function parseSyncthingGuiConfig(xml: string): { url: string; apiKey: string } | null {
  const guiBlock = tagBlocks(xml, "gui")[0];
  if (!guiBlock) return null;
  const guiAttrs = attrs(firstOpenTag(guiBlock));
  const address = tagTexts(guiBlock, "address")[0] || "127.0.0.1:8384";
  const apiKey = tagTexts(guiBlock, "apikey")[0] || "";
  if (!apiKey) return null;
  const scheme = guiAttrs.tls === "true" ? "https" : "http";
  const url = address.startsWith("http://") || address.startsWith("https://")
    ? address
    : `${scheme}://${address}`;
  return { url: `${url.replace(/\/$/, "")}/rest/system/status`, apiKey };
}

export async function readSyncthingSnapshotWithStatus(
  vaultRoot: string,
  zoteroRoots: string[] = []
): Promise<SyncthingSnapshot> {
  const configPath = findSyncthingConfigPath();
  if (!configPath) return { config_path: null, devices: [], folders: [] };
  const xml = readFileSync(configPath, "utf-8");
  const snapshot = parseSyncthingConfig(xml, vaultRoot, homedir(), zoteroRoots);
  snapshot.config_path = configPath;
  const gui = parseSyncthingGuiConfig(xml);
  if (!gui) return snapshot;
  try {
    const response = await fetch(gui.url, {
      headers: { "X-API-Key": gui.apiKey },
    });
    if (response.ok) {
      const status = await response.json();
      if (status && typeof status === "object") {
        const myID = (status as Record<string, unknown>).myID;
        if (typeof myID === "string" && myID) snapshot.status = { myID };
      }
    }
  } catch {
    // Syncthing may be stopped or use a self-signed HTTPS GUI. Static config
    // parsing still gives remote devices; current-device marking falls back.
  }
  return snapshot;
}

export function inferLocalDeviceId(
  devices: SyncthingDevice[],
  host = hostname(),
  status?: { myID?: string }
): string | undefined {
  if (status?.myID) return status.myID;
  const names = new Set([host.toLowerCase(), host.split(".")[0].toLowerCase()]);
  const match = devices.find((device) => names.has(device.name.toLowerCase()));
  return match?.device_id;
}

function inferRegistryLocalDeviceId(
  devices: Record<string, Record<string, unknown>>,
  activeDeviceIds?: Set<string>,
  repoPath?: string
): string | undefined {
  if (repoPath) {
    for (const [id, device] of Object.entries(devices)) {
      if (activeDeviceIds && !activeDeviceIds.has(id)) continue;
      const backend = device.backend as Record<string, unknown> | undefined;
      const recorded = typeof backend?.repo_path === "string" ? backend.repo_path : "";
      if (recorded && samePath(recorded, repoPath)) return id;
    }
  }
  const candidates = Object.entries(devices)
    .filter(([id, device]) => (!activeDeviceIds || activeDeviceIds.has(id)) && (device.platform || device.backend))
    .map(([id, device]) => [Number(device.updated_at || 0), id] as const)
    .sort((a, b) => b[0] - a[0]);
  return candidates[0]?.[1];
}

export function mergeDeviceRegistry(
  existing: Partial<DeviceRegistry> | null | undefined,
  snapshot: SyncthingSnapshot,
  settings: Pick<PluginSettings, "incuratorBackendCommand" | "incuratorBackendArgs" | "incuratorRepoPath">,
  now = Math.floor(Date.now() / 1000),
  localDeviceId = inferLocalDeviceId(snapshot.devices, hostname(), snapshot.status)
): DeviceRegistry {
  const activeDeviceIds = new Set(snapshot.devices.map((device) => device.device_id));
  const existingDevices = existing?.devices || {};
  if (!localDeviceId && snapshot.devices.length) {
    localDeviceId = inferRegistryLocalDeviceId(
      existingDevices,
      activeDeviceIds,
      settings.incuratorRepoPath
    );
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
        repo_path: settings.incuratorRepoPath || "",
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
    logger.warn(`Cached backend command not found: ${command}. Falling back to auto-discovery.`);
    return undefined;
  }
  
  return command || undefined;
}

/**
 * Read the local device's repository path from a DeviceRegistry. This lets a
 * synced plugin `data.json` keep a stale absolute path while each machine uses
 * its own `.curator/devices.json` path at runtime.
 */
export function getLocalBackendRepoPath(
  registry: Partial<DeviceRegistry> | null | undefined
): string | undefined {
  if (!registry?.local_device_id || !registry.devices) return undefined;
  const local = registry.devices[registry.local_device_id];
  const backend = local?.backend as { repo_path?: string } | undefined;
  const repoPath = backend?.repo_path;
  return repoPath && repoPath.trim() ? repoPath : undefined;
}

/**
 * Auto-discover the absolute path to the `wiki` binary.
 *
 * Probes ONLY the canonical repo-root venv: `<repoPath>/.venv/bin/wiki`.
 *
 * `setup.sh` sets `VIRTUAL_ENV="$ROOT_DIR/.venv"` and installs the backend there,
 * so the live `wiki` always lands in `<repo>/.venv/bin/wiki`. We deliberately do
 * NOT fall back to `<repoPath>/backend/.venv/bin/wiki`: that path is a leftover
 * from the retired `cd backend` workflow and is frequently STALE, so probing it
 * would silently run an out-of-date backend (wrong version, missing fixes)
 * without the user noticing — the exact failure this avoids. If only a stale
 * `backend/.venv` exists, returning `undefined` (which prompts a proper
 * `./setup.sh`) is safer than running it.
 *
 * Returns the absolute path if found, otherwise undefined.
 */
export function resolveWikiBinary(repoPath: string): string | undefined {
  if (!repoPath) return undefined;
  const candidate = resolve(expandPath(repoPath), ".venv/bin/wiki");
  return existsSync(candidate) ? candidate : undefined;
}

export function getGlobalRegistryDir(repoPath?: string, home = homedir()): string | null {
  if (!repoPath) return null;
  const expandedRepo = expandPath(repoPath, home);
  const constsPath = resolve(expandedRepo, "backend/src/curator/constants.py");
  let cacheDir = ".cache/config";
  
  if (existsSync(constsPath)) {
    const py = readFileSync(constsPath, "utf-8");
    const dirMatch = py.match(/DIR_GLOBAL_CACHE\s*=\s*"([^"]+)"/);
    if (dirMatch) cacheDir = dirMatch[1];
  }
  return resolve(expandedRepo, cacheDir);
}

export function getGlobalRegistryPath(repoPath?: string, home = homedir()): string | null {
  const dir = getGlobalRegistryDir(repoPath, home);
  return dir ? resolve(dir, "devices.json") : null;
}
