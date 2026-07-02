import type { ZoteroImportProfile } from "../types";

/** Durable store for Zotero import profiles + recent-item LRU (v0.30.0).
 *
 * Lives in `.curator/` so Syncthing carries it across devices — the same
 * pattern as `sessions.json`. Before v0.30.0 both fields lived in the plugin's
 * `data.json`, which is typically excluded from sync, so every device saw a
 * different profile list (PLUGIN_SCHEMA "Zotero profile storage").
 */
export const ZOTERO_PROFILES_PATH = ".curator/zotero_profiles.json";

/** PLUGIN_SCHEMA: recentItems is an LRU of Zotero item keys, newest first. */
const RECENT_ITEMS_MAX = 50;

export interface ZoteroProfilesFile {
  profiles: ZoteroImportProfile[];
  recentItems: string[];
}

/** Defensively parse a raw `.curator/zotero_profiles.json` payload.
 *  Any malformed shape degrades to an empty store instead of throwing —
 *  a Syncthing-truncated or hand-edited file must never break plugin load. */
export function normalizeZoteroProfilesFile(raw: unknown): ZoteroProfilesFile {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    return { profiles: [], recentItems: [] };
  }
  const obj = raw as Partial<Record<keyof ZoteroProfilesFile, unknown>>;
  const profiles = (Array.isArray(obj.profiles) ? obj.profiles : []).filter(
    (p): p is ZoteroImportProfile =>
      typeof p === "object" && p !== null && !Array.isArray(p)
  );
  const recentItems = (Array.isArray(obj.recentItems) ? obj.recentItems : [])
    .filter((k): k is string => typeof k === "string")
    .slice(0, RECENT_ITEMS_MAX);
  return { profiles, recentItems };
}

/** Extract the legacy `data.json` fields for one-time migration.
 *  Returns null when there is nothing to migrate (fresh install, or the
 *  fields were already stripped by a previous migration). */
export function extractLegacyZoteroProfiles(raw: {
  zoteroProfiles?: unknown;
  recentZoteroItems?: unknown;
}): ZoteroProfilesFile | null {
  const legacy = normalizeZoteroProfilesFile({
    profiles: raw.zoteroProfiles,
    recentItems: raw.recentZoteroItems,
  });
  if (legacy.profiles.length === 0 && legacy.recentItems.length === 0) {
    return null;
  }
  return legacy;
}
