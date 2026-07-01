import type { ExternalPdfState } from "./externalPdfView";

export interface SyncedExternalPdfStateInput {
  docId: string;
  name?: string;
  fallbackName: string;
  /** Legacy/runtime input only; deliberately omitted from persisted output. */
  path?: string;
  externalRef?: string;
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
    zoom: input.zoom,
    darkMode: input.darkMode,
    tocOpen: input.tocOpen,
    currentPage: input.currentPage,
  };

  if (input.path) {
    state.path = input.path;
  }
  if (input.zoteroAttachmentKey) {
    state.zoteroAttachmentKey = input.zoteroAttachmentKey;
  }
  if (input.externalRef) {
    state.externalRef = input.externalRef;
  }
  if (input.targetAnnotationKey) {
    state.targetAnnotationKey = input.targetAnnotationKey;
  }

  return state;
}

/**
 * Persisted external-PDF entries require portable identity. Legacy path-only
 * records are dropped instead of being trusted on another device.
 */
export function isRetainablePersistedDoc(doc: {
  zoteroAttachmentKey?: string;
  externalRef?: string;
  path?: string;
}): boolean {
  return Boolean(doc.zoteroAttachmentKey || doc.externalRef || doc.path);
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
