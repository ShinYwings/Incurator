import { logger } from "../utils/logger";
import { Notice } from "obsidian";
import { basename } from "path";
import type { ExternalPdfState } from "./externalPdfView";
import { isRetainablePersistedDoc, resolveExternalPdfPath } from "./externalPdfState";

export interface ExternalPdfDoc {
  id: string;
  name: string;
  path?: string;
  file?: File;
  zoteroAttachmentKey?: string;
  externalRef?: string;
}

const STORAGE_KEY = "incurator-obsidian-agent-external-pdfs";

function loadPersistedDocs(): Map<string, ExternalPdfDoc> {
  const map = new Map<string, ExternalPdfDoc>();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    let migrated = false;
    for (const [id, doc] of raw ? JSON.parse(raw) as Array<[string, ExternalPdfDoc]> : []) {
      if (isRetainablePersistedDoc(doc)) {
        map.set(id, {
          id: doc.id,
          name: doc.name,
          // Restore path into the in-memory registry so local PDFs can re-resolve
          // after restart. persistDocs deliberately omits path (cross-device safety).
          path: doc.path,
          zoteroAttachmentKey: doc.zoteroAttachmentKey,
          externalRef: doc.externalRef,
        });
        migrated ||= Boolean(doc.path);
      } else {
        migrated = true;
      }
    }
    if (migrated) {
      persistDocs(map);
    }
  } catch (err) {
    logger.warn("Failed to load persisted PDF docs:", err);
  }
  return map;
}

function persistDocs(map: Map<string, ExternalPdfDoc>): void {
  try {
    const toPersist = Array.from(map.entries()).map(([id, doc]) => [
      id,
      {
        id: doc.id,
        name: doc.name,
        // For local-only PDFs (no portable identity), persist the path so
        // isRetainablePersistedDoc can recognise them on the next startup.
        // For Zotero/externalRef docs, path is omitted (cross-device safety).
        ...(!doc.zoteroAttachmentKey && !doc.externalRef && doc.path
          ? { path: doc.path }
          : {}),
        zoteroAttachmentKey: doc.zoteroAttachmentKey,
        externalRef: doc.externalRef,
      },
    ]);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toPersist));
  } catch (err) {
    logger.warn("Failed to persist PDF docs:", err);
  }
}

const externalPdfDocs = loadPersistedDocs();

function newDocId(): string {
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

export function getExternalPdfDoc(docId: string): ExternalPdfDoc | undefined {
  return externalPdfDocs.get(docId);
}

export function getExternalPdfDocName(docId: string, fallback = "External PDF"): string {
  return externalPdfDocs.get(docId)?.name || fallback;
}

export function getExternalPdfDocPath(docId: string): string | undefined {
  return externalPdfDocs.get(docId)?.path;
}

export function putExternalPdfDoc(doc: ExternalPdfDoc): void {
  externalPdfDocs.set(doc.id, doc);
  persistDocs(externalPdfDocs);
}

export function setExternalPdfRuntimePath(
  docId: string,
  resolvedPath: string | undefined
): ExternalPdfDoc | undefined {
  if (!resolvedPath) return getExternalPdfDoc(docId);
  const current = getExternalPdfDoc(docId);
  if (!current || current.path === resolvedPath) return current;
  const next = { ...current, path: resolvedPath };
  putExternalPdfDoc(next);
  return next;
}

export function registerExternalPdf(
  file: File,
  explicitPath?: string
): ExternalPdfState {
  const id = newDocId();
  const rawPath = explicitPath || (file as unknown as { path?: string }).path;
  const path = typeof rawPath === "string" && rawPath.length > 0 ? rawPath : undefined;
  const doc: ExternalPdfDoc = { id, name: file.name || "External PDF", path, file };
  putExternalPdfDoc(doc);
  new Notice(path
    ? `Registered PDF: ${file.name}\nPath: ${path}`
    : `Registered PDF: ${file.name}\nWarning: No absolute path captured!`);
  return { docId: id, name: doc.name, path };
}

export function registerExternalPdfByPath(filePath: string, attachmentKey?: string): ExternalPdfState {
  const id = newDocId();
  const name = basename(filePath);
  const doc: ExternalPdfDoc = {
    id,
    name,
    path: filePath,
    zoteroAttachmentKey: attachmentKey,
  };
  putExternalPdfDoc(doc);
  return { docId: id, name, zoteroAttachmentKey: attachmentKey };
}

export function resolveCachedExternalPdfPath(
  docId: string,
  docStatePath: string | undefined
): string | undefined {
  return resolveExternalPdfPath(docStatePath, getExternalPdfDocPath(docId));
}
