/**
 * Plan G — single plugin-side source/asset identity model.
 *
 * Replaces ad-hoc path/identity resolution scattered across the popover, badge,
 * and external-PDF code (`getPdfRefSourcePath`, `resolveExternalPdfPath`,
 * `resolveZoteroAttachmentPath`, `toAbsolutePath`, …). Covers PDFs, markdown
 * notes, and external image attachments — hence `AssetSource`, not `PdfSource`.
 *
 * See PLUGIN_SCHEMA §1.2 and SYSTEM_BEHAVIOR §29.6 for the contract.
 */

export interface AssetSource {
  absPath?: string; // resolved real file on disk
  relpath?: string; // in-vault path / Reference Mode stub
  zoteroKey?: string;
  fileHash?: string;
  displayName: string;
  resolutionStatus: "resolved" | "path_unresolved" | "untracked";
}

/**
 * Single canonical key for the backend source-status map. Identity-first
 * (Zotero key before any resolved path) so a Zotero source keeps a STABLE key
 * across its lifecycle — the writer (post-ingest) and the badge reader always
 * agree, fixing the badge desync (audit item 3).
 */
export function assetStatusKey(s: AssetSource): string {
  if (s.zoteroKey) return `zotero:${s.zoteroKey}`;
  if (s.absPath) return s.absPath;
  if (s.relpath) return s.relpath;
  if (s.fileHash) return `hash:${s.fileHash}`;
  return `name:${s.displayName}`;
}

/**
 * Configuration epoch for the Zotero path cache. Any change to the inputs that
 * affect Zotero path resolution (data directory, active workspace, linked
 * attachment roots) yields a new epoch, which invalidates cached paths.
 */
export function zoteroConfigEpoch(input: {
  zoteroBasePath: string;
  workspaceId?: string;
  profileRoots?: string[];
}): string {
  return JSON.stringify([
    input.zoteroBasePath ?? "",
    input.workspaceId ?? "",
    ...(input.profileRoots ?? []),
  ]);
}

export interface ZoteroPathCacheDeps {
  /** Existence probe (injected for testability). */
  fileExists: (path: string) => boolean;
}

/**
 * In-memory only Zotero `attachment_key -> absPath` cache for the offline/local
 * resolution hot path. Mandatory invalidation (PLUGIN_SCHEMA §1.2):
 * - tied to the config epoch: a different epoch clears the whole cache;
 * - a cached path whose file no longer exists is treated as a miss;
 * - `clear()` is called on plugin reload (never persisted to disk).
 */
export class ZoteroPathCache {
  private epoch = "";
  private readonly map = new Map<string, string>();

  constructor(private readonly deps: ZoteroPathCacheDeps) {}

  get(key: string, epoch: string): string | undefined {
    if (epoch !== this.epoch) {
      this.clear();
      this.epoch = epoch;
      return undefined;
    }
    const path = this.map.get(key);
    if (path === undefined) return undefined;
    if (!this.deps.fileExists(path)) {
      this.map.delete(key);
      return undefined;
    }
    return path;
  }

  set(key: string, epoch: string, path: string): void {
    if (epoch !== this.epoch) {
      this.clear();
      this.epoch = epoch;
    }
    this.map.set(key, path);
  }

  clear(): void {
    this.map.clear();
  }
}

export interface ResolveAssetSourceInput {
  absPath?: string;
  relpath?: string;
  zoteroKey?: string;
  fileHash?: string;
  displayName: string;
}

export interface ResolveAssetSourceDeps {
  backendAvailable: boolean;
  resolveZoteroViaBackend: (key: string) => Promise<string | undefined>;
  resolveZoteroLocally: (key: string) => string | undefined;
  cache: ZoteroPathCache;
  epoch: string;
  fileExists: (path: string) => boolean;
}

/**
 * Resolve whatever identifiers are known into an {@link AssetSource}. Zotero
 * paths prefer the backend resolver ("single entry point"); the local resolver
 * is used ONLY when the backend command is offline (C2). Resolved Zotero paths
 * are cached with epoch + missing-file invalidation.
 */
export async function resolveAssetSource(
  input: ResolveAssetSourceInput,
  deps: ResolveAssetSourceDeps
): Promise<AssetSource> {
  let resolvedAbs: string | undefined;
  if (input.zoteroKey && !input.absPath) {
    resolvedAbs = deps.cache.get(input.zoteroKey, deps.epoch);
    if (!resolvedAbs) {
      resolvedAbs = deps.backendAvailable
        ? await deps.resolveZoteroViaBackend(input.zoteroKey)
        : deps.resolveZoteroLocally(input.zoteroKey);
      if (resolvedAbs) deps.cache.set(input.zoteroKey, deps.epoch, resolvedAbs);
    }
  }

  const finalAbs = input.absPath ?? resolvedAbs;
  let resolutionStatus: AssetSource["resolutionStatus"];
  if (finalAbs && deps.fileExists(finalAbs)) {
    resolutionStatus = "resolved";
  } else if (input.relpath) {
    resolutionStatus = "resolved";
  } else if (input.zoteroKey || input.fileHash || finalAbs) {
    resolutionStatus = "path_unresolved";
  } else {
    resolutionStatus = "untracked";
  }

  return {
    absPath: finalAbs,
    relpath: input.relpath,
    zoteroKey: input.zoteroKey,
    fileHash: input.fileHash,
    displayName: input.displayName,
    resolutionStatus,
  };
}
