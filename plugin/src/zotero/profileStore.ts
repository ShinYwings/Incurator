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
export const RECENT_ITEMS_MAX = 50;

export interface ZoteroProfilesFile {
  profiles: ZoteroImportProfile[];
  recentItems: string[];
  deletedProfiles: Record<string, number>;
}

/** Merge a freshly read synced store with this process's pending edits.
 * Local entries win on a same-name edit; peer-only profiles and recent keys
 * survive an unrelated save from a stale in-memory mirror. */
export function mergeZoteroProfilesFiles(
  disk: unknown,
  local: unknown
): ZoteroProfilesFile {
  const safeDisk = normalizeZoteroProfilesFile(disk);
  const safeLocal = normalizeZoteroProfilesFile(local);
  const profiles = [...safeLocal.profiles];
  const localNames = new Set(safeLocal.profiles.map((profile) => profile.name));
  for (const profile of safeDisk.profiles) {
    if (!localNames.has(profile.name)) profiles.push(profile);
  }
  const recentItems = [
    ...safeLocal.recentItems,
    ...safeDisk.recentItems.filter((key) => !safeLocal.recentItems.includes(key)),
  ].slice(0, RECENT_ITEMS_MAX);
  const deletedProfiles = { ...safeDisk.deletedProfiles };
  for (const [name, deletedAt] of Object.entries(safeLocal.deletedProfiles)) {
    deletedProfiles[name] = Math.max(deletedProfiles[name] || 0, deletedAt);
  }
  const liveProfiles = profiles.filter((profile) => {
    const deletedAt = deletedProfiles[profile.name] || 0;
    const profileAt = profile.lastUsedAt || 0;
    if (profileAt > deletedAt) {
      delete deletedProfiles[profile.name];
      return true;
    }
    return deletedAt === 0;
  });
  return normalizeZoteroProfilesFile({
    profiles: liveProfiles,
    recentItems,
    deletedProfiles,
  });
}

/** Required string fields of ZoteroImportProfile. Damaged or pre-migration
 *  entries get these coerced to "" so UI/runtime code always sees usable
 *  strings — dropping the whole profile would turn field-level damage into
 *  silent data loss on the next save (PR #78 second review). */
const PROFILE_STRING_FIELDS = [
  "templatePath",
  "outputFolder",
  "outputSubfolder",
  "outputFilename",
  "assetFolder",
  "assetSubfolder",
  "bibliographyStyle",
] as const;

function sanitizeProfile(p: Record<string, unknown>): ZoteroImportProfile {
  // Spread first: deprecated/extra keys (e.g. imageFolder) must survive — the
  // asset-folder migration still reads them.
  const out: Record<string, unknown> = { ...p };
  for (const field of PROFILE_STRING_FIELDS) {
    if (typeof out[field] !== "string") out[field] = "";
  }
  if (typeof out.lastUsedAt !== "number") delete out.lastUsedAt;
  return out as unknown as ZoteroImportProfile;
}

/** Defensively normalize a decoded `.curator/zotero_profiles.json` payload.
 *  Malformed pieces degrade instead of throwing — a hand-edited file must
 *  never break plugin load. (Corrupted JSON / unrecognizable structure is a
 *  different case — see parseZoteroProfilesFile.) */
export function normalizeZoteroProfilesFile(raw: unknown): ZoteroProfilesFile {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    return { profiles: [], recentItems: [], deletedProfiles: {} };
  }
  const obj = raw as Partial<Record<keyof ZoteroProfilesFile, unknown>>;
  const profiles = (Array.isArray(obj.profiles) ? obj.profiles : [])
    .filter(
      (p): p is Record<string, unknown> =>
        typeof p === "object" &&
        p !== null &&
        !Array.isArray(p) &&
        // A profile without a string `name` ({} or junk) is not a real
        // ZoteroImportProfile — it renders as an empty dropdown entry and
        // breaks name-dependent code (PR #78 review). An empty-string name
        // stays valid: the settings UI allows blanking a name and renders a
        // "Profile N" fallback, so dropping it would destroy a real profile.
        typeof (p as { name?: unknown }).name === "string"
    )
    .map(sanitizeProfile);
  const recentItems = (Array.isArray(obj.recentItems) ? obj.recentItems : [])
    .filter((k): k is string => typeof k === "string")
    .slice(0, RECENT_ITEMS_MAX);
  const deletedProfiles =
    typeof obj.deletedProfiles === "object" &&
    obj.deletedProfiles !== null &&
    !Array.isArray(obj.deletedProfiles)
      ? Object.fromEntries(
          Object.entries(obj.deletedProfiles).filter(
            ([name, deletedAt]) =>
              name.length > 0 &&
              typeof deletedAt === "number" &&
              Number.isFinite(deletedAt)
          )
        )
      : {};
  return { profiles, recentItems, deletedProfiles };
}

/** Parse raw file content, distinguishing corruption from entry-level damage.
 *
 *  Returns null when the content is not valid JSON OR is not structurally a
 *  ZoteroProfilesFile (an object with `profiles` and `recentItems` arrays —
 *  the exact shape the plugin writes). In both cases the caller must treat the
 *  store as UNLOADED (leave the on-disk file untouched for recovery) rather
 *  than fall through to legacy migration: after the one-time migration the
 *  legacy fields are blank, so the fallback would load an empty list and the
 *  next save would silently overwrite the recoverable file (PR #78 reviews).
 *  Entry-level damage inside the arrays still normalizes. */
export function parseZoteroProfilesFile(raw: string): ZoteroProfilesFile | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (
    typeof parsed !== "object" ||
    parsed === null ||
    Array.isArray(parsed) ||
    !Array.isArray((parsed as { profiles?: unknown }).profiles) ||
    !Array.isArray((parsed as { recentItems?: unknown }).recentItems)
  ) {
    return null;
  }
  return normalizeZoteroProfilesFile(parsed);
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
