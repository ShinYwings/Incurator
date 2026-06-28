import { logger } from "../utils/logger";
import type { App, TFile } from "obsidian";
import { promises as fs } from "fs";
import type { ZoteroImportProfile } from "../types";
import { sanitizePathSegment, TemplateRenderer } from "./templateRenderer";

/**
 * Shared Zotero asset-localization, used by BOTH the import wizard and the
 * "Refresh Zotero Item" reload command so they can never diverge. The reload
 * command previously read the deprecated `imageFolder` field (empty after the
 * wizard migrated to `assetFolder`/`assetSubfolder`), which made it skip
 * localization and emit absolute Zotero cache paths like
 * `![[/Users/you/Zotero/cache/library/KEY.png]]` instead of vault-relative
 * `![[05_Assets/.../KEY.png]]`.
 */

export interface ResolvedAssetSpec {
  /** Asset root folder (Nunjucks-free), e.g. `05_Assets/Zotero Assets`. */
  assetFolder: string;
  /** Per-item subfolder template, e.g. `{{citekey}}` (still unresolved). */
  assetSubfolder: string;
}

const DEFAULT_ASSET_FOLDER = "05_Assets";
const DEFAULT_ASSET_SUBFOLDER = "{{citekey}}";

/**
 * Resolve a profile's asset spec, applying the legacy `imageFolder` →
 * `assetFolder`/`assetSubfolder` migration. Mirrors the wizard's `loadProfile`
 * so a single source of truth governs where assets land.
 */
export function resolveProfileAssetSpec(profile: ZoteroImportProfile): ResolvedAssetSpec {
  if (profile.assetFolder !== undefined && profile.assetFolder !== null) {
    return {
      assetFolder: profile.assetFolder,
      assetSubfolder: profile.assetSubfolder || DEFAULT_ASSET_SUBFOLDER,
    };
  }
  const legacy = profile.imageFolder;
  if (legacy) {
    const lastSlash = legacy.lastIndexOf("/");
    return {
      assetFolder: lastSlash >= 0 ? legacy.substring(0, lastSlash) : legacy,
      assetSubfolder: lastSlash >= 0 ? legacy.substring(lastSlash + 1) : DEFAULT_ASSET_SUBFOLDER,
    };
  }
  return { assetFolder: DEFAULT_ASSET_FOLDER, assetSubfolder: DEFAULT_ASSET_SUBFOLDER };
}

/**
 * One-time retirement of the deprecated `imageFolder` profile field: normalize
 * any profile still carrying `imageFolder` to `assetFolder`/`assetSubfolder`
 * (same mapping as `resolveProfileAssetSpec`) and delete `imageFolder`. Returns
 * true when any profile changed so the caller can persist settings.
 */
export function migrateZoteroProfileAssetFolders(
  profiles: ZoteroImportProfile[] | undefined
): boolean {
  let changed = false;
  for (const profile of profiles || []) {
    const legacy = profile as { imageFolder?: string };
    if (legacy.imageFolder === undefined) continue;
    const spec = resolveProfileAssetSpec(profile);
    profile.assetFolder = spec.assetFolder;
    profile.assetSubfolder = spec.assetSubfolder;
    delete legacy.imageFolder;
    changed = true;
  }
  return changed;
}

/** Join vault path parts, dropping empties and collapsing duplicate slashes. */
export function joinVaultPath(...parts: string[]): string {
  return parts.filter(Boolean).join("/").replace(/\/+/g, "/");
}

function buffersEqual(a: ArrayBuffer, b: ArrayBuffer): boolean {
  if (a.byteLength !== b.byteLength) return false;
  const ua = new Uint8Array(a);
  const ub = new Uint8Array(b);
  for (let i = 0; i < ua.length; i++) if (ua[i] !== ub[i]) return false;
  return true;
}

function toArrayBuffer(buf: Buffer): ArrayBuffer {
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer;
}

/**
 * Resolve the per-item asset folder (asset root + rendered+sanitized subfolder).
 * Returns "" when neither a folder nor a subfolder resolves (caller then clears
 * `imageRelativePath` rather than leaking an absolute path).
 */
export async function resolveAssetFolder(
  renderer: TemplateRenderer,
  spec: ResolvedAssetSpec,
  metadata: unknown
): Promise<string> {
  const renderedSub = await renderer.renderString(spec.assetSubfolder || "", metadata);
  const sub = renderedSub.split("/").map((p) => sanitizePathSegment(p)).filter(Boolean).join("/");
  return joinVaultPath(spec.assetFolder, sub);
}

interface AnnotationLike {
  key?: string;
  id?: string;
  imageRelativePath?: string;
}

/**
 * Copy each annotation's region image into the vault asset folder and rewrite
 * `imageRelativePath` to the VAULT-RELATIVE destination. Behavior:
 *  - no resolvable asset folder → clear `imageRelativePath` (never emit absolute);
 *  - destination absent → create it;
 *  - destination present but source bytes changed → OVERWRITE it, so an edited
 *    annotation region refreshes its asset (avoids sync churn when unchanged).
 */
export async function localizeAnnotationImages(
  app: App,
  renderer: TemplateRenderer,
  profile: ZoteroImportProfile,
  metadata: { annotations?: AnnotationLike[] }
): Promise<void> {
  const spec = resolveProfileAssetSpec(profile);
  const assetFolder = await resolveAssetFolder(renderer, spec, metadata);

  for (const ann of metadata.annotations || []) {
    if (!ann.imageRelativePath) continue;
    if (!assetFolder) {
      ann.imageRelativePath = "";
      continue;
    }
    try {
      if (!app.vault.getAbstractFileByPath(assetFolder)) {
        await app.vault.createFolder(assetFolder).catch(() => {});
      }
      const srcArr = toArrayBuffer(await fs.readFile(ann.imageRelativePath));
      const destPath = joinVaultPath(assetFolder, `${ann.key || ann.id}.png`);
      const existing = app.vault.getAbstractFileByPath(destPath) as TFile | null;
      if (!existing) {
        await app.vault.createBinary(destPath, srcArr);
      } else {
        const current = await app.vault.readBinary(existing).catch(() => null);
        if (!current || !buffersEqual(current, srcArr)) {
          await app.vault.modifyBinary(existing, srcArr);
        }
      }
      ann.imageRelativePath = destPath;
    } catch (e) {
      logger.error("Failed to localize annotation image", ann.key, e);
    }
  }
}
