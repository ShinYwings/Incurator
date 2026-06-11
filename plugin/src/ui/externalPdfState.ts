import type { ExternalPdfState } from "./externalPdfView";

export interface SyncedExternalPdfStateInput {
  docId: string;
  name?: string;
  fallbackName: string;
  path?: string;
  zoom: number;
  darkMode: boolean;
  tocOpen: boolean;
  currentPage: number;
  zoteroAttachmentKey?: string;
  targetAnnotationKey?: string;
}

export function buildSyncedExternalPdfState(
  input: SyncedExternalPdfStateInput
): ExternalPdfState {
  const state: ExternalPdfState = {
    docId: input.docId,
    name: input.name || input.fallbackName,
    path: input.path,
    zoom: input.zoom,
    darkMode: input.darkMode,
    tocOpen: input.tocOpen,
    currentPage: input.currentPage,
  };

  if (input.zoteroAttachmentKey) {
    state.zoteroAttachmentKey = input.zoteroAttachmentKey;
  }
  if (input.targetAnnotationKey) {
    state.targetAnnotationKey = input.targetAnnotationKey;
  }

  return state;
}

/**
 * A persisted external-PDF doc entry is retainable on load iff it carries a
 * non-empty path. `existsSync` is intentionally NOT checked at load time: the
 * cache is built at module-load, which races with Obsidian startup (a path on a
 * not-yet-mounted volume would be wrongly dropped). A genuinely missing file is
 * reported distinctly at resolve time instead — keeping the document identity so
 * "file moved/deleted" stays an actionable state rather than "no path at all".
 */
export function isRetainablePersistedDoc(doc: { path?: string }): boolean {
  return typeof doc.path === "string" && doc.path.length > 0;
}

/**
 * Canonical path resolution for an external-PDF view: prefer the live
 * `docState` path, fall back to the cached doc's path. Empty strings are treated
 * as absent. Returns `undefined` only when neither source knows a path — the one
 * case that justifies the "no path in docState or cache" warning.
 */
export function resolveExternalPdfPath(
  docStatePath: string | undefined,
  cachePath: string | undefined
): string | undefined {
  if (typeof docStatePath === "string" && docStatePath.length > 0) return docStatePath;
  if (typeof cachePath === "string" && cachePath.length > 0) return cachePath;
  return undefined;
}
