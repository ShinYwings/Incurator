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
